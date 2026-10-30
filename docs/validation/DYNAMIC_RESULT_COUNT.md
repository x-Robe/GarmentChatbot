> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# Dynamic Result Count 實作與驗證報告

驗證日期：2026-10-27（香港時間）。前端 `127.0.0.1:8000`，後端 `127.0.0.1:8001`。

1. **本次檔案範圍**
   - 新增 `src/result_count.py`、`tests/test_result_count.py`、`scripts/validate_result_count.py`。
   - 修改 `chatbot.py`、`api.py`、`src/query_attribute_extractor.py`、`src/product_search.py`、`SKILL.md`、`API.md`、`tests/test_chatbot_results.py`、`tests/test_api.py`。
   - 前端修改 `app.js`、`search.js`、`index.html`、`products.test.js`、`image-search.test.js`。沒有改 carousel 的渲染演算法。
   - 新增本目錄的 `dynamic_count_*` 測試證據。本次沒有修改 `.env`、FashionCLIP、zero-shot 分類器或資料集。

2. **數量抽取位置**：文字及圖片延續在既有 `plan_request` 同一次呼叫抽取。首次圖片加文字在既有 `extract_image_overrides` 呼叫抽取。不增加模型、agent 或額外分類呼叫；純圖片沒有新增 LLM 呼叫。

3. **結構化 schema**：`plan_request` 保留 `intent`、`relation_to_context`、`resolved_query`、`search_strategy`，加入必填但可為 null 的 `result_count: integer | null`。圖片 override schema 同樣新增此欄。API 回應保留原欄位，新增可選的 `requested_count`、`effective_count`、`count_capped`；`effective_count` 是上限，不是實際件數，實際件數是 `products.length`。

4. **集中設定**：`src/result_count.py` 分別定義最少 1、預設 8、最多 8。文字／圖片入口與圖片搜尋驗證共用設定。前端不再額外硬編 multipart limit=8，而讓 API 使用預設值。

5. **搜尋語意與數量分離**：同一 resolver 產生去除結果數量措辭的 standalone query。後端在明確數量請求使用該 query；一般獨立請求仍保留既有避免舊 context 汙染的處理。印花 7、尺寸 10、年份 2025、3/4 袖長、價格 20 不會自動變成數量，也不新增對應 filters。

6. **Exact／Similar／Auto／Both**：將有效 N 傳給原搜尋工具，每分支最多取得 N 個候選，最後合併最多 N 件。Exact-first 去重、原排名和 Similar 85% 相對尾部規則保留。Both 保留最多兩個 distinct Similar slots；小批次有 Exact 時至少保留一個 Exact。沒有 N+N 的最終展示，沒有重排或補造產品。

7. **分頁**：沿用 active search 的 query、mode、strategy、attributes 和現有 Qdrant 排除／adaptive retrieval。只將最終展示的產品加入 shown IDs。數量不寫入 active search；「more」未指定數字時回到 8。前端只保存 message-level 診斷資訊。

8. **圖片**：既有 multipart limit 保留；自然語言明確數量優先，沒有明確數量則使用 multipart limit。首次圖片仍只 encode 一次，保留 black 等顯式 overrides 和既有 image cosine 排名。延續沿用保存的原 embedding、effective filters 和 shown IDs；不重新 encode。encode-once／向量與 filters 重用由單元測試檢查，真實瀏覽器另外驗證了產品與跨頁去重。

9. **超上限**：12 或一百萬會限制至 8，文字明確告知最多 8，`count_capped=true`。不因此宣稱 `has_more=true`。

10. **無效／模糊數量**：zero、負數回傳澄清且不檢索，`effective_count=null`。字串、浮點數、布林等 malformed resolver 值在後端拒絕，沿用安全 JSON 錯誤處理；不將 exception 內容暴露前端。some／a few／沒有數量使用預設。圖片不支援的修改不檢索，保留 requested_count，但沒有 execution budget。

11. **Carousel**：仍每頁四件；尾頁直接顯示剩下的真實產品，沒有空白卡。測試涵蓋 1、2、3、4、5、7、8，及詳情、導航邊界和歷史保存；真實畫面驗證了 5 件的 4+1 尾頁。

12. **相容性**：舊 `/api/chat`、圖片上傳及 continuation request body 不必更改。原有 text／response_id／products 等欄位保留，CLI 使用 result['text'] 不變。localStorage key 和 active-search schema 不變，不需要遷移。沒有新增永久數量偏好。

13. **自動化測試**：後端 **138 通過**，前端 **48 通過**，共 **186 通過、0 失敗**。後端數量測試包含多語言 resolver-output fixtures、每個 1–8 的 mode/strategy 組合、去重、少量／耗盡、無效值、上限、狀態重設、圖片與傳輸；語言 fixtures 不是實際 LLM 能力的替代證據。原 Full History、分頁、圖片搜尋測試也通過。見 `dynamic_count_unit_tests.txt`、`dynamic_count_frontend_tests.txt`。

