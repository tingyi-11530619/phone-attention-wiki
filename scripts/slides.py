"""topic-slides 各關卡的檢查和渲染腳本（見 .claude/skills/topic-slides/SKILL.md）。

用法：
    python scripts/slides.py g1 outputs/slides-intro      # sources.md 只列 wiki 頁面
    python scripts/slides.py g2 outputs/slides-intro      # 覆蓋率關卡
    python scripts/slides.py g3 outputs/slides-intro      # 證據卡
    python scripts/slides.py g4 outputs/slides-intro      # 大綱
    python scripts/slides.py g6 outputs/slides-intro      # 逐頁稿的忠實度（腳本部分）
    python scripts/slides.py render outputs/slides-intro  # G7 渲染 deck.html
    python scripts/slides.py g7 outputs/slides-intro      # deck.html 和 drafts 文字完全一致
    python scripts/slides.py g8 outputs/slides-intro      # 溢出檢查和截圖（需要 Edge 或 Chrome）

結束代碼：有錯誤是 1，沒有錯誤是 0（只有警告也是 0）。
重用 lint.py 的正規化、引文格式和數字比對；只用標準函式庫。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import lint

ROOT = lint.ROOT
CARD_ID_RE = re.compile(r"^c\d{2,3}$")
REF_RE = re.compile(r"\[(c\d{2,3})\]")
DESIGN_RE = re.compile(r"^【([^｜】]+)(?:｜([^】]*))?】$")
SECTION_RE = re.compile(r"^## 段落 (S\d+)｜(.+?)\s*$")
SLIDE_HEAD_RE = re.compile(r"^## (slide-\d{2})｜(.+?)\s*$")
EXCLUDED_SECTIONS = ("目前怎麼看", "相關但沒有直接測試的研究", "專家意見")
NEGATIONS = ("不是", "不能", "沒有", "沒證據", "不等於", "不代表", "無法", "並非", "不一定")
TITLE_MAX = 20
BODY_MAX = 80
SLIDES_MIN, SLIDES_MAX = 10, 15


# ---------------------------------------------------------------- 共用
class Result:
    def __init__(self, gate: str):
        self.gate, self.errors, self.warns, self.notes = gate, [], [], []

    def err(self, msg): self.errors.append(msg)
    def warn(self, msg): self.warns.append(msg)
    def note(self, msg): self.notes.append(msg)

    def finish(self) -> int:
        print(f"## {self.gate}")
        for n in self.notes:
            print(f"- {n}")
        for w in self.warns:
            print(f"- **警告**：{w}")
        for e in self.errors:
            print(f"- **錯誤**：{e}")
        status = "不通過" if self.errors else "通過"
        print(f"\n結果：{status}（錯誤 {len(self.errors)} 個，警告 {len(self.warns)} 個）")
        return 1 if self.errors else 0


def wiki_index():
    pages = lint.load_pages()
    by_slug = {}
    for p in pages:
        by_slug.setdefault(p.slug, p)
    return pages, by_slug


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def numbers_in(text: str) -> list[str]:
    """和 lint.py 第 11 項相同的規則：去掉引文、連結、日期、頁碼後取數字，跳過 0–9 的單獨整數。"""
    nums = [lint.norm_num(m.group(0)) for m in lint.NUM_RE.finditer(lint.strip_for_numbers(text))]
    return [n for n in nums if "." in n or len(n) > 1]


def parse_sources(d: Path):
    """回傳 {段落 id: {"title":…, "claims":[slug], "others":[slug]}} 和所有列出的 slug。"""
    sections, listed, cur = {}, set(), None
    for ln in read(d / "sources.md").splitlines():
        m = SECTION_RE.match(ln)
        if m:
            cur = m.group(1)
            sections[cur] = {"title": m.group(2), "claims": [], "others": []}
            continue
        links = [x.group(1).strip() for x in lint.LINK_RE.finditer(ln)]
        listed.update(links)
        if cur and ln.lstrip().startswith("- 主張頁"):
            sections[cur]["claims"] += links
        elif cur and ln.lstrip().startswith("- 其他頁"):
            sections[cur]["others"] += links
    return sections, listed


def load_cards(d: Path):
    cards = {}
    for p in sorted((d / "cards").glob("*.md")):
        meta, body, _ = lint.parse_frontmatter(read(p))
        parts = re.split(r"(?m)^## ", body)
        sec = {}
        for part in parts[1:]:
            head, _, rest = part.partition("\n")
            sec[head.strip()] = rest.strip()
        finding = sec.get("發現", "")
        cite_block = next((v for k, v in sec.items() if k.startswith("出處")), "")
        cards[p.stem] = {"path": p, "meta": meta, "finding": finding, "cites": cite_block}
    return cards


def parse_outline(d: Path):
    slides, cur = {}, None
    for ln in read(d / "outline.md").splitlines():
        m = SLIDE_HEAD_RE.match(ln)
        if m:
            cur = m.group(1)
            slides[cur] = {"title": m.group(2), "section": "", "cards": [], "point": ""}
            continue
        if not cur:
            continue
        s = ln.strip()
        if s.startswith("- 段落："):
            slides[cur]["section"] = s.split("：", 1)[1].split("（")[0].strip()
        elif s.startswith("- 重點："):
            slides[cur]["point"] = s.split("：", 1)[1].strip()
        elif s.startswith("- 卡片："):
            v = s.split("：", 1)[1].split("（")[0]
            slides[cur]["cards"] = [] if v.strip() in ("無", "") else [x.strip() for x in re.split(r"[,、，]", v) if x.strip()]
    return slides


def parse_draft(path: Path):
    """回傳 (title, lines)；lines 是 [(kind, text)]，kind 是 fact 或 lead。"""
    title, lines = "", []
    for ln in read(path).splitlines():
        s = ln.rstrip()
        if s.startswith("# ") and not title:
            title = s[2:].strip()
        elif s.startswith("- "):
            lines.append(("fact", s[2:].strip()))
        elif s.startswith("> "):
            lines.append(("lead", s[2:].strip()))
        elif s.strip():
            lines.append(("other", s.strip()))
    return title, lines


def plain(text: str) -> str:
    """畫面上看得到的文字：去掉 ** 粗體標記，合併空白。"""
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


WLINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")


def char_count(text: str) -> int:
    """正文字數：不含 [card-id]、[[wiki 連結]]、** 和空白。"""
    t = WLINK_RE.sub("", REF_RE.sub("", text)).replace("**", "")
    return len(re.sub(r"\s+", "", t))


def load_banned(d: Path):
    """讀 glossary.md「## 禁用詞」：回傳 [(詞, 否定句是否例外)]；沒有用詞表時回傳 None。"""
    path = d / "glossary.md"
    if not path.is_file():
        return None
    out, on = [], False
    for ln in read(path).splitlines():
        if ln.startswith("## "):
            on = ln.strip() == "## 禁用詞"
            continue
        m = re.match(r"^- `([^`]+)`(.*)$", ln.strip()) if on else None
        if m:
            out.append((m.group(1), "否定句" in m.group(2)))
    return out


