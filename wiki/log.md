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

## [2026-11-23] ingest | ward-2017
- 新增：[[ward-2017]]、[[phone-presence-reduces-cognition]]、[[phone-face-down-or-off]]、[[brain-drain-effect]]、[[working-memory]]、[[fluid-intelligence]]、[[sustained-attention]]、[[smartphone-dependence]]
- 修改：[[index]]；`AGENTS.md` 和 `requirements.md` 新增 R5.4（`page_offset`、避開抽字錯誤的句子）；`scripts/lint.py`（修正兩個誤報）
- I3 使用者決定：強調「翻面或關機沒用」「專注力沒受影響」「效果小、對象只有大學生」，並明確區分認知容量和專注力；頁碼用期刊頁碼；FAQ 等 pileggi-2025 之後再寫；省略 OSpan 和 Raven 的量表頁，改在概念頁說明
- 檢查結果：
  - 問題：抽字時符號被抽錯（`=` 變成 `5`、`×` 變成 `/C2`、`η²` 變成 `h2`、`−1 SD` 和 `+1 SD` 變成 `21SD` 和 `11 SD`），統計數字無法逐字引用｜步驟：I1 抽字｜處理：短引避開有符號錯誤的句子；有特殊符號的數字改用白話寫，例如「不到百分之三」；新增規則 R5.4
  - 問題：PDF 頁碼（1–15）和期刊頁碼（p. 140–154）不一致｜步驟：I1 抽字｜處理：出處一律用期刊頁碼，來源頁加 `page_offset: 139`（期刊頁碼 = PDF 頁碼 + 139）
  - 問題：論文提到的線上附錄不在 raw/ 裡｜步驟：I1 抽字｜處理：不引用附錄內容，並在來源頁的「限制」註明
  - 問題：[[phone-face-down-or-off]] 的「目前怎麼看」轉述了作者的說法，但沒有附短引｜步驟：I4 寫頁（自我檢查）｜處理：補上 p. 150 的短引
  - 問題：[[ward-2017]] 中「手機依賴」第一次出現時沒有附英文｜步驟：I4 寫頁（自我檢查）｜處理：補上（smartphone dependence）
  - 問題：lint 把 log.md 裡行內程式碼中的 `[[slug]]` 範例當成斷鏈｜步驟：I5 自我檢查（腳本第 5 項誤報）｜處理：修改 lint.py，比對連結前先移除程式碼片段
  - 問題：lint 把內文提到的頁碼（p. 140–154 等）當成需要核對的數據｜步驟：I5 自我檢查（腳本第 11 項誤報）｜處理：修改 lint.py，排除 `p. N` 和 `pp. N–M` 格式的頁碼

## [2026-11-23] ingest | pileggi-2025
- 新增：[[pileggi-2025]]、[[replication]]
- 修改：[[phone-presence-reduces-cognition]]（加入反對證據，改寫「簡短回答」和「目前怎麼看」）、[[phone-face-down-or-off]]（「目前怎麼看」加第 3 點）、[[brain-drain-effect]]（相關研究）、[[ward-2017]]（主要發現 1 加註「有研究未能重現」）、[[index]]；`scripts/lint.py`
- I3 使用者決定：強調「刻意讓效應更容易出現，還是沒有」和「只有摘要，看不到樣本數」；新增 replication 概念頁；FAQ 等 6 篇都 ingest 完再一起寫；作者對其他重複驗證研究的描述可以寫，但要標成「作者對其他研究的描述，wiki 尚未收錄」
- 這是第一次觸發矛盾處理規則（R7）：[[phone-presence-reduces-cognition]] 並列支持和反對的證據，「目前怎麼看」整理出三個可能原因（設計不同、原始效應很小、反對證據資訊不足）
- 檢查結果：
  - 問題：raw/ 的 PDF 只有封面和摘要，樣本數、對象、作業都不知道｜步驟：I1 抽字｜處理：coverage 標「僅摘要」，population 和 n 標「未載明」，所有證據都加「（僅根據摘要）」，位置寫 `Abstract`
  - 問題：摘要說「abstinence was found to increase over time」，沒有說明是什麼增加了｜步驟：I2 閱讀報告｜處理：只照原句轉述，在來源頁「限制」註明不做推測
  - 問題：把 [[pileggi-2025]] 放進 [[phone-face-down-or-off]] 的「反對」證據，可能過度詮釋，因為這篇沒有測試翻面，整體效應也沒有出現｜步驟：I3 討論（使用者指出）｜處理：不放進「反對」，改放到「目前怎麼看」，說明這篇無法回答翻面或關機有沒有用
  - 問題：[[replication]] 的「白話解釋」「研究上怎麼看待」「常見誤解」三節是一般性的方法說明，收錄的來源裡沒有｜步驟：I4 寫頁（自我檢查）｜處理：每一節開頭標註「本節是 wiki 的一般說明，不是出自任何一篇收錄的來源」
  - 問題：研究設計標籤【重複驗證】讓「重複驗證」的第一次出現落在標籤裡，但標籤是固定格式，不能加英文｜步驟：I4 寫頁（[[brain-drain-effect]]）｜處理：修改 lint.py，檢查附英文時跳過【…】標籤
  - 問題：[[phone-presence-reduces-cognition]] 中「腦力流失效應」第一次出現時沒有附英文｜步驟：I4 寫頁（自我檢查）｜處理：補上（brain drain effect）
  - 問題：[[pileggi-2025]] 的 H1 標題裡，「腦力流失效應」後面接的是作者括號，不是英文｜步驟：I5 自我檢查（腳本第 8 項）｜處理：標題改成「再測一次『腦力流失』」
  - 問題：來源頁寫了「CogSci 2025」，年份沒有附出處｜步驟：I5 自我檢查（腳本第 11 項）｜處理：改寫成學會名稱，不寫年份
