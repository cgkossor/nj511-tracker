$SSH_KEY = "C:\Users\cgkos\Documents\recgov_scanner\ssh-key-2026-02-24.key"
$SERVER = "ubuntu@138.2.214.121"
$REMOTE_DIR = "/home/ubuntu/nj511-tracker"

Write-Host "Pushing to GitHub..."
git push

Write-Host "Pulling on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && git pull"

Write-Host "Installing dependencies on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && pip install -r requirements.txt -q"

Write-Host "Clearing alert history and restarting monitor on VM..."
ssh -i $SSH_KEY $SERVER "pkill -f 'python3 $REMOTE_DIR/monitor.py' 2>/dev/null; sleep 1; rm -f $REMOTE_DIR/seen_incidents.db; cd $REMOTE_DIR && setsid python3 $REMOTE_DIR/monitor.py >> $REMOTE_DIR/monitor.log 2>&1 < /dev/null &"

Start-Sleep -Seconds 3

Write-Host "Deployed! Checking status..."
ssh -i $SSH_KEY $SERVER "ps aux | grep '$REMOTE_DIR/monitor.py' | grep -v grep"
