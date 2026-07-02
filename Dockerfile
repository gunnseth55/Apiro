# =============================================================================
# Apiro — Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): install Python deps into a venv
#   Stage 2 (runtime): copy venv + app, pre-download HF models, expose port
#
# CPU-only PyTorch is used deliberately — keeps the image ~4 GB instead of ~8 GB.
# The model weights (all-mpnet-base-v2 + nli-MiniLM2-L6-H768) are baked into
# the image at build time so container startup is instant.
# =============================================================================

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.10-slim AS builder

WORKDIR /build

# System deps needed to compile some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# Install CPU-only PyTorch FIRST (separate layer for Docker cache efficiency).
# This avoids downloading the 2 GB CUDA wheel on every requirements change.
RUN pip install --no-cache-dir \
    torch==2.2.2 \
    --index-url https://download.pytorch.org/whl/cpu

# Copy and install remaining requirements (torch excluded — already installed above)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Install the apiro package itself in editable mode
COPY pyproject.toml .
COPY apiro/ ./apiro/
RUN pip install --no-cache-dir -e .


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.10-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY apiro/ ./apiro/
COPY scripts/ ./scripts/
COPY data/synthetic_case_1.json ./data/synthetic_case_1.json
COPY pyproject.toml .

# Copy Docker entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Pre-download HuggingFace models at build time so runtime startup is instant.
# These are baked into the image layer — no internet needed at container start.
ARG HF_TOKEN=""
ENV HF_TOKEN=${HF_TOKEN}
RUN python - <<'EOF'
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import os
token = os.environ.get("HF_TOKEN") or None
print("[BUILD] Downloading all-mpnet-base-v2 ...")
SentenceTransformer("all-mpnet-base-v2", token=token)
print("[BUILD] Downloading nli-MiniLM2-L6-H768 ...")
AutoTokenizer.from_pretrained("cross-encoder/nli-MiniLM2-L6-H768", token=token)
AutoModelForSequenceClassification.from_pretrained("cross-encoder/nli-MiniLM2-L6-H768", token=token)
print("[BUILD] Model download complete.")
EOF

# Default environment (overridden by docker-compose / .env)
ENV OLLAMA_BASE_URL="http://ollama:11434" \
    PRIMARY_MODEL="mistral:latest" \
    EMBED_MODEL="all-mpnet-base-v2" \
    CHROMA_COLLECTION="apiro_corpus" \
    RAG_TOP_K="6" \
    MAX_TRAVERSAL_DEPTH="8" \
    MAX_NODES_PER_RUN="30" \
    N_CHILD_HYPOTHESES="3" \
    APP_HOST="0.0.0.0" \
    APP_PORT="8000" \
    CHROMA_DIR="/app/data/chroma_db" \
    LOG_DIR="/app/data/logs" \
    DATA_DIR="/app/data" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1"

# Expose web port
EXPOSE 8000

# Health check — used by docker-compose depends_on
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -sf http://localhost:8000/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
