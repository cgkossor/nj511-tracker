#!/bin/bash
SSH_KEY="./ssh-key-2026-02-24.key"
SERVER="ubuntu@138.2.214.121"
REMOTE_DIR="/home/ubuntu/nj511-tracker"

echo "🚀 Pushing to GitHub..."
git push

echo "📥 Pulling on VM..."
ssh -i "$SSH_KEY" "$SERVER" "cd $REMOTE_DIR && git pull"

echo "📦 Installing dependencies on VM..."
ssh -i "$SSH_KEY" "$SERVER" "cd $REMOTE_DIR && pip install -r requirements.txt -q"

echo "🔄 Restarting monitor on VM..."
ssh -i "$SSH_KEY" "$SERVER" "sudo systemctl restart gsp-monitor 2>/dev/null || (cd $REMOTE_DIR && pkill -f 'python3 monitor.py'; nohup python3 $REMOTE_DIR/monitor.py >> $REMOTE_DIR/monitor.log 2>&1 &)"

echo "✅ Deployed! Checking status..."
ssh -i "$SSH_KEY" "$SERVER" "ps aux | grep 'monitor.py' | grep -v grep"