# ---------------------------------------------------------------- G1
def g1(d: Path) -> int:
    r = Result("G1 sources.md")
    _, by_slug = wiki_index()
    text = read(d / "sources.md")
    sections, listed = parse_sources(d)
    if not sections:
        r.err("sources.md 沒有任何「## 段落 Sx｜…」")
    for slug in sorted(listed):
        if slug not in by_slug:
            r.err(f"`[[{slug}]]` 不是 wiki 中存在的頁面")
    if re.search(r"outputs[/\\]|raw[/\\]|raw-text[/\\]|https?://", text):
        r.err("sources.md 只能列 wiki 頁面，不可以有 outputs/、raw/、raw-text/ 或外部連結")
    r.note(f"段落 {len(sections)} 個，列出 wiki 頁面 {len(listed)} 個")
    return r.finish()


# ---------------------------------------------------------------- G2
def evidence_lines(page) -> list[str]:
    out, heading = [], ""
    for ln in page.body.splitlines():
        if ln.startswith("## "):
            heading = ln[3:]
            continue
        if any(x in heading for x in EXCLUDED_SECTIONS):
            continue
        if ln.lstrip().startswith("- 【") and lint.CITE_RE.search(ln):
            out.append(ln)
    return out


def g2(d: Path) -> int:
    r = Result("G2 覆蓋率關卡")
    _, by_slug = wiki_index()
    sections, _ = parse_sources(d)
    print("| 段落 | 問題 | 主張頁 | 有出處的證據 |\n|---|---|---|---|")
    for sid, s in sections.items():
        claims = [c for c in s["claims"] if c in by_slug and by_slug[c].folder == "claims"]
        bad = [c for c in s["claims"] if c not in claims]
        for c in bad:
            r.err(f"{sid}：`[[{c}]]` 不是主張頁（wiki/claims/）")
        n_ev = sum(len(evidence_lines(by_slug[c])) for c in claims)
        print(f"| {sid} | {s['title']} | {len(claims)} | {n_ev} |")
        if len(claims) < 1:
            r.err(f"{sid}「{s['title']}」沒有主張頁")
        if n_ev < 2:
            r.err(f"{sid}「{s['title']}」有出處的證據只有 {n_ev} 條（至少要 2 條）")
    print()
    return r.finish()


