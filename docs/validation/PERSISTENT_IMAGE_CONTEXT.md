> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# 持久多模態對話上下文實作報告

日期：2026-10-26。前端 `http://127.0.0.1:8000`，後端 `http://127.0.0.1:8001`。

## 1. 修改檔案

- 後端：`api.py`、`chatbot.py`、`SKILL.md`、`src/product_search.py`、`src/query_attribute_extractor.py`、`src/search_state.py`。
- 新增：`src/image_reference.py`（驗證）、`src/json_size_limit.py`（請求大小）、`src/image_messages.py`（搬移既有圖片回應文案，供上傳與延續共用）。
- 前端：`app.js`、`state.js`、`search.js`、`index.html`。沒有重設計卡片或輪播。
- 測試：新增 `tests/test_image_context.py`、`frontend/image-context.test.js`；調整 `tests/test_api.py` 的新增可選欄位，以及 `tests/test_chatbot_results.py` 的測試依賴載入。
- 文件／證據：更新 `API.md`、`frontend/README.md`；新增 `scripts/validate_image_context.py`、本報告及 `image_context_*.json`／截圖。

工作目錄還有前次工作的未提交變更；本次沒有修改 FashionCLIP 編碼器、zero-shot 分類器、資料集向量、`.env` 或套件需求。

## 2–3. API 與初始向量

`POST /api/image-search` 保留原 multipart 輸入與文字／商品／closing／分析欄位，成功搜尋額外回 `image_reference`、`active_search`。直接使用本次已計算的向量 `.tolist()`，不為回應再編碼一次。Image-only 不需要 LLM。

新增 `POST /api/image-search/continue`：JSON 包含 `query`、`mode`、`context`、完整 `reference_image` 和最新 `active_search`。同一 GarmentAgent resolver 決定圖片修改／分頁、獨立文字搜尋、問答或拒答。延續回應保留 chat contract，增加可選 `search_type`、`continuation`、`text_overrides`、`image_analysis`；不再次回傳向量。

## 4–6. localStorage 與實際結構

沿用 `garment.conversations.v1`。每個 conversation 只存一份原始 reference，不把向量複製進 messages、request snapshots 或 Full History。

```text
conversation
  id, title, messages, ...
  reference_revision: 本地 UUID（僅供重試防止誤用新圖）
  reference_image:
    version: 1
    model: 目前 CLIP_MODEL
    dimension: 512
    embedding: 完整 512 個數值
    image_analysis:
      colors/patterns/neckline/sleeve/style/buttons:
        label, score, runner_up, runner_up_score, margin
  active_search:
    search_type: image
    text_overrides: {colors: [black], sleeve: [long sleeve]}
    effective_filters: 實際本次使用的合法 filters
    shown_product_ids: [...字串 ID]
    shown_point_ids: [...字串 ID]
```

原分析失敗時仍沿用既有 pure-visual fallback，original analysis 為空。一般文字 active_search 結構維持原本 query／mode／strategy／attributes 欄位。

實測一份原始 reference JSON 為 **12,462 bytes**（UTF-8），若以 UTF-16 字串估算約 25 KB；訊息及商品歷史另佔容量。localStorage 受瀏覽器配額、隱私模式、清除站點資料及同源限制影響，不提供跨裝置同步。保存失敗會顯示警告，當前記憶體搜尋仍可用，但不聲稱已持久保存。

## 7. 後端驗證

Pydantic 驗證陣列恰為 512 個有限數字，拒絕字串、布林、NaN、Infinity、零向量；L2 norm 必須在 0.999–1.001。版本必須為整數 1，dimension 為整數 512，model 必須完全符合目前 CLIP_MODEL。

原分析只允許六種既有屬性與合法標籤，驗證 score／runner-up／margin 的有限值、範圍和差值一致性。覆寫與 filters 限制既有欄位／值，禁止任意 Qdrant filter；明確要求必須仍包含在 effective_filters 中。沿用 product／point ID 驗證與每組 4,096 上限。JSON body 在解析前限制 **2 MiB**。

無效／不相容回 safe 422 與重新上傳提示，過大回 413，檢索錯誤回 502；不回傳原始輸入、例外堆疊或秘密。若同一 model identifier 下的預處理或向量語義改變，需提升 reference version，不能假設字串相同代表所有未來權重相容。

