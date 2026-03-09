import feedparser
import sqlite3
import smtplib
import schedule
import time
import re
from email.mime.text import MIMEText
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from dateutil import parser as dateparser
import config

ET = ZoneInfo("America/New_York")

# --- Feed Definitions ---
FEEDS = [
    {
        "url": "https://511nj.org/client/rest/rss/RSSActiveIncidents",
        "category": "Incident",
        "emoji": "\U0001f6a8",
        "urgent": True,
        "require_lane_closure": False,
    },
    {
        "url": "https://511nj.org/client/rest/rss/RSSActiveCongestion",
        "category": "Congestion",
        "emoji": "\U0001f697",
        "urgent": True,
        "require_lane_closure": False,
    },
    {
        "url": "https://511nj.org/client/rest/rss/RSSActiveConstruction",
        "category": "Construction",
        "emoji": "\U0001f6a7",
        "urgent": False,
        "require_lane_closure": True,
    },
    {
        "url": "https://511nj.org/client/rest/rss/RSSActiveWeather",
        "category": "Weather",
        "emoji": "\U0001f327\ufe0f",
        "urgent": True,
        "require_lane_closure": False,
    },
    {
        "url": "https://511nj.org/client/rest/rss/RSSActiveSpecialEvents",
        "category": "Special Event",
        "emoji": "\U0001f3aa",
        "urgent": False,
        "require_lane_closure": False,
    },
    {
        "url": "https://511nj.org/client/rest/rss/RSSPlannedConstructionAndSpecialEvents",
        "category": "Planned",
        "emoji": "\U0001f4cb",
        "urgent": False,
        "require_lane_closure": True,
    },
]

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

def already_alerted_recently(conn, incident_id):
    row = conn.execute("SELECT last_alerted FROM seen WHERE incident_id = ?", (incident_id,)).fetchone()
    if row is None or row[0] is None:
        return False
    try:
        last = datetime.fromisoformat(row[0])
        if last.tzinfo is None:
            last = last.replace(tzinfo=ET)
        return (datetime.now(ET) - last) < timedelta(hours=config.ALERT_COOLDOWN_HOURS)
    except ValueError:
        return False

def mark_seen(conn, incident_id):
    conn.execute("INSERT OR IGNORE INTO seen (incident_id, first_seen) VALUES (?, ?)",
                 (incident_id, datetime.now(ET).isoformat()))
    conn.commit()

def mark_alerted(conn, incident_id):
    now = datetime.now(ET).isoformat()
    conn.execute("""
        INSERT INTO seen (incident_id, first_seen, last_alerted) VALUES (?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET last_alerted = ?
    """, (incident_id, now, now, now))
    conn.commit()

