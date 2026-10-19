# FeedOps Automation & Scheduler Guide

## 1. CLI Commands vs. Active Scheduler

FeedOps provides administrative CLI automation commands implemented via Click and the Flask Application Factory:

- `flask refresh-feeds`: Iterates through all configured RSS/Atom feeds, fetches entries safely using SSRF-hardened network handlers, and inserts new articles idempotently.
- `flask check-price-alerts`: Scans saved items, verifies user notification preferences, and dispatches price drop notification events when catalog prices drop.

### Key Distinction
> [!IMPORTANT]
> **CLI commands are single-run automation utilities, NOT an active in-process daemon.**  
> Executing `flask refresh-feeds` runs one cycle synchronously and exits cleanly. To run automated refreshes continuously or at recurring intervals, an external scheduler or process supervisor must invoke these CLI commands.

---

## 2. Production Scheduler Configurations

### Option A: Linux Cron (Recommended for VM / Bare Metal)
Set up a standard cron job under the application user:

```bash
# Edit crontab
crontab -e

# Run feed refresh every 30 minutes
*/30 * * * * cd /opt/feedops && /opt/feedops/.venv/bin/flask --app run refresh-feeds >> /var/log/feedops/feeds.log 2>&1

# Run price alert monitor every hour
0 * * * * cd /opt/feedops && /opt/feedops/.venv/bin/flask --app run check-price-alerts >> /var/log/feedops/alerts.log 2>&1
```

### Option B: Systemd Timers (Modern Linux)
Create `/etc/systemd/system/feedops-refresh.service`:
```ini
[Unit]
Description=FeedOps Background Feed Ingestion
After=network.target

[Service]
Type=oneshot
User=feedops
WorkingDirectory=/opt/feedops
ExecStart=/opt/feedops/.venv/bin/flask --app run refresh-feeds
```

Create `/etc/systemd/system/feedops-refresh.timer`:
```ini
[Unit]
Description=Run FeedOps Feed Ingestion periodically

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```
Enable and start the timer:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now feedops-refresh.timer
```

### Option C: Windows Task Scheduler (Windows Environments)
Create a Scheduled Task via PowerShell:
```powershell
$Action = New-ScheduledTaskAction -Execute "d:\Larxius Projects\feedops\.venv\Scripts\flask.exe" -Argument "--app run refresh-feeds" -WorkingDirectory "d:\Larxius Projects\feedops"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "FeedOps-RefreshFeeds" -Action $Action -Trigger $Trigger -Description "Recurring RSS Feed Ingestion"
```

---

## 3. Concurrency & Non-Blocking Design

- **SQLite WAL Mode & Read/Write Isolation**: The CLI commands run in their own short-lived process. Because SQLite supports multi-reader single-writer transactions, background ingestion does not block ordinary HTTP web requests.
- **Deduplication**: `feed_service.fetch_and_store` queries by `(feed_id, url)` before inserting. Repeated executions will never produce duplicate articles.
- **Alert Deduplication**: `privacy_service.trigger_price_drop_alert` checks `(user_id, product_id, event_type, title)` before dispatching notifications, guaranteeing that repeated runs do not spam users with duplicate notifications.
- **Error Logging**: Ingestion failures are recorded directly on the `feeds` table (`last_fetch_status='error'`, `last_error=...`), and summarized in CLI stdout/stderr.