## 8–10. 原始分析重用、累積、更正與移除

`search_by_image_embedding` 使用已有向量和原分析，沿用 `retrieve_hybrid`、Qdrant client、原屬性選擇／放寬和商品格式。延續不呼叫圖片 encoder 或 zero-shot 分析。

同一 planner 新增 `image_refinement`、`image_more_results`。修改仍使用原 QueryAttributeExtractor，僅解析本輪明確要求，增加可選 `remove_overrides`；初始 image+text 的解析 contract 保持相容。

實測累積順序：

```json
{"colors":["black"]}
{"colors":["black"],"sleeve":["long sleeve"]}
{"colors":["white"],"sleeve":["long sleeve"]}
{"sleeve":["long sleeve"]}
```

未提及的欄位不清除；同類別替換；移除顏色要求後恢復原圖顏色繼承，而非禁止某顏色。`more futuristic` 回 unsupported/clarification，不偷偷套用。原始 reference analysis 不被這些修改覆蓋。

## 11–12. 圖片分頁與細化

圖片分頁保存原始向量、text overrides、**同一 effective_filters** 與已展示 ID。直接在既有 Qdrant cosine 排序中排除已展示商品；不重新選 image filters、不因翻頁而自動放寬條件。細化則清除本次 seen IDs，重新走既有 image-derived filter 選擇／放寬；明確文字要求始終 mandatory。

沿用前次排除機制：優先 Qdrant product_id must_not；現有 hosted collection 的整數 payload／keyword index 不相容時，已知 point 在檢索前排除，再以 8、16…最多 4,096 的候選預算排除商品 ID，順序不變。達上限仍不能完成則回錯誤，不宣稱耗盡。空的成功結果才可回 `has_more:false`，不加入重複填充。

## 13–16. 隔離、重啟、版本與舊資料

每個聊天擁有自己的 reference 和 active_search；新聊天為空。成功新圖片上傳替換 reference、清除舊 overrides／seen IDs，歷史商品仍保留。失敗／取消不推進狀態，舊訊息重試不能覆蓋更新話題；如果該重試所用參考已被替換，提示重新上傳，不暗用新圖。

重新整理從 localStorage 恢復；後端新程序從 request 接收／驗證向量，不依賴前一程序。沒有新增後端 reference cache、Redis、資料庫、collection 或永久圖片檔案。舊聊天無 embedding 仍可閱讀，圖片延續需重新上傳；壞 reference 被清除並提示，不杜撰向量。整份存檔無法解析時保留原記錄，顯示本 session 只存於記憶體。

向量屬於圖片衍生的潛在敏感資料，同源 JavaScript 可以讀取。它不是匿名化或安全多用戶儲存方案。正式公開服務仍需 HTTPS、適當認證／限流與 XSS 防護。向量不送給 LLM、不寫 analytics、不放 URL、不記原始向量日誌。

## 17. 自動測試

**168 項全通過：後端 121、前端 47。** 單元測試無付費 LLM 或雲端 Qdrant 呼叫。

新增覆蓋：完整 reference、單次編碼／零次重新編碼、原分析不變、向量／版本／analysis／ID 驗證、2 MiB 限制、相同 reference 結果一致、凍結 filters、累積／更正／移除、多頁 seen、失敗不推進、耗盡、unsupported、不把向量放入 LLM、獨立文字／問答／拒答、重建 backend instance、localStorage 保存／恢復／配額失敗、聊天隔離、新圖替換與舊重試保護。原圖片／混合／文字／輪播回歸也通過。

## 18. 真實驗證

真實 API 腳本完成 **14 次**請求，所有斷言通過，使用現有 LLM、FashionCLIP、Qdrant。見 API 結果 (historical artifact omitted)。此檔只保留商品 ID、分析和搜尋狀態，不保留 raw vector。

瀏覽器逐項實測紀錄見 瀏覽器結果 (historical artifact omitted)。A–G 已完成：

