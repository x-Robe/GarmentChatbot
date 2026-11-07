# Hosting Checklist — 2026-11-07

`[x]` 本次已完成；`[ ] 待驗證` 尚未完成；`[ ] Owner` 需要 owner 手動操作／明確批准。歷史 release tests 不當作本次部署結果。

## Audit 與準備

- [x] 在獨立 hosting-preparation clone 檢查 upstream commit cfb2f657f7bbcb7f01ae6ebc4574e4a26e8c65bd；原有開發目錄保持原樣。
- [x] 讀取指定 README、handover、deployment/integration docs、backend SKILL/API/src、frontend config/search 和 Firebase config。
- [x] 記錄先行 audit、Python/entry point、catalog/cache、CORS 與整合 blockers。
- [x] 保留原始 images、dataset、evaluation、prompts 和 retrieval/ranking。
- [x] backend/.env 從新 clone Git index 移除，本機檔案仍在；修復 ignore 並建立安全 .env.example。
- [x] current-tree／八個 reachable commits 進行 redacted heuristic secret scan。
- [ ] Owner：撤銷／輪替所有可能洩漏 provider、Qdrant、HF keys，檢查存取與費用紀錄。
- [ ] Owner：另行決定 Git history/fork/cache remediation；本次沒有 rewrite history。
- [x] Render Blueprint、one worker、PORT、Python 3.12、auto deploy Off。
- [x] 分開 liveness/readiness；Qdrant/LLM timeouts、global admission limits。
- [x] Firebase publish directory／JSON 語法、HTTPS API 常數、排除 test/doc、config.js cache 設定。
- [x] Chinese HOSTING_GUIDE.md、environment table、rollback／manual deploy commands。
- [x] PR／manual offline CI 設定；未啟用 automatic deployment。

## 本次實際 local tests

- [x] 現有環境 backend：160 tests passed。
- [x] 新增 hosting transport：4 tests passed（cold/warm readiness、rate limit、concurrency）。
- [x] Frontend：103 tests passed。
- [x] 新 Python 3.12.14 venv 從 requirements 完成安裝；pip check 無 broken dependencies。
- [x] 新 venv 完整 backend + hosting suite：164 tests passed，無 model/provider live calls。
- [x] Catalog layout/hash/static HTTP tests 包含於 backend suite；所有已追蹤 catalog 資料沒有改動。
- [x] JSON/YAML parse、Git whitespace check、Python syntax checks 通過。
- [ ] 待驗證：GitHub Ubuntu CI／Render Linux build 與 target platform wheels。
- [ ] 待驗證：FashionCLIP/MiniLM 真實 downloads、inference、RAM／cold/warm latency。

## 既有外部網站：read-only observation，並非本次 deploy

- [x] https://garmentchatbot.web.app/ 回 HTTP 200 並引用 app.js。
- [x] https://garmentchatbot.onrender.com/api/health 回 HTTP 200／預期 liveness JSON。
- [x] 既有 /images/tshirt/941.jpg HEAD 回 HTTP 200。
- [x] 既有 frontend config API origin 相符；CORS preflight 回 200 並允許 Firebase origin。
- [ ] Owner：確認這些服務／Firebase project 的帳戶所有權、deploy permission 和目前 revision。
- [ ] 待驗證：新的 hosting changes 尚未部署；不能以舊站 HTTP 200 宣稱本次部署完成。

## Live integrations 與公開批准

- [ ] Owner：提供新授權的 Qdrant endpoint/key、collection、ingestion model identity。
- [ ] 待驗證：執行唯讀 verify_integrations.py；512/Cosine、payload/sample images、owner model identity 確認。
- [ ] 待驗證：models script + minimal provider request；實際 structured tool compatibility。
- [ ] Owner：確認 catalog/model hosting rights，批准公開與付費 compute（2 GB 只是候選）。
- [ ] Owner：review／批准 push 及服務更新；不可直接覆蓋 shared branch。
- [ ] Owner：登入 Render/Firebase，確認 project，配置新 secrets 與精確 CORS。
- [ ] 待驗證：Render manual deploy 核准 commit；warm service 後 readiness。
- [ ] 待驗證：必要時把 frontend API_BASE_URL 更新為 dashboard 確認的真實 origin。
- [ ] Owner：在 tests 通過後執行 Firebase deployment，記錄 release／commit。
- [ ] 待驗證：text/image/mixed × Auto/Exact/Similar 真實 E2E。
- [ ] 待驗證：context/refinement、pagination/counts、refresh continuation、圖片和 graceful errors。
- [ ] 待驗證：HTTPS 真實 microphone recognition／speech synthesis。
- [ ] 待驗證：browser secrets check、provider spending cap、memory/concurrency、rollback rehearsal。

未執行 ingestion、Qdrant mutation、credential rotation、paid resource creation、public deployment、push 或 history rewrite。
