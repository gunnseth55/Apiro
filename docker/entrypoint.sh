#!/usr/bin/env bash
# =============================================================================
# docker/entrypoint.sh — Apiro container startup
# =============================================================================
# Executed as the Docker ENTRYPOINT. Does three things before starting the app:
#
#   1. Wait for the Ollama service to become healthy (up to 120 seconds).
#   2. Pull the configured PRIMARY_MODEL if it's not already cached in the
#      Ollama volume (ollama pull is idempotent — safe to run every startup).
#   3. Exec uvicorn to replace this shell with the app process (PID 1).
#
# Environment variables (set by docker-compose or .env):
#   OLLAMA_BASE_URL  — URL of the Ollama server
#   PRIMARY_MODEL    — model tag to pull and use
#   APP_HOST         — uvicorn bind host  (default: 0.0.0.0)
#   APP_PORT         — uvicorn bind port  (default: 8000)
# =============================================================================

set -euo pipefail

OLLAMA_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
MODEL="${PRIMARY_MODEL:-mistral:latest}"
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8000}"

echo ""
echo "=============================================="
echo "  Apiro Clinical AI Detective"
echo "=============================================="
echo "  Ollama URL : $OLLAMA_URL"
echo "  Model      : $MODEL"
echo "  App        : http://$HOST:$PORT"
echo "=============================================="
echo ""

# ── 1. Wait for Ollama ────────────────────────────────────────────────────────
echo "[*] Waiting for Ollama to be ready..."
MAX_WAIT=120
WAITED=0
until curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "[!] Ollama did not become ready within ${MAX_WAIT}s. Exiting."
        exit 1
    fi
    echo "    ... not ready yet (${WAITED}s elapsed)"
    sleep 5
    WAITED=$((WAITED + 5))
done
echo "[+] Ollama is ready."

# ── 2. Pull model if not already present ─────────────────────────────────────
echo "[*] Checking model: $MODEL ..."
MODELS_JSON=$(curl -sf "${OLLAMA_URL}/api/tags")
if echo "$MODELS_JSON" | grep -q "\"${MODEL}\""; then
    echo "[+] Model '$MODEL' already cached — skipping pull."
else
    echo "[*] Pulling model '$MODEL' (this may take several minutes on first run)..."
    curl -sf -X POST "${OLLAMA_URL}/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${MODEL}\", \"stream\": false}" \
        | tail -1 || true
    echo "[+] Model pull complete."
fi

# ── 3. Start the application ─────────────────────────────────────────────────
echo ""
echo "[*] Starting Apiro web server on http://${HOST}:${PORT} ..."
echo ""

exec uvicorn scripts.app:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers 1 \
    --log-level info
