# GarmentChatbot 生產 Hosting 指南

狀態日期：2026-11-07。這是部署準備，尚未建立／修改雲端服務、公開網站、push 或操作 Qdrant 資料。所有命令由 repository root 執行，除非另有註明。現有介面、LLM prompts、ranking、embeddings 和資料集保持原樣。

## 1. 先處理安全與授權

1. Owner 在 LLM provider、Qdrant Cloud／原 Qdrant 管理介面、Hugging Face token settings 撤銷歷史 key，建立最小權限的新 key。Qdrant 如支援 scoped read-only key，限定現有 collection。檢查使用紀錄、費用及異常存取；不要在 chat、commit、截圖或 logs 貼出 key。
2. 本次已 `git rm --cached backend/.env`，本機檔案仍保留，僅供 owner 私下處理，不應再使用其中可能洩露的 key。`.gitignore` 現在忽略所有層級 `.env`、`.env.*`，只容許 template。
3. 刪除當前檔案不能消除 Git history、fork、clone、cache 或下載副本。history scan 找到舊 `.env`、`backend/.env`、`Credentials/qdrant` 中的 provider、HF 或 Qdrant token。先撤銷 key；之後由 owner 決定是否使用 history rewrite、聯絡 GitHub 清理 cache，並協調其他 clone。這次不 rewrite history。
4. Owner 確認圖片／模型 hosting 權利，以及公開與付費服務預算。沒有這些批准，不執行下方 deploy。

