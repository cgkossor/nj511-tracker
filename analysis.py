import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import config

ET = ZoneInfo("America/New_York")


# --- Timezone / formatting helpers ---

def to_et(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET)


def format_date(dt):
    """Mar 5, 2026"""
    dt = to_et(dt)
    return dt.strftime("%b ") + str(dt.day) + dt.strftime(", %Y")


def format_time(dt):
    """3:00 PM ET"""
    dt = to_et(dt)
    h = dt.hour
    m = dt.minute
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ampm} ET"


def format_datetime(dt):
    """Mar 5, 2026 at 3:00 PM ET"""
    return f"{format_date(dt)} at {format_time(dt)}"


def format_hour_label(hour):
    """Convert 0-23 hour to '5 AM ET', '3 PM ET'"""
    if hour == 0:
        return "12 AM ET"
    elif hour < 12:
        return f"{hour} AM ET"
    elif hour == 12:
        return "12 PM ET"
    else:
        return f"{hour - 12} PM ET"


# --- Data loading ---

def load_events(days=None, db_path=None, category=None):
    db = db_path or config.TRACKER_DB
    conn = sqlite3.connect(db)

    # Try new events table first, fall back to congestion_events
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "events" in tables:
        table = "events"
    elif "congestion_events" in tables:
        table = "congestion_events"
    else:
        conn.close()
        return pd.DataFrame()

    query = f"SELECT * FROM {table}"
    conditions = []
    params = []

    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conditions.append("first_seen >= ?")
        params.append(cutoff)

    if category and table == "events":
        conditions.append("category = ?")
        params.append(category)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return df

    # Add category column for old table
    if table == "congestion_events" and "category" not in df.columns:
        df["category"] = "Congestion"

    df["first_seen"] = pd.to_datetime(df["first_seen"], utc=True)
    df["last_seen"] = pd.to_datetime(df["last_seen"], utc=True)
    df["first_seen_et"] = df["first_seen"].dt.tz_convert(ET)
    df["last_seen_et"] = df["last_seen"].dt.tz_convert(ET)
    df["duration_min"] = (df["last_seen"] - df["first_seen"]).dt.total_seconds() / 60
    df["hour"] = df["first_seen_et"].dt.hour
    df["dow"] = df["first_seen_et"].dt.dayofweek
    df["dow_name"] = df["first_seen_et"].dt.day_name()
    df["date"] = df["first_seen_et"].dt.date
    df["section"] = df.apply(
        lambda r: f"Exit {int(r['exit_end'])}-{int(r['exit_start'])}"
        if pd.notna(r.get("exit_start")) and pd.notna(r.get("exit_end"))
        else "Unknown",
        axis=1,
    )
    return df


# --- Category-level analysis ---

def events_by_category(df):
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("category")
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .sort_values("events", ascending=False)
        .reset_index()
    )


def category_by_time_of_day(df):
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["category", "hour"])
        .agg(events=("event_id", "count"))
        .reset_index()
    )


# --- Section analysis ---