# ---------------------------------------------------------------- G3
def g3(d: Path) -> int:
    r = Result("G3 證據卡")
    _, by_slug = wiki_index()
    sections, listed = parse_sources(d)
    cards = load_cards(d)
    if not cards:
        r.err("cards/ 裡沒有任何卡片")
    for cid, c in cards.items():
        m, where = c["meta"], f"`cards/{cid}.md`"
        if not CARD_ID_RE.match(cid) or m.get("id") != cid:
            r.err(f"{where}：檔名和 id 不一致，或 id 格式不是 c01 這種形式")
        for k in ("id", "section", "wiki_page", "design", "abstract_only"):
            if k not in m:
                r.err(f"{where}：缺少 `{k}`")
        if m.get("section") not in sections:
            r.err(f"{where}：section `{m.get('section')}` 不在 sources.md")
        wp = ROOT / str(m.get("wiki_page", ""))
        if not wp.is_file():
            r.err(f"{where}：wiki_page `{m.get('wiki_page')}` 不存在")
            continue
        if wp.stem not in listed:
            r.err(f"{where}：wiki_page `{wp.stem}` 沒有列在 sources.md")
        wtext = read(wp)
        cites = list(lint.CITE_RE.finditer(c["cites"]))
        if not cites:
            r.err(f"{where}：「出處」沒有任何符合格式的引文")
        if not c["finding"]:
            r.err(f"{where}：「發現」是空的")
        pools, srcs = [], []
        for x in cites:
            if x.group(0) not in wtext:
                r.err(f"{where}：出處不是從 `{m.get('wiki_page')}` 逐字照抄的：{x.group(0)[:60]}…")
            slug = x.group(1)
            sp = by_slug.get(slug)
            if not sp or sp.folder != "sources":
                r.err(f"{where}：`{slug}` 不是來源頁")
                continue
            srcs.append(sp)
            st = lint.source_text(slug, by_slug)
            if st is None:
                r.err(f"{where}：找不到 `{slug}` 的 raw-text")
                continue
            pools.append(st[2])
            res = lint.quote_found(x.group(3), st[0], st[1])
            if not res:
                r.err(f"{where}：短引在 `{slug}` 原文中找不到：\"{x.group(3)[:50]}\"")
            elif res == "loose":
                r.warn(f"{where}：短引只在寬鬆比對下符合：\"{x.group(3)[:50]}\"")
        # 數字
        for n in numbers_in(c["finding"] + " " + str(m.get("design", ""))):
            if pools and not any(n in p for p in pools):
                r.err(f"{where}：數字 `{n}` 在引用來源的原文中找不到")
        # 研究設計
        dm = DESIGN_RE.match(str(m.get("design", "")))
        if not dm:
            r.err(f"{where}：design 格式不是【設計｜對象 N=…】")
        elif srcs and dm.group(1) not in {s.meta.get("design") for s in srcs}:
            r.err(f"{where}：design「{dm.group(1)}」和來源頁的 design 不一致（{', '.join(s.meta.get('design', '?') for s in srcs)}）")
        # 僅摘要
        expect = any(s.meta.get("coverage") == "僅摘要" for s in srcs)
        got = str(m.get("abstract_only", "")).lower() == "true"
        if srcs and expect != got:
            r.err(f"{where}：abstract_only 應該是 {str(expect).lower()}")
        if got and lint.ABSTRACT_MARK not in c["finding"]:
            r.err(f"{where}：僅摘要的卡片，「發現」要加「{lint.ABSTRACT_MARK}」")
    r.note(f"卡片 {len(cards)} 張")
    return r.finish()


