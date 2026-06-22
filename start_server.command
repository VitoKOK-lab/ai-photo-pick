#!/bin/bash
# ─────────────────────────────────────────────
#  Tahir Zainab Selection  —  伺服器啟動
#  放到桌面後，第一次執行：在 Terminal 輸入
#    chmod +x ~/Desktop/start_server.command
# ─────────────────────────────────────────────

PROJECT_DIR="/Users/vitomini/ai-photo-pick"   # ← 若資料夾名稱不同請改這裡

cd "$PROJECT_DIR" || {
    osascript -e 'display dialog "❌ 找不到專案目錄，請確認路徑是否正確。" buttons {"OK"} default button 1'
    exit 1
}

# 停掉舊的 uvicorn（避免 port 衝突）
pkill -f "uvicorn api.main:app" 2>/dev/null
sleep 1

clear
echo "==========================================="
echo "  Tahir Zainab Selection  伺服器已啟動"
echo "  本機：  http://localhost:8000"
echo "  區網：  http://$(ipconfig getifaddr en0 2>/dev/null || echo 'xxx.xxx.x.x'):8000"
echo "==========================================="
echo ""
echo "  關閉這個視窗 = 停止伺服器"
echo ""

python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
