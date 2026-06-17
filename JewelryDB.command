#!/bin/bash
# 雙擊自動執行，不需要任何輸入
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"
mkdir -p logs

echo "▶ 同步代碼…"
git pull origin "$(git rev-parse --abbrev-ref HEAD)" 2>&1

LOCAL_AHEAD=$(git log "origin/$(git rev-parse --abbrev-ref HEAD)"..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
if [ "$LOCAL_AHEAD" -gt 0 ]; then
  echo "▶ 推送本地更新…"
  git push origin "$(git rev-parse --abbrev-ref HEAD)" 2>&1
fi

echo "▶ 重啟伺服器…"
pkill -f "uvicorn api.main:app" 2>/dev/null || true
sleep 1
nohup python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 >> logs/uvicorn.log 2>&1 &
disown $!

sleep 1.5
echo "✅ 完成！http://localhost:8000"
osascript -e 'display notification "已同步並重啟 ✓" with title "Jewelry DB" sound name "Glass"' 2>/dev/null
sleep 2