# ---------------------------------------------------------------- G4
def g4(d: Path) -> int:
    r = Result("G4 大綱")
    sections, _ = parse_sources(d)
    cards = load_cards(d)
    slides = parse_outline(d)
    if not (SLIDES_MIN <= len(slides) <= SLIDES_MAX):
        r.err(f"頁數 {len(slides)} 不在 {SLIDES_MIN}–{SLIDES_MAX} 之間")
    used = set()
    for sid, s in slides.items():
        if len(s["title"]) > TITLE_MAX:
            r.err(f"{sid}：標題超過 {TITLE_MAX} 字（{len(s['title'])} 字）")
        if s["section"] not in ("無", "") and s["section"] not in sections:
            r.err(f"{sid}：段落 `{s['section']}` 不在 sources.md")
        if not s["point"]:
            r.err(f"{sid}：沒有寫「重點」")
        for cid in s["cards"]:
            if cid not in cards:
                r.err(f"{sid}：卡片 `{cid}` 不存在")
            used.add(cid)
    for cid in cards:
        if cid not in used:
            r.warn(f"卡片 `{cid}` 沒有被大綱用到")
    banned = load_banned(d)
    if banned is None:
        r.err("沒有 glossary.md（用詞表）；G4 要同時產出用詞表")
    elif not banned:
        r.err("glossary.md 沒有「## 禁用詞」清單")
    r.note(f"頁數 {len(slides)}，使用卡片 {len(used)}/{len(cards)} 張，禁用詞 {len(banned or [])} 個")
    return r.finish()


