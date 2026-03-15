import feedparser
import sqlite3
import schedule
import time
import re
from datetime import datetime, timezone
import config


FEEDS = [
    {"url": "https://511nj.org/client/rest/rss/RSSActiveIncidents", "category": "Incident"},
    {"url": "https://511nj.org/client/rest/rss/RSSActiveCongestion", "category": "Congestion"},
    {"url": "https://511nj.org/client/rest/rss/RSSActiveConstruction", "category": "Construction"},
    {"url": "https://511nj.org/client/rest/rss/RSSActiveWeather", "category": "Weather"},
    {"url": "https://511nj.org/client/rest/rss/RSSActiveSpecialEvents", "category": "Special Event"},
    {"url": "https://511nj.org/client/rest/rss/RSSPlannedConstructionAndSpecialEvents", "category": "Planned"},
]


def init_db():
    conn = sqlite3.connect(config.TRACKER_DB)
    # New unified events table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT NOT NULL,
            category    TEXT NOT NULL,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            direction   TEXT,
            exit_start  INTEGER,
            exit_end    INTEGER,
            title       TEXT,
            description TEXT,
            UNIQUE(event_id, category)
        )
    """)
    conn.commit()
    return conn


def extract_exit_numbers(text):
    exits = [int(x) for x in re.findall(r'\bExit\s+(\d+)', text, re.IGNORECASE)]
    if not exits:
        lower = text.lower()
        for landmark, (exit_lo, exit_hi) in config.LANDMARK_EXITS.items():
            if landmark in lower:
                exits.extend([exit_lo, exit_hi])
    return exits


def extract_direction(title):
    lower = title.lower()
    if "northbound" in lower:
        return "Northbound"
    if "southbound" in lower:
        return "Southbound"
    return None


def collect():
    now_utc = datetime.now(timezone.utc).isoformat()
    print(f"[{now_utc}] Collecting all GSP feeds...")
    conn = init_db()

    total_new = 0
    total_updated = 0

    for feed_config in FEEDS:
        category = feed_config["category"]
        try:
            feed = feedparser.parse(feed_config["url"])
            entries = feed.entries
        except Exception as e:
            print(f"  [{category}] Feed error: {e}")
            continue

        new_count = 0
        updated_count = 0

        for entry in entries:
            title = entry.get("title") or ""
            desc = entry.get("description") or entry.get("summary") or ""

            # Only GSP entries
            if "garden state parkway" not in title.lower():
                continue

            event_id = entry.get("id") or entry.get("link") or str(hash(str(entry)))
            direction = extract_direction(title)
            exits = extract_exit_numbers(f"{title} {desc}")
            exit_start = max(exits) if exits else None
            exit_end = min(exits) if exits else None

            row = conn.execute(
                "SELECT event_id FROM events WHERE event_id = ? AND category = ?",
                (event_id, category)
            ).fetchone()

            if row:
                conn.execute(
                    "UPDATE events SET last_seen = ? WHERE event_id = ? AND category = ?",
                    (now_utc, event_id, category)
                )
                updated_count += 1
            else:
                conn.execute("""
                    INSERT INTO events (event_id, category, first_seen, last_seen, direction, exit_start, exit_end, title, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, category, now_utc, now_utc, direction, exit_start, exit_end, title, desc))
                new_count += 1

        total_new += new_count
        total_updated += updated_count
        gsp_count = new_count + updated_count
        print(f"  [{category}] {len(entries)} feed entries, {gsp_count} GSP ({new_count} new, {updated_count} updated)")

    conn.commit()
    conn.close()
    print(f"[{now_utc}] Total: {total_new} new, {total_updated} updated")


if __name__ == "__main__":
    print(f"GSP Collector started. Polling {len(FEEDS)} feeds every {config.COLLECTOR_POLL_INTERVAL} minutes.")
    print(f"Database: {config.TRACKER_DB}")
    collect()
    schedule.every(config.COLLECTOR_POLL_INTERVAL).minutes.do(collect)
    while True:
        schedule.run_pending()
        time.sleep(30)
