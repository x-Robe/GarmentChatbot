# GarmentChatbot Hosting 成本與資源評估

評估日期：2026-11-07（Asia/Hong_Kong）。分支：`codex/production-hosting`，目錄：`hosting-preparation`。

本次只讀取程式、設定、已存在的 model cache，執行本機離線 inference 與既有網站 GET。沒有 deploy、push、建立資源、修改 production data、發送 LLM request 或輪替外部 credentials。新增本報告和去敏感化的量測 evidence；Blueprint／應用程式未修改。

## 1. 建議結論

優先重用既有 Firebase `garmentchatbot`、既有 Render `garmentchatbot` Web Service、現有 populated Qdrant collection 與現有 Poe provider 帳戶。不要為這次 demo 新建 database、GPU、Redis、Cloud Functions 或另一套網站。

- 最低成本的「待驗證方案」：現有 Render Standard／`1c-2g`，1 CPU、2 GB，US$25/month；適合 1–2 個同時提交、1–5 人輪流操作。必須通過 Linux container memory／latency 測試才能確認足夠。
- 以 1–5 人 demo 的容量餘裕為優先：建議預算採 Pro／`2c-4g`，2 CPU、4 GB，US$85/month。這是較保守的建議，不是已量測證實的 Render 保證。本次不改目前 `plan: standard`，也不升級或建立任何服務。
- 重要限制：目前分支／Blueprint 的 `API_MAX_INFLIGHT=2`，5 人同時按搜尋時，最多接納 2 個，其他可能回 429；shared `_agent_lock` 仍只允許一次實際搜尋。升級 RAM／CPU 不會解除這兩個限制。如果必須接納五個同時提交，後續需明確同意 operational setting 調整、測試排隊延遲與大圖記憶體；現在不修改。
- Firebase、Qdrant 若可重用且既有 quota 足夠，新增固定 infrastructure 成本可以是 US$0；LLM 仍消耗既有 Poe points，不能宣稱免費。

