#!/bin/bash
# ListenClaw demo launcher — one command, one ngrok tunnel
# Usage: bash scripts/start-demo.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Backend ───────────────────────────────────────────────────────────────────
echo "[1/3] Starting backend on :8765..."
source "$ROOT/.venv/bin/activate" 2>/dev/null || true
cd "$ROOT"
python -m uvicorn server.main:app --host 0.0.0.0 --port 8765 &
BACKEND_PID=$!

# ── Frontend (with WS proxy) ──────────────────────────────────────────────────
echo "[2/3] Building frontend..."
cd "$ROOT/web"
npm run build 2>&1 | tail -5
echo "Starting frontend + WS proxy on :3000..."
node server-proxy.mjs &
FRONTEND_PID=$!

# ── Single ngrok tunnel ───────────────────────────────────────────────────────
echo "[3/3] Starting ngrok tunnel..."
sleep 3

(
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
  ngrok http 3000 --log stdout 2>&1 | grep -E "url=|Tunnel established|started tunnel" &
  NGROK_PID=$!
  sleep 3
  # Fetch URL from ngrok API
  URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | grep -o '"public_url":"https://[^"]*"' \
    | head -1 \
    | cut -d'"' -f4)
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " ListenClaw Demo Running"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if [ -n "$URL" ]; then
    echo " Frontend : $URL"
    echo " WS URL   : ${URL/https/wss}/ws"
    echo ""
    echo " Phone: open $URL"
    echo " WS is already proxied — no settings change needed!"
  else
    echo " Check http://127.0.0.1:4040 for the HTTPS URL"
    echo " WS is proxied through the same URL — no settings change needed!"
  fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " Press Ctrl+C to stop everything"
  wait $NGROK_PID
)

# ── Cleanup ───────────────────────────────────────────────────────────────────
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; pkill -f ngrok; exit" INT TERM
wait $BACKEND_PID