# ---------------------------------------------------------------- G6 (a)
def g6(d: Path) -> int:
    r = Result("G6 (a) 忠實度檢查（腳本）")
    cards = load_cards(d)
    slides = parse_outline(d)
    _, listed = parse_sources(d)
    banned = load_banned(d)
    if banned is None:
        r.err("沒有 glossary.md，無法檢查禁用詞")
        banned = []
    drafts = {p.stem: p for p in sorted((d / "drafts").glob("slide-*.md"))}
    for sid, path in drafts.items():
        title, lines = parse_draft(path)
        for text in [title] + [t for _, t in lines]:
            for word, neg_ok in banned:
                if word in text and not (neg_ok and any(n in text for n in NEGATIONS)):
                    r.err(f"{sid}：出現禁用詞「{word}」：「{plain(text)[:30]}」")
    for sid in slides:
        if sid not in drafts:
            r.err(f"{sid}：大綱有這一頁，但 drafts/ 沒有稿子")
    for sid, path in drafts.items():
        if sid not in slides:
            r.err(f"{sid}：drafts/ 有稿子，但大綱沒有這一頁")
            continue
        title, lines = parse_draft(path)
        allowed = set(slides[sid]["cards"])
        if not title:
            r.err(f"{sid}：沒有標題（# 開頭）")
        if len(plain(title)) > TITLE_MAX:
            r.err(f"{sid}：標題 {len(plain(title))} 字，超過 {TITLE_MAX} 字")
        body_n = sum(char_count(t) for _, t in lines)
        if body_n > BODY_MAX:
            r.err(f"{sid}：正文 {body_n} 字，超過 {BODY_MAX} 字")
        for kind, text in lines:
            refs = REF_RE.findall(text)
            for slug in WLINK_RE.findall(text):
                if slug not in listed:
                    r.err(f"{sid}：[[{slug}]] 沒有列在 sources.md")
            if kind == "other":
                r.err(f"{sid}：「{text[:20]}」不是 `- ` 事實句或 `> ` 引導句")
            if kind == "lead":
                if refs:
                    r.err(f"{sid}：引導句不可以標卡片：「{text[:20]}」")
                if numbers_in(text):
                    r.err(f"{sid}：引導句不可以有數字：「{text[:20]}」")
                continue
            if kind == "fact" and not refs:
                r.err(f"{sid}：事實句沒有標 [card-id]：「{text[:20]}」")
            for cid in refs:
                if cid not in cards:
                    r.err(f"{sid}：[{cid}] 不存在")
                elif cid not in allowed:
                    r.err(f"{sid}：[{cid}] 沒有列在大綱這一頁的卡片裡")
            pool = " ".join(cards[c]["finding"] + " " + str(cards[c]["meta"].get("design", "")) for c in refs if c in cards)
            pool_nums = set(numbers_in(pool))
            for n in numbers_in(REF_RE.sub(" ", text)):
                if n not in pool_nums:
                    r.err(f"{sid}：數字 `{n}` 不在這一行標註的卡片裡")
        r.note(f"{sid}：標題 {len(plain(title))} 字，正文 {body_n} 字")
    return r.finish()


