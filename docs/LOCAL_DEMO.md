# 本機 Mac + Cloudflare Tunnel 啟停

使用 existing Firebase Hosting → HTTPS Tunnel → 本機 FastAPI → existing Qdrant/Poe。Render 保留作備選，不使用、不升級。本流程不會 push 或 deploy Firebase。

在 `hosting-preparation` 目錄執行：

```sh
# 已在此機安裝到 .tools；其他 Mac 首次才需安裝
./scripts/install_cloudflared.sh
# .env.local 已建立；請填入「新」授權值，不能複製歷史洩漏 key
chmod 600 .env.local
./scripts/demo.sh check
./scripts/demo.sh start
./scripts/demo.sh status
```

`.env.local.example` 列出變數名稱。需要 POE_API、POE_URL、OPENAI_MODEL、QDRANT_URL、QDRANT_API、QDRANT_COLLECTION、與 ingestion 相同的 CLIP_MODEL。Secrets 只保留在 `.env.local` 或父程序環境，後者優先。啟動會拒絕比對到 fetched Git history 的 key，並停用所有舊 backend/.env 的載入。這是已知曝光比對，不是所有外部洩漏的偵測保證。

`start` 會：檢查設定／port → 啟動單 worker API（127.0.0.1:8765）→ Quick Tunnel → 更新本機 frontend/config.js → 建立 `.runtime/firebase/public` 靜態前端 → localhost:8766 preview → caffeinate 防止 idle sleep。API 與 preview 不綁 LAN。請保持 Mac 開機、接電、螢幕蓋打開及網路穩定；鎖屏不等同關機，caffeinate 也不能保證闔蓋後仍運作。

狀態與私有 logs 在 ignored `.runtime/`，權限限制為本機 owner。不要公開整個 repo 或 `.runtime`，也不要把 logs 當作 frontend assets。CLI `stop` 只關閉此 supervisor 自己建立的 processes，不使用廣泛 pkill。

```sh
# 關閉 API、Tunnel、preview、keep-awake
./scripts/demo.sh stop
# 可重啟；Quick Tunnel URL 會變
./scripts/demo.sh start
```

程序 crash 時 supervisor 停止整組服務，不會悄悄換一個新 hostname；cloudflared 自身可在程序仍存活時 reconnect。若啟動失敗，查 `.runtime/supervisor.log`、backend.log、tunnel.log；修正後重新 start。Port 已被其他服務佔用時會拒絕啟動，不會關閉他人的服務；可修改 LOCAL_API_PORT／LOCAL_FRONTEND_PORT，CORS origins 亦需對應 preview port。

## 只有連線測試、尚無 credentials 時

```sh
./scripts/demo.sh start --transport-only
```

此模式清空 integration credentials，供 health／catalog images／CORS 驗證；搜尋不會成功。填好新 keys 後先 stop，再不帶此旗標 start。不能把此模式當作 live chatbot 已完成。

## 真實 integration 與搜尋測試

```sh
./scripts/demo.sh verify --models --llm
.venv/bin/python scripts/smoke_local_demo.py --confirm-live
```

第一項使用新 settings 唯讀查 Qdrant、驗證既有 models、發送 minimal provider request；第二項透過實際 HTTPS Tunnel 執行 text/image/mixed × Auto/Exact/Similar、refinement、pagination、readiness 及 returned image URL checks。它們會消耗 provider points，但不寫 Qdrant。執行前需有有效 credentials；結果／latency／可取得的 backend RSS 存 `.runtime/live-tests.json`。圖像 Exact 可以合理零結果；自動測試不能證明人工 relevance 或 voice。目標 browser 另測 microphone permission、真實語音辨識、synthesis、refresh 後 context 與 image continuation。

## Firebase：先預覽，批准後才發布

start 後開啟 http://127.0.0.1:8766/，顯示既有 UI、API 連往新 Tunnel。CORS 預設允許既有 Firebase web.app／firebaseapp.com origins 與 localhost preview，沒有 wildcard。改 .env.local 後必須 stop/start 才生效。

只有在 credentials／live checks 通過、你批准公開更新後，才在 Firebase owner 已登入的機器執行：

```sh
./scripts/firebase.sh login --interactive
./scripts/firebase.sh projects:list
./scripts/firebase.sh deploy --only hosting --project garmentchatbot --config .runtime/firebase/firebase.json
```

Firebase 已在 2026-11-07 更新至本機 Quick Tunnel，Hosting version `35f729266b8bd67c`。本機 config 更新不會自動改動公開網站。此機已從官方 npm registry 安裝 Firebase CLI 至 ignored .tools，使用 scripts/firebase.sh；OAuth state 位於 private .runtime/firebase-cli-config。不必建立新 project。

Quick Tunnel 每次重啟的 URL 不同，因此重新啟動後若要給 Firebase 公開站使用，就必須在再次批准後更新 Hosting release。舊 conversation 保存的 absolute image URL 也可能指向已停止的 Quick Tunnel。最終 demo 優先採用下方固定 hostname，避免此問題。

要還原本機前端原 API URL（不影響公開站）：

```sh
./scripts/demo.sh restore-frontend
```

## 固定 hostname（不購買服務）

[Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) 是測試用途、沒有 uptime 保證，hostname 不固定。[Named Tunnel](https://developers.cloudflare.com/tunnel/get-started/) 的 public hostname 需要 Cloudflare 帳戶及已在其管理的 domain；Firebase 的 web.app domain 不能直接當作你擁有的 Cloudflare DNS zone。

如果你已有 domain／named tunnel，可沿用，沒有必要新買 domain。範例 `cloudflare/config.example.yml` 只含 placeholders；把實際 locally-managed config 放在 ignored `cloudflare/config.local.yml` 或 repo 外，credentials JSON/cert.pem 只放 owner 私人位置。在 `.env.local` 設定 CLOUDFLARED_CONFIG（該 config 的絕對路徑）及 LOCAL_TUNNEL_ORIGIN（已存在的 HTTPS hostname），腳本便使用 named tunnel，仍不改 DNS、不建立 tunnel。

若只有 remotely-managed tunnel token，本機安裝流程需另行設定安全 token file／官方 connector；目前腳本不把 token 放 command line。本次沒有登入 Cloudflare 帳戶、建立 named tunnel、變更 DNS 或購買 domain。沒有既有 domain 時，先保持同一 Quick Tunnel process 運行至 demo 結束；它仍不能提供固定名稱或 uptime 保證。

## Owner 明确例外

只有 owner 明确授权使用 history-matching credentials 时，才在 check／verify／start 命令加入 `--allow-historical-credentials`。默认仍会拦截；不会把 key 写入 source、command line 或公开 frontend。本次 owner 已在 chat 明确授权该例外，当前启动使用：

```sh
./scripts/demo.sh start --allow-historical-credentials
```
