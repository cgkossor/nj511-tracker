# NJ 511 GSP Traffic Monitor

Polls [511NJ.org](https://511nj.org) RSS feeds every 5 minutes for traffic events on the **Garden State Parkway** between **Exits 117–140** (northbound and southbound). Sends email alerts via Gmail when relevant events are detected.

## Alert Types

| Category | Emoji | Trigger | When Sent |
|---|---|---|---|
| **Incident** | 🚨 | Any matching event | Immediately, once per day per incident |
| **Congestion** | 🚗 | Any matching event | After 8 PM ET only, once per day |
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
CONGESTION_ALERT_AFTER_HOUR = 20  # only send congestion alerts at or after this hour (24h, local time)
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

---

## Congestion Trend Tracker

A separate system that monitors the **full length of the GSP** to collect congestion data and analyze trends over time.

### Components

| File | Purpose | Runs On |
|---|---|---|
| `collector.py` | Polls congestion feed every 5 min, stores all GSP events in SQLite | VM (systemd) |
| `analysis.py` | Shared analysis functions (worst sections, NB vs SB, commute patterns, etc.) | Imported |
| `digest.py` | Sends a daily HTML email digest with key stats | VM (cron/schedule) |
| `dashboard.py` | Generates a standalone HTML report with interactive Plotly charts | Local |

### Analysis Capabilities

- **Worst Sections** — Which exit ranges have the most congestion events
- **NB vs SB by Time of Day** — Direction comparison by hour
- **Commute Comparison** — Morning (5-10 AM) vs Evening (3-8 PM) by direction
- **Day of Week Patterns** — Weekday vs weekend congestion
- **Duration Analysis** — How long congestion persists by section
- **Weekly Trends** — Is congestion getting better or worse over time
- **Peak Hours Heatmap** — Hour x day-of-week congestion grid

### VM Setup (Collector + Digest)

```bash
# Install the collector service
sudo cp gsp-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gsp-collector
sudo systemctl start gsp-collector

# Run digest on a daily cron (e.g., 9 PM)
crontab -e
# Add: 0 21 * * * cd /home/ubuntu/nj511-tracker && python3 digest.py --now
```

### Local Dashboard

```bash
# Sync the DB from the VM
scp ubuntu@your-vm:~/nj511-tracker/gsp_congestion.db .

# Generate the report (opens in browser)
python dashboard.py

# Options
python dashboard.py --days 7          # last 7 days only
python dashboard.py --days 90         # last 90 days
python dashboard.py --no-open         # don't auto-open browser
python dashboard.py --output my.html  # custom output file
```
