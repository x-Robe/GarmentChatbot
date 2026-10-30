# Known Development Versions (Not a Lock)

Release-copy isolated checks reused Python 3.12.14 and Node v24.22.1. No dependency installation or clean-environment test was performed. backend/requirements.txt and requirements-api-test.txt are preserved; exact cross-platform dependency pinning was not assumed safe without a fresh resolver/install test. Do not treat this list as pip freeze or a guarantee of reproducibility on every host.

| Direct package | Installed version used |
|---|---|
| torch | 2.14.1 |
| transformers | 5.18.0 |
| safetensors | 0.8.0 |
| pillow | 12.3.0 |
| pandas | 3.0.6 |
| numpy | 2.5.3 |
| qdrant-client | 1.19.1 |
| tqdm | 4.70.1 |
| fastapi | 0.142.2 |
| pydantic | 2.13.5 |
| uvicorn | 0.54.0 |
| python-dotenv | 1.2.4 |
| openai | 3.24.0 |
| sentence-transformers | 6.1.0 |
| python-multipart | 0.0.32 |
| httpx | 0.28.1 |

Install both backend requirements files for the documented tests; the API-test subset alone misses currently imported NumPy/Pillow/multipart dependencies. The host should create an independent environment, validate supported wheels/SDK APIs and generate an appropriate lock after a clean install. Public model identifiers do not lock Hugging Face revisions; approve and record compatible model versions separately. No environment directory/cache or weights are bundled.