14. **真實驗證證據**：`dynamic_count_api.json` 的 16 個真實 LLM/Qdrant HTTP 案例全部通過；`dynamic_count_cantonese.json` 的 3 個真實跨頁案例也通過。`dynamic_count_browser.json` 有 18 個 UI 檢查記錄，其中 1 個保留修正前圖片錯誤澄清，另 17 個是成功檢查（包括 refresh 還原）。A–F 及 G 的文字、圖片、手動模式、Auto、完整歷史引用、refinement、去重、domain guardrail、carousel、details、localStorage 還原已實際操作。畫面：`dynamic_count_cap.jpg`、`dynamic_count_image.jpg`。

15. **要求數量與實際結果**

| 真實案例 | 有效上限 | 實際回傳 |
|---|---:|---:|
| 7 black T-shirts | 7 | 7 |
| 3 more → 5 more | 3 → 5 | 3 → 5，與首批共 15 個不同 IDs |
| 未指定數量 more | 8 | 8 |
| 3 black → white（無數量） | 3 → 8 | 3 → 8 |
| 印有數字 7 | 8（requested=null） | 8，保留印花數字語意 |
| 12 shirts | 8 | 8，有上限提示 |
| 圖片 + 5 similar black | 5 | 5 |
| 圖片 3 more → refresh → more | 3 → 8 | 3 → 8，連首批共 16 個不同 IDs |
| 手動 Exact one red | 1 | 1 |
| 手動 Similar two Japanese streetwear | 2 | 2 |
| Auto/Both 3 black + Japanese inspiration | 3 | 3（2 Exact + 1 Similar） |
| 有冇兩件其他款 → 再給我五件 | 2 → 5 | 2 → 5，跨頁無重複 |
| 引用多輪以前的黑色款、改成長袖（無數量） | 8 | 8，resolved_query=long sleeve black T-shirts |
| 純圖片 | 8 | 8 |
| zero／minus five | 無檢索 | 0／0 |
| one million designs | 8 | 8，有上限提示 |

16. **限制與實測修正**：第一次圖片「5 similar black shirts」雖抽出 5 和 black，仍產生澄清。已在同一圖片解析提示明確區分 quantity-only 與 quantity+modification；重跑後為 modify/black/5，並完成後續分頁。曾遇到外部模型站點等待；目前開發程序使用已快取的相同模型（僅啟動環境的 HF offline flags），LLM 和 Qdrant 仍是真實線上服務，未修改專案 `.env`。自然語言解析仍有模型不確定性；未提供任意語句百分之百正確的保證。結果表示「最多 N 件」，現有 filters／相似度規則可能留下少於 N 件。印花數字仍是向量語意，沒有新增精確數字 filter，也不保證產品印花實際為 7。

## 明確答覆

| 問題 | 答覆 |
|---|---|
| Q1 要求七件，不超過七件？ | 是，瀏覽器實際 7 件。 |
| Q2「3 more」最多三個未見產品？ | 是，文字與圖片均實測 3 件且沒有跨頁重複。 |
| Q3 無數量 more 使用預設八件？ | 是，文字和圖片均實測 8。 |
| Q4 數量不成為永久偏好？ | 是，新主題、refinement、無數量分頁均回預設。 |
| Q5 區分 7 designs 與 printed 7？ | 是，實際 LLM 案例分別為 7 與 null；printed 7 保留語意。 |
| Q6 各 mode／Both／圖片相容？ | 是，單元測試及真實 API／瀏覽器驗證如上。 |
| Q7 FashionCLIP／Qdrant 排名保留？ | 是，沒有修改 embedding、scoring、collection、ranking、filter policy 或相對尾部規則。 |
| Q8 自動化與真實瀏覽器均有成功執行？ | 是，186 自動化測試、19 真實 HTTP 案例；瀏覽器最終驗證成功，修正前失敗記錄亦有保留。 |

變更了數量 schema、相關理解提示、limit 傳遞及展示上限；沒有新增搜尋演算法、filters 或數量記憶。

## 重跑

在 backend 目錄：

```sh
PYTHONPATH=.:tests .venv/bin/python -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count
uvicorn api:app --host 127.0.0.1 --port 8001
# 需真實 API，可能產生 LLM 費用；非單元測試
.venv/bin/python scripts/validate_result_count.py --run-live
```

前端目錄：`node --test *.test.js`。瀏覽器證據由實際 UI 操作取得，HTTP 腳本不冒充瀏覽器測試。