價格按官方當日公開標價估算，美元、未含稅與匯率、額外 bandwidth/build usage。現有帳戶的 plan、credits、已付費額及剩餘 quota 尚不可見，不能把公開標價當作你的新增帳單。[Render pricing](https://render.com/pricing)、[Render compute specs](https://render.com/docs/compute-plans)。

## 2. 實際 Blueprint 與依賴

已檢查 `render.yaml`、`backend/requirements.txt`、API、model loader、ProductSearch、LLM clients、image upload、frontend/Firebase 設定。

| 項目 | 目前實際設定 | 成本／容量影響 |
|---|---|---|
| Service | Python Web Service，`plan: standard` | 對應 1 CPU／2 GB；不是雲端當前 instance 的證據 |
| Build | 先官方 CPU Torch wheel，再 existing requirements | 避免 CPU host 安裝 CUDA runtime；Linux build 仍未驗證 |
| Runtime | Python 3.12.14，單 Uvicorn worker，綁定 PORT | 不複製 models 到多個 workers |
| Root Directory | Blueprint 未設 rootDir，從 repo root build | 保留 root data/images，start 時 cd backend |
| Health | /api/health | 只證明 process 活著，不能量測 model／Qdrant／LLM |
| Auto deploy | off | 本次不啟動自動部署 |
| Cache | HF_HOME 位於 /tmp，未配置 persistent disk | restart/redeploy 後可能重新下載 |
| Admission | 30 POST/min 全站，2 inflight | 包含等待 lock 的請求；不是每位用戶 30/min |

Dependencies 含 Torch、Transformers、sentence-transformers、NumPy、SciPy/sklearn（間接）、Pillow、Pandas、Qdrant client、OpenAI-compatible SDK 和 FastAPI/Uvicorn。requirements 基本未 pin；本機成功安裝不等同 Linux 可完全重現。沒有額外獨立的本機 generative LLM；LLM compute 在 provider 端。

FashionCLIP 在首次搜尋 lazy load。MiniLM 是現有 attribute matcher 的額外 lazy path，並非每次標準搜尋都必然載入；但其 import/dependencies 已在 process 中，容量規劃仍應包含啟用它的情況。兩個 model 共用單 process；catalog JPEG 以 static files 提供，不會一次把 1,993 張全讀入 Python RAM。

## 3. 本次真正量測的資源

環境是本機 macOS arm64、Python 3.12.14、10 logical CPUs、Torch 4 threads；不是 Render 的 1／2 CPU Linux container。使用既有 Hugging Face cache，明確開啟 offline flags、停用 dotenv loading，沒有使用舊 credentials，也沒有下載 model 或呼叫 Qdrant／LLM。

以下 RSS 是 `resource.getrusage(...).ru_maxrss` 的**累積 process peak**，不是各組件獨立大小，也不是當下 RSS；各行不能相加。作業系統 page cache、mmap、架構與 thread 數會影響結果。

| 階段 | 本次量測累積 peak RSS | 本階段 wall time |
|---|---:|---:|
| API import，未載 models | 55.5 MiB | 0.231 s |
| Search module/dependencies import，未載 weights | 478.6 MiB | 3.869 s |
| FashionCLIP load | 525.4 MiB | 0.179 s |
| 首次 text inference | 673.8 MiB | 0.034 s |
| 首次 catalog image inference | 1,008.6 MiB | 0.048 s |
| MiniLM load／label encode | 1,061.0 MiB | 0.183 s |
| 同時持有兩張 20 MP decoded images | 1,287.3 MiB | 0.077 s |
| 上述狀態再做一張 20 MP image inference | **1,518.8 MiB（約 1.48 GiB）** | 0.135 s |

整個第二次量測約 4.86 s；warm text／catalog image inference 約 0.007／0.023 s。這些是本機 warm file-cache 結果，不含網路／LLM／database、完整 request、Linux cgroup memory 或五人 load test，不能當作 demo 回應時間。20 MP 測試圖是在記憶體建立的 synthetic plain image，只測 upload decode/inference memory，不是假裝真實商品搜尋。未改動任何 catalog asset。第一次量測因 current-RSS 查詢權限不足而中止，改用 OS peak-RSS 後成功；不存在 current-RSS 量測值。

| Disk 項目 | 本次實測 logical size | 備註 |
|---|---:|---|
| 1,993 張 catalog JPEG | 378,919,404 bytes＝361.37 MiB | 保留原檔；7 個已知缺圖 records 不補造 |
| FashionCLIP cache blobs | 580.57 MiB | 既有 cache，不是 RAM |
| MiniLM cache blobs | 87.34 MiB | 既有 cache，不是 RAM |
| 新 Python venv | 1,252.57 MiB | macOS package footprint，不含上述 model cache |
| frontend 全部檔案 | 145,038 bytes，約 0.14 MiB | 含不會部署的 tests/docs；實際發布更小 |

Evidence：`docs/validation/hosting-resource-memory.json`、`hosting-resource-storage.json`。離線 model loader／text/image／MiniLM 已真正執行成功；這更新了前一階段「尚未測 local model inference」的狀態，但沒有證明 hosted integrations 可用。

## 4. Render resource 規劃：以下全部是估算

| 使用情境 | RAM 規劃估算 | CPU／容量判斷 |
|---|---|---|
| 一般單請求，models 已 warm | 約 1–1.8 GiB | 1 CPU 可作低頻 demo，實際 latency 未測 |
| 現有 2 inflight、大圖 decode/inference | 約 1.5–2.5 GiB peak | 2 GB 可能接近／超過限制；4 GB 較有餘裕 |
| 若未來調整為 5 inflight，且多人上傳大圖 | 約 2–3.5 GiB peak | 4 GB 是合理測試起點，不承諾低延遲 |

估算不是把 cache disk size 直接加到 RAM。它參考本機 peak、Torch native allocations、mmap/page cache、Linux runtime 差異、model 載入暫存和 upload 複本。20 MP decoded image 的 RGB 原始資料理論至少約 57 MiB，Pillow 實際 stride／轉換／resize 可用更多，不能只按 10 MiB 壓縮 upload 上限估 RAM。Image decode 在 model lock 之前，等待中的 image request 也會持有 decoded image。

CPU 規劃：單 worker＋shared lock，2 CPU 可改善 model/preprocessing 的 CPU headroom，但不能令五個 LLM/search 同時執行。完整搜尋可能包含 planning、attribute extraction、final wording 三次 provider calls，通常 provider/network latency 比本機 embedding 時間更重要。例如每個完整 request 若需 10 s，五個序列處理最後一個可能約 50 s 才完成，這只是排隊例子。每次 LLM call 30 s timeout 不代表整個 request 的總期限。

Disk 規劃：Linux packages、source/catalog、約 668 MiB model cache 加暫存，建議 runtime 準備約 4–8 GiB 可用空間，build/install 暫存另留約 6–10 GiB 工作空間；這是估算，尚未量測 Render build filesystem。需要持久化的只是 model cache，而非整個 venv 或圖片副本。2 GB persistent cache 作為可選項約 US$0.50/month；保留多個 model revisions 時需重新評估。Persistent disk 僅 runtime 可用，不能靠 build command 寫入，且影響 zero-downtime deploy，不是無代價優化。[Render disks](https://render.com/docs/disks)。

Cold start 規劃估算：

- cache 已在目標 host：process＋重型 imports＋weights/inference 初始化約 20–90 s 作演示準備預算；本機約 5 s 不可直接外推。
- cache 不存在：下載約 668 MiB，連同載入先預留約 2–15 min，視 Hugging Face egress、下載速度與 CPU 而定；沒有服務保證。
- dependency installation 是 build 時間，獨立於上述 process cold start；預留數分鐘至十多分鐘，待 Linux build 量測。
- Free idle 約 15 min 後 spin down，再加平台喚醒與 cache 重建，增加不確定性。不要在 demo 前最後一分鐘才 warm-up。[Render free limitations](https://render.com/docs/free)。

## 5. 可行 instance 與月費

| Render instance | CPU／RAM | 公開月費（US$） | 對本專案的判斷 |
|---|---|---:|---|
| Free | 0.1 CPU／512 MB | 0 | 不建議；重型 imports 已約 479 MiB，本機實際 inference 超過 1 GiB，另有 sleep |
| Starter／0.5c-512mb | 0.5 CPU／512 MB | 7 | 不足；付費消除部分 free 限制但沒有改善 RAM |
| Standard／1c-2g | 1 CPU／2 GB | 25 | 最低測試候選；適合輪流展示，需要 Linux 峰值驗證 |
| Pro／2c-4g | 2 CPU／4 GB | 85 | 建議的 demo 安全預算，對 image/memory 波動較寬裕 |

規格依 [Render compute plans](https://render.com/docs/compute-plans)，價格依 [Render pricing](https://render.com/pricing)。本報告沒有把 workspace Pro 和 compute Pro 混為一談：Hobby workspace 的固定費用為 US$0，仍可付 compute 費。若既有團隊 workspace 原本已付費，其原有費用繼續存在；不為本 demo 任意升級 workspace。

| 月度方案 | 新架構總固定成本估算，不含既有付費服務與 LLM 用量 |
|---|---:|
| Standard，無 persistent disk | US$25 |
| Standard＋2 GB model cache disk | US$25.50 |
| Pro／4 GB，無 persistent disk | US$85 |
| Pro／4 GB＋2 GB model cache disk | US$85.50 |

若既有 Render instance 已是足夠的付費方案，重用同一 instance 的**新增 compute 固定費可以為 US$0**；如果由 Standard 升為 Pro，整月 compute 差額約 US$60，而非另加一整台 US$85。未取得帳單，不能斷言你目前在哪一種情況。

Render compute 依運行時間按秒比例計費；用 30 天粗估，Standard 只運行 3 天約 US$2.50，Pro 約 US$8.50，另加仍存在的 disk／workspace／超額用量。只是不開瀏覽器不會停止 paid instance 計費；需在 demo 後另行授權停止／調整。[Render billing FAQ](https://render.com/docs/faq)。

目前公開 Hobby quota：5 GB/month outbound，超出 US$0.15/GB；workspace 已有其他 traffic 時剩餘 quota 會變少。JPEG 由 Render 提供，**不計入 Firebase bandwidth**。平均 catalog JPEG 約 186 KiB，5 人各 20 次搜尋、每次 8 張，未計 browser cache 約 145 MiB 圖片流量；100 次搜尋共約 800 圖，是 workload 假設，不是實際 traffic。300 次同等搜尋約 435 MiB。API JSON 與其他 workspace 流量另計，通常 demo 圖片不會獨自耗盡 5 GB，但不能保證帳戶尚有 quota。Build quota 也需看現有帳戶用量。[Render bandwidth](https://render.com/docs/outbound-bandwidth)。

## 6. Firebase、Qdrant、LLM 能否重用

### Firebase／Render

本次重新 GET 既有 `https://garmentchatbot.web.app/` 與 `https://garmentchatbot.onrender.com/api/health`，均 HTTP 200；後者 JSON 是預期 liveness 回覆。前一階段亦已檢查 live frontend config、sample image HEAD 和 CORS。這些證明既有 endpoint 存在，不代表知道 cloud account owner、current instance size、Git branch/revision、secret configuration 或完整 readiness。

`.firebaserc` 的 project 是 `garmentchatbot`，public directory 是 `frontend`；現有 frontend source 已指向同一 Render URL，因此優先在原服務更新，保留 URL、CORS 和 localStorage origin。**不要直接 Import Blueprint 以為一定會自動接管現有服務**；先在 Render 確認 service 是否已受哪個 Blueprint 管理、service ID、repo/branch、region、plan，再決定更新原設定或採納 Blueprint。本次不建立新 Blueprint instance。

Firebase Hosting 的 10 GB storage／360 MB/day no-cost allowance，對約 0.14 MiB frontend 和 1–5 人 demo 通常足夠；現有 project quota 須確認。這是傳統 Firebase Hosting，不是 Firebase App Hosting，無需為此新增 Cloud Run。[Firebase Hosting pricing](https://firebase.google.com/pricing)。

### Qdrant

可以重用現有 collection，條件是 owner 確認可存取、仍 populated、unnamed 512-dimensional Cosine vectors 且 ingestion model/revision 相容。2,000 條、512 維 float32 的純向量理論為 4,096,000 bytes（約 3.91 MiB）；這**不是 live collection size**，沒有包含 payload、HNSW、WAL、replicas、其他 collections 和系統 overhead。Qdrant 不存 JPEG binaries。

既有 cluster 若有容量／授權，不用新增 database；新增 infrastructure 固定成本可 US$0，但原本 paid cluster 的帳單不會消失。官方 Free Tier 是 0.5 vCPU／1 GB RAM／4 GB disk，這個 catalog 的向量量級看來很小；本次不申請新 cluster，也不能把 Free Tier 當作已存在資料的自動替代或批准重建。仍未用新 key 執行 live collection checks。[Qdrant pricing](https://qdrant.tech/pricing/)。

### LLM provider

本機設定的 provider 類型可辨識為 Poe；不在報告列出私有 endpoint／model 值。可重用原 Poe 帳戶及支援本程式 Responses／structured tools 的 model，不需要自行 hosting LLM 或 GPU。新增 server infrastructure 成本可為 US$0，但 request 消耗 owner 的 points；paid model 要有有效訂閱／add-on points。帳戶餘額、model rate card、既有 subscription 成本未能讀取，所以沒有可信的固定美元推算。

一般新 text search 約三次 calls：planning、extraction、wording；例如 100 次＝約 300 calls，而不是 100。Image-only 可以不需 LLM；image＋文字 override、continuation 的 call 數不同。多輪 context 令 input tokens 成長。應以實際 model rate card × 各 calls 的 token/points 用量估算，不能以 request 數直接宣稱免費。這次沒有消耗 provider points 或測試 provider compatibility。[Poe API access](https://creator.poe.com/docs/external-applications/external-application-guide)、[Poe key management](https://creator.poe.com/api-reference/overview)。

## 7. Environment 缺漏：只報狀態，不列值

本次「current process」中下列 variables 都未設定；程式本機通常會從 backend/.env 載入，因此須和 local file 分開判讀。雲端 Environment 目前沒有授權讀取，**不能宣稱 production 也缺同樣欄位**。

| Variable | local backend/.env 狀態 | 是否阻擋／處理 |
|---|---|---|
| POE_API | 空白 | 阻擋 LLM；需新授權 provider key |
| OPENAI_API_KEY | 缺少 | Poe 模式非必須；若改標準模式才需設定並 unset POE_* |
| POE_URL | 有值，未驗證相容性 | provider base URL；不是替代 key |
| OPENAI_MODEL | 有值，未驗證 | 要確認原 provider 支援 actual tools/schema |
| QDRANT_URL | 空白 | 阻擋 database connection |
| QDRANT_API | 空白 | authenticated Qdrant 阻擋；需要新 read-only key |
| QDRANT_COLLECTION | 有值，未驗證存在 | 需 owner 確認現有 populated collection |
| CLIP_MODEL | 有值 | 本機 cache inference 通過；與 ingestion identity 仍未核實 |
| CORS_ORIGINS | 空白 | production 必須填精確 Firebase HTTPS origins；明確空字串會得到空 allowlist，不是 localhost default |
| HF_TOKEN | 空白 | public models 已有 cache 可離線執行；不必為此新增 token，但歷史 token 仍需撤銷 |
| PYTHON_VERSION | 缺少 | Blueprint 已指定；不是 app secret |
| HF_HOME | 缺少 | Blueprint 已給 /tmp path；未部署則不會自動生效 |
| PORT | 缺少 | 本機缺少正常，Render 自動提供 |
| API_REQUESTS_PER_MINUTE | 缺少 | code default 30，Blueprint 亦指定 |
| API_MAX_INFLIGHT | 缺少 | code default 2，Blueprint 亦指定 |

沒有檢查其他舊開發目錄來補用 key，也不重用任何歷史 exposed key。去敏感 evidence：`docs/validation/hosting-environment-presence.json`。

## 8. 應輪替的 credentials 與 replacements 放哪裡

已確認 history 中非空 credential names 是 `POE_API`、`QDRANT_API`、`HF_TOKEN`，出現在舊 `.env`／`backend/.env`，另有 `Credentials/qdrant`。目前 local file 清空不代表舊 key 已撤銷。以下是 owner 後續操作，不是本次已執行：

| Credential | 撤銷／建立 replacement 的位置 | replacement 配置 |
|---|---|---|
| POE_API | 原 key 發行 provider；現設定指向 Poe，進 Poe API Keys 撤銷對應舊 key，建立 demo/production 專用 key | 現有 Render Service → Environment → POE_API；本機 untracked backend/.env 用獨立 dev key |
| QDRANT_API | 現有 Qdrant cluster → Cluster Detail → API Keys；撤銷洩漏 database keys，建立只限現有 collection 的 read-only key | Render Environment → QDRANT_API；不是 Cloud Management Key |
| HF_TOKEN | Hugging Face → Settings → Access Tokens，撤銷所有出現在 repo history 的 token | 如 public model 不需 token，保持 unset；真的需要則 Render HF_TOKEN，最小 read scope |

Poe 使用 [API Keys](https://poe.com/api/keys)；Qdrant database keys 和 cloud management keys 是不同 credentials，可用 collection-scoped read-only 權限；HF 使用 [Access Tokens](https://huggingface.co/settings/tokens)。參見 [Qdrant authentication](https://qdrant.tech/documentation/cloud/authentication/)。本次沒有證據顯示 Firebase service-account key 或 Render API token 也被此 repo 曝露，不把 public project ID／service URL 當作需要輪替的 secret。

Production replacements 只放現有 Render secret environment；不要放 frontend/config.js、Firebase public files、render.yaml value、Git commit 或本報告。若日後啟用 deploy CI，再使用 GitHub Secrets／OIDC，不是現在新增 service account。刪除當前 .env 或 git rm --cached 不會消除歷史曝光，owner 仍需撤銷，history rewrite 另行批准。

## 9. 未解 blockers 與精確下一步

1. **帳戶／現況確認，唯讀**：owner 登入 Firebase Console 確認 project ID／Hosting site／部署權限／quota；登入 Render Dashboard 確認原 service、repo/branch、plan、region、Blueprint 管理關係、實際 Environment 欄位與 Billing。只回報欄位是否存在和 plan／usage，不分享 secret 值。Poe 確認 subscription/points/model rate card；Qdrant 確認原 cluster/collection/version/capacity。
2. **先選 workload 目標**：若只是 5 人輪流操作，保留 Standard 作最低成本測試；若希望 demo 有較大記憶體餘裕，預算 Pro 4 GB。若明確要 5 人同時提交且都被接納，需後續批准 admission setting 調整；它仍序列執行，不承諾五路並行。
3. **明確批准後才輪替 key**：owner 撤銷上述 exposed keys；replacements 私下配置於既有服務，開發／production 分開。這次沒有批准或執行 rotation。
4. **新 key 的唯讀 integration checks**：先跑 `python scripts/verify_integrations.py`，核對 dimension/distance、sample payload/image paths、owner ingestion model identity；不 ingestion、不改 indexes／collection。Provider minimal probe 需另行同意其可能費用。
5. **批准 hosting update／費用後才做目標測試**：在現有服務或已核准環境做 Linux cold/warm boot、text/image/mixed、最大 upload、1/2/5 人 burst、20 次混合操作；記錄 cgroup memory peak、CPU、P50/P95、429、LLM usage。2 GB 的接受條件建議 peak ≤實際 memory limit 的 70–75%、無 OOM、延遲符合預定 demo；不達標才提出 4 GB 升級，禁止自行付費變更。
6. **最後才 deploy/push**：review 本分支所有既有 changes、CI 通過，再取得 shared-branch push／public update 授權；沿用原 Firebase/Render URL。演示前預留 15–30 min warm-up/rehearsal，驗證 readiness 與真實 search，演示後由 owner 決定停止／縮減 paid resource。

目前可以確認的是本機離線 models、資產大小與 public endpoint 存在；尚未確認的是 Render 真正 RAM/CPU/plan、Cloud Environment、Qdrant live compatibility、Poe 餘額/實際 tool compatibility 及五人 E2E。這些差異是選擇 US$25 測試方案或 US$85 較保守方案前的必要資訊。
