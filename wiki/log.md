---
type: log
title: 變更紀錄
sources: []
origin: ingest
updated: 2026-11-23
---

# 變更紀錄

只能在最後追加，不可修改舊紀錄。格式見 `AGENTS.md` 第 10 節。

## [2026-11-23] setup | 初始化
- 新增：`AGENTS.md`、`CLAUDE.md`、`requirements.md`、資料夾結構、`scripts/extract_text.py`、`scripts/lint.py`
- 檢查結果：
  - 問題：Windows 工具（PowerShell）寫出的檔案開頭有 BOM，lint 讀不到 frontmatter，誤報「缺少 frontmatter」｜步驟：setup 腳本自我測試（用 scratchpad 的假資料）｜處理：讀檔改用 `utf-8-sig`，重新測試後通過
  - 問題：環境缺少 `pypdf` 和 `git`｜步驟：setup 環境檢查｜處理：使用者同意後安裝了 pypdf 7.1.1（pip）和 Git 2.56.1（winget）

## [2026-11-23] setup | 規則調整
- 決定：`raw/` 和 `raw-text/` 寫進 `.gitignore`，不進 git（版權和檔案大小的考量）；改用 `sources-list.md` 列出作者、年份、標題、連結，這份要進 git。〔R12.3〕〔R12.4〕
- 新增規則：來源頁 frontmatter 加 `coverage: 全文 | 僅摘要`；僅摘要的來源，主張頁的證據要標「（僅根據摘要）」，不可以寫出摘要以外的細節。lint 第 8 項加入對應檢查。〔R5.3〕
- 修改：`AGENTS.md`、`requirements.md`、`scripts/lint.py`、`.gitignore`；新增 `sources-list.md`；刪除 `raw-text/.gitkeep`（資料夾已不進 git）
- 檢查結果：
  - 問題：第 8 項「專有名詞附英文」腳本只能檢查已經有概念頁或人物頁的術語，無法判斷沒有頁面的術語、同義詞，以及哪些詞算專有名詞｜步驟：setup 規則檢討（使用者要求說明檢查方式）｜處理：拆成兩部分，腳本只檢查詞彙表內的術語，其他移到 AI 審查（8b），可以直接修〔R11.9〕
  - 問題：英文檢查會把沒有顯示文字的 `[[slug]]` 留下殘字 `[[slug`｜步驟：setup 檢查程式碼｜處理：改成直接移除 `[[slug]]`，有 `|顯示文字` 時才保留顯示文字
  - 問題：`sources-list.md` 還沒有資料，因為 `raw/` 目前是空的｜步驟：setup 讀取 raw/｜處理：先建立空白表格，等資料放進來後補上

## [2026-11-23] setup | sources-list
- 修改：`sources-list.md` 補上 6 篇資料（讀取每篇的第一頁和 metadata，沒有寫入 raw-text）
- 決定：ingest 順序是 ward-2017 → pileggi-2025 → nguyen-2025 → panova-2018 → odgers-2024 → goodyear-2025；重複驗證那篇用 pileggi-2025，不用 ruiz-pardo-2022（使用者指定）
- 檢查結果：
  - 問題：pileggi-2025 的 PDF 只有封面和一頁摘要，沒有全文｜步驟：setup 讀取 raw/ 第一頁｜處理：coverage 標「僅摘要」，在 sources-list 註明，並告知使用者
  - 問題：odgers-2024 原文裡沒有 DOI｜步驟：setup 讀取 raw/｜處理：連結欄標「待補」，只寫原文可以確認的卷期和頁碼，不用記憶補 DOI
  - 問題：使用者列了 7 個名字，但只有 6 篇資料｜步驟：setup 讀取 raw/｜處理：使用者確認不用 ruiz-pardo-2022
