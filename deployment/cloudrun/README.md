# Cloud Run 执行与回滚

当前状态：Cloud Run 与 Firebase 已实际部署，owner 已批准正式切换。本机 backend/Tunnel 已停止，云端完整矩阵再次通过。Mac/Tunnel 脚本、配置和旧 Firebase version `35f729266b8bd67c` 保留用于回滚。

## 固定设置

- `asia-east2`、Python 3.12、CPU-only Torch、1 vCPU／4 GiB。
- Request-based billing (`cpu-throttling=true`)，startup CPU boost 关闭。
- min=0、max=1、concurrency=1、Uvicorn workers=1、request timeout=180s。
- `/api/health` 是不载模型的启动探针；`/api/ready` 及真实搜索用于 warm readiness。
- 原始 catalog 与两套模型的 pinned snapshot baked into image，HF offline；不在 cold start 下载。
- `.env.cloudrun` 与 `.env.local` 分离。POE_API/QDRANT_API 只存 Secret Manager，以固定 version 注入；不放 image/build args/JS。
- Dedicated runtime service account 仅授予这两个 secret 的 accessor 权限；不授予 Editor。

## 执行顺序

1. 先由 owner 明确批准按量计费／必要资源，并恢复可用 billing account、关联本项目。已验证 billingEnabled=true，并设置 HKD 8 Cloud Run 月度 spend cap 和独立项目预算提醒。
2. 准备 allowlisted build context：`python scripts/prepare_cloudrun.py`，路径记于 ignored `.runtime/cloudrun/context.json`。
3. 在同一区域创建一个 Artifact Registry Docker repository、必要 source upload bucket 和两个 Secret Manager versions；启用 Cloud Run/Build/Registry/Secret Manager API。默认 Cloud Build pool，不选昂贵 machine、不启用可收费 image scanning。
4. 提交 `deployment/cloudrun/cloudbuild.yaml`，`_IMAGE` 为实际 registry image URI。上传只允许 prepared context，不上传原 repo／Git history。构建验证 CPU Torch 与 pip check；部署使用返回的 immutable digest。
5. 以实际 image digest、runtime account、secret versions 运行 `scripts/render_cloudrun_service.py`，生成 private `.runtime/cloudrun/service.ready.yaml`。仅创建独立 Cloud Run service，不改 Firebase。
6. 新 API 完成真实 text/image/mixed × 全模式、refinement、pagination、全部 returned images 测试。复用：`python scripts/smoke_local_demo.py --confirm-live --origin ACTUAL_HTTPS_CLOUD_RUN_ORIGIN`。Cloud 测试写独立 `.runtime/cloudrun/live-tests.json`，不覆盖 Mac evidence。
7. 用 Cloud Run logs/cgroup metrics／Cloud Monitoring 量测 Linux cold/warm latency、memory；不能用本机模型测试代替。通过空闲 scale-to-zero 后的请求量测自然 cold start；不增加 minimum instances。
8. `python scripts/stage_cloudrun_frontend.py --api-url ACTUAL_HTTPS_CLOUD_RUN_ORIGIN` 只生成 `.runtime/cloudrun/frontend`。采用稳定 Cloud Run HTTPS origin＋精确 Firebase CORS，不依赖 Tunnel，也不修改工作中的 Mac frontend config。
9. **真实 Cloud Run tests 通过且 owner 再次批准后**才发布：`./scripts/firebase.sh deploy --only hosting --project garmentchatbot --config .runtime/cloudrun/frontend/firebase.json`。
10. 发布后检查公开网站，再按任务要求 stop Mac/Tunnel，重新测试网站与图片，证明不依赖本机。

本机未安装 Docker/gcloud；以上云端构建／部署可通过已授权 Google API 执行，或在有官方 gcloud CLI 的环境执行。计费／资源批准前不得执行步骤 3–5。

## 回滚

- 已把原 Firebase staging 备份在 `.runtime/cloudrun/rollback/firebase`，未覆盖 `.runtime/firebase` 或修改 local supervisor。
- Mac/Tunnel 仍运行且原 hostname 有效时，经批准发布 `.runtime/cloudrun/rollback/firebase/firebase.json`，即可恢复原本连接。
- 如果已停止 Quick Tunnel，旧 hostname 不能恢复。先用现有脚本重新启动 Mac/Tunnel（owner 历史 key 例外时带 `--allow-historical-credentials`），验证新 URL，再使用 `.runtime/firebase/firebase.json` 发布新 Mac origin。**不能只回滚旧 Firebase version 就假定已停止的 Quick Tunnel 又能连通。**
- 不删除 Cloud Run、Render、Qdrant 或已有 Firebase releases；需要回退 Cloud Run revision 时只改流量指向已验证的实际 revision。

## 计费控制

已设置 HKD 8/月 Cloud Run spend cap（折扣前估算费用，达到后暂停 Cloud Run），另有整个项目 HKD 8/月预算提醒。提醒不是硬 spending cap；暂停阈值执行有延迟，其他服务不在其范围，不能保证总账单上限。详见 `cost-controls.md`。最低实例 0 不消除 Registry/storage/egress/Secret Manager 等独立费用。


## 本次部署验收（2026-11-07）

- Firebase：https://garmentchatbot.web.app/，version `2ccb3d0676d8bd6e`。
- Cloud Run：https://garmentchatbot-cloud-otov3dshpq-df.a.run.app。
- Revision：`garmentchatbot-cloud-00001-zwm`；build `abb9389e-64ad-4319-9a8a-9bf3745cb16a`。
- Image digest：`sha256:798caf2c7d5b002a997255abbd694fc6f33d970239652ec3c527138ac84cfd31`。
- 实测压缩 image 1,350,248,167 bytes（1.26 GiB），包含原模型与 1,993 张图片。
- 真实 API 两轮各 12/12；第二轮在 Mac backend/Tunnel 已停止后执行。覆盖 text/image/mixed × Auto/Exact/Similar、context、pagination、readiness；23 张返回图片均可读取。Qdrant 只读，未写 collection。
- 公开 Firebase 浏览器实测 text、image、mixed、三种模式选择、多轮修改、结果翻页、刷新恢复对话；16 个可见图片均从 Cloud Run 加载成功。
- 首次模型请求 31.375 秒；首轮热搜索 0.687–5.785 秒，中位数 3.103 秒。请求计时包含返回商品图片检查，不能当纯模型推理时间。
- Linux 日志实测进程 peak RSS 1,170.31 MiB（约 1.14 GiB）。cgroup memory counter 不可读；进程 RSS 不是容器总内存。Monitoring 有容器利用率样本，但不能视为精确峰值。
- 语音朗读开始/停止控件正常；内嵌浏览器语音识别停于 Starting microphone，已取消，没有发送语音。仍需真人在 Chrome 授权麦克风验证。
- 自然闲置 scale-to-zero 后的完整 HTTP 冷启动尚未量测；31.375 秒是已启动容器的首次模型载入请求，不等同完整冷启动。
- 新部署脚本测试 8/8。Linux Docker 构建完成 pip check 并确认 CPU Torch 无 CUDA。
- 目前不需要启动 Mac 或 cloudflared。访问 Firebase 即可使用云端；保留 Mac rollback 文件，不依赖旧 Quick Tunnel hostname 永久有效。
- 费用控制详情见 `cost-controls.md`；暂停阈值可能让示范中断，不能保证整张账单永不超过 HKD 8。
