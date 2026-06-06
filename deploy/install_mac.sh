#!/bin/bash
# install_mac.sh - Mac mini 首次部署腳本
# 使用方式：bash deploy/install_mac.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_HOME="$HOME"
LAUNCHD_DIR="$USER_HOME/Library/LaunchAgents"

echo "=== Jewelry DB - Mac mini 部署 ==="
echo "Repo: $REPO_DIR"
echo ""

# 1. 虛擬環境
if [ ! -d "$REPO_DIR/venv" ]; then
    echo "[1/5] 建立虛擬環境..."
    python3.11 -m venv "$REPO_DIR/venv"
fi
echo "[1/5] 安裝套件..."
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

# 2. 初始化 DB
echo "[2/5] 初始化資料庫..."
cd "$REPO_DIR" && "$REPO_DIR/venv/bin/python" scripts/01_init_db.py

# 3. 建立 .env（若不存在）
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "[3/5] 建立 .env..."
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "⚠  請編輯 .env 設定 JEWELRY_AUTH_TOKEN"
else
    echo "[3/5] .env 已存在，跳過"
fi

# 4. 安裝 launchd plists（替換路徑為實際路徑）
echo "[4/5] 安裝 launchd services..."
mkdir -p "$LAUNCHD_DIR"

for plist in api watcher; do
    src="$REPO_DIR/deploy/com.jewelrydb.$plist.plist"
    dst="$LAUNCHD_DIR/com.jewelrydb.$plist.plist"
    # 把 plist 裡的 /Users/vito 換成實際 home
    sed "s|/Users/vito|$USER_HOME|g" "$src" > "$dst"
    launchctl load -w "$dst" 2>/dev/null || true
    echo "  ✓ com.jewelrydb.$plist loaded"
done

# 5. 完成
echo "[5/5] 完成！"
echo ""
echo "  本機：http://localhost:8000"
echo "  同 WiFi：http://$(ipconfig getifaddr en0):8000"
echo ""
echo "  Log 位置："
echo "    tail -f $REPO_DIR/logs/api.log"
echo "    tail -f $REPO_DIR/logs/watcher.log"
echo ""
echo "  重啟服務："
echo "    launchctl kickstart -k gui/\$(id -u)/com.jewelrydb.api"