- A：646 白色圖 → black → long sleeve → white again；原圖只上傳一次。
- B：34 紫色圖初始與兩次 more，三批共 24 個不重複商品。
- C：細化後再分頁不重複；再次細化可重用相關商品。
- D：重新整理後 white again 成功，長袖保留。
- E：實際終止後端程序 68778，再啟動新程序；原聊天未上傳圖片便成功移除顏色要求。
- F：聊天 A 的 646 圖黑色長袖結果與聊天 B 的 34 圖長袖結果不同，切換均恢復各自條件。
- G：在 B 上傳新 646 圖＋black，清掉舊長袖；再 long sleeve 使用新 646 圖並保留 black。

H 已完成：圖片單獨搜尋、初始 image+black、跨輪修改、fashion Q&A、領域拒答、獨立 Japanese streetwear 文字搜尋及文字 more 均通過。文字首批為 `19,635,18,374,378,138,712,91`，下一批 `11,673,1611,542,764,440,649,229`，無重複。輪播已多次切換；詳情面板實際顯示 Black／Long sleeve。歷史恢復後重讀 DOM，共保存 19 筆結果；自動比對四組分頁交集為空、聊天 A 回復結果一致、新圖替換結果符合獨立新圖搜尋。

實際瀏覽器截圖 (historical artifact omitted)；更換過程沒有刪除既有聊天。原始瀏覽器 E2E 發生於本次工作；中途工具重新連接後，部分證據從恢復的商品卡 DOM 重讀，未從 LLM 回應文字重建 ID。

可重跑離線測試（後端目錄）：

```sh
PYTHONPATH=.:tests .venv/bin/python -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context
```

前端目錄：`node --test *.test.js`。真實 API 驗證為 `python scripts/validate_image_context.py`，會使用既有外部服務，不屬於離線測試。另已通過 Python／JavaScript 語法檢查與 `git diff --check`。

## 19–20. 實際商品例子

白色 646 圖原始首批與前一版 image v2 相同：`646,411,516,816,175,631,745,941`。

| 搜尋 | 第一頁 | 下一頁 |
|---|---|---|
| 646 原圖（API） | 646,411,516,816,175,631,745,941 | 95,1503,502,688,46,748,496,315 |
| 34 原圖（瀏覽器） | 34,301,334,136,44,515,113,669 | 149,418,7,484,384,483,76,93 |
| 646＋黑色長袖（瀏覽器） | 388,689,94,728,1850,347,926,393 | 252,296,198,767,1535,462,195,1679 |

黑色首批 `679,447,773,569,620,187,313,890`；加入長袖後得到上表第三行首批。改回白色長袖得到 `95,748,209,477,147,685,1338,1133`。移除顏色明確要求後可能仍看到這些白色商品，因為原圖顏色可被繼承，這不表示 black 仍在生效。

## 21. 限制

只保留一個 active reference／聊天，沒有跨裝置同步或舊圖庫；被替換的圖片若要再次使用需重傳。存儲被清除、配額失敗、schema/model 不相容時也需重傳。原始照片／base64 不永久保存，歷史縮圖可能顯示 Preview not retained，商品圖照常可開啟。自然語言分類仍依賴既有 LLM，測試通過不代表所有模糊句子都必然正確。原有 image guess heuristic 和文字不支援的語義限制維持不變。

## 明確回答 Q1–Q11

1. **Yes**：reference 在 localStorage，不是後端 reference cache。
2. **Yes**：同一圖片可跨輪修改，不需重傳。
3. **Yes**：每次成功上傳流程只編碼一次，延續不重新編碼。
4. **Yes**：圖片 more 返回未展示商品，真實多頁已驗證。
5. **Yes**：明確修改累積，支援替換與移除。
6. **Yes**：重新整理後可繼續。
7. **Yes**：後端重啟後可繼續，前提為 localStorage 可用且 model/version 相容。
8. **No**：沒有新資料庫、Redis 或 collection。
9. **No**：沒有永久保存原始圖片或 base64。
10. **No**：沒有改 FashionCLIP、dataset embeddings、Qdrant ranking 或既有文字檢索規則；新增的是圖片上下文保存、路由與延續。提示新增了圖片關係及明確移除解析。
11. **Yes**：真實 browser → saved reference → 新 backend process → Qdrant 已測試。
