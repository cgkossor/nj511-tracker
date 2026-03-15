# NJ 511 GSP Traffic Monitor & Trend Tracker

Two systems running on a VM that monitor the **Garden State Parkway** via [511NJ.org](https://511nj.org) RSS feeds:

1. **Alert Monitor** (`monitor.py`) — Emails you about incidents, congestion, and construction near Exits 117–140
2. **Trend Tracker** (`collector.py`) — Logs ALL GSP events (full parkway) for analysis, with a daily digest email and local HTML dashboard

---

## Deployment

### How to deploy code changes

From your local machine (PowerShell):

```powershell
git add .
git commit -m "description of changes"
.\deploy.ps1
```

This does the following automatically:
1. Pushes your commit to GitHub
2. Pulls the latest code on the VM
3. Installs any new pip dependencies
4. Copies and enables both systemd services
5. Restarts both `gsp-monitor` and `gsp-collector`

**Note:** `config.py` is gitignored (contains passwords). If you add new config values, you must manually edit `config.py` on the VM:

```bash
nano ~/nj511-tracker/config.py
```

---

## Alert Monitor (`monitor.py`)

Polls every 5 minutes for events on GSP Exits 117–140. Sends email alerts via Gmail.

### Alert Types

| Category | Trigger | When Sent |
|---|---|---|
| 🚨 **Incident** | Any matching event | Immediately, once per day |
| 🚗 **Congestion** | Any matching event | After 8 PM ET only |
| 🌧️ **Weather** | Any matching event | Immediately, once per day |
| 🚧 **Construction** | Lane closure keywords | When active or starting within 30 min |
| 🎪 **Special Event** | Any matching event | When active or starting within 30 min |
| 📋 **Planned** | Lane closure keywords | When active or starting within 30 min |

### Filtering Rules

An event triggers an alert only if **all** of these are true:

1. "Garden State Parkway" in the RSS title
2. "northbound" or "southbound" in the title
3. At least one exit number between 117–140
4. Lane closure keywords (construction/planned only)
5. Currently active or starting within 30 min (non-urgent only)
6. For overnight windows (e.g. 8 PM–6 AM), the early-morning hours on the first date and evening hours on the last date are excluded (they belong to sessions outside the date range)
7. Not already alerted within 18 hours

---

## Trend Tracker

Collects ALL GSP events (full parkway, all 6 feed types) every 5 minutes into a SQLite database for trend analysis. All times displayed in ET, dates as "Mar 5, 2026".

### Components

| File | Purpose | Runs On |
|---|---|---|
| `collector.py` | Polls all 6 feeds every 5 min, stores GSP events in SQLite | VM (systemd) |
| `analysis.py` | Shared analysis functions with ET timezone support | Imported |
| `digest.py` | Daily email digest with cross-category analysis | VM (cron) |
| `dashboard.py` | Generates standalone HTML report with Plotly charts | Local |

### Feeds Collected

| Category | What it captures |
|---|---|
| 🚨 Incident | Crashes, breakdowns, hazards |
| 🚗 Congestion | Slowdowns, stop-and-go traffic |
| 🚧 Construction | Active construction zones |
| 🌧️ Weather | Weather-related events |
| 🎪 Special Event | Sporting events, concerts, etc. |
| 📋 Planned | Upcoming construction and events |

### Analysis Capabilities

**Overview:**
- Events by category breakdown
- All events by hour of day (stacked by category)
- Section severity ranking (composite across all types)

**Incident Analysis:**
- Incident hotspots (worst sections)
- Incident vs congestion correlation (scatter plot)
- Simultaneous incident + congestion overlap

**Congestion Analysis:**
- Most congested sections
- NB vs SB by hour of day (ET)
- Morning vs evening commute comparison by direction
- Day of week patterns

**Trends & Patterns:**
- Peak hours heatmap (hour x day of week)
- Weekly trend by category
- Congestion duration distribution

### Daily Digest Email

Sent automatically at 9 PM ET with:
- Yesterday's events by category
- Top incident and congestion hotspots (7 days)
- Incident-congestion overlap sections
- NB vs SB commute comparison
- Weekly trend by category (week-over-week change)

### Local Dashboard

After data accumulates, sync the DB and generate the report:

```powershell
scp user@your-vm:~/nj511-tracker/gsp_congestion.db .
python dashboard.py
```

Options:

```powershell
python dashboard.py --days 7          # last 7 days only
python dashboard.py --days 90         # last 90 days
python dashboard.py --no-open         # don't auto-open browser
python dashboard.py --output my.html  # custom output filename
```

---

## Setup (from scratch)

### 1. Clone and install

```bash
git clone https://github.com/cgkossor/nj511-tracker.git
cd nj511-tracker
pip install -r requirements.txt
```

### 2. Create `config.py`

```python
# Email settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "you@gmail.com"
EMAIL_TO = "you@gmail.com"
EMAIL_PASSWORD = "your-app-password"

# Alert filters
ROAD_NAME = "Garden State Parkway"
EXIT_MIN = 117
EXIT_MAX = 140
DIRECTIONS = ["northbound", "southbound"]

# Poll interval (minutes)
POLL_INTERVAL = 5
ALERT_LEAD_MINUTES = 30
CONGESTION_ALERT_AFTER_HOUR = 20  # 8 PM ET

# Trend Tracker
TRACKER_DB = "gsp_congestion.db"
CONGESTION_DB = TRACKER_DB
COLLECTOR_POLL_INTERVAL = 5
DIGEST_HOUR = 21  # 9 PM ET
```

### 3. Set up daily digest cron

```bash
crontab -e
# Add: 0 2 * * * cd /home/ubuntu/nj511-tracker && python3 digest.py --now
```

(0 2 UTC = 9 PM ET during EST)

---

## Useful Commands

```bash
# Check services
sudo systemctl status gsp-monitor gsp-collector

# View logs
journalctl -u gsp-monitor -f
journalctl -u gsp-collector -f

# Restart services
sudo systemctl restart gsp-monitor gsp-collector

# Check collected data
sqlite3 gsp_congestion.db "SELECT category, COUNT(*) FROM events GROUP BY category;"

# Send a test digest
python3 digest.py --now
```