def worst_sections(df, top_n=10, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    if data.empty:
        return pd.DataFrame()
    return (
        data.groupby("section")
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .sort_values("events", ascending=False)
        .head(top_n)
        .reset_index()
    )


def incident_hotspots(df, top_n=10):
    return worst_sections(df, top_n=top_n, category="Incident")


def severity_ranking(df, top_n=15):
    """Sections ranked by total events across ALL categories."""
    if df.empty:
        return pd.DataFrame()
    known = df[df["section"] != "Unknown"]
    if known.empty:
        return pd.DataFrame()
    result = (
        known.groupby(["section", "category"])
        .agg(events=("event_id", "count"))
        .reset_index()
    )
    totals = result.groupby("section")["events"].sum().sort_values(ascending=False).head(top_n)
    return result[result["section"].isin(totals.index)]


# --- Cross-category analysis ---

def incident_congestion_correlation(df):
    """Per-section: incident count vs congestion count for scatter plot."""
    if df.empty:
        return pd.DataFrame()
    incidents = df[df["category"] == "Incident"].groupby("section").size().rename("incidents")
    congestion = df[df["category"] == "Congestion"].groupby("section").size().rename("congestion")
    merged = pd.concat([incidents, congestion], axis=1).fillna(0).reset_index()
    merged = merged[merged["section"] != "Unknown"]
    return merged


def concurrent_events(df):
    """Sections where incidents and congestion overlap in time."""
    if df.empty:
        return pd.DataFrame()
    inc = df[df["category"] == "Incident"][["section", "first_seen", "last_seen"]].copy()
    cong = df[df["category"] == "Congestion"][["section", "first_seen", "last_seen"]].copy()
    if inc.empty or cong.empty:
        return pd.DataFrame()

    merged = inc.merge(cong, on="section", suffixes=("_inc", "_cong"))
    overlaps = merged[
        (merged["first_seen_inc"] <= merged["last_seen_cong"]) &
        (merged["first_seen_cong"] <= merged["last_seen_inc"])
    ]
    if overlaps.empty:
        return pd.DataFrame()
    return (
        overlaps.groupby("section")
        .size()
        .reset_index(name="overlaps")
        .sort_values("overlaps", ascending=False)
    )


# --- Direction / time analysis ---

def direction_by_time_of_day(df, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    data = data[data["direction"].notna()]
    if data.empty:
        return pd.DataFrame()
    return (
        data.groupby(["direction", "hour"])
        .agg(events=("event_id", "count"))
        .reset_index()
    )


def commute_comparison(df, category="Congestion"):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    data = data[data["direction"].notna()]
    if data.empty:
        return pd.DataFrame()

    def period(hour):
        if 5 <= hour < 10:
            return "Morning (5-10 AM ET)"
        elif 15 <= hour < 20:
            return "Evening (3-8 PM ET)"
        return "Other"

    data = data.copy()
    data["period"] = data["hour"].apply(period)
    commute = data[data["period"] != "Other"]
    if commute.empty:
        return pd.DataFrame()
    return (
        commute.groupby(["direction", "period"])
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .reset_index()
    )


def day_of_week_patterns(df, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    data = data[data["direction"].notna()]
    if data.empty:
        return pd.DataFrame()
    return (
        data.groupby(["dow", "dow_name", "direction"])
        .agg(events=("event_id", "count"))
        .reset_index()
        .sort_values("dow")
    )


def avg_duration_by_section(df, top_n=10, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    data = data[data["duration_min"] > 0]
    if data.empty:
        return pd.DataFrame()
    return (
        data.groupby("section")
        .agg(avg_duration_min=("duration_min", "mean"), events=("event_id", "count"))
        .sort_values("avg_duration_min", ascending=False)
        .head(top_n)
        .reset_index()
    )


def weekly_trend(df, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    if data.empty:
        return pd.DataFrame()
    data = data.copy()
    data["week"] = data["first_seen_et"].dt.to_period("W").apply(lambda r: r.start_time)
    return (
        data.groupby("week")
        .agg(events=("event_id", "count"))
        .reset_index()
    )


def weekly_trend_by_category(df):
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["week"] = df["first_seen_et"].dt.to_period("W").apply(lambda r: r.start_time)
    return (
        df.groupby(["week", "category"])
        .agg(events=("event_id", "count"))
        .reset_index()
    )


def peak_hours_heatmap(df, category=None):
    if df.empty:
        return pd.DataFrame()
    data = df[df["category"] == category] if category else df
    if data.empty:
        return pd.DataFrame()
    return (
        data.groupby(["dow", "hour"])
        .agg(events=("event_id", "count"))
        .reset_index()
        .pivot(index="hour", columns="dow", values="events")
        .fillna(0)
        .rename(columns={0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"})
    )
