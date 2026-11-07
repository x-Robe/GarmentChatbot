# Cost controls

Verified 2026-11-07 on project `garmentchatbot`:

- Billing account active and linked; project uses pay-as-you-go billing.
- Cloud Run monthly spend cap: HKD 8, `CONFIGURED`. Single-project, Cloud Run only; estimated gross list-price usage, excluding credits. Alerts at 50%, 80%, 100%; project owners receive notifications.
- Separate whole-project monthly HKD 8 budget alert. This alert does not stop spending.
- Spend-cap enforcement is delayed; in-flight requests and other services can still accrue charges. This is not a guaranteed total invoice ceiling.
- Artifact Registry and Cloud Build are outside the Cloud Run cap. Retain one recent image; older images eligible for cleanup after seven days. Temporary source bucket objects expire after one day.
- Deployment settings: minimum 0, maximum 1, concurrency 1, 1 vCPU, 4 GiB RAM, one Uvicorn worker, request-based CPU allocation, startup CPU boost disabled, 180-second request timeout.
- Application admission controls: one in-flight inference and 30 requests/minute. These are not a billing cap.

The HKD 8 Cloud Run cap can interrupt a classroom demonstration even when free-tier credits make the actual compute invoice zero: its accounting excludes credits. Do not silently increase or lift it. Check its remaining gross usage before the demonstration.

Official references:
https://docs.cloud.google.com/billing/docs/how-to/budget-api-spend-cap
https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
https://docs.cloud.google.com/run/docs/configuring/billing-settings
