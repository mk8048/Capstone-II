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
if ss -tlnp 2>/dev/null | grep -qE ':(5432|4222)\s'; then
  echo "  already up"
elif ssh -fN capstone-vm; then
  echo "  started 'ssh -fN capstone-vm', waiting for ports..."
  for i in {1..10}; do
    if ss -tlnp 2>/dev/null | grep -qE ':(5432|4222)\s'; then
      echo "  tunnel ready (${i}s)"
      break
    fi
    sleep 1
    if [ "$i" -eq 10 ]; then
      echo "  ⚠️  터널 포트(5432/4222) 안 올라옴. ~/.ssh/config 의 capstone-vm 확인."
    fi
  done
else
  echo "  ⚠️  'ssh -fN capstone-vm' 실패. 수동으로 띄우세요. 계속 진행함."
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
if [ -f "$ROOT/dashboard/.env" ]; then
  set -a; . "$ROOT/dashboard/.env"; set +a
  echo "  loaded dashboard/.env"
else
  echo "  ⚠️  dashboard/.env 없음 — 이미지 프록시용 MINIO_SECRET_KEY 미설정 (cp dashboard/.env.example dashboard/.env)"
fi
nohup .venv/bin/python dashboard_app.py > "$LOG_DIR/dashboard.log" 2>&1 &
DASH_PID=$!
echo "  PID: $DASH_PID, log: $LOG_DIR/dashboard.log"

sleep 2

echo ""
echo "[start] services started:"
echo "  main-server: http://127.0.0.1:8000  (PID $MAIN_PID)"
echo "  dashboard:   http://127.0.0.1:5001  (PID $DASH_PID)"
echo ""
echo "Stop: $ROOT/scripts/main_stop.sh"
echo "Logs: tail -F $LOG_DIR/main-server.log $LOG_DIR/dashboard.log"
