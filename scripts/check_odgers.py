"""確認 wiki 中所有 [[odgers-2024]] 的短引，都不在 Claudia de Rham 那篇文章的範圍內。

用途：
    raw/odgers-2024.pdf 的第 2 頁混進了另一篇不相關的 Nature 文章（物理學家 Claudia de Rham 的訪談），
    頁面上還有一個引言框，旁邊印著 "CLAUDIA DE RHAM" 版面標籤，但引言內容其實出自 Odgers 本文。
    lint.py 第 2 項只檢查「短引是否出現在 raw-text 中」，無法分辨它來自 Odgers 本文還是 de Rham 那篇，
    所以用這個腳本逐句比對行號，確認每一句短引都至少有一處出現在 Odgers 本文的範圍內。

用法：
    python scripts/check_odgers.py

排除範圍（raw-text/odgers-2024.txt 的行號，ingest odgers-2024 時人工判讀後設定）：
    140–228：Claudia de Rham 訪談本文
    288–292：引言框與 "CLAUDIA DE RHAM" 版面標籤
如果重新抽字（extract_text.py --force），行號可能改變，要重新判讀並更新 EXCLUDED。

結束代碼：有任何一句找不到，或只出現在排除範圍內，是 1；否則是 0。
"""
from __future__ import annotations

import sys
from pathlib import Path

import lint  # 同一個資料夾：重用 lint.py 的正規化和引文格式

ROOT = Path(__file__).resolve().parent.parent
SLUG = "odgers-2024"
EXCLUDED = [(140, 228), (288, 292)]
MAX_SPAN = 8  # 一句短引最多跨幾行


def windows(quote: str, lines: list[str]) -> list[tuple[int, int]]:
    """找出所有能包住整句短引的最小行區間 (起, 迄)，行號從 1 開始。"""
    target = lint.normalize(quote)
    hits = []
    for i in range(len(lines)):
        for j in range(i, min(i + MAX_SPAN, len(lines))):
            if target in lint.normalize("\n".join(lines[i:j + 1])):
                hits.append((i + 1, j + 1))
                break
    return [h for h in hits if not any(o != h and h[0] <= o[0] and o[1] <= h[1] for o in hits)]


def excluded(win: tuple[int, int]) -> bool:
    return any(not (win[1] < a or win[0] > b) for a, b in EXCLUDED)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    lines = (ROOT / "raw-text" / f"{SLUG}.txt").read_text(encoding="utf-8-sig").splitlines()
    bad = total = 0
    for page in sorted((ROOT / "wiki").rglob("*.md")):
        for n, ln in enumerate(page.read_text(encoding="utf-8-sig").splitlines(), 1):
            for m in lint.CITE_RE.finditer(ln):
                if m.group(1) != SLUG:
                    continue
                total += 1
                quote = m.group(3)
                wins = windows(quote, lines)
                if not wins:
                    status = "找不到"
                elif not [w for w in wins if not excluded(w)]:
                    status = "只出現在排除範圍"
                else:
                    status = "OK"
                bad += status != "OK"
                loc = "、".join(f"{a}-{b}" + ("(排除)" if excluded((a, b)) else "") for a, b in wins) or "-"
                print(f"[{status}] {page.relative_to(ROOT).as_posix()}:{n}  raw-text 第 {loc} 行  \"{quote[:50]}\"")
    print(f"\n共 {total} 句，問題 {bad} 句")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
