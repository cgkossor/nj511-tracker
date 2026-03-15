# NJ 511 GSP Tracker

Monitor **Garden State Parkway** traffic events via [511NJ.org](https://511nj.org) RSS feeds. Get real-time email alerts for incidents, congestion, and construction in your commute zone, plus a weekly digest with trend analysis.

## Features

- **Real-time alerts** — Email notifications for incidents, construction, congestion, and weather events matching your exit range and direction
- **Smart filtering** — Only alerts for events in your configured exit range, with schedule-aware timing for planned work
- **Landmark recognition** — Resolves GSP service areas (e.g., Colonia, Jon Bon Jovi) to exit numbers when the feed omits them
- **Express/Local distinction** — Alerts south of exit 123 indicate which lanes are affected
- **Event collection** — Logs all GSP events to SQLite for historical analysis
- **Weekly digest** — Sunday email summarizing the week's hotspots, commute patterns, and trends
- **HTML dashboard** — Local Plotly-based report with interactive charts

## Components

| File | Purpose |
|---|---|
| `monitor.py` | Real-time alert monitor (polls every 5 min, sends email alerts) |
| `collector.py` | Event collector (polls every 5 min, stores all GSP events in SQLite) |
| `digest.py` | Weekly digest email with cross-category analysis |
| `analysis.py` | Shared analysis functions (hotspots, trends, commute comparisons) |
| `dashboard.py` | Generates standalone HTML report with Plotly charts |
| `config.py` | Configuration (gitignored — contains credentials and alert filters) |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-user/nj511-tracker.git
cd nj511-tracker
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2. Create `config.py`

```python
# Email settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "you@gmail.com"
EMAIL_TO = "you@gmail.com"
EMAIL_PASSWORD = "your-gmail-app-password"

# Alert filters
ROAD_NAME = "Garden State Parkway"
EXIT_MIN = 117          # Southern boundary of your commute
EXIT_MAX = 140          # Northern boundary of your commute
DIRECTIONS = ["northbound", "southbound"]

# Landmark-to-exit mapping for feed entries without explicit exit numbers
LANDMARK_EXITS = {
    "colonia service area": (132, 135),
    "jon bon jovi service area": (120, 123),
}

# Timing
POLL_INTERVAL = 5                 # minutes
ALERT_LEAD_MINUTES = 30           # alert before scheduled work starts
CONGESTION_ALERT_AFTER_HOUR = 20  # only send congestion alerts after 8 PM ET
ALERT_COOLDOWN_HOURS = 18         # suppress re-alerts for same event

# Trend Tracker
TRACKER_DB = "gsp_congestion.db"
CONGESTION_DB = TRACKER_DB
COLLECTOR_POLL_INTERVAL = 5
DIGEST_HOUR = 20  # 8 PM ET — weekly digest (Sundays)
```

### 3. Run locally (for testing)

```bash
python monitor.py      # start alert monitor
python collector.py    # start event collector
python digest.py --now # send a test digest immediately
```

### 4. Deploy as services

Create systemd service files for `monitor.py`, `collector.py`, and `digest.py`. Example:

```ini
[Unit]
Description=NJ511 Traffic Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/nj511-tracker
ExecStart=/path/to/nj511-tracker/venv/bin/python -u monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nj511-monitor nj511-collector nj511-digest
```

## Alert Types

| Category | Feed | Trigger | When Sent |
|---|---|---|---|
| Incident | Active Incidents | Any matching event | Immediately |
| Congestion | Active Congestion | Any matching event | After configured hour only |
| Weather | Active Weather | Any matching event | Immediately |
| Construction | Active Construction | Lane closure keywords | When active or starting soon |
| Special Event | Active Special Events | Any matching event | When active or starting soon |
| Planned | Planned Construction | Lane closure keywords | When active or starting soon |

## Filtering Rules

An event triggers an alert only if **all** of these are true:

1. "Garden State Parkway" appears in the RSS title
2. Direction matches your config (northbound/southbound)
3. At least one exit number (or recognized landmark) falls within your exit range
4. For construction/planned: lane closure keywords present in the description
5. For scheduled events: currently active or starting within the lead time window
6. Not already alerted within the cooldown period

## Weekly Digest

Sent automatically on Sundays with:
- Week summary by category with busiest day
- Top incident and congestion hotspots
- Incident-congestion overlap sections
- NB vs SB commute comparison (morning/evening)
- Week-over-week trend by category

## Dashboard

Generate an interactive HTML report from collected data:

```bash
python dashboard.py              # all data
python dashboard.py --days 7     # last 7 days
python dashboard.py --days 90    # last 90 days
python dashboard.py --no-open    # don't auto-open browser
```

## Data

All events are stored in a SQLite database (`gsp_congestion.db`) with fields for category, direction, exit range, title, description, and timestamps. The `seen_incidents.db` database tracks alert deduplication.

## License

MIT
