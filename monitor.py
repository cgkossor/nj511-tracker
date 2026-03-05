import feedparser
import sqlite3
import smtplib
import schedule
import time
import re
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from dateutil import parser as dateparser
import config

# --- Database ---
def init_db():
    conn = sqlite3.connect("seen_incidents.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            incident_id  TEXT PRIMARY KEY,
            first_seen   TEXT,
            last_alerted TEXT
        )
    """)
    conn.commit()
    return conn

def already_alerted_today(conn, incident_id):
    row = conn.execute("SELECT last_alerted FROM seen WHERE incident_id = ?", (incident_id,)).fetchone()
    if row is None or row[0] is None:
        return False
    try:
        last = datetime.fromisoformat(row[0])
        return last.date() == datetime.now().date()
    except ValueError:
        return False

def mark_seen(conn, incident_id):
    conn.execute("INSERT OR IGNORE INTO seen (incident_id, first_seen) VALUES (?, ?)",
                 (incident_id, datetime.now().isoformat()))
    conn.commit()

def mark_alerted(conn, incident_id):
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO seen (incident_id, first_seen, last_alerted) VALUES (?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET last_alerted = ?
    """, (incident_id, now, now, now))
    conn.commit()

# --- Feed Parsing ---
def fetch_incidents():
    try:
        feed = feedparser.parse(config.FEED_URL)
        if feed.bozo:
            print(f"[{datetime.now()}] Feed parse warning: {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"[{datetime.now()}] Feed fetch error: {e}")
        return []

def extract_exit_numbers(text):
    return [int(x) for x in re.findall(r'\bExit\s+(\d+)', text, re.IGNORECASE)]

def is_relevant(entry):
    title = (entry.get("title") or "").lower()
    desc = (entry.get("description") or entry.get("summary") or "").lower()

    # Must have GSP in the TITLE (not description — avoids interchange false positives)
    if config.ROAD_NAME.lower() not in title:
        return False

    # Must be a lane closure
    lane_keywords = ["lane closed", "lane blocked", "lanes closed", "lanes blocked"]
    text = f"{title} {desc}"
    if not any(kw in text for kw in lane_keywords):
        return False

    # Must be in our direction(s) — check title
    if not any(d in title for d in config.DIRECTIONS):
        return False

    # Must be in our exit range
    exits = extract_exit_numbers(desc)
    if exits:
        if not any(config.EXIT_MIN <= e <= config.EXIT_MAX for e in exits):
            return False

    return True

# --- Schedule Parsing ---
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}

DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

def parse_schedule(desc):
    """Parse schedule info from description text. Returns dict or None."""
    info = {}

    # Date range: "Monday March 2nd, 2026 thru Saturday March 7th, 2026"
    date_range = re.search(
        r'(\w+ \w+ \d+\w*,?\s*\d{4})\s+thru\s+(\w+ \w+ \d+\w*,?\s*\d{4})',
        desc, re.IGNORECASE
    )
    if date_range:
        try:
            info["start_date"] = dateparser.parse(re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_range.group(1)))
            info["end_date"] = dateparser.parse(re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_range.group(2)))
        except (ValueError, TypeError):
            pass

    # Day-of-week range: "Monday thru Friday"
    dow_range = re.search(
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+thru\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        desc, re.IGNORECASE
    )
    if dow_range:
        info["dow_start"] = DAY_MAP.get(dow_range.group(1).lower())
        info["dow_end"] = DAY_MAP.get(dow_range.group(2).lower())

    # Time window: "08:00 PM thru 06:00 AM" (take the first one as the main window)
    time_windows = re.findall(
        r'(\d{1,2}:\d{2}\s*[AP]M)\s+thru\s+(\d{1,2}:\d{2}\s*[AP]M)',
        desc, re.IGNORECASE
    )
    if time_windows:
        try:
            info["time_start"] = datetime.strptime(time_windows[0][0].strip(), "%I:%M %p").time()
            info["time_end"] = datetime.strptime(time_windows[0][1].strip(), "%I:%M %p").time()
        except ValueError:
            pass

    return info if info else None