# ---------------------------------------------------------------- G7 渲染
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#6b6b70;--accent:#b4432f;--card:#ffffff;--ref:#8a8a8f}
@media (prefers-color-scheme: dark){:root{--bg:#17171a;--fg:#ececef;--muted:#a0a0a8;--accent:#ff8a70;--card:#222226;--ref:#8f8f97}}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
.slide{display:none;position:absolute;inset:0;padding:6vh 8vw;flex-direction:column;justify-content:center;overflow:hidden}
.slide.active{display:flex}
.slide h1{font-size:clamp(28px,5vw,56px);line-height:1.25;margin:0 0 4vh;color:var(--fg);text-wrap:balance;word-break:keep-all;overflow-wrap:anywhere}
body.hide-refs .ref{display:none}
.slide.sources h1{font-size:clamp(24px,3.6vw,40px);margin-bottom:3vh}
.slide.sources ul{columns:2;column-gap:4vw}
.slide.sources li{font-size:clamp(12px,1.35vw,17px);line-height:1.45;margin:0 0 .5vh;break-inside:avoid;padding-left:0}
.slide.sources li::before{display:none}
.slide.cover h1{font-size:clamp(34px,6.5vw,72px)}
.slide ul{list-style:none;margin:0;padding:0}
.slide li{font-size:clamp(18px,2.8vw,32px);line-height:1.55;margin:0 0 2.2vh;padding-left:1.1em;position:relative}
.slide li::before{content:"";position:absolute;left:0;top:.62em;width:.42em;height:.42em;border-radius:50%;background:var(--accent)}
.slide p.lead{font-size:clamp(18px,2.6vw,30px);line-height:1.55;margin:2vh 0 0;color:var(--muted);border-left:4px solid var(--accent);padding-left:.8em}
.slide p.lead + ul{margin-top:3.5vh}
.ref{font-size:.55em;color:var(--ref);vertical-align:super;margin-left:.15em;cursor:help;white-space:nowrap}
.wref{font-size:.6em;color:var(--ref);margin-left:.4em;cursor:help;white-space:nowrap}
.chrome{position:fixed;bottom:2vh;right:3vw;font-size:14px;color:var(--muted)}
.chrome.hint{left:3vw;right:auto}
#overflow-report{position:fixed;top:0;left:0;margin:0;font-size:12px;white-space:pre;display:none}
"""

JS = """
(function(){
  var s=[].slice.call(document.querySelectorAll('.slide')),i=0,c=document.getElementById('counter');
  var q=new URLSearchParams(location.search);
  function show(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach(function(e,k){e.classList.toggle('active',k===i)});c.textContent=(i+1)+' / '+s.length;}
  document.addEventListener('keydown',function(e){
    if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){show(i+1);e.preventDefault();}
    if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){show(i-1);e.preventDefault();}
    if(e.key==='Home')show(0); if(e.key==='End')show(s.length-1);
    if(e.key==='s'||e.key==='S'){document.body.classList.toggle('hide-refs');}
  });
  document.addEventListener('click',function(e){ if(e.target.closest('.ref'))return; show(e.clientX>innerWidth/2?i+1:i-1); });
  show(q.has('slide')?parseInt(q.get('slide'),10)-1:0);
  if(q.has('check')){
    var out=[];
    s.forEach(function(e,k){show(k);var o=e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1;
      out.push({slide:e.dataset.slide,overflow:o,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight});});
    var r=document.getElementById('overflow-report');r.textContent='OVERFLOW_REPORT '+JSON.stringify(out);
    show(q.has('slide')?parseInt(q.get('slide'),10)-1:0);
  }
})();
"""


def render_inline(text: str, cards) -> str:
    out, pos = [], 0
    for m in re.finditer(r"\*\*(.+?)\*\*|\[\[([a-z0-9-]+)\]\]|\[(c\d{2,3})\]", text):
        out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f"<strong>{html.escape(m.group(1))}</strong>")
        elif m.group(2) is not None:
            slug = m.group(2)
            out.append(f'<span class="wref" title="wiki 概念頁：wiki/concepts/{slug}.md">[[{slug}]]</span>')
        else:
            cid = m.group(3)
            tip = re.sub(r"\s+", " ", cards[cid]["cites"]) if cid in cards else ""
            out.append(f'<span class="ref" title="{html.escape(tip, quote=True)}">[{cid}]</span>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


SOURCES_TITLE = "資料來源"


def source_label(slug: str, by_slug) -> str:
    """從 wiki 來源頁的 H1 取「作者, 年份」，例如「（Ward 等人, 2017）」→「Ward 等人, 2017」。"""
    p = by_slug.get(slug)
    if p:
        for ln in p.body.splitlines():
            if ln.startswith("# "):
                m = re.search(r"（([^（）]+)）\s*$", ln)
                if m:
                    return m.group(1)
                break
    return slug


def sources_lines(cards) -> list[str]:
    """「資料來源」頁的每一行：卡片 id → 作者、年份、頁碼。完全由 cards/ 和 wiki 來源頁產生。"""
    _, by_slug = wiki_index()
    out = []
    for cid in sorted(cards):
        parts = {}
        for m in lint.CITE_RE.finditer(cards[cid]["cites"]):
            slug, pos = m.group(1), m.group(2).strip()
            parts.setdefault(slug, [])
            if pos not in parts[slug]:
                parts[slug].append(pos)
        segs = []
        for slug, poss in parts.items():
            sp = by_slug.get(slug)
            tail = "（僅摘要）" if sp and sp.meta.get("coverage") == "僅摘要" else ""
            segs.append(f"{source_label(slug, by_slug)}, {'；'.join(poss)}{tail}")
        out.append(f"[{cid}] " + "／".join(segs))
    return out


def render(d: Path) -> int:
    r = Result("G7 渲染")
    cards = load_cards(d)
    slides = parse_outline(d)
    deck_title = read(d / "outline.md").splitlines()[0].lstrip("# ").replace("大綱：", "").strip()
    parts = []
    for k, path in enumerate(sorted((d / "drafts").glob("slide-*.md"))):
        title, lines = parse_draft(path)
        cls = "slide cover" if k == 0 else "slide"
        items, leads = [], []
        body = []
        for kind, text in lines:
            if kind == "fact":
                body.append(f"<li>{render_inline(text, cards)}</li>")
            else:
                body.append(f'<p class="lead">{render_inline(text, cards)}</p>')
        # 連續的 li 包進 ul
        html_body, buf = [], []
        for b in body:
            if b.startswith("<li>"):
                buf.append(b)
            else:
                if buf:
                    html_body.append("<ul>" + "".join(buf) + "</ul>")
                    buf = []
                html_body.append(b)
        if buf:
            html_body.append("<ul>" + "".join(buf) + "</ul>")
        parts.append(f'<section class="{cls}" data-slide="{path.stem}"><h1>{render_inline(title, cards)}</h1>{"".join(html_body)}</section>')
    # 最後一頁「資料來源」：由腳本從 cards/ 自動產生，不由 AI 撰寫
    lis = "".join(f"<li>{html.escape(x)}</li>" for x in sources_lines(cards))
    parts.append(f'<section class="slide sources generated" data-slide="sources"><h1>{SOURCES_TITLE}</h1><ul>{lis}</ul></section>')
    doc = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(deck_title)}</title><style>{CSS}</style></head>
<body>
{chr(10).join(parts)}
<div class="chrome" id="counter"></div>
<div class="chrome hint">← → 翻頁　S 顯示／隱藏出處標記</div>
<pre id="overflow-report" class="chrome"></pre>
<script>{JS}</script>
</body></html>
"""
    (d / "deck.html").write_text(doc, encoding="utf-8")
    r.note(f"已寫入 {(d / 'deck.html').relative_to(ROOT).as_posix()}（{len(parts)} 頁）")
    return r.finish()


