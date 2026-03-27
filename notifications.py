import json
import re
import smtplib
import time
import urllib.request
from email.mime.text import MIMEText
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import config

ET = ZoneInfo("America/New_York")


def _strip_html(html):
    """Convert HTML to plain text for Discord."""
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</td>', '  ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&#9650;', '▲', text)
    text = re.sub(r'&#9660;', '▼', text)
    text = re.sub(r'&#8212;', '—', text)
    text = re.sub(r'&[a-zA-Z]+;', '', text)  # remaining HTML entities
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_discord_message(subject, message, limit=1900):
    """Split message into Discord-safe chunks (2000 char limit)."""
    header = f"**{subject}**\n"
    overhead = len(header) + 8  # ```\n ... \n```
    available = limit - overhead

    if len(message) <= available:
        return [f"{header}```\n{message}\n```"]

    chunks = []
    lines = message.split("\n")
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > available:
            if current:
                chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))

    result = []
    for i, chunk in enumerate(chunks):
        prefix = header if i == 0 else f"**{subject} (cont.)**\n"
        result.append(f"{prefix}```\n{chunk}\n```")
    return result


def _send_discord(subject, message, max_retries=3):
    """Send a message to Discord via webhook. Splits long messages automatically."""
    url = config.DISCORD_WEBHOOK_URL
    chunks = _split_discord_message(subject, message)

    for chunk in chunks:
        payload = json.dumps({"content": chunk})
        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "gsp-511",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"[{datetime.now(ET)}] Discord notification sent (HTTP {resp.status})")
                break
            except Exception as e:
                if attempt < max_retries:
                    delay = 5 * (2 ** (attempt - 1))
                    print(
                        f"[{datetime.now(ET)}] Discord send failed (attempt {attempt}/{max_retries}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    print(f"[{datetime.now(ET)}] Discord send failed after {max_retries} attempts: {e}")
                    return False
    return True


def _send_email(subject, body):
    """Send an HTML email via SMTP."""
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
        return True
    except Exception as e:
        print(f"[{datetime.now(ET)}] Email error: {e}")
        return False


def notify_email(subject, body):
    """Send notification via email only."""
    return _send_email(subject, body)


def notify_discord(subject, body):
    """Send notification via Discord only. HTML body is auto-stripped to plain text."""
    if config.DISCORD_ENABLED and config.DISCORD_WEBHOOK_URL:
        plain = _strip_html(body)
        return _send_discord(subject, plain)
    return False
