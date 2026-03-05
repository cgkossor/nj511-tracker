# NJ 511 GSP Traffic Monitor

Polls [511NJ.org](https://511nj.org) RSS feeds every 5 minutes for traffic events on the **Garden State Parkway** between **Exits 117–140** (northbound and southbound). Sends email alerts via Gmail when relevant events are detected.

## Alert Types

| Category | Emoji | Trigger | When Sent |
|---|---|---|---|
| **Incident** | 🚨 | Any matching event | Immediately, once per day per incident |
| **Congestion** | 🚗 | Any matching event | Immediately, once per day |
| **Weather** | 🌧️ | Any matching event | Immediately, once per day |
| **Construction** | 🚧 | Lane closure keywords required | When active or starting within 30 min |
| **Special Event** | 🎪 | Any matching event | When active or starting within 30 min |
| **Planned** | 📋 | Lane closure keywords required | When active or starting within 30 min |

## Filtering Rules

An event triggers an alert only if **all** of these are true:

1. **Road** — "Garden State Parkway" appears in the RSS title
2. **Direction** — "northbound" or "southbound" in the title
3. **Exit range** — At least one exit number between 117–140 mentioned
4. **Lane closure** (construction/planned only) — Description contains "lane closed", "lane blocked", etc.
5. **Schedule** (non-urgent only) — Event is currently active or starts within 30 minutes
6. **Dedup** — Not already alerted today for this incident

## Email Format

Alerts are sent as HTML emails with a structured table:

```
Subject: 🚧 GSP Construction:  ⬇️ Exit 136 → 132

🚧 CONSTRUCTION ALERT

📍 Where:   Garden State Parkway Southbound
🔢 Exits:   136 → 132
📅 Dates:   Monday March 2nd, 2026 – Saturday March 7th, 2026
⏰ When:    Mon–Fri, 08:00 PM → 06:00 AM
🚗 Impact:  1 Left lane of 5 lanes closed
📋 Status:  ⚠️ Starting in 25m
🔧 Type:    construction

🔗 Details
```

## Setup

1. Clone the repo on your server
2. Install dependencies: `pip install -r requirements.txt`
3. Create `config.py` with your settings:

```python
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "you@gmail.com"
EMAIL_TO = "you@gmail.com"
EMAIL_PASSWORD = "your-app-password"

ROAD_NAME = "Garden State Parkway"
EXIT_MIN = 117
EXIT_MAX = 140
DIRECTIONS = ["northbound", "southbound"]

POLL_INTERVAL = 5          # minutes
ALERT_LEAD_MINUTES = 30    # alert before scheduled events start
```

4. Install the systemd service:
```bash
sudo cp gsp-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gsp-monitor
sudo systemctl start gsp-monitor
```

## Deployment

From your local machine, run the PowerShell deploy script:

```powershell
.\deploy.ps1
```

This pushes to GitHub, pulls on the VM, installs dependencies, and restarts the systemd service.

## Useful Commands

```bash
sudo systemctl status gsp-monitor    # check if running
sudo systemctl restart gsp-monitor   # restart
journalctl -u gsp-monitor -f         # view live logs
```
