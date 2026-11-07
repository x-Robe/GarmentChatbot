# Build on linux/amd64 for Cloud Run. No credentials are accepted as build args.
FROM python:3.12-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
COPY deployment/cloudrun/constraints.txt ./constraints.txt
RUN python -m venv /venv \
 && TORCH_VERSION=$(/venv/bin/python -c "from pathlib import Path; print(next(x.split('==')[1] for x in Path('constraints.txt').read_text().splitlines() if x.startswith('torch==')))") \
 && /venv/bin/pip install "torch==${TORCH_VERSION}" --index-url https://download.pytorch.org/whl/cpu \
 && /venv/bin/pip install -r requirements.txt -c constraints.txt \
 && /venv/bin/pip check \
 && /venv/bin/python -c "import torch; assert torch.version.cuda is None, 'CPU wheel required'"

FROM python:3.12-slim-bookworm AS runtime
ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
    HF_HOME=/opt/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    API_MAX_INFLIGHT=1 API_REQUESTS_PER_MINUTE=30
RUN apt-get update \
 && apt-get install --yes --no-install-recommends libgomp1 libstdc++6 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 garment \
 && useradd --uid 10001 --gid garment --create-home garment
COPY --from=dependencies /venv /venv
WORKDIR /app
# Explicit allowlist: .env, Git history, logs, OAuth state and Mac tools never enter layers.
COPY --chown=garment:garment backend/api.py backend/chatbot.py backend/SKILL.md ./backend/
COPY --chown=garment:garment backend/src/ ./backend/src/
COPY --chown=garment:garment backend/data/samples/ ./backend/data/samples/
COPY --chown=garment:garment data/images/ ./data/images/
COPY --chown=garment:garment deployment/cloudrun/serve.py deployment/cloudrun/models.json ./deployment/cloudrun/
COPY --chown=garment:garment .cloudrun-models/ /opt/hf/hub/
USER garment
WORKDIR /app/backend
EXPOSE 8080
CMD ["python", "/app/deployment/cloudrun/serve.py"]