def is_active_or_upcoming(schedule_info):
    """Check if a scheduled closure is active now or starting within ALERT_LEAD_MINUTES."""
    if not schedule_info:
        return True  # No schedule info = treat as immediate/active

    now = datetime.now()
    today = now.date()
    current_time = now.time()
    lead = timedelta(minutes=config.ALERT_LEAD_MINUTES)

    # Check date range
    if "start_date" in schedule_info and "end_date" in schedule_info:
        if not (schedule_info["start_date"].date() <= today <= schedule_info["end_date"].date()):
            return False

    # Check day of week
    if "dow_start" in schedule_info and "dow_end" in schedule_info:
        current_dow = now.weekday()  # Monday=0
        dow_start = schedule_info["dow_start"]
        dow_end = schedule_info["dow_end"]
        if dow_start <= dow_end:
            if not (dow_start <= current_dow <= dow_end):
                return False
        else:  # wraps around weekend
            if not (current_dow >= dow_start or current_dow <= dow_end):
                return False

    # Check time window
    if "time_start" in schedule_info and "time_end" in schedule_info:
        t_start = schedule_info["time_start"]
        t_end = schedule_info["time_end"]

        # Calculate "upcoming" threshold
        lead_time = (datetime.combine(today, t_start) - lead).time()

        if t_start > t_end:
            # Overnight window (e.g., 8PM-6AM)
            is_active = current_time >= t_start or current_time <= t_end
            is_upcoming = current_time >= lead_time and current_time < t_start
        else:
            # Same-day window
            is_active = t_start <= current_time <= t_end
            is_upcoming = lead_time <= current_time < t_start

        if not (is_active or is_upcoming):
            return False

    return True

# --- Detail Extraction ---
def parse_details(entry):
    """Extract structured fields from an RSS entry for the email."""
    title = entry.get("title") or ""
    desc = entry.get("description") or entry.get("summary") or ""

    # Direction from title: "Garden State Parkway northbound : Roadwork"
    direction = ""
    for d in ["northbound", "southbound"]:
        if d in title.lower():
            direction = d.capitalize()
            break

    # Short direction for subject
    dir_short = {"Northbound": "NB", "Southbound": "SB"}.get(direction, "")

    # Exits
    exits = extract_exit_numbers(desc)
    if exits:
        exit_str = f"{max(exits)} \u2192 {min(exits)}" if len(exits) > 1 else str(exits[0])
    else:
        exit_str = "N/A"

    # Event type from title: "Garden State Parkway northbound : Roadwork"
    event_type = title.split(":")[-1].strip() if ":" in title else "Lane Closure"

    # Date range
    date_range = re.search(
        r'(\w+ \w+ \d+\w*,?\s*\d{4})\s+thru\s+(\w+ \w+ \d+\w*,?\s*\d{4})',
        desc, re.IGNORECASE
    )
    date_str = f"{date_range.group(1)} \u2013 {date_range.group(2)}" if date_range else "N/A"

    # Day-of-week
    dow_match = re.search(
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+thru\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
        desc, re.IGNORECASE
    )
    dow_str = f"{dow_match.group(1)[:3]}\u2013{dow_match.group(2)[:3]}" if dow_match else ""

    # Time windows
    time_windows = re.findall(
        r'(\d{1,2}:\d{2}\s*[AP]M)\s+thru\s+(\d{1,2}:\d{2}\s*[AP]M)',
        desc, re.IGNORECASE
    )
    time_str = f"{time_windows[0][0]} \u2192 {time_windows[0][1]}" if time_windows else "N/A"

    # When string (combine day + time)
    if dow_str and time_str != "N/A":
        when_str = f"{dow_str}, {time_str}"
    elif time_str != "N/A":
        when_str = time_str
    else:
        when_str = "Check details"

    # Lane impact — extract all "X lane(s) of Y lanes closed" patterns
    impacts = re.findall(r'(\d+\s+\w+\s+lanes?\s+of\s+\d+\s+lanes?\s+closed)', desc, re.IGNORECASE)
    impact_str = " | ".join(impacts) if impacts else "Lane closure"

    # Status
    schedule_info = parse_schedule(desc)
    if schedule_info and "time_start" in schedule_info:
        now = datetime.now()
        t_start = schedule_info["time_start"]
        start_dt = datetime.combine(now.date(), t_start)
        if now.time() < t_start:
            mins_until = int((start_dt - now).total_seconds() / 60)
            status = f"\u26a0\ufe0f Starting in {mins_until} min"
        else:
            status = "\U0001f534 Active Now"
    else:
        status = "\U0001f534 Active Now"

    return {
        "direction": direction,
        "dir_short": dir_short,
        "exits": exit_str,
        "event_type": event_type,
        "date_range": date_str,
        "when": when_str,
        "impact": impact_str,
        "status": status,
    }

