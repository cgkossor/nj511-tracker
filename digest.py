import smtplib
import schedule
import time
from email.mime.text import MIMEText
from datetime import datetime
import config
import analysis


def build_digest():
    df = analysis.load_events(days=7)
    if df.empty:
        return None, None

    today = datetime.now().date()
    yesterday = df[df["date"] == (today - __import__("datetime").timedelta(days=1))]

    # --- Yesterday's summary ---
    if not yesterday.empty:
        y_count = len(yesterday)
        y_avg_dur = yesterday["duration_min"].mean()
        y_busiest = yesterday["section"].value_counts().index[0] if not yesterday["section"].value_counts().empty else "N/A"
        yesterday_html = f"""
        <tr><td>Events</td><td><b>{y_count}</b></td></tr>
        <tr><td>Avg Duration</td><td><b>{y_avg_dur:.0f} min</b></td></tr>
        <tr><td>Busiest Section</td><td><b>{y_busiest}</b></td></tr>
        """
    else:
        yesterday_html = '<tr><td colspan="2">No events yesterday</td></tr>'

    # --- Worst sections (7 days) ---
    worst = analysis.worst_sections(df, top_n=5)
    if not worst.empty:
        worst_rows = "\n".join(
            f'<tr><td>{r["section"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in worst.iterrows()
        )
    else:
        worst_rows = '<tr><td colspan="3">No data</td></tr>'

    # --- Commute comparison ---
    commute = analysis.commute_comparison(df)
    if not commute.empty:
        commute_rows = "\n".join(
            f'<tr><td>{r["direction"]}</td><td>{r["period"]}</td><td>{r["events"]}</td><td>{r["avg_duration_min"]:.0f} min</td></tr>'
            for _, r in commute.iterrows()
        )
    else:
        commute_rows = '<tr><td colspan="4">No commute data</td></tr>'

    # --- Weekly trend ---
    trend = analysis.weekly_trend(df)
    if len(trend) >= 2:
        this_week = trend.iloc[-1]["events"]
        last_week = trend.iloc[-2]["events"]
        diff = this_week - last_week
        pct = (diff / last_week * 100) if last_week > 0 else 0
        arrow = "&#9650;" if diff > 0 else "&#9660;" if diff < 0 else "&#8212;"
        trend_html = f"{arrow} {abs(diff):.0f} events ({pct:+.0f}%) vs last week"
    else:
        trend_html = "Not enough data for trend"

    total_events = len(df)
    subject = f"GSP Congestion Digest — {today.strftime('%b %d')} ({total_events} events this week)"

    body = f"""\
<div style="font-family:sans-serif;font-size:14px;max-width:600px;">

<h2>GSP Congestion Daily Digest</h2>
<p style="color:#666;">{today.strftime('%A, %B %d, %Y')} | Last 7 days</p>

<h3>Yesterday's Summary</h3>
<table style="border-collapse:collapse;width:100%;" border="1" cellpadding="6">
{yesterday_html}
</table>

<h3>Worst 5 Sections (7 days)</h3>
<table style="border-collapse:collapse;width:100%;" border="1" cellpadding="6">
<tr style="background:#f0f0f0;"><th>Section</th><th>Events</th><th>Avg Duration</th></tr>
{worst_rows}
</table>

<h3>NB vs SB Commute Comparison</h3>
<table style="border-collapse:collapse;width:100%;" border="1" cellpadding="6">
<tr style="background:#f0f0f0;"><th>Direction</th><th>Period</th><th>Events</th><th>Avg Duration</th></tr>
{commute_rows}
</table>

<h3>Weekly Trend</h3>
<p>{trend_html}</p>

<br>
<small style="color:#999;">GSP Congestion Trend Tracker | Full parkway coverage</small>
</div>
"""
    return subject, body


def send_digest():
    print(f"[{datetime.now()}] Generating daily digest...")
    subject, body = build_digest()
    if subject is None:
        print(f"[{datetime.now()}] No data for digest, skipping.")
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
        print(f"[{datetime.now()}] Digest sent: {subject}")
    except Exception as e:
        print(f"[{datetime.now()}] Digest email error: {e}")


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
