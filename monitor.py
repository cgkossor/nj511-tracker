import feedparser
import sqlite3
import smtplib
import schedule
import time
import re
from email.mime.text import MIMEText
from datetime import datetime
import config

# --- Database ---
def init_db():
    conn = sqlite3.connect("seen_incidents.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            incident_id TEXT PRIMARY KEY,
            first_seen  TEXT
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
        feed = feedparser.parse(config.FEED_URL)
        if feed.bozo:
            print(f"[{datetime.now()}] Feed parse warning: {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"[{datetime.now()}] Feed fetch error: {e}")
        return []

def extract_exit_numbers(text):
    """Pull any exit numbers mentioned in the text."""
    return [int(x) for x in re.findall(r'\bExit\s+(\d+)', text, re.IGNORECASE)]

def is_relevant(entry):
    """Return True if this entry matches our road/exit/direction filters."""
    title = (entry.get("title") or "").lower()
    desc = (entry.get("description") or entry.get("summary") or "").lower()
    text = f"{title} {desc}"

    # Must be GSP
    if config.ROAD_NAME.lower() not in text and "parkway" not in text:
        return False

    # Must be a lane closure type
    lane_keywords = ["lane closed", "lane blocked", "lanes closed", "lanes blocked"]
    if not any(kw in text for kw in lane_keywords):
        return False

    # Must be in our direction(s)
    if not any(d in text for d in config.DIRECTIONS):
        return False

    # Must be in our exit range
    exits = extract_exit_numbers(text)
    if exits:
        if not any(config.EXIT_MIN <= e <= config.EXIT_MAX for e in exits):
            return False

    return True

# --- Email ---
def send_email(subject, body):
    msg = MIMEText(body, "plain")
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
    title = entry.get("title") or "GSP Incident"
    desc = entry.get("description") or entry.get("summary") or "No description"
    link = entry.get("link") or ""
    published = entry.get("published") or ""

    subject = f"GSP Lane Closure Alert - {title[:60]}"
    body = f"""New lane closure detected on your monitored segment.

Title:     {title}
Details:   {desc}
Published: {published}
Reported:  {datetime.now().strftime('%I:%M %p, %b %d %Y')}
Link:      {link}

--
GSP Monitor | Exits {config.EXIT_MIN}-{config.EXIT_MAX}
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
        # Use link or id as unique identifier
        inc_id = entry.get("id") or entry.get("link") or str(hash(str(entry)))

        if already_seen(conn, inc_id):
            continue

        if is_relevant(entry):
            subject, body = format_alert(entry)
            send_email(subject, body)
            matched += 1

        mark_seen(conn, inc_id)

    print(f"[{datetime.now()}] {matched} new relevant alerts sent")
    conn.close()

if __name__ == "__main__":
    print(f"GSP Monitor started. Polling every {config.POLL_INTERVAL} minutes.")
    print(f"Watching: {config.ROAD_NAME} | Exits {config.EXIT_MIN}-{config.EXIT_MAX} | {config.DIRECTIONS}")
    print(f"Feed: {config.FEED_URL}")
    check_feed()  # Run immediately on start
    schedule.every(config.POLL_INTERVAL).minutes.do(check_feed)
    while True:
        schedule.run_pending()
        time.sleep(30)
