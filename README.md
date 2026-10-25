# zoneminder-camera-monitoring-with-email
Lightweight watchdog for ZoneMinder: polls the REST API on a cron schedule, averages CaptureFPS over the last N samples to filter ZoneMinder's noisy reporting, and emails an alert when a camera stays below threshold. Each camera gets its own backoff schedule (1h → 2h → 4h → 8h → 24h) so a stuck camera doesn't flood your inbox — but a recovered-then-failed camera alerts immediately.
Features

    ZoneMinder API v2 (JWT access/refresh tokens, auto-refresh)

    Rolling average over the last 3 samples — kills single-sample false positives

    Per-camera exponential backoff

    Deleted cameras drop out of state automatically

    Gmail SMTP over implicit TLS (port 465)

    Single-file, stdlib + requests, no daemon — cron-friendly

    Chart + webui built-in
