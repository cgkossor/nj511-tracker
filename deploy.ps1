$SSH_KEY = "./ssh-key-2026-02-24.key"
$SERVER = "ubuntu@138.2.214.121"
$REMOTE_DIR = "/home/ubuntu/nj511-tracker"

Write-Host "Pushing to GitHub..."
git push

Write-Host "Pulling on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && git pull"

Write-Host "Installing dependencies on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && pip install -r requirements.txt -q"

Write-Host "Restarting monitor on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && pkill -f 'python3 monitor.py'; nohup python3 $REMOTE_DIR/monitor.py >> $REMOTE_DIR/monitor.log 2>&1 &"

Write-Host "Deployed! Checking status..."
ssh -i $SSH_KEY $SERVER "ps aux | grep 'monitor.py' | grep -v grep"
