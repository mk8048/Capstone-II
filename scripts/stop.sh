#!/bin/bash
# main-server + dashboard 종료.

echo "[stop] stopping services..."

if pkill -f "uvicorn app.main:app" 2>/dev/null; then
  echo "  main-server stopped"
else
  echo "  main-server not running"
fi

if pkill -f "dashboard_app.py" 2>/dev/null; then
  echo "  dashboard stopped"
else
  echo "  dashboard not running"
fi

sleep 1

# 종료 확인
if ss -tlnp 2>/dev/null | grep -qE ':(8000|5001)\s'; then
  echo "  ⚠️  여전히 8000 또는 5001 listen 중. 수동 확인 필요."
  ss -tlnp 2>/dev/null | grep -E ':(8000|5001)\s'
else
  echo "  ✅ 8000, 5001 모두 정리됨"
fi
