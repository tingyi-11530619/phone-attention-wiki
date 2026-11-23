"""從 raw/ 的原始檔抽出文字，存到 raw-text/<slug>.txt。

用法：
    python scripts/extract_text.py raw/<檔名> <slug> [--force]

- PDF：用 pypdf 逐頁抽字，每頁前面加上 "=== page N ===" 標記，方便查頁碼。
- .md / .txt / .html：讀取文字（HTML 會去掉標籤）。
- 只讀 raw/，絕不寫入 raw/（AGENTS.md 鐵則 1）。
- raw-text/<slug>.txt 已存在時，必須加 --force 才會覆寫。
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW_TEXT = ROOT / "raw-text"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("找不到 pypdf。請先執行：python -m pip install pypdf")
    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"=== page {i} ===\n{text.strip()}\n")
    return "\n".join(parts)


def extract_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="raw/ 裡的原始檔路徑")
    ap.add_argument("slug", help="來源 slug，例如 ward-2017")
    ap.add_argument("--force", action="store_true", help="覆寫已存在的 raw-text 檔")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    if RAW.resolve() not in src.parents:
        sys.exit(f"來源必須位於 raw/ 之內：{src}")
    if not src.is_file():
        sys.exit(f"找不到檔案：{src}")
    if not SLUG_RE.match(args.slug):
        sys.exit(f"slug 格式錯誤（只能有小寫英文、數字、連字號）：{args.slug}")

    out = RAW_TEXT / f"{args.slug}.txt"
    if out.exists() and not args.force:
        sys.exit(f"{out.relative_to(ROOT)} 已存在；要覆寫請加 --force")

    ext = src.suffix.lower()
    if ext == ".pdf":
        text = extract_pdf(src)
    elif ext in {".md", ".markdown", ".txt"}:
        text = src.read_text(encoding="utf-8-sig", errors="replace")
    elif ext in {".html", ".htm"}:
        text = extract_html(src.read_text(encoding="utf-8-sig", errors="replace"))
    else:
        sys.exit(f"不支援的格式：{ext}")

    RAW_TEXT.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")

    pages = text.count("=== page ")
    words = len(text.split())
    print(f"已寫入 {out.relative_to(ROOT)}（{words} 個詞" + (f"，{pages} 頁" if pages else "") + "）")
    if ext == ".pdf":
        empty = [m.group(1) for m in re.finditer(r"=== page (\d+) ===\n\s*(?==== page|\Z)", text)]
        if empty:
            print(f"警告：這些頁面沒有抽到文字（可能是掃描圖片）：{', '.join(empty)}")


if __name__ == "__main__":
    main()
