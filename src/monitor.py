import logging
import os
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import config
import db

log = logging.getLogger("nvr.monitor")

SECONDS_PER_HOUR = 3600
COLLECTOR_ENV = (
    "ZM_URL", "ZM_USER", "ZM_PASSWORD",
    "EMAIL_FROM", "EMAIL_PASS", "EMAIL_TO",
)


@dataclass(frozen=True)
class Settings:
    zm_url: str
    zm_user: str
    zm_password: str
    verify: bool
    email_from: str
    email_pass: str
    email_to: str


def load_settings() -> Settings | None:
    missing = [name for name in COLLECTOR_ENV if not os.environ.get(name, "").strip()]
    if missing:
        log.error("collector disabled: missing %s", ", ".join(missing))
        return None
    return Settings(
        zm_url=os.environ["ZM_URL"].strip().rstrip("/"),
        zm_user=os.environ["ZM_USER"].strip(),
        zm_password=os.environ["ZM_PASSWORD"].strip(),
        verify=not config.flag("ZM_INSECURE"),
        email_from=os.environ["EMAIL_FROM"].strip(),
        email_pass=os.environ["EMAIL_PASS"].strip(),
        email_to=os.environ["EMAIL_TO"].strip(),
    )


@dataclass(frozen=True)
class Camera:
    source: str
    resolution: str
    fps: float
    bandwidth_kb: float
    connected: bool


@dataclass(frozen=True)
class Decision:
    samples: tuple
    avg: float
    next_at: float
    step: int
    notify: bool


def slot_for(now: float, interval: int = config.SAMPLE_SECONDS) -> int:
    timestamp = int(now)
    return timestamp - timestamp % interval


def next_backoff(step: int, backoff_h=config.BACKOFF_H) -> float:
    return backoff_h[min(step, len(backoff_h) - 1)] * SECONDS_PER_HOUR


def extract(entry: dict) -> Camera | None:
    monitor = entry.get("Monitor") or {}
    if monitor.get("Deleted"):
        return None

    status = entry.get("Monitor_Status") or {}
    fallback = monitor.get("Path") or monitor.get("Type") or ""
    source = monitor.get("Name") or fallback
    width = monitor.get("Width") or 0
    height = monitor.get("Height") or 0
    resolution = f"{width}x{height}" if width and height else "-"
    fps = float(status.get("CaptureFPS") or 0)
    bandwidth_kb = round(int(status.get("CaptureBandwidth") or 0) / 1024, 1)
    connected = status.get("Status") == "Connected"
    return Camera(source, resolution, fps, bandwidth_kb, connected)


def should_notify(
    samples,
    next_at: float,
    step: int,
    fps: float,
    now: float,
    *,
    threshold: float = config.LOW_FPS_THRESHOLD,
    min_samples: int = config.MIN_SAMPLES,
    max_samples: int = config.MAX_SAMPLES,
    backoff_h=config.BACKOFF_H,
) -> Decision:
    window = (tuple(samples) + (float(fps),))[-max_samples:]
    avg = sum(window) / len(window)

    if len(window) < min_samples:
        return Decision(window, avg, next_at, step, False)

    if avg >= threshold:
        return Decision(window, avg, 0.0, 0, False)

    if next_at != 0.0 and now < next_at:
        return Decision(window, avg, next_at, step, False)

    return Decision(
        window,
        avg,
        now + next_backoff(step, backoff_h),
        min(step + 1, len(backoff_h) - 1),
        True,
    )


def build_email_body(alerts, ts: int, threshold: float,
                     tz_name: str = config.DISPLAY_TZ) -> str:
    if not alerts:
        return ""

    stamp = datetime.fromtimestamp(ts, ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        f"{len(alerts)} camera(s) below {threshold:g} fps (checked at {stamp})",
        "-" * 70,
    ]
    for alert in alerts:
        lines += [
            f"Source     : {alert['source']}",
            f"Resolution : {alert['resolution']}",
            f"Avg FPS    : {alert['avg_fps']:.2f}",
            f"Bandwidth  : {alert['bandwidth_kb']:.1f} KB/s",
            "",
        ]
    return "\n".join(lines)


def send_gmail(username: str, app_password: str, to: str, subject: str, body: str,
               *, from_name: str | None = None, timeout: float = 15.0) -> None:
    message = EmailMessage()
    message["From"] = f"{from_name} <{username}>" if from_name else username
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=timeout) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(message)


