import feedparser
import sqlite3
import schedule
import time
import re
from datetime import datetime
import config


CONGESTION_FEED = "https://511nj.org/client/rest/rss/RSSActiveCongestion"


def init_db():
    conn = sqlite3.connect(config.CONGESTION_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS congestion_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT NOT NULL UNIQUE,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            direction   TEXT NOT NULL,
            exit_start  INTEGER,
            exit_end    INTEGER,
            title       TEXT,
            description TEXT
        )
    """)
    conn.commit()
    return conn


def extract_exit_numbers(text):
    return [int(x) for x in re.findall(r'\bExit\s+(\d+)', text, re.IGNORECASE)]


def extract_direction(title):
    lower = title.lower()
    if "northbound" in lower:
        return "Northbound"
    if "southbound" in lower:
        return "Southbound"
    return None


def collect():
    print(f"[{datetime.now()}] Collecting congestion data...")
    conn = init_db()

    try:
        feed = feedparser.parse(CONGESTION_FEED)
        if feed.bozo:
            print(f"[{datetime.now()}] Feed parse warning: {feed.bozo_exception}")
        entries = feed.entries
    except Exception as e:
        print(f"[{datetime.now()}] Feed fetch error: {e}")
        conn.close()
        return

    now = datetime.now().isoformat()
    active_ids = set()
    new_count = 0
    updated_count = 0

    for entry in entries:
        title = entry.get("title") or ""
        desc = entry.get("description") or entry.get("summary") or ""

        # Only GSP entries
        if "garden state parkway" not in title.lower():
            continue

        direction = extract_direction(title)
        if not direction:
            continue

        event_id = entry.get("id") or entry.get("link") or str(hash(str(entry)))
        active_ids.add(event_id)

        exits = extract_exit_numbers(f"{title} {desc}")
        exit_start = max(exits) if exits else None
        exit_end = min(exits) if exits else None

        row = conn.execute("SELECT event_id FROM congestion_events WHERE event_id = ?", (event_id,)).fetchone()
        if row:
            conn.execute("UPDATE congestion_events SET last_seen = ? WHERE event_id = ?", (now, event_id))
            updated_count += 1
        else:
            conn.execute("""
                INSERT INTO congestion_events (event_id, first_seen, last_seen, direction, exit_start, exit_end, title, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, now, now, direction, exit_start, exit_end, title, desc))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"[{datetime.now()}] Done: {new_count} new, {updated_count} updated, {len(entries)} total feed entries")


if __name__ == "__main__":
    print(f"GSP Congestion Collector started. Polling every {config.COLLECTOR_POLL_INTERVAL} minutes.")
    print(f"Database: {config.CONGESTION_DB}")
    collect()
    schedule.every(config.COLLECTOR_POLL_INTERVAL).minutes.do(collect)
    while True:
        schedule.run_pending()
        time.sleep(30)
