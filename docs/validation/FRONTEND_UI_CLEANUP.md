> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# Frontend UI Cleanup

完成日期：2026-10-30（香港）。範圍僅前端顯示、歷史文字序列化與附件入口；無新增依賴。

## 修改檔案

前端根目錄為本儲存庫外的 `../frontend/`。

- `app.js`：圖片訊息直接儲存原始 query；渲染使用顯示正規化函數；移除 PDF handler；非圖片歷史附件使用通用 FILE 標記；更新模組版本以避免瀏覽器快取舊依賴。
- `presentation.js`：加入純函數 `userDisplayText(entry, request)`。
- `context.js`：使用相同函數取得真正使用者文字，保留獨立 `Reference image search` 路由標記。
- `index.html`：移除 Add PDF、PDF 說明、`.pdf` accept；保留 Add image、10 MiB 與 JPEG/PNG/WebP 指引。
- `state.js`、`search.js`：附件驗證只接受既有三種圖片格式，錯誤訊息不再宣傳 PDF。
- `presentation.test.js`、`state.test.js`、`image-search.test.js`、`voice-app.test.js`：新增或更新針對性測試。
- 本報告、兩份測試紀錄及 `frontend_ui_cleanup.png` 為驗證產物。

## 原因與處理

原本 `submitMessage` 把 `Image search: filename — query` 存入 user.text，渲染直接展示，因此混入技術標籤。現在 text 只存 query，附件資料與 `search_type: image` 保持獨立。純圖片只展示附件卡；圖文展示附件及原始文字；普通文字不變。HTTP 上傳仍使用原始 File、原始 query 和選取 mode。

舊訊息僅在 user/image 類型、附件 ID／名稱／圖片 MIME 與原上傳 request 全部吻合，而且 text 完整等於已知合成格式時，才以 request.query 取代顯示。沒有廣泛正則刪除檔名；新訊息即使使用者自己輸入相似前綴，也不會被誤刪。此函數不修改歷史；產品、附件、參考 embedding 原樣保留。Full History 同樣使用已核對的文字，圖片路由標記不含檔名。

無足夠原始 request/附件證據的異常舊資料不會猜測或刪除，可能仍保留原標籤。這是避免破壞真正使用者文字的保守限制。

## 驗證結果

### 自動測試

- 前端：**103 / 103 通過**，包含真實 app.js 的模擬 DOM/event 測試；無付費呼叫。
- 後端回歸：**156 / 156 通過**；這些單元測試使用 mocks，不代表真實 LLM/Qdrant 執行。
- 前端測試涵蓋新／舊圖文、純圖片無 bubble、保留真正使用者前綴、Full History、附件驗證、原始 File/query/mode 傳送、刷新後參考、產品 UI 與語音事件。
- 19 個後端 Python／SKILL／voice.js 原始檔 SHA-256 比對均未變更。

命令（從外層專案目錄）：

```sh
<local-path-omitted> --test frontend/*.test.js
cd GarmentChatbot
PYTHONPATH=.:tests .venv/bin/python -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count test_unified_modes
```

紀錄：前端 (historical artifact omitted)、後端 (historical artifact omitted)。

### 實際瀏覽器（8000 → 8001，非 mock）

使用目錄圖片 `data/images/tshirt/941.jpg`，未覆寫或刪除現有 localStorage。

| 情境 | 操作及實際結果 |
|---|---|
| 舊歷史 | 重載上一輪已知測試對話：原 `Image search: 941.jpg` bubble 消失；附件、原產品與後續對話保留。混合式舊前綴另以單元測試驗證。 |
| 純圖片 | Auto，上傳無文字；只有附件卡，沒有文字 bubble；真實 API 返回 8 件產品。 |
| 圖文 | Exact，上傳並輸入 `get me some short-sleeves version`；bubble 完全等於此句，檔名僅在卡片；返回 8 件產品。 |
| 刷新 | 圖片卡、原始文字、產品恢復；顯示 Preview not retained，無新增圖片持久化。 |
| 延續／更多 | 刷新後在 Similar UI 下送出 `show me 3 more`，成功返回 3 件 Exact：符合既有「更多沿用前次策略」設計。原始圖片 File 已不在記憶體，使用既有儲存參考。 |
| Similar 細化 | `make it black and show me 2 designs` 返回 2 件 Similar 黑色產品。 |
| 普通文字 | 新對話 Auto，`show me 2 black t-shirts` 原樣顯示，返回 2 件產品。 |
| 產品操作 | 實際點擊輪播 Next，顯示 5–8 of 8；點擊產品 5 展開 Color/Style/Pattern/Neckline/Sleeve 等詳細資料，成功關閉。 |
| 選單 | 實際打開僅有 Add image，JPEG/PNG/WebP、10 MiB 指引正確，沒有 PDF 項目或說明。 |
| 語音控制 | Voice Mode 實際切換 On/Off；麥克風可用，請求期間停用。沒有實際錄製麥克風或聽取合成音訊；辨識及自動播音流程以既有模擬事件回歸驗證。 |

後端伺服器紀錄確認兩次 `/api/image-search`、兩次 `/api/image-search/continue` 回傳 HTTP 200；普通文字亦成功返回產品。未以 mock 結果冒充瀏覽器驗證。

[Historical screenshot omitted from release.]

## 保留與限制

- 後端 API／FashionCLIP／Qdrant／排名／filter／attribute extraction／LLM prompts／模式策略／語音程式均未修改。
- 上傳大小、空檔及 MIME／副檔名一致性檢查保留；PDF 現在也在前端選檔驗證階段拒絕，後端安全驗證未變。因此「驗證完全沒變」並不精確：僅前端可接受格式縮限至原本真正支援的圖片。
- 不儲存原圖或 base64；刷新後無縮圖是既有設計，附件卡和參考 embedding 仍可恢復。
- 未部署、未新增 PDF 功能、未重新匯入 Qdrant 資料。
