#!/usr/bin/env python3
"""
Merge split database files from services/ into data/ on the VPS.

Run on the VPS after stopping services:
    sudo systemctl stop gsp-monitor gsp-collector nj511-digest
    cd /opt/hobbies/services/nj511-tracker
    python3 merge_dbs.py

This merges:
  services/nj511-tracker/gsp_congestion.db  ->  data/nj511-tracker/gsp_congestion.db
  services/nj511-tracker/seen_incidents.db  ->  data/nj511-tracker/seen_incidents.db
"""
import os
import sqlite3
import shutil

SERVICES_DIR = "/opt/hobbies/services/nj511-tracker"
DATA_DIR = "/opt/hobbies/data/nj511-tracker"


def merge_events_db():
    """Merge gsp_congestion.db — dedup on (event_id, category)."""
    src = os.path.join(SERVICES_DIR, "gsp_congestion.db")
    dst = os.path.join(DATA_DIR, "gsp_congestion.db")

    src_exists = os.path.exists(src)
    dst_exists = os.path.exists(dst)

    print(f"\n--- gsp_congestion.db ---")
    print(f"  services/ copy: {'EXISTS' if src_exists else 'NOT FOUND'}")
    print(f"  data/ copy:     {'EXISTS' if dst_exists else 'NOT FOUND'}")

    if not src_exists and not dst_exists:
        print("  Nothing to merge.")
        return

    if src_exists and not dst_exists:
        print(f"  Copying {src} -> {dst}")
        shutil.copy2(src, dst)
        print("  Done.")
        return

    if not src_exists and dst_exists:
        print("  Only data/ copy exists, nothing to merge.")
        return

    # Both exist — merge
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)

    # Ensure events table exists in dst
    dst_conn.execute("""
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

    # Get existing keys in dst
    existing = set(dst_conn.execute("SELECT event_id, category FROM events").fetchall())
    print(f"  data/ has {len(existing)} existing events")

    # Read all from src
    src_rows = src_conn.execute(
        "SELECT event_id, category, first_seen, last_seen, direction, exit_start, exit_end, title, description FROM events"
    ).fetchall()
    print(f"  services/ has {len(src_rows)} events")

    inserted = 0
    updated = 0
    for row in src_rows:
        event_id, category = row[0], row[1]
        if (event_id, category) not in existing:
            dst_conn.execute("""
                INSERT INTO events (event_id, category, first_seen, last_seen, direction, exit_start, exit_end, title, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
            inserted += 1
        else:
            # Update last_seen if src has a newer timestamp
            src_last = row[3]
            dst_last = dst_conn.execute(
                "SELECT last_seen FROM events WHERE event_id = ? AND category = ?",
                (event_id, category)
            ).fetchone()[0]
            if src_last > dst_last:
                dst_conn.execute(
                    "UPDATE events SET last_seen = ? WHERE event_id = ? AND category = ?",
                    (src_last, event_id, category)
                )
                updated += 1

    dst_conn.commit()
    final_count = dst_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"  Merged: {inserted} new, {updated} updated last_seen")
    print(f"  data/ now has {final_count} total events")

    src_conn.close()
    dst_conn.close()


def merge_seen_db():
    """Merge seen_incidents.db — dedup on incident_id."""
    src = os.path.join(SERVICES_DIR, "seen_incidents.db")
    dst = os.path.join(DATA_DIR, "seen_incidents.db")

    src_exists = os.path.exists(src)
    dst_exists = os.path.exists(dst)

    print(f"\n--- seen_incidents.db ---")
    print(f"  services/ copy: {'EXISTS' if src_exists else 'NOT FOUND'}")
    print(f"  data/ copy:     {'EXISTS' if dst_exists else 'NOT FOUND'}")

    if not src_exists and not dst_exists:
        print("  Nothing to merge.")
        return

    if src_exists and not dst_exists:
        print(f"  Copying {src} -> {dst}")
        shutil.copy2(src, dst)
        print("  Done.")
        return

    if not src_exists and dst_exists:
        print("  Only data/ copy exists, nothing to merge.")
        return

    # Both exist — merge
    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)

    # Ensure table exists in dst
    dst_conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            incident_id  TEXT PRIMARY KEY,
            first_seen   TEXT,
            last_alerted TEXT
        )
    """)

    existing = set(r[0] for r in dst_conn.execute("SELECT incident_id FROM seen").fetchall())
    print(f"  data/ has {len(existing)} existing records")

    src_rows = src_conn.execute("SELECT incident_id, first_seen, last_alerted FROM seen").fetchall()
    print(f"  services/ has {len(src_rows)} records")

    inserted = 0
    for row in src_rows:
        if row[0] not in existing:
            dst_conn.execute("INSERT INTO seen (incident_id, first_seen, last_alerted) VALUES (?, ?, ?)", row)
            inserted += 1

    dst_conn.commit()
    final_count = dst_conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    print(f"  Merged: {inserted} new records")
    print(f"  data/ now has {final_count} total records")

    src_conn.close()
    dst_conn.close()


if __name__ == "__main__":
    print("=== NJ511 Tracker DB Merge ===")
    print(f"Source: {SERVICES_DIR}")
    print(f"Destination: {DATA_DIR}")

    os.makedirs(DATA_DIR, exist_ok=True)

    merge_events_db()
    merge_seen_db()

    print("\n=== Done! ===")
    print("Now update systemd units to use --data-dir and restart:")
    print("  sudo systemctl start gsp-monitor gsp-collector nj511-digest")
