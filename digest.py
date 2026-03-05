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
    today = now_et.date()
    yesterday_date = today - timedelta(days=1)
    yesterday = df[df["date"] == yesterday_date]

    # --- Yesterday by category ---
    if not yesterday.empty:
        cat_summary = analysis.events_by_category(yesterday)
        yesterday_rows = "\n".join(
            f'<tr><td>{r["category"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in cat_summary.iterrows()
        )
        y_total = len(yesterday)
        yesterday_header = f"Yesterday ({analysis.format_date(datetime.combine(yesterday_date, datetime.min.time()))}) — {y_total} events"
    else:
        yesterday_rows = '<tr><td colspan="3">No events yesterday</td></tr>'
        yesterday_header = "Yesterday — No events"

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
    date_str = now_et.strftime("%a, %b ") + str(now_et.day) + now_et.strftime(", %Y")
    subject = f"GSP Traffic Digest \u2014 {now_et.strftime('%b')} {now_et.day} ({total_events} events this week)"

    ts = 'style="border-collapse:collapse;width:100%;" border="1" cellpadding="6"'
    hs = 'style="background:#f0f0f0;"'

    body = f"""\
<div style="font-family:sans-serif;font-size:14px;max-width:600px;">

<h2>GSP Traffic Daily Digest</h2>
<p style="color:#666;">{date_str} | Last 7 days | All times ET</p>

<h3>{yesterday_header}</h3>
<table {ts}>
<tr {hs}><th>Category</th><th>Events</th><th>Avg Duration</th></tr>
{yesterday_rows}
</table>

<h3>Top Incident Hotspots (7 days)</h3>
<table {ts}>
<tr {hs}><th>Section</th><th>Incidents</th></tr>
{inc_rows}
</table>

<h3>Top Congestion Hotspots (7 days)</h3>
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

<h3>Weekly Trend by Category</h3>
<table {ts}>
<tr {hs}><th>Category</th><th>This Week</th><th>Last Week</th><th>Change</th></tr>
{trend_rows}
</table>

<br>
<small style="color:#999;">GSP Traffic Trend Tracker | Full parkway, all event types</small>
</div>
"""
    return subject, body


def send_digest():
    now = analysis.to_et(datetime.now(timezone.utc))
    print(f"[{analysis.format_datetime(now)}] Generating daily digest...")
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
        print(f"GSP Digest scheduler started. Will send at {config.DIGEST_HOUR}:00 daily.")
        schedule.every().day.at(f"{config.DIGEST_HOUR:02d}:00").do(send_digest)
        while True:
            schedule.run_pending()
            time.sleep(60)
