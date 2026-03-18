#!/bin/bash
# ListenClaw demo launcher
# Starts backend, frontend, and ngrok tunnels in one command
# Usage: bash scripts/start-demo.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Backend ───────────────────────────────────────────────────────────────────
echo "[1/3] Starting backend..."
source "$ROOT/.venv/bin/activate" 2>/dev/null || true
cd "$ROOT"
python -m uvicorn server.main:app --host 0.0.0.0 --port 8765 &
BACKEND_PID=$!

# ── Frontend ──────────────────────────────────────────────────────────────────
echo "[2/3] Starting frontend..."
cd "$ROOT/web"
npm run dev -- --hostname 0.0.0.0 &
FRONTEND_PID=$!

# ── ngrok ─────────────────────────────────────────────────────────────────────
echo "[3/3] Starting ngrok tunnels (proxy disabled for ngrok only)..."
sleep 3  # wait for servers to start

# Unset proxy only for this subshell — your main terminal stays unaffected
(
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
  NGROK_DEFAULT="$HOME/Library/Application Support/ngrok/ngrok.yml"
  ngrok start --all --config "$NGROK_DEFAULT" --config "$ROOT/scripts/ngrok.yml" 2>&1 &
  NGROK_PID=$!
  echo "ngrok PID: $NGROK_PID"
)

# ── Wait & print URLs ─────────────────────────────────────────────────────────
sleep 4
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ListenClaw Demo Running"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ngrok dashboard: http://127.0.0.1:4040"
echo " (check dashboard for HTTPS URLs)"
echo ""
echo " Phone setup:"
echo " 1. Open the frontend HTTPS URL in Safari"
echo " 2. Go to Settings, set WS URL to:"
echo "    wss://<backend-ngrok-url>/ws"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Press Ctrl+C to stop everything"
echo ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; pkill -f ngrok; exit" INT TERM

wait $BACKEND_PID
