import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import config


def load_events(days=None, db_path=None):
    db = db_path or config.CONGESTION_DB
    conn = sqlite3.connect(db)
    query = "SELECT * FROM congestion_events"
    params = []
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query += " WHERE first_seen >= ?"
        params.append(cutoff)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return df

    df["first_seen"] = pd.to_datetime(df["first_seen"])
    df["last_seen"] = pd.to_datetime(df["last_seen"])
    df["duration_min"] = (df["last_seen"] - df["first_seen"]).dt.total_seconds() / 60
    df["hour"] = df["first_seen"].dt.hour
    df["dow"] = df["first_seen"].dt.dayofweek  # 0=Mon, 6=Sun
    df["dow_name"] = df["first_seen"].dt.day_name()
    df["date"] = df["first_seen"].dt.date
    df["section"] = df.apply(
        lambda r: f"Exit {int(r['exit_end'])}-{int(r['exit_start'])}" if pd.notna(r["exit_start"]) and pd.notna(r["exit_end"]) else "Unknown",
        axis=1,
    )
    return df


def worst_sections(df, top_n=10):
    """Sections with most congestion events, ranked."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("section")
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .sort_values("events", ascending=False)
        .head(top_n)
        .reset_index()
    )


def direction_by_time_of_day(df):
    """NB vs SB event counts by hour of day."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["direction", "hour"])
        .agg(events=("event_id", "count"))
        .reset_index()
    )


def commute_comparison(df):
    """Morning (5-10 AM) vs evening (3-8 PM) event counts by direction."""
    if df.empty:
        return pd.DataFrame()

    def period(hour):
        if 5 <= hour < 10:
            return "Morning (5-10 AM)"
        elif 15 <= hour < 20:
            return "Evening (3-8 PM)"
        return "Other"

    df = df.copy()
    df["period"] = df["hour"].apply(period)
    commute = df[df["period"] != "Other"]
    return (
        commute.groupby(["direction", "period"])
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .reset_index()
    )


def day_of_week_patterns(df):
    """Events by day of week, split by direction."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["dow", "dow_name", "direction"])
        .agg(events=("event_id", "count"))
        .reset_index()
        .sort_values("dow")
    )


def avg_duration_by_section(df, top_n=10):
    """Average congestion duration by section."""
    if df.empty:
        return pd.DataFrame()
    return (
        df[df["duration_min"] > 0]
        .groupby("section")
        .agg(avg_duration_min=("duration_min", "mean"), events=("event_id", "count"))
        .sort_values("avg_duration_min", ascending=False)
        .head(top_n)
        .reset_index()
    )


def weekly_trend(df):
    """Weekly event counts over time."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["week"] = df["first_seen"].dt.to_period("W").apply(lambda r: r.start_time)
    return (
        df.groupby("week")
        .agg(events=("event_id", "count"))
        .reset_index()
    )


def peak_hours_heatmap(df):
    """Hour-of-day x day-of-week event count matrix."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["dow", "hour"])
        .agg(events=("event_id", "count"))
        .reset_index()
        .pivot(index="hour", columns="dow", values="events")
        .fillna(0)
        .rename(columns={0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"})
    )


def commute_impact_score(df):
    """Frequency x avg duration for commute windows, by direction and section."""
    if df.empty:
        return pd.DataFrame()

    def period(hour):
        if 5 <= hour < 10:
            return "Morning"
        elif 15 <= hour < 20:
            return "Evening"
        return None

    df = df.copy()
    df["period"] = df["hour"].apply(period)
    commute = df[df["period"].notna()]
    if commute.empty:
        return pd.DataFrame()
    result = (
        commute.groupby(["direction", "period", "section"])
        .agg(events=("event_id", "count"), avg_duration_min=("duration_min", "mean"))
        .reset_index()
    )
    result["impact_score"] = result["events"] * result["avg_duration_min"]
    return result.sort_values("impact_score", ascending=False)
