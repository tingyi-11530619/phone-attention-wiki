---
name: topic-slides
description: 用本專案的 wiki 製作給一般大眾看的教學 HTML 簡報。依照 G1–G8 關卡逐步產出 outputs/<產出名稱>/ 下的 sources.md、cards/、outline.md、drafts/、deck.html、report.md，每個關卡都有腳本或 AI 審查把關。使用者要求「做簡報」「教學簡報」「slides」時使用。
---

# topic-slides：從 wiki 產出教學簡報

本 skill 是 `AGENTS.md` 第 9 節（產出）的執行細節。`AGENTS.md` 的鐵則仍然適用，特別是：
- **知識只能來自 wiki/**：簡報裡每個事實都要能追溯到「卡片 → wiki 頁面 → raw-text 原文」。
- **outputs/ 不能回流到 wiki**：簡報裡發現的問題，要回到 wiki 修正（經使用者同意），不可以只在簡報裡改。

## 預設規格（第一份：slides-intro）

| 項目 | 規格 |
|---|---|
| 產出資料夾 | `outputs/slides-intro/` |
| 標題 | 「手機成癮是真的嗎？注意力研究怎麼說」 |
| 對象 | 完全不懂的一般人（高中生、家長） |
| 語言 | 繁體中文 |
| 頁數 | 10–15 頁 |
| 每頁字數 | 標題最多 20 字；正文最多 80 字（不含卡片標記，見 G6） |

其他主題沿用同樣的流程，只改上表。

## 檔案結構

```
outputs/<產出名稱>/
  sources.md        G1：用到的 wiki 頁面，依段落分組
  cards/<id>.md     G3：證據卡，一張卡一個發現
  outline.md        G4：大綱
  drafts/slide-NN.md  G5：逐頁稿
  deck.html         G7：渲染結果
  screenshots/      G8：截圖（如果做得到）
  report.md         最後：每個關卡的結果
```

所有檢查都用 `python scripts/slides.py <關卡> outputs/<產出名稱>`。結束代碼是 0 代表通過，是 1 代表不通過。

---

## G1 檢索 → `sources.md`

1. 讀 `wiki/index.md`，再讀和主題相關的主張頁、來源頁、概念頁。
2. 把簡報分成幾個**段落**（每個段落回答一個問題），寫成以下格式：

```
# 簡報來源：<產出名稱>

## 段落 S1｜<這一段要回答的問題>
- 主張頁：[[claim-slug]]、[[claim-slug-2]]
- 其他頁：[[source-slug]]、[[concept-slug]]
```

規則：
- **只能列 wiki/ 的頁面**，用 `[[slug]]` 格式。不可以列 outputs/、raw/ 或外部連結。
- 之後的卡片只能取自 sources.md 列出的頁面。

檢查：`python scripts/slides.py g1 <dir>`：確認每個連結都是 wiki 中存在的頁面。

## G2 覆蓋率關卡（腳本）

`python scripts/slides.py g2 <dir>`

每個段落必須滿足：
- 至少 **1 個主張頁**（`wiki/claims/` 底下的頁面）
- 這些主張頁裡，至少有 **2 條有出處的證據**。「證據」的定義是：以 `- 【` 開頭、而且有出處的列表行；`目前怎麼看`、`相關但沒有直接測試的研究`、`專家意見` 這三節不算（見 AGENTS.md R6.3）。

**不通過就停下來回報使用者，不准硬湊。** 例如不可以為了湊數，把專家意見當成證據，也不可以臨時去改 wiki。

## G3 證據卡 → `cards/<id>.md`

一張卡一個發現。id 格式是 `c01`、`c02`……，檔名和 id 要一致。

```
---
id: c01
section: S1
wiki_page: wiki/claims/is-smartphone-addiction-real.md
design: 【評論】
abstract_only: false
---

## 發現
<一句白話的發現；如果 abstract_only 是 true，句尾要加「（僅根據摘要）」>

## 出處（從 wiki 照抄）
（[[panova-2018]], p. 252: "..."）
```

規則：
- **出處要從 wiki_page 逐字照抄**，從 `[[` 開始到短引的右引號為止，不可以改任何一個字。
- `design` 照抄 wiki 上的研究設計標籤；設計類型要和來源頁 frontmatter 的 `design` 一致。
- `abstract_only`：引用的來源只要有一篇的 `coverage` 是「僅摘要」，就要填 `true`。
- 「發現」只能寫 wiki 上有的內容，不可以加入新的解讀。

檢查：`python scripts/slides.py g3 <dir>`
- 出處字串確實出現在 wiki_page 裡（照抄）
- 短引能在 raw-text 裡找到（重用 `lint.py` 的 `normalize` 和 `quote_found`）
- 「發現」和 `design` 裡的數字，都能在引用來源的 raw-text 裡找到（重用 `lint.py` 第 11 項的數字比對）
- `design` 和來源頁一致；`abstract_only` 和來源頁的 coverage 一致，而且有「（僅根據摘要）」標註
- `section` 存在於 sources.md，`wiki_page` 有列在 sources.md

## G4 大綱 → `outline.md`，然後**停下來等使用者確認**

```
# 大綱：<標題>

## slide-01｜<頁面標題>
- 段落：S1（封面、結尾等不屬於任何段落的頁面寫「無」）
- 重點：<這一頁要讓觀眾記住的一件事>
- 卡片：c01, c02（不用卡片就寫「無」）
```

檢查：`python scripts/slides.py g4 <dir>`：頁數在 10–15 頁之間、卡片都存在、段落都存在、每張卡片至少被用到一次（沒用到的會列為警告）。

**使用者確認大綱之前，不可以開始 G5。**

## G5 逐頁稿 → `drafts/slide-NN.md`

```
# <頁面標題>
- <一句事實> [c01]
- <一句事實> [c02][c03]
> <引導句：不含事實，例如提問或轉場，可以不標卡片>
```

規則：
- **只能使用大綱和該頁大綱列出的卡片。** 每個事實句（`- ` 開頭）後面都要標 `[card-id]`。
- 引導句（`> ` 開頭）不可以有事實，也不可以有數字。
- 標題最多 20 字；正文最多約 80 字。計算方式：去掉 `[card-id]`、`- `、`> `、`**` 和空白後的字元數。
- 給一般人看：不用術語，或者術語第一次出現時用一句話解釋。相關的發現不可以寫成因果。
- 寫完自己檢查，**最多 2 輪**：執行 `python scripts/slides.py g6 <dir>` 的腳本部分，看有沒有問題，然後修正。

## G6 忠實度檢查

**(a) 腳本**：`python scripts/slides.py g6 <dir>`
- 每個 `[card-id]` 都存在，而且列在大綱該頁的卡片裡
- 每一行的數字，都出現在該行標註的卡片裡（「發現」或 `design`）
- 引導句沒有數字
- 標題和正文沒有超過字數上限
- 每一頁大綱都有對應的稿子，反之亦然

**(b) AI 審查**：開一個**新的 subagent**，只給它 `drafts/` 和 `cards/` 的內容（不給 wiki、不給對話脈絡），請它逐頁檢查：
- 有沒有講錯（和卡片的發現不符）
- 有沒有講過頭（把限定的結果講成普遍的結論、漏掉「僅根據摘要」、把大學生的結果套到青少年身上）
- 有沒有把相關寫成因果

**不通過時，只退回出錯的那一頁**回到 G5 修改，然後重新跑 (a) 和 (b)。**最多 3 輪**；3 輪後還不通過，就停下來回報使用者。

## G7 渲染 → `deck.html`

`python scripts/slides.py render <dir>`：由腳本把 drafts 轉成單一 HTML 檔，**只做排版**，不改任何一個字。
- 方向鍵（← →）、空白鍵、PageUp、PageDown 可以翻頁；右下角顯示頁碼
- `[card-id]` 渲染成灰色小上標；滑鼠移到上面會顯示該卡片的出處；**按 S 鍵**可以切換顯示或隱藏
- 標題用 CSS `text-wrap: balance` 平均換行。換行問題用排版處理，不改字
- 頁碼、操作說明這類介面文字放在 `class="chrome"` 的元素裡，不算稿子內容
- **最後一頁「資料來源」由腳本自動產生**，不由 AI 撰寫：每張卡片一行，格式是「[卡片 id] 作者, 年份, 頁碼」。作者和年份取自 wiki 來源頁 H1 的括號，頁碼取自卡片的出處；僅摘要的來源加上「（僅摘要）」。這一頁不算在 10–15 頁的規格內

檢查：`python scripts/slides.py g7 <dir>`
- 逐頁比對 deck.html 的可見文字（排除 `.chrome`）和 drafts 是否**完全一致**
- 「資料來源」頁和腳本從 cards/ 重新產生的內容是否**完全一致**

不可以手動修改 deck.html。如果要改字，回到 G5 改稿子，再重新渲染。

## G8 渲染檢查

`python scripts/slides.py g8 <dir>`：用本機的 Edge 或 Chrome headless 模式：
1. 開啟 `deck.html?check=1`，由頁面內的腳本檢查每一頁有沒有文字溢出，輸出溢出報告
2. 逐頁截圖，存到 `screenshots/`

如果找不到瀏覽器，或者截圖失敗，就**交給使用者人工檢查**，並在 report.md 註明。

**有溢出就退回 G5 縮短稿子，不可以在 G7 改字或縮小字體來塞進去。**

## 最後：`report.md`

```
# 產出報告：<產出名稱>
## 規格
## 各關卡結果
| 關卡 | 結果 | 退回次數 | 說明 |
## 退回紀錄（每一次退回：哪一頁、在哪個關卡、為什麼、怎麼改）
## 限制與待確認
```

## log

每個關卡完成、每次退回，都要追加到 `wiki/log.md`，類型是 `write`（AGENTS.md R9.3）：

```
## [YYYY-MM-DD] write | slides-intro G6
- 檢查結果：
  - 問題：slide-05 把相關寫成因果｜步驟：G6 (b) AI 審查｜處理：退回 G5，改成「和……有關」
```
