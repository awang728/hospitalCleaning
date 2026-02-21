#!/bin/bash
# deploy_vultr.sh — Deploy CleanSight backend to a Vultr instance
#
# Prerequisites:
#   1. Create a Vultr account at vultr.com
#   2. Spin up an Ubuntu 22.04 instance ($6/mo Cloud Compute is fine for demo)
#      OR use a Cloud GPU instance for real Sphinx AI inference
#   3. Add your SSH public key to the instance
#   4. Set VULTR_IP below to your instance's IP address
#
# Usage:
#   chmod +x deploy_vultr.sh
#   ./deploy_vultr.sh

set -e

VULTR_IP="YOUR_VULTR_IP_HERE"   # ← paste your Vultr instance IP
REMOTE_USER="root"
REMOTE_DIR="/opt/cleansight"
APP_PORT=5000

echo "▶ Deploying CleanSight backend to Vultr ($VULTR_IP)..."

# ── 1. Copy backend files to server ──────────────────────────────────────────
echo "[1/6] Copying files..."
ssh $REMOTE_USER@$VULTR_IP "mkdir -p $REMOTE_DIR"
scp app.py sphinx_client.py vectorai_client.py requirements.txt .env \
    $REMOTE_USER@$VULTR_IP:$REMOTE_DIR/

# ── 2. Install dependencies ───────────────────────────────────────────────────
echo "[2/6] Installing Python dependencies..."
ssh $REMOTE_USER@$VULTR_IP << 'ENDSSH'
    apt-get update -qq
    apt-get install -y python3 python3-pip docker.io -qq
    pip3 install -r /opt/cleansight/requirements.txt -q
ENDSSH

# ── 3. Pull and start Actian VectorAI DB ─────────────────────────────────────
echo "[3/6] Starting Actian VectorAI DB container..."
ssh $REMOTE_USER@$VULTR_IP << 'ENDSSH'
    docker pull williamimoh/actian-vectorai-db:1.0b
    docker stop vectorai 2>/dev/null || true
    docker rm   vectorai 2>/dev/null || true
    docker run -d \
        --name vectorai \
        --restart unless-stopped \
        -p 50051:50051 \
        williamimoh/actian-vectorai-db:1.0b
    echo "VectorAI container started"
    sleep 3
    docker logs vectorai --tail 10
ENDSSH

# ── 4. Create systemd service for auto-restart ───────────────────────────────
echo "[4/6] Creating systemd service..."
ssh $REMOTE_USER@$VULTR_IP "cat > /etc/systemd/system/cleansight.service << 'EOF'
[Unit]
Description=CleanSight Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/cleansight
EnvironmentFile=/opt/cleansight/.env
ExecStart=/usr/local/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

# ── 5. Start the backend service ──────────────────────────────────────────────
echo "[5/6] Starting CleanSight service..."
ssh $REMOTE_USER@$VULTR_IP << ENDSSH
    systemctl daemon-reload
    systemctl enable cleansight
    systemctl restart cleansight
    sleep 2
    systemctl status cleansight --no-pager
ENDSSH

# ── 6. Open firewall port ─────────────────────────────────────────────────────
echo "[6/6] Opening firewall..."
ssh $REMOTE_USER@$VULTR_IP "ufw allow $APP_PORT/tcp 2>/dev/null || true"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✓  CleanSight backend is LIVE on Vultr!             ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Base URL:  http://$VULTR_IP:$APP_PORT               "
echo "║  Health:    http://$VULTR_IP:$APP_PORT/health        "
echo "║  Analyze:   POST http://$VULTR_IP:$APP_PORT/analyze  "
echo "║  Stream:    POST http://$VULTR_IP:$APP_PORT/analyze/stream "
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Now update BACKEND_URL in cleansight.html:"
echo "  var BACKEND_URL = 'http://$VULTR_IP:$APP_PORT';"