# ---------------------------------------------------------------- G7 比對
class DeckText(HTMLParser):
    BLOCKS = {"h1", "li", "p"}

    def __init__(self):
        super().__init__()
        self.slides, self.cur, self.buf, self.skip, self.in_block = {}, None, [], 0, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style") or "chrome" in (a.get("class") or "").split():
            self.skip += 1
            return
        if tag == "section" and "slide" in (a.get("class") or "").split():
            self.cur = a.get("data-slide")
            self.slides[self.cur] = []
        if tag in self.BLOCKS and self.cur:
            self.in_block += 1
            self.buf = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "div", "pre") and self.skip:
            self.skip -= 1
            return
        if tag in self.BLOCKS and self.cur and self.in_block:
            self.in_block -= 1
            self.slides[self.cur].append(re.sub(r"\s+", " ", "".join(self.buf)).strip())
        if tag == "section":
            self.cur = None

    def handle_data(self, data):
        if not self.skip and self.in_block:
            self.buf.append(data)


def g7(d: Path) -> int:
    r = Result("G7 deck.html 和 drafts 文字一致性")
    p = DeckText()
    p.feed(read(d / "deck.html"))
    drafts = {x.stem: x for x in sorted((d / "drafts").glob("slide-*.md"))}
    deck_pages = set(p.slides) - {"sources"}
    if deck_pages != set(drafts):
        r.err(f"頁面不一致：deck 有 {sorted(deck_pages - set(drafts))}，drafts 有 {sorted(set(drafts) - deck_pages)}")
    # 「資料來源」頁：和腳本從 cards/ 重新產生的內容逐字比對
    want_src = [SOURCES_TITLE] + sources_lines(load_cards(d))
    got_src = p.slides.get("sources")
    if got_src is None:
        r.err("deck.html 沒有「資料來源」頁")
    elif got_src != want_src:
        diff = next((k for k in range(max(len(want_src), len(got_src)))
                     if (want_src[k] if k < len(want_src) else None) != (got_src[k] if k < len(got_src) else None)), 0)
        r.err(f"「資料來源」頁和 cards/ 產生的內容不一致（第 {diff + 1} 行）")
    else:
        r.note(f"資料來源頁：{len(want_src) - 1} 張卡片，和 cards/ 產生的內容完全一致")
    for sid, path in drafts.items():
        title, lines = parse_draft(path)
        want = [plain(title)] + [plain(t) for _, t in lines]
        got = p.slides.get(sid, [])
        if want != got:
            for k in range(max(len(want), len(got))):
                a = want[k] if k < len(want) else "（無）"
                b = got[k] if k < len(got) else "（無）"
                if a != b:
                    r.err(f"{sid} 第 {k + 1} 段不一致：drafts「{a[:40]}」vs deck「{b[:40]}」")
                    break
        else:
            r.note(f"{sid}：{len(want)} 段完全一致")
    return r.finish()


