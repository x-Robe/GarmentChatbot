> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# 完整文字上下文與不重複搜尋結果：實作／驗證報告

驗證日期：2026-10-23。前端 `http://127.0.0.1:8000`，後端 `http://127.0.0.1:8001`。

## 實作說明（對應需求 1–21）

1. **檔案**：後端修改 `chatbot.py`、`api.py`、`SKILL.md`、`src/product_search.py`、`src/conversation_context.py`；新增 `src/search_state.py`。前端修改 `app.js`、`config.js`、`context.js`、`state.js`、`search.js`、`products.js`、`index.html`。測試修改 `tests/test_api.py`、`tests/test_chatbot_results.py`、前端 `context.test.js`／`image-search.test.js`，新增兩端 `test_pagination.py`／`pagination.test.js`。新增實測腳本 `scripts/validate_pagination.py`，更新 `API.md`／前端 `README.md`，保存本目錄驗證資料。這是本次範圍，不代表工作目錄其他既有變更由本次產生。
2. **完整文字歷史**：從目前聊天的先前 user/assistant 訊息建立 `{role,text}`；合併 assistant closing，略過失敗、待處理和中斷回合。目前輸入只送一次。圖片回合只保留文字標記和文字修改要求，不含原始圖片、檔名、產品物件或向量。
3. **限制與溢出**：預設 200 則、共 60,000 字元、每則 10,000 字元。前端 `CONTEXT_LIMITS` 可調；後端 `.env` 的 `MAX_CONTEXT_MESSAGES`／`MAX_CONTEXT_CHARS` 可調。後端硬上限 1,000 則輸入、每則 10,000 字元。超出正常上下文預算時，確定性保留最新文字；不呼叫 LLM 摘要。格式／硬上限違規回 422。
4. **分類方式**：沿用原有 `plan_request` LLM，增加結構化關係欄位；沒有新增分類模型或額外解析呼叫。歷史作為非特權資料送入；已展示 ID 和實際屬性不交給 LLM 重建。
5. **關係種類**：`new_topic`、`refinement`、`more_results`、`continuation`、`fashion_information`、`out_of_domain`、`clarification`。
6. **狀態結構**：文字搜尋保存 `search_type`、`resolved_query`、`mode`、`search_strategy`、實際 `attributes`、`shown_product_ids`、`shown_point_ids`。商品 ID 正規化為字串；point ID 必須為合法整數或 UUID。屬性限制於現有 schema，禁止額外欄位和任意資料庫 filter；每組 ID 最多 4,096 個。圖片只保存 image 標記。
7. **儲存位置**：既有 localStorage 聊天資料；API 每次接收可選 `active_search` 並回傳更新副本。後端沒有新增對話記憶或資料庫。儲存的 request 不再重複複製完整 context；重試由該訊息之前的歷史重建。
8. **聊天隔離**：狀態屬於單一 conversation；新聊天為 null、切換／重新整理恢復該聊天自己的狀態。
9. **已展示 ID**：只有最後 `products` 清單進入 seen 集合，未展示的 raw candidates 不計入。成功回應才在前端套用；失敗、取消不推進，舊訊息重試也不能覆蓋更新的 active search。檢索任一分支失敗現在整次回 502，避免部分成功被誤認為完成／耗盡；這是刻意的錯誤處理調整。
10. **Qdrant 排除**：保留原正向 filter，增加 product ID `must_not`（同時支援整數／字串）及已知 point ID `HasIdCondition`。一商品多個 points 時仍以 product ID 排除所有表示。
11. **排除階段與實測限制**：可用的 collection 會在向量檢索前排除。現有雲端 collection 的 product ID payload 是整數，但索引是 keyword；整數排除遭 400 index 錯誤。只對這個明確錯誤啟用 fallback，不改 collection：已知 points 在檢索前排除，商品 ID 在取回後排除；候選預算按 8、16、32…擴大，最多 4,096，維持原順序。達預算仍不能判定時報錯，不宣稱耗盡；其他 API 錯誤直接傳為安全失敗。
12. **模式**：more_results 使用 active search 原有 query、已抽取屬性、manual mode 和 Auto strategy；不重新抽取、不依「more」重新選模式。Both 兩支都排除 seen，沿用 Exact 優先、去重、最多 8 個及原有 Similar 顯示規則。
13. **細化與分頁**：refinement／一般搜尋建立新 seen 集合，允許舊商品重新出現；more_results 才累積排除。new_topic 使用當前獨立輸入，避免模型把舊搜尋條件混入。
14. **耗盡**：僅在所需檢索分支成功且實際候選皆空時回 `has_more:false`（Exact 要有有效條件）。不足 8 個就回實際數量。非空候選被既有顯示規則篩掉時，不擅稱整個資料集耗盡；不確定時 `has_more:null`，不是 true。
15. **舊資料**：無狀態聊天正常恢復，不杜撰歷史條件／ID；缺少可靠文字搜尋狀態的 more 請求先澄清。舊的成功圖片回合可恢復 image 標記，避免錯誤轉成文字搜尋。
16. **API 相容**：保留原 `text`、`response_id`、`products`、`search_results`、`closing_text`、`intent`、`search_strategy`、`resolved_query`；增加可選 `relation_to_context`、`active_search`、`has_more`。舊請求不必帶狀態。CLI 原入口和 `result['text']` 可用；CLI 沒有新增自動持久化分頁狀態。
17. **自動化結果**：148 項全數通過：後端 105（agent 21、API 32、pagination 15、image+text 12、hybrid 12、image 8、extractor robustness 5），前端 43。單元測試不使用付費 LLM 或雲端 Qdrant；排除測試包含記憶體 Qdrant。`git diff --check` 通過。
18. **真實 E2E**：見下表；真實 API 額外完成 17 次請求，包含八種英／中／粵語 more 表達、manual Exact／Similar、Auto Both、缺失狀態／圖片狀態澄清。證據：API JSON (historical artifact omitted)、瀏覽器 DOM 紀錄 (historical artifact omitted)、圖片回歸截圖 (historical artifact omitted)、耗盡截圖 (historical artifact omitted)。
19. **實際第一頁與第二頁 ID**：第一頁 `14,271,313,116,10,1872,440,42`；第二頁 `437,1651,1336,1864,1029,501,393,385`，交集為空。第三頁 `587,1946,84,1756,347,273,1008,1886`；第四頁 `814,1703,1749,788,1149,462,1330,159`，四頁全無重複。ID 來自 API／恢復後商品卡 DOM，不由 LLM 文字推測。
20. **細化範例**：Japanese streetwear → make them darker，resolved query 為 darker Japanese streetwear t-shirts；18、635、19 等舊商品可再次出現。之後 more 的八個 ID `494,374,829,620,712,673,336,262` 與細化首批無重複。
21. **圖片後續限制**：原圖片／embedding 未持久保留，image → more 會要求重新上傳，不假裝繼續圖片向量搜尋。圖片單獨搜尋及圖片＋文字修改均保留。既有圖片網址已可在瀏覽器顯示，這次沒有改圖片託管。

