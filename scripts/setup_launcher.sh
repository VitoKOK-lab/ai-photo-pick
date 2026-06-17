#!/bin/bash
# ── setup_launcher.sh ──────────────────────────────────────
# 在 Mac Mini 上執行一次，桌面就多一個雙擊即可的 JewelryDB.app
# 用法：bash scripts/setup_launcher.sh

set -e

PROJECT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PYTHON3="$(which python3)"
LOGDIR="$PROJECT/logs"
HELPER="$HOME/.jewelry_helper.sh"

echo "專案路徑：$PROJECT"
echo "Python3：  $PYTHON3"

# ── 建立後台執行的 helper script ──────────────────────────
mkdir -p "$LOGDIR"

cat > "$HELPER" << HELPER
#!/bin/bash
cd "$PROJECT"
mkdir -p logs

# 拉取最新代碼
git pull origin \$(git rev-parse --abbrev-ref HEAD) >> "$LOGDIR/update.log" 2>&1

# 如果有本地未推送的 commit，推上去
LOCAL_AHEAD=\$(git log origin/\$(git rev-parse --abbrev-ref HEAD)..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
if [ "\$LOCAL_AHEAD" -gt 0 ]; then
  git push origin \$(git rev-parse --abbrev-ref HEAD) >> "$LOGDIR/update.log" 2>&1
fi

# 重啟伺服器
pkill -f "uvicorn api.main:app" 2>/dev/null || true
sleep 1
nohup $PYTHON3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 \
    >> "$LOGDIR/uvicorn.log" 2>&1 &
disown \$!
HELPER

chmod +x "$HELPER"

# ── 建立 macOS .app（用 osacompile）─────────────────────
APPDIR="$HOME/Desktop/JewelryDB.app"
TMP_SCPT="/tmp/_jewelry.applescript"

cat > "$TMP_SCPT" << APPLESCRIPT
on run
  do shell script "$HELPER"
  delay 1.5
  display notification "已同步並重啟伺服器 ✓" with title "Jewelry DB" sound name "Glass"
end run
APPLESCRIPT

osacompile -o "$APPDIR" "$TMP_SCPT"
rm -f "$TMP_SCPT"

echo ""
echo "✅ 完成！桌面已出現 JewelryDB.app"
echo ""
echo "以後只要雙擊 JewelryDB.app："
echo "  → 自動同步代碼（上傳/下載）"
echo "  → 自動重啟伺服器"
echo "  → 完成後跳出 macOS 通知"