# ---------------------------------------------------------------- G8
def find_browser():
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in cands:
        if Path(c).is_file():
            return c
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        w = shutil.which(name)
        if w:
            return w
    return None


def g8(d: Path) -> int:
    r = Result("G8 渲染檢查")
    b = find_browser()
    if not b:
        r.err("找不到 Edge 或 Chrome，無法自動檢查；請交給使用者人工檢查")
        return r.finish()
    deck = (d / "deck.html").resolve().as_uri()
    base = [b, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1280,720"]
    try:
        out = subprocess.run(base + ["--virtual-time-budget=3000", "--dump-dom", deck + "?check=1"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    except Exception as e:  # noqa: BLE001
        r.err(f"執行瀏覽器失敗：{e}；請交給使用者人工檢查")
        return r.finish()
    m = re.search(r"OVERFLOW_REPORT (\[.*?\])", html.unescape(out.stdout))
    if not m:
        r.err("沒有取得溢出報告；請交給使用者人工檢查")
    else:
        for item in json.loads(m.group(1)):
            if item["overflow"]:
                r.err(f"{item['slide']}：文字溢出（內容高度 {item['scrollHeight']} > 畫面 {item['clientHeight']}）→ 退回 G5 縮短")
            else:
                r.note(f"{item['slide']}：沒有溢出")
    shots = d / "screenshots"
    shots.mkdir(exist_ok=True)
    # 頁數以 deck.html 實際的 section 數為準（含自動產生的「資料來源」頁）
    n = len(re.findall(r'<section class="slide', read(d / "deck.html")))
    ok = 0
    for k in range(1, n + 1):
        target = shots / f"slide-{k:02d}.png"
        try:
            subprocess.run(base + [f"--screenshot={target}", f"{deck}?slide={k}"],
                           capture_output=True, timeout=90)
        except Exception:  # noqa: BLE001
            pass
        ok += target.is_file()
    if ok < n:
        r.warn(f"截圖只成功 {ok}/{n} 張；缺少的頁面請人工檢查")
    else:
        r.note(f"截圖 {ok} 張，存在 {shots.relative_to(ROOT).as_posix()}/")
    return r.finish()


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="topic-slides 關卡檢查")
    ap.add_argument("gate", choices=["g1", "g2", "g3", "g4", "g6", "render", "g7", "g8"])
    ap.add_argument("dir", help="產出資料夾，例如 outputs/slides-intro")
    a = ap.parse_args()
    d = (ROOT / a.dir).resolve() if not Path(a.dir).is_absolute() else Path(a.dir)
    if (ROOT / "outputs").resolve() not in d.parents:
        sys.exit("產出資料夾必須在 outputs/ 之內")
    return {"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g6": g6, "render": render, "g7": g7, "g8": g8}[a.gate](d)


if __name__ == "__main__":
    sys.exit(main())
