#!/bin/bash
# setup_rclone.sh - 在 Mac mini 設定 rclone + Google Drive
# 執行一次即可
set -e

REMOTE_NAME="gdrive"

echo "=== 1. 安裝 rclone ==="
if ! command -v rclone &>/dev/null; then
    brew install rclone
fi
rclone --version

echo ""
echo "=== 2. 設定 Google Drive remote ==="
echo "會開瀏覽器讓你授權 Google 帳號，授權後自動完成。"
rclone config create "$REMOTE_NAME" drive scope drive

echo ""
echo "=== 3. 驗證連線 ==="
rclone lsd "$REMOTE_NAME": | head -10

echo ""
echo "=== 4. 初始化 Google Drive 目錄 ==="
rclone mkdir "$REMOTE_NAME:jewelry-db/originals"
rclone mkdir "$REMOTE_NAME:jewelry-db/db"
echo "目錄已建立：jewelry-db/originals 和 jewelry-db/db"

echo ""
echo "=== 5. 安裝備份 launchd ==="
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCHD_DIR"

sed "s|/Users/vito|$HOME|g" "$REPO_DIR/deploy/com.jewelrydb.backup.plist" \
    > "$LAUNCHD_DIR/com.jewelrydb.backup.plist"
launchctl load -w "$LAUNCHD_DIR/com.jewelrydb.backup.plist" 2>/dev/null || true
echo "備份排程已安裝（每天 02:00）"

echo ""
echo "=== 完成 ==="
echo "手動執行備份："
echo "  python -m scripts.backup"
echo "  python -m scripts.backup --db-only"
echo "  python -m scripts.backup --dry-run"