# --- Email ---
def send_email(subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_FROM, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        print(f"[{datetime.now()}] Email sent: {subject}")
    except Exception as e:
        print(f"[{datetime.now()}] Email error: {e}")

def format_alert(entry):
    details = parse_details(entry)
    link = entry.get("link") or ""

    subject = f"\U0001f6a7 GSP Lane Closure \u2014 Exit {details['exits']} {details['dir_short']}"

    body = f"""\U0001f6a7 LANE CLOSURE ALERT

\U0001f4cd Where:     {config.ROAD_NAME} {details['direction']}
\U0001f522 Exits:     {details['exits']}
\u23f0 When:      {details['when']}
\U0001f4c5 Dates:     {details['date_range']}
\U0001f697 Impact:    {details['impact']}
\U0001f4cb Status:    {details['status']}
\U0001f527 Type:      {details['event_type']}

\U0001f517 Details:   {link}

--
\U0001f6e3\ufe0f GSP Monitor | Exits {config.EXIT_MIN}\u2013{config.EXIT_MAX}
"""
    return subject, body

# --- Main Loop ---
def check_feed():
    print(f"[{datetime.now()}] Checking feed...")
    conn = init_db()
    entries = fetch_incidents()
    print(f"[{datetime.now()}] Found {len(entries)} total entries in feed")

    matched = 0
    for entry in entries:
        inc_id = entry.get("id") or entry.get("link") or str(hash(str(entry)))

        if not is_relevant(entry):
            mark_seen(conn, inc_id)
            continue

        desc = (entry.get("description") or entry.get("summary") or "")
        schedule_info = parse_schedule(desc)

        if schedule_info:
            # Scheduled event — only alert if active/upcoming and not already alerted today
            if is_active_or_upcoming(schedule_info):
                if not already_alerted_today(conn, inc_id):
                    subject, body = format_alert(entry)
                    send_email(subject, body)
                    mark_alerted(conn, inc_id)
                    matched += 1
            else:
                mark_seen(conn, inc_id)
        else:
            # Immediate event — alert once
            if not already_alerted_today(conn, inc_id):
                subject, body = format_alert(entry)
                send_email(subject, body)
                mark_alerted(conn, inc_id)
                matched += 1

    print(f"[{datetime.now()}] {matched} new relevant alerts sent")
    conn.close()

if __name__ == "__main__":
    print(f"GSP Monitor started. Polling every {config.POLL_INTERVAL} minutes.")
    print(f"Watching: {config.ROAD_NAME} | Exits {config.EXIT_MIN}\u2013{config.EXIT_MAX} | {config.DIRECTIONS}")
    print(f"Feed: {config.FEED_URL}")
    check_feed()
    schedule.every(config.POLL_INTERVAL).minutes.do(check_feed)
    while True:
        schedule.run_pending()
        time.sleep(30)
