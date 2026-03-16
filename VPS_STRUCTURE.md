# VPS Structure & How to Run Services

## Overview

Hostinger KVM 1 (Ubuntu 24.04) at `187.124.152.231`. SSH via `ssh root@187.124.152.231` (key-only auth).

Everything runs in Docker on a shared `web` network, fronted by an Nginx reverse proxy.

## Layout

```
/opt/
├── powmetrix/              ← Production SaaS (DO NOT TOUCH)
├── nginx-proxy/            ← Nginx reverse proxy (Docker container)
│   ├── docker-compose.yml
│   └── conf.d/             ← Per-site Nginx configs
├── hobbies/
│   ├── docker-compose.yml  ← All hobby Docker services
│   ├── .env                ← Secrets (recgov-monitor, etc.)
│   ├── down-the-canyon/    ← Next.js app (port 3001)
│   ├── recgov-monitor/     ← Python web app (port 5000)
│   ├── services/           ← Systemd-based services (not Docker)
│   │   ├── yosemite-scanner/
│   │   ├── inyo-scanner/
│   │   ├── nj511-tracker/
│   │   ├── grca-bot/
│   │   └── website-tracker/ ← Website change tracker (this repo)
│   └── data/               ← Persistent data (.db, .json)
│       ├── recgov-monitor/
│       ├── yosemite-scanner/
│       ├── inyo-scanner/
│       ├── nj511-tracker/
│       ├── grca-bot/
│       └── website-tracker/  ← tracker.db
└──
```

## How Services Run

### Docker services (via docker-compose)

The main compose file at `/opt/hobbies/docker-compose.yml` manages:
- **down-the-canyon** — Next.js standalone, port 3001 internal
- **recgov-monitor** + **recgov-poller** — Python, port 5000 internal

All containers sit on the `web` Docker network so Nginx can route to them.

### Systemd services (Python venvs)

Some services run as systemd units with Python virtual environments instead of Docker:
- yosemite-scanner, inyo-scanner, nj511-monitor, grca-bot, website-tracker
- Code under `/opt/hobbies/services/<name>/` (git repos, venvs)
- Data under `/opt/hobbies/data/<name>/` (event logs, databases, state files)
- Services use `--data-dir /opt/hobbies/data/<name>` to write persistent files to the data directory
- This separation means deploys (`git reset --hard`) can't destroy data files

Example systemd unit (`/etc/systemd/system/yosemite-scanner.service`):
```ini
[Service]
WorkingDirectory=/opt/hobbies/services/yosemite-scanner
ExecStart=/opt/hobbies/services/yosemite-scanner/venv/bin/python -u recgov_scanner.py --loop --config config.json --data-dir /opt/hobbies/data/yosemite-scanner
```

Example systemd unit (`/etc/systemd/system/website-tracker.service`):
```ini
[Service]
WorkingDirectory=/opt/hobbies/services/website-tracker
ExecStart=/opt/hobbies/services/website-tracker/venv/bin/python -u tracker.py --data-dir /opt/hobbies/data/website-tracker
```

## Migration Note: Data Directory Split

When we moved from the old Oracle VM to this Hostinger VPS, the data files (event_log.json, permit_history.db, etc.) were copied into `/opt/hobbies/data/<name>/`. However, the scanner scripts originally used relative paths — writing data to whichever directory they ran from (the `services/` folder). This caused the scanner to create **fresh data files in `services/`** while the real accumulated history sat untouched in `data/`.

**Symptoms:** Weekly reports showed only a few days of events despite getting email alerts all week. Two copies of data files existed — one in `services/` (recent, incomplete) and one in `data/` (older, more complete).

**How we fixed it (yosemite-scanner, March 2026):**
1. Stop the scanner: `sudo systemctl stop yosemite-scanner`
2. Merge both event logs into `data/`:
   ```bash
   python3 -c "
   import json
   d1 = json.load(open('/opt/hobbies/data/yosemite-scanner/event_log.json'))
   d2 = json.load(open('/opt/hobbies/services/yosemite-scanner/event_log.json'))
   seen = set()
   merged = []
   for e in d1 + d2:
       key = (e['time'], e.get('type'), e.get('division_id'), e.get('date'))
       if key not in seen:
           seen.add(key)
           merged.append(e)
   merged.sort(key=lambda e: e['time'])
   with open('/opt/hobbies/data/yosemite-scanner/event_log.json', 'w') as f:
       json.dump(merged, f, indent=2)
   "
   ```
3. Add `--data-dir` to the systemd service ExecStart line
4. `sudo systemctl daemon-reload && sudo systemctl start yosemite-scanner`

**For other services:** If inyo-scanner, nj511-tracker, or grca-bot have the same issue, they'll need the same treatment — add `--data-dir` support to the script, merge any split data files, and update their systemd units.

## Adding a New Service

1. Clone the repo into `/opt/hobbies/your-new-service/`
2. Add a service block in `/opt/hobbies/docker-compose.yml` on the `web` network
3. If it needs a subdomain:
   - Add an Nginx config in `/opt/nginx-proxy/conf.d/`
   - Add a Cloudflare A record pointing to `187.124.152.231` (proxied)
4. Run `docker compose up -d` from `/opt/hobbies/`

## DNS & SSL

- **Registrar**: WordPress.com
- **DNS**: Cloudflare (free plan)
- **SSL**: Cloudflare automatic, mode set to Full
- **A records**: `@`, `www`, `scanner` → `187.124.152.231` (proxied)
