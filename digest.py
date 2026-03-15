import smtplib
import schedule
import time
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
import config
import analysis


def build_digest():
    df = analysis.load_events(days=7)
    if df.empty:
        return None, None

    now_et = analysis.to_et(datetime.now(timezone.utc))
    week_start = (now_et - timedelta(days=7)).date()
    week_end = (now_et - timedelta(days=1)).date()

    # --- Week summary by category ---
    cat_summary = analysis.events_by_category(df)
    if not cat_summary.empty:
        summary_rows = "\n".join(
            f'<tr><td>{r["category"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in cat_summary.iterrows()
        )
    else:
        summary_rows = '<tr><td colspan="3">No events this week</td></tr>'

    # --- Busiest day ---
    day_counts = df.groupby("date").size()
    if not day_counts.empty:
        busiest_date = day_counts.idxmax()
        busiest_count = day_counts.max()
        busiest_str = f"{analysis.format_date(datetime.combine(busiest_date, datetime.min.time(), tzinfo=analysis.ET))} ({busiest_count} events)"
    else:
        busiest_str = "N/A"

    # --- Top incident hotspots (7 days) ---
    inc_hot = analysis.incident_hotspots(df, top_n=5)
    if not inc_hot.empty:
        inc_rows = "\n".join(
            f'<tr><td>{r["section"]}</td><td>{r["events"]}</td></tr>'
            for _, r in inc_hot.iterrows()
        )
    else:
        inc_rows = '<tr><td colspan="2">No incident data</td></tr>'

    # --- Top congestion hotspots (7 days) ---
    cong_hot = analysis.worst_sections(df, top_n=5, category="Congestion")
    if not cong_hot.empty:
        cong_rows = "\n".join(
            f'<tr><td>{r["section"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in cong_hot.iterrows()
        )
    else:
        cong_rows = '<tr><td colspan="3">No congestion data</td></tr>'

    # --- Incident-congestion overlap ---
    overlap = analysis.concurrent_events(df)
    if not overlap.empty:
        overlap_rows = "\n".join(
            f'<tr><td>{r["section"]}</td><td>{r["overlaps"]}</td></tr>'
            for _, r in overlap.head(5).iterrows()
        )
    else:
        overlap_rows = '<tr><td colspan="2">No overlapping events found</td></tr>'

    # --- NB vs SB commute comparison (congestion) ---
    commute = analysis.commute_comparison(df)
    if not commute.empty:
        commute_rows = "\n".join(
            f'<tr><td>{r["direction"]}</td><td>{r["period"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in commute.iterrows()
        )
    else:
        commute_rows = '<tr><td colspan="4">No commute data</td></tr>'

    # --- Weekly trend by category ---
    trend = analysis.weekly_trend_by_category(df)
    if not trend.empty and len(trend["week"].unique()) >= 2:
        weeks = sorted(trend["week"].unique())
        this_week = trend[trend["week"] == weeks[-1]]
        last_week = trend[trend["week"] == weeks[-2]]
        trend_rows = ""
        for cat in sorted(df["category"].unique()):
            tw = this_week[this_week["category"] == cat]["events"].sum()
            lw = last_week[last_week["category"] == cat]["events"].sum()
            diff = tw - lw
            arrow = "&#9650;" if diff > 0 else "&#9660;" if diff < 0 else "&#8212;"
            trend_rows += f'<tr><td>{cat}</td><td>{tw}</td><td>{lw}</td><td>{arrow} {abs(diff)}</td></tr>\n'
    else:
        trend_rows = '<tr><td colspan="4">Not enough data for trend</td></tr>'

    total_events = len(df)
    week_start_str = analysis.format_date(datetime.combine(week_start, datetime.min.time(), tzinfo=analysis.ET))
    week_end_str = analysis.format_date(datetime.combine(week_end, datetime.min.time(), tzinfo=analysis.ET))
    subject = f"GSP Weekly Digest \u2014 {week_start_str} \u2013 {week_end_str} ({total_events} events)"

    ts = 'style="border-collapse:collapse;width:100%;" border="1" cellpadding="6"'
    hs = 'style="background:#f0f0f0;"'

    body = f"""\
<div style="font-family:sans-serif;font-size:14px;max-width:600px;">

<h2>GSP Tracker Weekly Digest</h2>
<p style="color:#666;">{week_start_str} \u2013 {week_end_str} | {total_events} total events | All times ET</p>

<h3>Week Summary by Category</h3>
<table {ts}>
<tr {hs}><th>Category</th><th>Events</th><th>Avg Duration</th></tr>
{summary_rows}
</table>
<p style="font-size:12px;color:#666;">Busiest day: {busiest_str}</p>

<h3>Top Incident Hotspots</h3>
<table {ts}>
<tr {hs}><th>Section</th><th>Incidents</th></tr>
{inc_rows}
</table>

<h3>Top Congestion Hotspots</h3>
<table {ts}>
<tr {hs}><th>Section</th><th>Events</th><th>Avg Duration</th></tr>
{cong_rows}
</table>

<h3>Incident-Congestion Overlap</h3>
<p style="color:#666;font-size:12px;">Sections where incidents and congestion occur at the same time</p>
<table {ts}>
<tr {hs}><th>Section</th><th>Overlapping Events</th></tr>
{overlap_rows}
</table>

<h3>NB vs SB Commute (Congestion)</h3>
<table {ts}>
<tr {hs}><th>Direction</th><th>Period</th><th>Events</th><th>Avg Duration</th></tr>
{commute_rows}
</table>

<h3>Week-over-Week Trend</h3>
<table {ts}>
<tr {hs}><th>Category</th><th>This Week</th><th>Last Week</th><th>Change</th></tr>
{trend_rows}
</table>

<br>
<small style="color:#999;">GSP Tracker | Full parkway, all event types</small>
</div>
"""
    return subject, body


def send_digest():
    now = analysis.to_et(datetime.now(timezone.utc))
    print(f"[{analysis.format_datetime(now)}] Generating weekly digest...")
    subject, body = build_digest()
    if subject is None:
        print(f"[{analysis.format_datetime(now)}] No data for digest, skipping.")
        return

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_FROM, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        print(f"[{analysis.format_datetime(now)}] Digest sent: {subject}")
    except Exception as e:
        print(f"[{analysis.format_datetime(now)}] Digest email error: {e}")


if __name__ == "__main__":
    import sys
    if "--now" in sys.argv:
        send_digest()
    else:
        # Convert ET hour to UTC for the scheduler (VPS runs UTC)
        digest_et = datetime.now(analysis.ET).replace(hour=config.DIGEST_HOUR, minute=0, second=0)
        digest_utc_hour = digest_et.astimezone(timezone.utc).hour
        print(f"GSP Digest scheduler started. Will send Sundays at {config.DIGEST_HOUR}:00 ET ({digest_utc_hour}:00 UTC).")
        schedule.every().sunday.at(f"{digest_utc_hour:02d}:00").do(send_digest)
        while True:
            schedule.run_pending()
            time.sleep(60)
