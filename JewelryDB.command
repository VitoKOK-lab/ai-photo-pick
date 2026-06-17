#!/bin/bash
# ────────────────────────────────────────────────────────
#  Jewelry DB 管理工具
#  把這個檔案放到桌面，雙擊即可
# ────────────────────────────────────────────────────────

# 顏色
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m'
C='\033[0;36m' B='\033[1m'    N='\033[0m'

# 自動定位專案目錄（不管放哪裡都能找到）
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"
mkdir -p logs

# ── 函式 ─────────────────────────────────────────────────

show_status() {
  local PID
  PID=$(pgrep -f "uvicorn api.main:app" | head -1)
  if [ -n "$PID" ]; then
    echo -e "  狀態：${G}●  運行中 (PID: $PID)${N}  →  http://localhost:8000"
  else
    echo -e "  狀態：${R}●  未運行${N}"
  fi
}

start_server() {
  pkill -f "uvicorn api.main:app" 2>/dev/null
  sleep 0.8
  nohup python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 \
      > "$DIR/logs/uvicorn.log" 2>&1 &
  local PID=$!
  sleep 1.5
  if kill -0 "$PID" 2>/dev/null; then
    echo -e "\n  ${G}✓ 伺服器已啟動 (PID: $PID)${N}"
    echo -e "  ${C}→  http://localhost:8000${N}"
    # macOS 系統通知
    osascript -e 'display notification "伺服器已啟動 ✓  http://localhost:8000" with title "Jewelry DB" sound name "Glass"' 2>/dev/null
  else
    echo -e "\n  ${R}✗ 啟動失敗，查看日誌：${N}"
    tail -20 "$DIR/logs/uvicorn.log"
  fi
}

do_update() {
  local BRANCH
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
  echo -e "\n  ${C}▶ git pull origin $BRANCH …${N}"
  git pull origin "$BRANCH"
  if [ $? -ne 0 ]; then
    echo -e "\n  ${R}✗ Pull 失敗，請先解決衝突後再試${N}"
    return 1
  fi
  echo -e "  ${G}✓ 代碼已更新${N}"
  return 0
}

do_push() {
  local BRANCH
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
  echo -e "\n  ${C}▶ git push origin $BRANCH …${N}"
  git push origin "$BRANCH"
  if [ $? -ne 0 ]; then
    echo -e "\n  ${R}✗ Push 失敗${N}"
  else
    echo -e "  ${G}✓ 已推送到 $BRANCH${N}"
  fi
}

# ── 主選單 ───────────────────────────────────────────────

while true; do
  clear
  echo ""
  echo -e "${B}${C}  ╔══════════════════════════════════╗${N}"
  echo -e "${B}${C}  ║       Jewelry DB  管理工具        ║${N}"
  echo -e "${B}${C}  ╚══════════════════════════════════╝${N}"
  echo ""
  show_status
  echo ""
  echo -e "  ${B}選擇操作：${N}"
  echo ""
  echo "   1   拉取最新代碼 + 重啟伺服器   ← 最常用"
  echo "   2   只重啟伺服器"
  echo "   3   停止伺服器"
  echo "   ─────────────────────────────"
  echo "   4   推送本地代碼到 GitHub"
  echo "   5   查看 Git 狀態"
  echo "   ─────────────────────────────"
  echo "   6   在瀏覽器打開"
  echo "   7   查看即時日誌 (Ctrl+C 返回)"
  echo ""
  echo "   0   離開"
  echo ""
  read -rp "  → " CHOICE
  echo ""

  case "$CHOICE" in
  1)
    do_update && start_server
    echo ""
    read -rp "  按 Enter 返回選單…"
    ;;
  2)
    echo -e "  ${C}▶ 重啟伺服器…${N}"
    start_server
    echo ""
    read -rp "  按 Enter 返回選單…"
    ;;
  3)
    if pkill -f "uvicorn api.main:app" 2>/dev/null; then
      echo -e "  ${G}✓ 伺服器已停止${N}"
    else
      echo -e "  ${Y}伺服器本來就沒在運行${N}"
    fi
    echo ""
    read -rp "  按 Enter 返回選單…"
    ;;
  4)
    do_push
    echo ""
    read -rp "  按 Enter 返回選單…"
    ;;
  5)
    echo -e "  ${C}▶ Git 狀態：${N}"
    git status --short
    echo ""
    git log --oneline -5
    echo ""
    read -rp "  按 Enter 返回選單…"
    ;;
  6)
    open "http://localhost:8000" 2>/dev/null || \
      echo -e "  ${Y}請確認伺服器運行中後再試${N}"
    ;;
  7)
    echo -e "  ${C}即時日誌（Ctrl+C 返回選單）：${N}"
    echo ""
    trap '' INT
    tail -f "$DIR/logs/uvicorn.log" 2>/dev/null || echo "  尚無日誌"
    trap - INT
    ;;
  0)
    echo "  再見 👋"
    echo ""
    exit 0
    ;;
  *)
    echo -e "  ${R}無效選項，請重新輸入${N}"
    sleep 1
    ;;
  esac
done
