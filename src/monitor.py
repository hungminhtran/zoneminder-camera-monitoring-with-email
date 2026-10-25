import logging
import smtplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import config

log = logging.getLogger("nvr.monitor")

SECONDS_PER_HOUR = 3600


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

    def get(self, path: str) -> dict:
        if time.time() > self.access_exp - 60:
            data = self.login({"token": self.refresh})
            self.access = data["access_token"]
            self.refresh = data.get("refresh_token", self.refresh)
            self.access_exp = time.time() + data.get("access_token_expires", 3600)
        response = self.session.get(
            f"{self.base}{path}", params={"token": self.access}, timeout=15
        )
        response.raise_for_status()
        return response.json()

    def monitors(self) -> list:
        return self.get("/api/monitors.json").get("monitors", [])
