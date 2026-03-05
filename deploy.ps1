$SSH_KEY = "C:\Users\cgkos\Documents\recgov_scanner\ssh-key-2026-02-24.key"
$SERVER = "ubuntu@138.2.214.121"
$REMOTE_DIR = "/home/ubuntu/nj511-tracker"

Write-Host "Pushing to GitHub..."
git push

Write-Host "Pulling on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && git pull"

Write-Host "Installing dependencies on VM..."
ssh -i $SSH_KEY $SERVER "cd $REMOTE_DIR && pip install -r requirements.txt -q"

Write-Host "Installing systemd service..."
ssh -i $SSH_KEY $SERVER "sudo cp $REMOTE_DIR/gsp-monitor.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable gsp-monitor"

Write-Host "Restarting monitor..."
ssh -i $SSH_KEY $SERVER "sudo systemctl restart gsp-monitor"

Start-Sleep -Seconds 3

Write-Host "Deployed! Checking status..."
ssh -i $SSH_KEY $SERVER "sudo systemctl status gsp-monitor --no-pager"