# --- Feed Parsing ---
def fetch_feed(url):
    try:
        feed = feedparser.parse(url)
        if feed.bozo:
            print(f"[{datetime.now(ET)}] Feed parse warning ({url}): {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"[{datetime.now(ET)}] Feed fetch error ({url}): {e}")
        return []

def extract_exit_numbers(text):
    return [int(x) for x in re.findall(r'\bExit\s+(\d+)', text, re.IGNORECASE)]

def is_relevant(entry, feed_config):
    title = (entry.get("title") or "").lower()
    desc = (entry.get("description") or entry.get("summary") or "").lower()
    text = f"{title} {desc}"

    # Must have GSP in the TITLE
    if config.ROAD_NAME.lower() not in title:
        return False

    # Construction/planned feeds require lane closure keywords
    if feed_config["require_lane_closure"]:
        lane_keywords = ["lane closed", "lane blocked", "lanes closed", "lanes blocked"]
        if not any(kw in text for kw in lane_keywords):
            return False

    # Must be in our direction(s) — check title
    if not any(d in title for d in config.DIRECTIONS):
        return False

    # Must mention exits in our range
    exits = extract_exit_numbers(text)
    if not exits:
        return False
    if not any(config.EXIT_MIN <= e <= config.EXIT_MAX for e in exits):
        return False

    return True

# --- Schedule Parsing ---
DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

def parse_schedule(desc):
    info = {}

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

    dow_range = re.search(
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+thru\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        desc, re.IGNORECASE
    )
    if dow_range:
        info["dow_start"] = DAY_MAP.get(dow_range.group(1).lower())
        info["dow_end"] = DAY_MAP.get(dow_range.group(2).lower())

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
    if not schedule_info:
        return True

    now = datetime.now(ET)
    today = now.date()
    current_time = now.time()
    lead = timedelta(minutes=config.ALERT_LEAD_MINUTES)

    if "start_date" in schedule_info and "end_date" in schedule_info:
        if not (schedule_info["start_date"].date() <= today <= schedule_info["end_date"].date()):
            return False

    if "dow_start" in schedule_info and "dow_end" in schedule_info:
        current_dow = now.weekday()
        dow_start = schedule_info["dow_start"]
        dow_end = schedule_info["dow_end"]
        if dow_start <= dow_end:
            if not (dow_start <= current_dow <= dow_end):
                return False
        else:
            if not (current_dow >= dow_start or current_dow <= dow_end):
                return False

    if "time_start" in schedule_info and "time_end" in schedule_info:
        t_start = schedule_info["time_start"]
        t_end = schedule_info["time_end"]
        lead_time = (datetime.combine(today, t_start, tzinfo=ET) - lead).time()

        if t_start > t_end:
            # Overnight window (e.g. 8 PM–6 AM) spans two calendar days.
            # Early-morning hours (before t_end) belong to the previous
            # night's session, so they are NOT active on the first date.
            # Evening hours (after t_start) are NOT active on the last date
            # because the work already ended that morning.
            in_morning_portion = current_time <= t_end
            in_evening_portion = current_time >= t_start
            start_date = schedule_info.get("start_date")
            end_date = schedule_info.get("end_date")
            if in_morning_portion and start_date and today == start_date.date():
                is_active = False
            elif in_evening_portion and end_date and today == end_date.date():
                is_active = False
            else:
                is_active = in_evening_portion or in_morning_portion
            is_upcoming = current_time >= lead_time and current_time < t_start
        else:
            is_active = t_start <= current_time <= t_end
            is_upcoming = lead_time <= current_time < t_start

        if not (is_active or is_upcoming):
            return False

    return True

# --- Detail Extraction ---
def parse_details(entry, feed_config):
    title = entry.get("title") or ""
    desc = entry.get("description") or entry.get("summary") or ""

    direction = ""
    for d in ["northbound", "southbound"]:
        if d in title.lower():
            direction = d.capitalize()
            break

    dir_arrow = {"Northbound": "\u2b06\ufe0f", "Southbound": "\u2b07\ufe0f"}.get(direction, "")

    exits = extract_exit_numbers(desc)
    if exits:
        exit_str = f"{max(exits)} \u2192 {min(exits)}" if len(exits) > 1 else str(exits[0])
    else:
        exit_str = "N/A"

    event_type = title.split(":")[-1].strip() if ":" in title else feed_config["category"]

    # Date range
    date_range = re.search(
        r'(\w+ \w+ \d+\w*,?\s*\d{4})\s+thru\s+(\w+ \w+ \d+\w*,?\s*\d{4})',
        desc, re.IGNORECASE
    )
    if date_range:
        date_str = f"{date_range.group(1)} \u2013 {date_range.group(2)}"
    else:
        published = entry.get("published") or ""
        if published:
            try:
                pub_dt = dateparser.parse(published)
                date_str = pub_dt.strftime("%A %B %d, %Y")
            except (ValueError, TypeError):
                date_str = published
        else:
            date_str = datetime.now(ET).strftime("%A %B %d, %Y")

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

    if dow_str and time_str != "N/A":
        when_str = f"{dow_str}, {time_str}"
    elif time_str != "N/A":
        when_str = time_str
    else:
        when_str = "Ongoing"

    # Lane impact
    impacts = re.findall(r'(\d+\s+\w+\s+lanes?\s+of\s+\d+\s+lanes?\s+closed)', desc, re.IGNORECASE)
    impact_str = " | ".join(impacts) if impacts else feed_config["category"]

    # Status
    schedule_info = parse_schedule(desc)
    if schedule_info and "time_start" in schedule_info:
        now = datetime.now(ET)
        t_start = schedule_info["time_start"]
        start_dt = datetime.combine(now.date(), t_start, tzinfo=ET)
        if now.time() < t_start:
            total_mins = int((start_dt - now).total_seconds() / 60)
            if total_mins >= 60:
                hours = total_mins // 60
                mins = total_mins % 60
                time_left = f"{hours}h {mins}m" if mins else f"{hours}h"
            else:
                time_left = f"{total_mins}m"
            status = f"\u26a0\ufe0f Starting in {time_left}"
        else:
            status = "\U0001f534 Active Now"
    else:
        status = "\U0001f534 Active Now"

    return {
        "direction": direction,
        "dir_arrow": dir_arrow,
        "exits": exit_str,
        "event_type": event_type,
        "date_range": date_str,
        "when": when_str,
        "impact": impact_str,
        "status": status,
    }

# --- Email ---
def send_email(subject, body):
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_FROM, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        print(f"[{datetime.now(ET)}] Email sent: {subject}")
    except Exception as e:
        print(f"[{datetime.now(ET)}] Email error: {e}")

def format_alert(entry, feed_config):
    details = parse_details(entry, feed_config)
    link = entry.get("link") or ""
    emoji = feed_config["emoji"]
    category = feed_config["category"].upper()

    subject = f"{emoji} GSP {feed_config['category']}:  {details['dir_arrow']} Exit {details['exits']}"

    rows = [
        ("\U0001f4cd", "Where:", f"{config.ROAD_NAME} {details['direction']}"),
        ("\U0001f522", "Exits:", details['exits']),
        ("\U0001f4c5", "Dates:", details['date_range']),
        ("\u23f0", "When:", details['when']),
        ("\U0001f697", "Impact:", details['impact']),
        ("\U0001f4cb", "Status:", details['status']),
        ("\U0001f527", "Type:", details['event_type']),
    ]

    table_rows = "\n".join(
        f'<tr><td style="padding-right:12px;white-space:nowrap;">{em} {label}</td><td>{value}</td></tr>'
        for em, label, value in rows
    )

    link_html = f'<br>\U0001f517 <a href="{link}">Details</a>' if link else ""

    body = f"""\
<div style="font-family:sans-serif;font-size:14px;">
<b>{emoji} {category} ALERT</b><br><br>
<table style="border-collapse:collapse;">
{table_rows}
</table>
{link_html}
<br>
<small>\U0001f6e3\ufe0f GSP Monitor | Exits {config.EXIT_MIN}\u2013{config.EXIT_MAX}</small>
</div>
"""
    return subject, body

# --- Main Loop ---
def check_feed():
    print(f"[{datetime.now(ET)}] Checking feeds...")
    conn = init_db()
    total_matched = 0

    for feed_config in FEEDS:
        entries = fetch_feed(feed_config["url"])
        print(f"[{datetime.now(ET)}] {feed_config['category']}: {len(entries)} entries")

        matched = 0
        for entry in entries:
            # Use title-based key to dedup same event across Construction/Planned feeds
            title_key = re.sub(r'\s+', ' ', (entry.get("title") or "").strip().lower())
            inc_id = title_key or entry.get("id") or entry.get("link") or str(hash(str(entry)))

            if not is_relevant(entry, feed_config):
                mark_seen(conn, inc_id)
                continue

            desc = (entry.get("description") or entry.get("summary") or "")
            schedule_info = parse_schedule(desc)

            if feed_config["urgent"]:
                # Congestion alerts only after configured hour
                if feed_config["category"] == "Congestion":
                    if datetime.now(ET).hour < config.CONGESTION_ALERT_AFTER_HOUR:
                        mark_seen(conn, inc_id)
                        continue
                # Urgent feeds (incidents, congestion, weather) — alert immediately
                if not already_alerted_recently(conn, inc_id):
                    subject, body = format_alert(entry, feed_config)
                    send_email(subject, body)
                    mark_alerted(conn, inc_id)
                    matched += 1
            elif schedule_info:
                # Scheduled event — only alert if active/upcoming
                if is_active_or_upcoming(schedule_info):
                    if not already_alerted_recently(conn, inc_id):
                        subject, body = format_alert(entry, feed_config)
                        send_email(subject, body)
                        mark_alerted(conn, inc_id)
                        matched += 1
                else:
                    mark_seen(conn, inc_id)
            else:
                # Non-urgent, no schedule — alert once
                if not already_alerted_recently(conn, inc_id):
                    subject, body = format_alert(entry, feed_config)
                    send_email(subject, body)
                    mark_alerted(conn, inc_id)
                    matched += 1

        total_matched += matched

    print(f"[{datetime.now(ET)}] {total_matched} new alerts sent across all feeds")
    conn.close()

if __name__ == "__main__":
    print(f"GSP Monitor started. Polling every {config.POLL_INTERVAL} minutes.")
    print(f"Watching: {config.ROAD_NAME} | Exits {config.EXIT_MIN}\u2013{config.EXIT_MAX} | {config.DIRECTIONS}")
    print(f"Feeds: {len(FEEDS)} categories")
    check_feed()
    schedule.every(config.POLL_INTERVAL).minutes.do(check_feed)
    while True:
        schedule.run_pending()
        time.sleep(30)
