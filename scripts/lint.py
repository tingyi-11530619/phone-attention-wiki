"""Wiki lint：腳本負責的第 2、5、7、8、9、10、11 項（見 AGENTS.md 第 11 節）。

用法：
    python scripts/lint.py            # 把報告印到畫面上
    python scripts/lint.py --write    # 同時寫入 lint-report.md 的「腳本檢查（L1）」段落

結束代碼：有錯誤是 1，只有警告或沒有問題是 0。
只用標準函式庫。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
RAW = ROOT / "raw"
RAW_TEXT = ROOT / "raw-text"
REPORT = ROOT / "lint-report.md"

FOLDER_TYPE = {"sources": "source", "concepts": "concept", "claims": "claim",
               "entities": "entity", "faq": "faq"}
SPECIAL = {"index": "index", "log": "log"}
REQUIRED = ["type", "title", "sources", "origin", "updated"]
DESIGNS = {"實驗", "重複驗證", "統合分析", "相關性研究", "評論"}
COVERAGE = {"全文", "僅摘要"}
ABSTRACT_MARK = "（僅根據摘要）"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
# （[[slug]], p. 142: "quote"）
CITE_RE = re.compile(r"\[\[([a-z0-9-]+)(?:\|[^\]]*)?\]\],\s*([^:\n\"]{1,40}?):\s*[\"“]([^\"”\n]+)[\"”]")
NUM_RE = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|(?<![\w.])\.\d+")
QUERY_BANNER = "【問答產生】"
LOG_HEAD_RE = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (ingest|query|lint|setup) \| (.+?)\s*$")


# ---------------------------------------------------------------- 資料結構
@dataclass
class Page:
    path: Path
    slug: str
    folder: str
    meta: dict
    body: str
    body_start: int  # body 第一行在檔案中的行號（1-based）

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


@dataclass
class Report:
    items: dict = field(default_factory=lambda: defaultdict(list))  # check -> [(level, msg)]

    def err(self, check: int, msg: str) -> None:
        self.items[check].append(("錯誤", msg))

    def warn(self, check: int, msg: str) -> None:
        self.items[check].append(("警告", msg))

    def count(self, level: str) -> int:
        return sum(1 for v in self.items.values() for lv, _ in v if lv == level)


CHECK_NAMES = {
    2: "引文可核對", 5: "斷鏈和孤兒頁", 7: "總覽和紀錄", 8: "語言和格式",
    9: "outputs 污染", 10: "Query 頁標註", 11: "數字可核對",
}
AUTO_FIX = {5, 7, 8}


# ---------------------------------------------------------------- 解析
def parse_frontmatter(text: str) -> tuple[dict, str, int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = {}
            for ln in lines[1:i]:
                ln = re.sub(r"\s+#.*$", "", ln)
                if ":" not in ln or ln.startswith(" "):
                    continue
                k, v = ln.split(":", 1)
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                else:
                    v = v.strip("'\"")
                meta[k.strip()] = v
            return meta, "\n".join(lines[i + 1:]), i + 2
    return {}, text, 1


def load_pages() -> list[Page]:
    pages = []
    for p in sorted(WIKI.rglob("*.md")):
        text = p.read_text(encoding="utf-8-sig", errors="replace")  # -sig：容許 Windows 的 BOM
        meta, body, start = parse_frontmatter(text)
        rel = p.relative_to(WIKI)
        folder = rel.parts[0] if len(rel.parts) > 1 else ""
        pages.append(Page(p, p.stem, folder, meta, body, start))
    return pages


# ---------------------------------------------------------------- 正規化
PAGE_MARK_RE = re.compile(r"^=== page \d+ ===\s*$", re.M)


def normalize(s: str) -> str:
    """嚴格比對用：NFKC、統一引號、合併連字號斷字、合併空白、小寫。"""
    s = unicodedata.normalize("NFKC", s)
    s = PAGE_MARK_RE.sub(" ", s)
    s = s.replace("­", "")  # soft hyphen
    s = re.sub(r"[‘’‚‛′]", "'", s)
    s = re.sub(r"[“”„‟″]", '"', s)
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # 行尾連字號斷字
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def loose(s: str) -> str:
    """寬鬆比對用：只保留字母和數字（處理 PDF 空白錯亂、真連字號被合併等情況）。"""
    return re.sub(r"[\W_]+", "", normalize(s))


def norm_num(n: str) -> str:
    n = n.replace(",", "")
    if n.startswith("."):
        n = "0" + n
    return n


_text_cache: dict[str, tuple[str, str, set] | None] = {}


def source_text(slug: str, pages_by_slug: dict) -> tuple[str, str, set] | None:
    """回傳（嚴格正規化文字、寬鬆文字、數字集合），找不到時回傳 None。"""
    if slug in _text_cache:
        return _text_cache[slug]
    page = pages_by_slug.get(slug)
    rel = page.meta.get("raw_text") if page else None
    path = ROOT / rel if isinstance(rel, str) and rel else RAW_TEXT / f"{slug}.txt"
    if not path.is_file():
        _text_cache[slug] = None
        return None
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    strict = normalize(raw)
    nums = {norm_num(m.group(0)) for m in NUM_RE.finditer(strict)}
    _text_cache[slug] = (strict, loose(raw), nums)
    return _text_cache[slug]


def quote_found(quote: str, strict: str, loose_txt: str) -> str:
    """回傳 'strict'、'loose' 或 ''（找不到）。引文中的 ... 會分段依序比對。"""
    parts = [p for p in re.split(r"\.\.\.|…", quote) if p.strip()]

    def in_order(segs, hay):
        pos = 0
        for seg in segs:
            i = hay.find(seg, pos)
            if i < 0:
                return False
            pos = i + len(seg)
        return True

    if in_order([normalize(p) for p in parts], strict):
        return "strict"
    if in_order([loose(p) for p in parts if loose(p)], loose_txt):
        return "loose"
    return ""


# ---------------------------------------------------------------- 檢查
def check_format(pages, by_slug, rep: Report) -> None:  # 第 8 項
    seen = defaultdict(list)
    for p in pages:
        seen[p.slug].append(p.rel)
        if not SLUG_RE.match(p.slug):
            rep.err(8, f"`{p.rel}`：檔名不是英文 kebab-case slug")
        if not p.meta:
            rep.err(8, f"`{p.rel}`：缺少 frontmatter")
            continue
        for k in REQUIRED:
            if k not in p.meta:
                rep.err(8, f"`{p.rel}`：frontmatter 缺少 `{k}`")
        expected = SPECIAL.get(p.slug) if p.folder == "" else FOLDER_TYPE.get(p.folder)
        if p.folder and p.folder not in FOLDER_TYPE:
            rep.err(8, f"`{p.rel}`：不在允許的資料夾裡（{', '.join(FOLDER_TYPE)}）")
        elif p.folder == "" and p.slug not in SPECIAL:
            rep.err(8, f"`{p.rel}`：wiki/ 根目錄只能放 index.md 和 log.md")
        elif expected and p.meta.get("type") not in (None, expected):
            rep.err(8, f"`{p.rel}`：type 是 `{p.meta.get('type')}`，但所在資料夾要求 `{expected}`")
        if p.meta.get("origin") not in (None, "ingest", "query"):
            rep.err(8, f"`{p.rel}`：origin 只能是 ingest 或 query")
        upd = p.meta.get("updated")
        if isinstance(upd, str) and not DATE_RE.match(upd):
            rep.err(8, f"`{p.rel}`：updated 不是 YYYY-MM-DD 格式")
        srcs = p.meta.get("sources", [])
        if not isinstance(srcs, list):
            rep.err(8, f"`{p.rel}`：sources 必須是清單，例如 [ward-2017]")
            srcs = []
        for s in srcs:
            sp = by_slug.get(s)
            if not sp or sp.folder != "sources":
                rep.err(8, f"`{p.rel}`：sources 列了 `{s}`，但沒有對應的來源頁")
        cited = {m.group(1) for m in CITE_RE.finditer(p.body)}
        missing = cited - set(srcs)
        if missing and p.folder != "sources":
            rep.warn(8, f"`{p.rel}`：內文引用了 {', '.join(sorted(missing))}，但 frontmatter 的 sources 沒有列")

        t = p.meta.get("type")
        if t == "source":
            for k in ("raw_file", "raw_text", "coverage", "design", "population", "n"):
                if k not in p.meta:
                    rep.err(8, f"`{p.rel}`：來源頁缺少 `{k}`")
            if p.meta.get("coverage") and p.meta["coverage"] not in COVERAGE:
                rep.err(8, f"`{p.rel}`：coverage 只能是 `全文` 或 `僅摘要`（目前是 `{p.meta['coverage']}`）")
            if p.meta.get("design") and p.meta["design"] not in DESIGNS:
                rep.err(8, f"`{p.rel}`：design `{p.meta['design']}` 不在允許清單（{'、'.join(sorted(DESIGNS))}）")
            rf = p.meta.get("raw_file")
            if isinstance(rf, str) and rf and not (RAW / Path(rf).name).is_file() and not (ROOT / rf).is_file():
                rep.err(8, f"`{p.rel}`：raw_file `{rf}` 在 raw/ 裡找不到")
            rt = p.meta.get("raw_text")
            if isinstance(rt, str) and rt and not (ROOT / rt).is_file():
                rep.err(8, f"`{p.rel}`：raw_text `{rt}` 不存在，請先執行 extract_text.py")
        if t in ("concept", "entity") and not p.meta.get("en"):
            rep.err(8, f"`{p.rel}`：概念頁和人物頁要有 `en`（英文名稱）")

    for slug, rels in seen.items():
        if len(rels) > 1:
            rep.err(8, f"slug `{slug}` 重複：{', '.join(rels)}")

    # 僅摘要的來源：主張頁中引用它的證據行要標「（僅根據摘要）」（R5.3）
    abstract_only = {p.slug for p in pages
                     if p.meta.get("type") == "source" and p.meta.get("coverage") == "僅摘要"}
    for p in pages:
        if p.meta.get("type") != "claim":
            continue
        for n, ln in enumerate(p.body.splitlines()):
            hit = {m.group(1) for m in CITE_RE.finditer(ln)} & abstract_only
            if hit and ABSTRACT_MARK not in ln:
                rep.err(8, f"`{p.rel}` 第 {p.body_start + n} 行：引用了僅摘要的來源"
                           f"（{', '.join(sorted(hit))}），但沒有標「{ABSTRACT_MARK}」")

    # 專有名詞第一次出現要附英文（只檢查「詞彙表內」的術語）：
    #   詞彙表 = 所有 concept/entity 頁的 title（中文）+ en（英文）。
    #   在每一頁找出 title 第一次出現的位置，檢查後面是否緊接（en）或 (en)。
    #   沒有自己頁面的術語、同義詞、判斷哪些詞算專有名詞，腳本做不到，由 AI 審查（AGENTS.md 11.2）。
    terms = [(p.meta["title"], p.meta["en"]) for p in pages
             if p.meta.get("type") in ("concept", "entity")
             and isinstance(p.meta.get("title"), str) and isinstance(p.meta.get("en"), str)]
    for p in pages:
        if p.slug in SPECIAL:
            continue
        # [[slug|顯示文字]] 換成顯示文字；[[slug]] 移除（slug 是英文，不影響中文比對）
        body = LINK_RE.sub(lambda m: m.group(0)[2:-2].split("|", 1)[1] if "|" in m.group(0) else "", p.body)
        for zh, en in terms:
            i = body.find(zh)
            if i < 0:
                continue
            after = body[i + len(zh): i + len(zh) + len(en) + 4]
            if not re.match(r"\s*[（(]\s*" + re.escape(en) + r"\s*[）)]", after, re.I):
                rep.warn(8, f"`{p.rel}`：「{zh}」第一次出現時沒有附英文（{en}）")


def check_links(pages, by_slug, rep: Report) -> None:  # 第 5 項
    inbound = defaultdict(set)
    for p in pages:
        for m in LINK_RE.finditer(p.body):
            target = m.group(1).strip()
            if target not in by_slug:
                rep.err(5, f"`{p.rel}`：斷鏈 `[[{target}]]`")
            elif p.slug not in SPECIAL and target != p.slug:
                inbound[target].add(p.slug)
    for p in pages:
        if p.slug not in SPECIAL and not inbound[p.slug]:
            rep.warn(5, f"`{p.rel}`：孤兒頁（除了 index 和 log 之外，沒有其他頁面連到它）")


def check_index_log(pages, by_slug, rep: Report) -> None:  # 第 7 項
    index, log = by_slug.get("index"), by_slug.get("log")
    if not index:
        rep.err(7, "找不到 `wiki/index.md`")
    else:
        listed = {m.group(1).strip() for m in LINK_RE.finditer(index.body)}
        for p in pages:
            if p.slug not in SPECIAL and p.slug not in listed:
                rep.err(7, f"`{p.rel}`：沒有列在 index.md")
    if not log:
        rep.err(7, "找不到 `wiki/log.md`")
        return
    entries = defaultdict(set)  # kind -> {target}
    lines = log.body.splitlines()
    heads = []
    for n, ln in enumerate(lines):
        if ln.startswith("## "):
            m = LOG_HEAD_RE.match(ln)
            if not m:
                rep.err(7, f"`wiki/log.md` 第 {log.body_start + n} 行：標題格式不符 `## [YYYY-MM-DD] <ingest|query|lint|setup> | <對象>`")
                continue
            heads.append(n)
            for t in re.split(r"[,、]\s*", m.group(3)):
                entries[m.group(2)].add(t.strip().strip("[]"))
    for k, start in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        if "檢查結果" not in "\n".join(lines[start:end]):
            rep.err(7, f"`wiki/log.md` 第 {log.body_start + start} 行的紀錄缺少「檢查結果」（問題、步驟、處理）")
    for p in pages:
        if p.meta.get("type") == "source" and p.slug not in entries["ingest"]:
            rep.err(7, f"`{p.rel}`：log.md 沒有 `ingest | {p.slug}` 紀錄")
        if p.meta.get("origin") == "query" and p.slug not in entries["query"]:
            rep.err(7, f"`{p.rel}`：log.md 沒有 `query | {p.slug}` 紀錄")


def check_outputs(pages, rep: Report) -> None:  # 第 9 項
    pat = re.compile(r"outputs[/\\]|\(\s*\.\./+\.\./*outputs|\[\[\s*outputs", re.I)
    for p in pages:
        if p.slug == "log":
            continue  # log 可以提到 outputs 的產出紀錄
        for n, ln in enumerate(p.body.splitlines()):
            if pat.search(ln):
                rep.err(9, f"`{p.rel}` 第 {p.body_start + n} 行：引用了 outputs/（outputs 不能當作知識來源）")
        for s in p.meta.get("sources", []) if isinstance(p.meta.get("sources"), list) else []:
            if "outputs" in s:
                rep.err(9, f"`{p.rel}`：frontmatter 的 sources 含有 outputs 路徑 `{s}`")


def check_query(pages, rep: Report) -> None:  # 第 10 項
    for p in pages:
        is_q = p.meta.get("origin") == "query"
        head = [ln for ln in p.body.splitlines() if ln.strip()][:3]
        has_banner = any(QUERY_BANNER in ln for ln in head)
        anywhere = QUERY_BANNER in p.body
        if is_q:
            if not has_banner:
                rep.err(10, f"`{p.rel}`：origin 是 query，但標題下方沒有「{QUERY_BANNER}」標註")
            for k in ("query", "query_date"):
                if not p.meta.get(k):
                    rep.err(10, f"`{p.rel}`：query 頁缺少 `{k}`")
            qd = p.meta.get("query_date")
            if isinstance(qd, str) and qd and not DATE_RE.match(qd):
                rep.err(10, f"`{p.rel}`：query_date 不是 YYYY-MM-DD")
        elif anywhere:
            rep.err(10, f"`{p.rel}`：有「{QUERY_BANNER}」標註，但 origin 不是 query")


def strip_for_numbers(line: str) -> str:
    line = CITE_RE.sub(" ", line)                      # 去掉引文、頁碼、slug
    line = LINK_RE.sub(" ", line)
    line = re.sub(r"\d{4}-\d{2}-\d{2}", " ", line)     # 日期
    line = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", " ", line)  # 清單編號
    return line


def check_quotes_and_numbers(pages, by_slug, rep: Report) -> None:  # 第 2、11 項
    for p in pages:
        if p.slug in SPECIAL:
            continue
        for n, ln in enumerate(p.body.splitlines()):
            lineno = p.body_start + n
            cites = list(CITE_RE.finditer(ln))
            # 第 2 項
            for m in cites:
                slug, pos, quote = m.group(1), m.group(2).strip(), m.group(3)
                sp = by_slug.get(slug)
                if not sp or sp.folder != "sources":
                    rep.err(2, f"`{p.rel}` 第 {lineno} 行：引用的 `{slug}` 不是來源頁")
                    continue
                st = source_text(slug, by_slug)
                if st is None:
                    rep.err(2, f"`{p.rel}` 第 {lineno} 行：找不到 `{slug}` 的 raw-text 檔，無法核對引文")
                    continue
                res = quote_found(quote, st[0], st[1])
                short = quote if len(quote) <= 60 else quote[:57] + "..."
                if not res:
                    rep.err(2, f"`{p.rel}` 第 {lineno} 行：引文在 `{slug}` 原文中找不到：\"{short}\"")
                elif res == "loose":
                    rep.warn(2, f"`{p.rel}` 第 {lineno} 行：引文只在寬鬆比對（忽略標點、空白）下符合，請人工確認：\"{short}\"")
                if len(quote.split()) > 30:
                    rep.warn(2, f"`{p.rel}` 第 {lineno} 行：引文超過 25 個英文單字（{len(quote.split())} 個）")
                if not pos:
                    rep.err(2, f"`{p.rel}` 第 {lineno} 行：引文缺少位置（頁碼或小節）")
            # 第 11 項
            if ln.lstrip().startswith("#"):
                continue
            nums = [norm_num(x.group(0)) for x in NUM_RE.finditer(strip_for_numbers(ln))]
            nums = [x for x in nums if "." in x or len(x) > 1]  # 跳過 0–9 的單獨整數
            if not nums:
                continue
            if not cites:
                rep.warn(11, f"`{p.rel}` 第 {lineno} 行：有數字 {', '.join(nums)} 但同一行沒有出處，無法核對")
                continue
            pools = [source_text(m.group(1), by_slug) for m in cites]
            pools = [x[2] for x in pools if x]
            if not pools:
                continue
            for x in nums:
                if not any(x in pool for pool in pools):
                    srcs = ", ".join(sorted({m.group(1) for m in cites}))
                    rep.err(11, f"`{p.rel}` 第 {lineno} 行：數字 `{x}` 在引用來源（{srcs}）的原文中找不到")


# ---------------------------------------------------------------- 輸出
def render(rep: Report, n_pages: int) -> str:
    today = dt.date.today().isoformat()
    out = [f"## 腳本檢查（L1）",
           f"",
           f"- 執行時間：{today}，共掃描 {n_pages} 個 wiki 頁面",
           f"- 錯誤 {rep.count('錯誤')} 個，警告 {rep.count('警告')} 個",
           f"- 可以直接修的項目（AGENTS.md 11.1）：第 5、7、8 項；其他項目要等使用者確認",
           ""]
    for c in sorted(CHECK_NAMES):
        items = rep.items.get(c, [])
        tag = "（可直接修）" if c in AUTO_FIX else "（需使用者確認）"
        out.append(f"### 第 {c} 項：{CHECK_NAMES[c]} {tag if items else ''}".rstrip())
        if not items:
            out.append("- 通過")
        else:
            for lv, msg in items:
                out.append(f"- **{lv}**：{msg}")
        out.append("")
    return "\n".join(out)


def write_report(section: str) -> None:
    today = dt.date.today().isoformat()
    REPORT.write_text(
        f"# Lint 報告 {today}\n\n{section}\n"
        "## AI 審查（L2）\n\n（待 AI 審查第 1、3、4、6、12 項）\n\n"
        "## 已直接修正（L3）\n\n（尚未修正）\n\n"
        "## 待使用者確認\n\n（待整理）\n",
        encoding="utf-8")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="Wiki lint（腳本檢查項目）")
    ap.add_argument("--write", action="store_true", help="覆寫 lint-report.md，寫入腳本檢查結果")
    args = ap.parse_args()

    pages = load_pages()
    by_slug = {}
    for p in pages:
        by_slug.setdefault(p.slug, p)
    rep = Report()
    check_format(pages, by_slug, rep)
    check_links(pages, by_slug, rep)
    check_index_log(pages, by_slug, rep)
    check_outputs(pages, rep)
    check_query(pages, rep)
    check_quotes_and_numbers(pages, by_slug, rep)

    section = render(rep, len(pages))
    print(section)
    if args.write:
        write_report(section)
        print(f"已寫入 {REPORT.relative_to(ROOT)}")
    return 1 if rep.count("錯誤") else 0


if __name__ == "__main__":
    sys.exit(main())
