#!/bin/bash
# main-server + dashboard를 함께 시작한다.
# 순서: main-server 먼저 (dashboard가 시작 시 main-server /events 호출).

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

echo "[start] stopping existing services..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "dashboard_app.py" 2>/dev/null || true
sleep 1

echo "[start] checking SSH tunnel (5432, 4222)..."
if ! ss -tlnp 2>/dev/null | grep -qE ':(5432|4222)\s'; then
  echo "  ⚠️  SSH 터널 안 떠 있음. 'ssh -fN capstone-vm'로 먼저 띄우세요."
  echo "  계속 진행하지만 PG/NATS 연결 실패할 수 있음."
fi

echo "[start] starting main-server..."
cd "$ROOT/main-server"
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  > "$LOG_DIR/main-server.log" 2>&1 &
MAIN_PID=$!
echo "  PID: $MAIN_PID, log: $LOG_DIR/main-server.log"

echo "[start] waiting for main-server /health..."
for i in {1..15}; do
  if curl -sf -m 1 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "  ready (${i}s)"
    break
  fi
  sleep 1
  if [ "$i" -eq 15 ]; then
    echo "  ⚠️  15초 대기 후에도 /health 응답 없음. log 확인하세요."
  fi
done

echo "[start] starting dashboard..."
cd "$ROOT/dashboard"
nohup .venv/bin/python dashboard_app.py > "$LOG_DIR/dashboard.log" 2>&1 &
DASH_PID=$!
echo "  PID: $DASH_PID, log: $LOG_DIR/dashboard.log"

sleep 2

echo ""
echo "[start] services started:"
echo "  main-server: http://127.0.0.1:8000  (PID $MAIN_PID)"
echo "  dashboard:   http://127.0.0.1:5001  (PID $DASH_PID)"
echo ""
echo "Stop: $ROOT/scripts/stop.sh"
echo "Logs: tail -F $LOG_DIR/main-server.log $LOG_DIR/dashboard.log"
