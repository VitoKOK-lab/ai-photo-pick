#!/bin/bash
# setup_tunnel.sh - 在 Mac mini 上設定 Cloudflare Tunnel
# 執行一次即可，之後開機自動連線
#
# 前置：需有 Cloudflare 帳號並在 Zero Trust 建立 Tunnel
# 參考：https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

set -e

TUNNEL_NAME="jewelry-db"
LOCAL_PORT=8000

echo "=== 1. 安裝 cloudflared ==="
if ! command -v cloudflared &>/dev/null; then
    brew install cloudflared
fi
cloudflared --version

echo ""
echo "=== 2. 登入 Cloudflare（會開瀏覽器授權） ==="
cloudflared tunnel login

echo ""
echo "=== 3. 建立 Tunnel ==="
cloudflared tunnel create "$TUNNEL_NAME"
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

echo ""
echo "=== 4. 設定 config ==="
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<EOF
tunnel: $TUNNEL_ID
credentials-file: /Users/$USER/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: jewelry.yourdomain.com   # ← 改成你的 domain
    service: http://localhost:$LOCAL_PORT
  - service: http_status:404
EOF
echo "config 已寫入 ~/.cloudflared/config.yml"
echo "請把 hostname 改成你的實際 domain 再繼續。"

echo ""
echo "=== 5. 設定 DNS ==="
echo "執行以下指令把 domain 指向 Tunnel："
echo "  cloudflared tunnel route dns $TUNNEL_NAME jewelry.yourdomain.com"

echo ""
echo "=== 6. 設為開機自動啟動 ==="
cloudflared service install
echo "cloudflared 已加入 launchd，開機自動啟動。"

echo ""
echo "=== 完成 ==="
echo "本機測試：cloudflared tunnel run $TUNNEL_NAME"
echo "之後瀏覽 https://jewelry.yourdomain.com"
