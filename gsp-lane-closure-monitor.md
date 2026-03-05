# GSP Lane Closure Email Alert Monitor

A Python script that polls the 511NJ feed every 5 minutes and emails you when a lane closure is detected on the Garden State Parkway between exits 123–138 (NB & SB).

---

## Project Structure

```
gsp-monitor/
├── monitor.py          # Main polling script
├── config.py           # Your settings (email, exits, interval)
├── seen_incidents.db   # SQLite DB (auto-created on first run)
├── requirements.txt    # Python dependencies
└── README.md
```

---

## Setup

### 1. Install Dependencies

```bash
pip install requests feedparser schedule
```

Or use the `requirements.txt`:

```
requests
feedparser
schedule
```

```bash
pip install -r requirements.txt
```

---

### 2. `config.py`

```python
# Email settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "your_gmail@gmail.com"
EMAIL_TO   = "your_gmail@gmail.com"
EMAIL_PASSWORD = "your_app_password"  # Use a Gmail App Password, not your real password

# Alert filters
ROAD_NAME  = "Garden State Parkway"
EXIT_MIN   = 123
EXIT_MAX   = 138
DIRECTIONS = ["northbound", "southbound"]  # or just one

# Poll interval (minutes)
POLL_INTERVAL = 5
```

> **Gmail App Password**: Go to myaccount.google.com → Security → 2-Step Verification → App Passwords. Generate one for "Mail".

---

### 3. `monitor.py`

```python
import requests
import sqlite3
import smtplib
import schedule
import time
import re
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from datetime import datetime
import config

FEED_URL = "https://511nj.org/api/GetAllIncidents?format=xml"

# --- Database ---
def init_db():
    conn = sqlite3.connect("seen_incidents.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            incident_id TEXT PRIMARY KEY,
            first_seen   TEXT
        )
    """)
    conn.commit()
    return conn

def already_seen(conn, incident_id):
    row = conn.execute("SELECT 1 FROM seen WHERE incident_id = ?", (incident_id,)).fetchone()
    return row is not None

def mark_seen(conn, incident_id):
    conn.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)", (incident_id, datetime.now().isoformat()))
    conn.commit()

# --- Feed Parsing ---
def fetch_incidents():
    try:
        resp = requests.get(FEED_URL, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return root.findall(".//incident")  # adjust tag name if needed after inspecting feed
    except Exception as e:
        print(f"[{datetime.now()}] Feed fetch error: {e}")
        return []

def extract_exit_numbers(description):
    """Pull any exit numbers mentioned in the description text."""
    return [int(x) for x in re.findall(r'\bExit\s+(\d+)', description, re.IGNORECASE)]

def is_relevant(incident):
    """Return True if this incident matches our road/exit/direction filters."""
    road    = (incident.findtext("RoadwayName") or "").lower()
    desc    = (incident.findtext("Description") or incident.findtext("EventDescription") or "").lower()
    event   = (incident.findtext("EventType") or "").lower()

    # Must be GSP
    if config.ROAD_NAME.lower() not in road and "parkway" not in desc:
        return False

    # Must be a lane closure type
    lane_keywords = ["lane closed", "lane blocked", "lanes closed", "lanes blocked"]
    if not any(kw in desc for kw in lane_keywords):
        return False

    # Must be in our direction(s)
    if not any(d in desc for d in config.DIRECTIONS):
        return False

    # Must be in our exit range
    exits = extract_exit_numbers(desc)
    if exits:
        if not any(config.EXIT_MIN <= e <= config.EXIT_MAX for e in exits):
            return False

    return True

# --- Email ---
def send_email(subject, body):
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"]    = config.EMAIL_FROM
    msg["To"]      = config.EMAIL_TO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_FROM, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        print(f"[{datetime.now()}] Email sent: {subject}")
    except Exception as e:
        print(f"[{datetime.now()}] Email error: {e}")

def format_alert(incident):
    desc      = incident.findtext("Description") or incident.findtext("EventDescription") or "No description"
    road      = incident.findtext("RoadwayName") or "GSP"
    direction = incident.findtext("DirectionOfTravel") or ""
    inc_id    = incident.findtext("ID") or "unknown"
    url       = f"https://511nj.org/event/{inc_id}"

    subject = f"🚧 GSP Lane Closure Alert — {road} {direction}"
    body = f"""New lane closure detected on your monitored segment.

Road:      {road} {direction}
Details:   {desc}
Reported:  {datetime.now().strftime('%I:%M %p, %b %d %Y')}
View:      {url}

--
GSP Monitor | Exits {config.EXIT_MIN}–{config.EXIT_MAX}
"""
    return subject, body

# --- Main Loop ---
def check_feed():
    print(f"[{datetime.now()}] Checking feed...")
    conn = init_db()
    incidents = fetch_incidents()

    for incident in incidents:
        inc_id = incident.findtext("ID") or incident.findtext("id") or str(hash(ET.tostring(incident)))

        if already_seen(conn, inc_id):
            continue

        if is_relevant(incident):
            subject, body = format_alert(incident)
            send_email(subject, body)

        mark_seen(conn, inc_id)

    conn.close()

if __name__ == "__main__":
    print(f"GSP Monitor started. Polling every {config.POLL_INTERVAL} minutes.")
    print(f"Watching: {config.ROAD_NAME} | Exits {config.EXIT_MIN}–{config.EXIT_MAX} | {config.DIRECTIONS}")
    check_feed()  # Run immediately on start
    schedule.every(config.POLL_INTERVAL).minutes.do(check_feed)
    while True:
        schedule.run_pending()
        time.sleep(30)
```

---

## Running It

### Locally (VS Code Terminal)

```bash
cd gsp-monitor
python monitor.py
```

You'll see polling logs in the terminal. Leave it running while you work.

### On a VM (Always-On)

SSH into your VM and run as a background process:

```bash
# Run in background, log output to file
nohup python monitor.py >> monitor.log 2>&1 &

# Check it's running
ps aux | grep monitor.py

# Watch the log
tail -f monitor.log
```

Or set up a **cron job** to auto-restart on reboot:

```bash
crontab -e
```

Add this line:

```
@reboot cd /home/youruser/gsp-monitor && python monitor.py >> monitor.log 2>&1 &
```

---

## Recommended Free/Cheap VM Options

| Provider | Plan | Cost | Notes |
|---|---|---|---|
| Oracle Cloud | Ampere A1 | **Free forever** | 4 CPU / 24GB RAM free tier |
| DigitalOcean | Basic Droplet | ~$4/mo | Easy setup |
| Linode (Akamai) | Nanode | ~$5/mo | Reliable |
| Hetzner | CX11 | ~$4/mo | Best value in EU |

---

## Troubleshooting

- **Feed tag names may differ** — Run `python -c "import requests; print(requests.get('https://511nj.org/api/GetAllIncidents?format=xml').text[:2000])"` to inspect the raw XML and adjust the `findtext()` tag names in `monitor.py` accordingly.
- **No emails arriving** — Check your Gmail App Password is correct and that "Less secure app access" or App Passwords are enabled.
- **Too many alerts** — Tune `EXIT_MIN`/`EXIT_MAX` in `config.py` or add a time-of-day filter to only alert during commute hours.

---

## Optional Enhancements

- Add a **time window filter** (e.g., only alert 6–9 AM and 4–7 PM)
- Log all incidents to a CSV for review
- Add **SMS via Twilio** as a secondary alert
- Filter out **shoulder closures** (only alert on travel lane closures)