class ZmClient:
    def __init__(self, base: str, user: str, password: str, verify: bool = True):
        import requests

        self.base = base.rstrip("/")
        self.user = user
        self.password = password
        self.verify = verify
        self.session = requests.Session()
        self.session.verify = verify
        self.access = ""
        self.refresh = ""
        self.access_exp = 0.0

    def login(self, payload: dict) -> dict:
        response = self.session.post(
            f"{self.base}/api/host/login.json", data=payload, timeout=15
        )
        response.raise_for_status()
        data = response.json()
        if "access_token" not in data:
            raise RuntimeError(f"no access_token (ZM < 1.34 or API disabled): {data}")
        return data

    def authenticate(self) -> None:
        data = self.login({"user": self.user, "pass": self.password})
        self.access = data["access_token"]
        self.refresh = data["refresh_token"]
        self.access_exp = time.time() + data["access_token_expires"]

    def _ensure_token(self) -> None:
        if not self.access:
            self.authenticate()
            return
        if time.time() > self.access_exp - 60:
            data = self.login({"token": self.refresh})
            self.access = data["access_token"]
            self.refresh = data.get("refresh_token", self.refresh)
            self.access_exp = time.time() + data.get("access_token_expires", 3600)

    def get(self, path: str) -> dict:
        self._ensure_token()
        response = self.session.get(
            f"{self.base}{path}", params={"token": self.access}, timeout=15
        )
        response.raise_for_status()
        return response.json()

    def monitors(self) -> list:
        return self.get("/api/monitors.json").get("monitors", [])


def tick(conn, client: "ZmClient", now: float) -> list:
    slot = slot_for(now, config.SAMPLE_SECONDS)
    alerts = []

    for entry in client.monitors():
        camera = extract(entry)
        if camera is None:
            continue

        db.add_sample(conn, camera.source, slot, camera.fps, camera.bandwidth_kb)
        prior = db.recent_fps(conn, camera.source, config.MAX_SAMPLES)[:-1]
        state = db.get_camera(conn, camera.source)
        next_at = state["next_at"] if state else 0.0
        step = state["step"] if state else 0

        decision = should_notify(prior, next_at, step, camera.fps, now)

        db.save_camera(
            conn, camera.source, camera.resolution, decision.next_at, decision.step, slot
        )
        log.info(
            "%s %s fps=%.2f avg=%.2f bw=%.1f KB/s notify=%s",
            camera.source, camera.resolution, camera.fps,
            decision.avg, camera.bandwidth_kb, decision.notify,
        )

        if decision.notify:
            alerts.append({
                "source": camera.source,
                "resolution": camera.resolution,
                "avg_fps": decision.avg,
                "bandwidth_kb": camera.bandwidth_kb,
                "step": decision.step,
            })

    return alerts


def deliver(conn, ts: int, alerts: list, settings: Settings) -> None:
    subject = f"[NVR] {len(alerts)} camera(s) below {config.LOW_FPS_THRESHOLD:g} fps"
    body = build_email_body(alerts, ts, config.LOW_FPS_THRESHOLD)

    ok, error = True, None
    try:
        send_gmail(
            settings.email_from, settings.email_pass, settings.email_to,
            subject, body, from_name="ZoneMinder monitoring",
        )
        log.info("email sent for %d camera(s)", len(alerts))
    except Exception as exc:
        ok, error = False, str(exc)
        log.exception("email failed")

    for alert in alerts:
        db.add_notification(
            conn, ts, alert["source"], alert["resolution"], alert["avg_fps"],
            alert["bandwidth_kb"], alert["step"], ok, error,
        )


def run(stop_event, settings: Settings) -> None:
    client = ZmClient(
        settings.zm_url, settings.zm_user, settings.zm_password, settings.verify
    )
    conn = db.connect()
    log.info("collector started: interval=%ss retention=%sd",
             config.SAMPLE_SECONDS, config.RETENTION_DAYS)

    if db.is_seeded(conn):
        log.warning("database contains seed data; delete it before production use")

    try:
        while not stop_event.is_set():
            now = time.time()
            slot = slot_for(now, config.SAMPLE_SECONDS)
            try:
                alerts = tick(conn, client, now)
                if alerts and db.notify_enabled(conn):
                    deliver(conn, slot, alerts, settings)
                elif alerts:
                    log.info("notifications paused: %d alert(s) suppressed", len(alerts))
                db.prune(
                    conn, slot - int(config.RETENTION_DAYS * config.SECONDS_PER_DAY)
                )
                db.record_db_size(
                    db.db_size_samples, now, db.file_size(config.DB_PATH)
                )
            except Exception:
                log.exception("tick failed, retrying next interval")
            stop_event.wait(config.SAMPLE_SECONDS - (time.time() % config.SAMPLE_SECONDS) + 2)
    finally:
        conn.close()
        log.info("collector stopped")