## 2. 本機環境與測試

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-api-test.txt
cp .env.example backend/.env
```

最後一行僅適用沒有現有 private config 的新環境；不要覆蓋已存在的 backend/.env。填入新授權值。Production 使用 Render Environment，不上傳 `.env`。目前 requirements 未 pin；成功安裝一次不保證未來 resolver 或 Linux wheel 相同。Linux CI 通過及 Render build 後應記錄實際版本，經測試再建立 lock，不直接套用歷史版本表。

```sh
node --test frontend/*.test.js
cd backend
PYTHON_DOTENV_DISABLED=1 CLIP_MODEL=patrickjohncyh/fashion-clip API_REQUESTS_PER_MINUTE=10000 PYTHONPATH=.:tests python -B -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count test_unified_modes test_repository_layout test_hosting
cd ..
```

這些是 offline regression tests；models／LLM 是 mocks、部分 Qdrant 是 in-memory，不能證明 production 可用。測試提高 request limit 以免整個 suite 共用 app 時觸發限流；production 預設不變。

## 3. Environment variables

| Variable | 用途 | 必須／可選 | 設定位置 | Secret |
|---|---|---|---|---|
| PYTHON_VERSION | Render Python 3.12.14 | Render 必須 | render.yaml／Render Environment | 否 |
| PORT | Render 分配 listen port | Render 自動提供 | Render | 否 |
| POE_API | 相容 provider key | provider 模式必須 | Render Environment；本機 backend/.env | 是 |
| POE_URL | 相容 provider base URL | provider 模式必須 | 同上 | 通常否，不可含 credentials |
| OPENAI_API_KEY | SDK 標準 key fallback | 標準模式必須，與上述二者二擇一 | 同上 | 是 |
| OPENAI_MODEL | provider 支援的實際 model ID | 必須 | 同上 | 否 |
| QDRANT_URL | 既有 Qdrant HTTPS endpoint | 必須 | 同上 | 通常否 |
| QDRANT_API | 現有 collection 授權 key | authenticated server 必須 | 同上 | 是 |
| QDRANT_COLLECTION | 已填入的 collection name | 必須 | 同上 | 否 |
| CLIP_MODEL | 必須與 ingestion 相同的 model ID | 必須 | 同上 | 否 |
| HF_HOME | Hugging Face cache 路徑 | 建議 | Render Environment | 否 |
| HF_TOKEN | 模型下載授權 | 需要授權時才設定 | Render Environment | 是 |
| HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE | 禁止模型網路下載 | 可選，完整 cache 後才啟用 | Render Environment／offline tests | 否 |
| CORS_ORIGINS | 逗號分隔允許 frontend origins | production 必須 | Render Environment | 否 |
| MAX_CONTEXT_MESSAGES | 最近 context message 上限 | 可選，200 | Render Environment | 否 |
| MAX_CONTEXT_CHARS | context 字元預算 | 可選，60000 | Render Environment | 否 |
| API_REQUESTS_PER_MINUTE | 單 process 全站 POST admission 上限 | 可選，30 | Render Environment | 否 |
| API_MAX_INFLIGHT | 單 process 最大同時 POST（包含排隊） | 可選，2 | Render Environment | 否 |
| PRODUCT_FILE / BATCH_SIZE | offline ingestion inputs | hosting 不使用 | 只在另行批准的 ingestion 環境 | 否 |

標準 API 模式必須「移除／unset」POE_API 和 POE_URL；空字串不等同 unset。Blueprint 預備的是相容 provider 模式，改用標準模式前先改 blueprint 的 secret 欄位。HF_TOKEN 不需要時不設定。所有 private key 都只能留在 backend／secret store。Frontend `API_BASE_URL` 是公開常數，並非環境注入。

## 4. Qdrant 與 models：唯讀驗證

先由 collection owner 提供新授權 endpoint/key、collection、ingestion model ID／revision。不能單靠 dimension 相同證明 model 語意相容。

1. 要求現有 populated collection，historical model 是 `patrickjohncyh/fashion-clip`、unnamed vector、512 dimensions、Cosine。不要 create_collection、upsert、delete 或執行 `ingest_product.py`。
2. 檢查 metadata：product_id、image_url、colors、patterns、neckline、sleeve、style、buttons、category；比較 backend schema。product_id 歷史 integer／keyword index 不一致，既有 paging 有 fallback，不在此改 index。
3. Qdrant 僅存向量與 payload，JPEG 留在 root `data/images/tshirt/`。全部 1,993 張應保持 hash；原始 records 357–363 已知缺圖，不補造或刪資料。隨機 sample 通過不代表全部 remote payload 都正確。
4. 在安全 shell 注入「新」environment variables。不要把 key 放 command arguments 或 history。以下 script 不讀取 backend/.env，也不寫 database：

```sh
python scripts/verify_integrations.py
# Owner 同意模型下載後：
python scripts/verify_integrations.py --models
# Owner 同意一次可能付費的 provider request 後：
python scripts/verify_integrations.py --llm
```

`--models` 驗證 text/image 512 維 output 和 MiniLM inference；不重建 embeddings。`--llm` 只驗證最小 Responses request，不能代替實際 structured tools／JSON schema／多輪流程測試。Script 不列印 payload、provider response 或 SDK exception 內容。若失敗，在 private 環境檢查設定、權限、網路和 model identity，不直接重建 collection。

## 5. Render backend

### 容量選擇

Free 與最小 paid 512 MB 不宜用於本專案：FashionCLIP 歷史 cache 約 581 MiB，再加 Torch、imports、inference allocations，512 MB 沒有可信餘裕；這是容量推估，尚無本次 Linux 峰值量測。Free 另有 idle spin-down、ephemeral filesystem，影響 live demo cold start。

建議最低「候選」為 Standard／`1c-2g`，1 CPU、2 GB，官方目前列價約 US$25/month；不是已證明足夠的最低方案。需 owner 同意費用後才建立；warm-up 和最大上傳測試若 OOM，停止服務評估 4 GB，不能自動升級。既有 cache 共約 668 MiB，加 catalog 約 361 MiB、Python packages 與下載暫存，build/runtime disk 應留數 GiB 餘裕。單 worker 避免 model memory 複製。記錄 Render logs 中 process／container memory，目標峰值保留至少 25% headroom，並量測 cold/warm latency。

### 建立服務（需要 owner 批准公開與付費）

1. Owner review 本 clone 的 code/config 和 secret deletion；由授權者 push 經批准的 deployment branch，禁止 force push/shared-branch 直接覆蓋。當前沒有 push。
2. Render 連接此 GitHub repo。使用 `render.yaml` Blueprint，先核對費用、branch、region，才按建立。Blueprint 未固定 branch，必須明確選擇已批准的穩定 branch。
3. Root Directory 留空（repository root）。不要設 backend，否則 root catalog 無法使用。
4. Python `3.12.14`；Build Command `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu && python -m pip install -r backend/requirements.txt`。先安裝官方 CPU wheel，再由既有 requirements 補齊，避免 Linux CPU host 額外安裝 CUDA runtime；此 Linux build 仍待 CI／Render 驗證。
5. Start Command：

```sh
cd backend && uvicorn api:app --host 0.0.0.0 --port "$PORT" --workers 1 --limit-concurrency 16 --timeout-keep-alive 5
```

6. Health Check Path `/api/health`。設定 Environment table 中必須值，`CORS_ORIGINS=https://garmentchatbot.web.app,https://garmentchatbot.firebaseapp.com` 只在 owner 確認此 Firebase project 正確後使用；custom domain 另加精確 origin，不加 slash，不設 `*`。
7. Auto-Deploy 維持 Off。Blueprint 不建立 database 或 persistent disk。先在 ephemeral `/tmp/garment-hf-cache` 下載 cache；每次 restart/redeploy 可能重下載，演示前必須 warm-up。若需 persistent disk，另行批准費用與 path，再設定 HF_HOME。
8. 從 Render Dashboard 複製真正的 HTTPS service URL。不要以現有 config 常數推定服務存在／屬於自己。更新 frontend/config.js 的 API_BASE_URL 為該 origin；不能填 secret，不能改 HTTP。

### Liveness、readiness、timeouts

`/api/health` 只代表 process 活著。`/api/ready` 在 cold start 回 503；不自動下載 models、不呼叫 LLM。經批准的首次實際 search warm-up 後，readiness 唯讀驗證目前 shared model dimension、Qdrant config／非空 collection 及 catalog sentinel image。busy 時暫回 503，不作 Render 重啟探針。它明確回 `llm_verified:false`，provider 和完整 payload／所有圖片仍由 E2E 驗證。採 liveness 作平台 probe 是為避免 lazy model 尚未 warm 時無限重啟，不代表可立即開始 demo。

LLM agent/extractor 每次 call 30s、no retries；Qdrant 每次 call 10s。這些是單次 network timeout，並非整個 request wall-clock deadline。多次 LLM calls、model download/inference 可更久；`timeout-keep-alive` 也不是 inference timeout。不要把 thread timeout 當作可取消 PyTorch 工作。Frontend 保留既有 cancel/error behavior。仍需 target host latency 和最大 request 驗證。

全站 30 POST/minute、2 inflight，超額回 429 並附 Retry-After；GET/OPTIONS 不計數，health/images 可用。這是單 process 全站限制，沒有 per-user authentication／公平性，重啟即重置；CORS 不能防直接 API abuse。demo 前 owner 需 provider spending cap、監察費用及明確關閉服務方法；公開長期使用應另行評估 authentication/gateway，不在本次改 chatbot 架構。

## 6. Firebase frontend

唯讀觀察：現有 Firebase HTML、config.js、Render liveness、sample image HEAD 和 Firebase origin 的 CORS preflight 均回 200，live config API origin 與 source 相符。這不表示本次 changes 已部署或帳戶權限已確認。

目前 `.firebaserc` 是 `garmentchatbot`、`firebase.json` public 是 `frontend`，無 build。這只驗證檔案語法與路徑，未驗證帳戶權限。

Owner 在自己有權限的機器執行：

```sh
npm install -g firebase-tools
firebase login
firebase projects:list
firebase hosting:sites:list --project garmentchatbot
```

若無該 project，請 owner 在 Firebase Console 確認 project ID 並授予適當 Hosting deploy 權限；不要猜新 ID 或自行建立另一個。若 ID 不符，先修正 `.firebaserc` 與下方命令。

確認 frontend/config.js 是真正 backend HTTPS origin，Render CORS 與預定 frontend origin 相同。以下本機 preview 不會發布：

```sh
firebase emulators:start --only hosting --project garmentchatbot
```

檢查 frontend/index.html 的 CSS／ES module、圖示、details、carousel；config.js no-store 避免 URL 改動後沿用舊設定。test files／Markdown／package.json 排除在 hosting deployment。API 不經 Firebase rewrite 代理，仍直接連 Render；現有 SPA rewrite 保留。

Owner 已批准公開，並且 relevant tests 通過後才執行：

```sh
firebase deploy --only hosting --project garmentchatbot
```

CLI 回傳 deploy 結果後，實際打開其 HTTPS URL，測 frontend + backend + images，再記錄 release ID／commit。不要只憑 CLI 完成即宣布 E2E 成功。

## 7. HTTPS E2E 驗收與記錄

在最終 origin 的 Chrome／目標 browser 執行；使用現有真實圖片，禁止 mock results。每項記錄時間、commit、實際 URL、pass/fail、非敏感 evidence。

| 檢查 | 驗收方式 |
|---|---|
| Frontend 載入 | HTTPS、CSS/modules 無 404、Console 無錯 |
| Backend liveness | GET /api/health 200 |
| Qdrant | 唯讀 script 通過，model owner 確認 ingestion identity |
| Models | --models 通過、service warm search 後 /api/ready 200 |
| LLM | --llm 通過，actual tool/structured calls 亦成功 |
| Text | 真正 query 回傳相關 catalog product，不代入 fixture |
| Image | 上傳既有 JPEG 得到可見相似商品 |
| Mixed | 同張圖片加文字 refinement 正常 |
| Modes | Auto／Exact／Similar 分別測 text、image、mixed |
| Context | refinement 保留／替換偏好；獨立新 topic 正常 |
| Pagination/count | 要求 1／8 個、超過上限、more results 不重複 |
| Images | thumbnails/details 真正載入，已知 missing ID 404 正常 |
| Speech | HTTPS microphone permission、真實 recognition、synthesis、stop |
| Refresh | 同 origin localStorage continuation；image vectors 可重用，原圖 preview 不保留 |
| Errors | invalid upload、backend unavailable、429、provider failure 有既有友善錯誤 |
| Secrets | browser Sources/Network/storage 只有 public URL，無 key／.env |

目前這些 production E2E 均待執行；offline tests 不取代它們。

## 8. 自動化、rollback、故障處理

`.github/workflows/hosting-checks.yml` 在 PR／手動執行 Python 3.12 + Node 24 offline checks，無 deployment／secret access。首次 GitHub Ubuntu clean run 尚待授權 push 後驗證。當 requirements 尚未 lock，CI 可能因 upstream release 失敗；先定位，不為部署任意改模型版本。

最低手動更新流程：review PR → CI 通過 → owner 批准 merge/push → Render manual deploy 該 commit → backend smoke → Firebase deploy → HTTPS E2E。未啟用不穩定 branch 自動部署。若之後批准 Render auto deploy，僅穩定受保護 branch、`checksPass`，並要求 PR checks。Firebase CLI 使用 owner login；若日後改 GitHub Actions，使用受保護 production environment + GitHub Secrets／OIDC，不能 commit service account JSON。

每次記錄已知良好 backend commit、Render deploy ID、Firebase release、API origin/CORS 與 model/collection identity，不記錄 key。失敗時 Render Dashboard rollback 前一個良好 deploy；Firebase Console → Hosting → Release history rollback 同時期良好 release。若 API URL/config 改動，兩端要配套回退。重啟後重新 warm-up，查 /api/health、/api/ready、圖片和實際 query。不要恢復已撤銷 key，不用 Git reset/force push 代替雲端 rollback，不修改 Qdrant。

503 cold readiness：先完成批准的 warm search，確認 HF cache/egress、RAM。502：private logs 查 exception type、provider compatibility／timeout。429：等 Retry-After，檢查是否多人同時 demo。404 image：核對 payload 與 root catalog，保留已知缺圖記錄。CORS：精確比較 scheme/host/port 並重啟 backend。OOM：查看 container peak，停止再評估資源，不自動付費升級。

## 官方參考（2026-11-07 查閱）

- [Render Blueprint](https://render.com/docs/blueprint-spec)
- [Render Python version](https://render.com/docs/python-version)
- [Render free limitations](https://render.com/docs/free)
- [Render pricing](https://render.com/pricing)
- [Render compute plans](https://render.com/docs/compute-plans)
- [Firebase Hosting configuration](https://firebase.google.com/docs/hosting/full-config)

- [PyTorch CPU/Linux installation](https://pytorch.org/get-started/locally/)