## 真實瀏覽器驗證

| 案例 | 實際結果 |
|---|---|
| A 分頁 | black oversized 連續三頁各 8，無重複；切換回來第四頁也無重複。初次遇到 index 錯誤後修正並成功重試，狀態未提前推進。 |
| B 細化 | Japanese → darker 保留風格並更新深色條件；細化可重用商品，後續 more 排除細化首頁。 |
| C 新主題 | white minimalist 建立新搜尋，沒有帶入 Japanese／darker；應用層另有 new_topic 忽略 stale rewrite 測試。 |
| D 遠距參照 | 超過三輪、期間插入白色搜尋及服裝問答後，回到「第一個風格，改藍色」，解析為 blue Japanese streetwear。 |
| E 耗盡 | purple striped 實際只有 6 個：34,148,44,149,825,636；下一次 0，清楚告知已看完。API black oversized 另實測 8×6、1、0、0，共 49 個不重複商品。 |
| F 重新整理 | 原聊天 reload 後 more 正確取第三批；歷史商品與輪播恢復。 |
| G 隔離 | 新聊天 black oversized 返回原首批，不繼承舊聊天排除；切回原聊天用粵語 more 得第四批。 |
| H 回歸 | 文字搜尋、mock neck 問答、政治問題拒答、image-only、image+make it black、四張輪播、詳情、歷史恢復均通過。圖片後 more 清楚要求重傳。 |

Image-only 實際 ID：646,411,516,816,175,631,745,941。
Image + make it black：679,447,773,569,620,187,313,890；詳情顯示實際 Black / Navy blue 等屬性。

## Q1–Q8

- Q1：**Yes**。一般大小聊天使用完整文字歷史；有文件化安全上限。
- Q2：**Yes**。more 取同一 active search 的未展示商品。
- Q3：**Yes**。真實案例多次取得不同商品直到耗盡；極大型搜尋仍受 4,096 候選／ID 安全上限保護。
- Q4：**Yes**。make them darker 是 fresh refinement，可重用相關商品。
- Q5：**Yes**。每個聊天獨立保存狀態。
- Q6：**Yes**。重新整理後可繼續分頁。
- Q7：**No**。沒有改 FashionCLIP、Qdrant 向量排序、資料集 embeddings 或既有圖片搜尋流程；修改的是文字上下文、關係提示、狀態與排除已展示結果。
- Q8：**Yes**。已用真實瀏覽器、LLM、FashionCLIP 與 Qdrant 驗證。

LLM 的語意分類不是對所有自然語言的數學保證；上述結論基於已記錄案例及單元測試。不加入新的模型、資料庫、向量記憶或自動摘要。
