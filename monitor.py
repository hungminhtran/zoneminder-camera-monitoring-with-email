#!/usr/bin/env python3
"""
NVR monitor: query ZoneMinder for cameras with low capture FPS, notify by email.

FPS is averaged over the last MAX_SAMPLES cron runs to smooth out
ZoneMinder's noisy CaptureFPS reporting.

Env vars:
    ZM_URL, ZM_USER, ZM_PASSWORD       ZoneMinder base URL (include /zm if used)
    ZM_INSECURE=1                      skip TLS verify (self-signed cert)
    EMAIL_FROM, EMAIL_PASS, EMAIL_TO   Gmail sender (App Password), recipient
    LOW_FPS_THRESHOLD=10               FPS below this counts as "low"

State:
    ./monitor_config.json              per-camera rolling samples + backoff
"""
import json
import os
import smtplib
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import requests


# ---------- config ----------
BASE = "http://10.66.66.2"  # e.g. https://host/zm
USER = "admin"
PASS = ""
VERIFY = True
EMAIL_FROM = ""
EMAIL_PASS = ""
EMAIL_TO = ""

STATE_FILE        = Path("./monitor_config.json")
LOW_FPS_THRESHOLD = float(os.environ.get("LOW_FPS_THRESHOLD", "18"))
BACKOFF_H         = [1, 2, 4, 8, 24]     # hours; last element is the ceiling
MIN_SAMPLES       = 3                    # samples needed before deciding
MAX_SAMPLES       = 3                    # rolling window size
VN_TZ             = timezone(timedelta(hours=7))


# ---------- email ----------
def send_gmail(
    username: str,
    app_password: str,
    to: str,
    subject: str,
    body: str,
    *,
    html: bool = False,
    from_name: str | None = None,
    timeout: float = 15.0,
) -> None:
    """Send email via Gmail using implicit TLS on port 465."""
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{username}>" if from_name else username
    msg["To"] = to
    msg["Subject"] = subject
    if html:
        msg.set_content("This message requires an HTML-capable client.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=timeout) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(msg)


# ---------- ZoneMinder API ----------
def login(payload: dict) -> dict:
    r = requests.post(f"{BASE}/api/host/login.json", data=payload, verify=VERIFY, timeout=15)
    r.raise_for_status()
    d = r.json()
    if "access_token" not in d:
        sys.exit(f"No access_token (ZM < 1.34 or API disabled): {d}")
    return d


_d = login({"user": USER, "pass": PASS})
access, refresh = _d["access_token"], _d["refresh_token"]
access_exp = time.time() + _d["access_token_expires"]


def get(path: str) -> dict:
    global access, access_exp
    if time.time() > access_exp - 60:
        access = login({"token": refresh})["access_token"]
        access_exp = time.time() + 3600
    r = requests.get(f"{BASE}{path}", params={"token": access}, verify=VERIFY, timeout=15)
    r.raise_for_status()
    return r.json()


def extract(entry: dict) -> tuple[str, str, float, float] | None:
    """Return (source, resolution, fps, bandwidth_kbps), or None if deleted."""
    mon = entry.get("Monitor") or {}
    if mon.get("Deleted"):
        return None
    st     = entry.get("Monitor_Status") or {}
    source = mon.get("Path") or mon.get("Type") or ""
    w, h   = mon.get("Width") or 0, mon.get("Height") or 0
    res    = f"{w}x{h}" if w and h else "-"
    fps    = float(st.get("CaptureFPS") or 0)
    bw_kb  = round(int(st.get("CaptureBandwidth") or 0) / 1024, 1)
    return source, res, fps, bw_kb


# ---------- state ----------
def load_state() -> dict:
    """Read ./monitor_config.json. Missing or corrupt -> {}."""
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    """Write ./monitor_config.json atomically via .tmp + rename."""
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_FILE)


def should_notify(state: dict, source: str, fps: float) -> tuple[bool, float]:
    """
    Append fps to the camera's rolling window, then decide.

    Rules:
      - len(samples) < MIN_SAMPLES              -> no decision yet
      - avg >= LOW_FPS_THRESHOLD                -> healthy, reset backoff
      - avg < threshold, backoff not due        -> quiet
      - avg < threshold, backoff due or unset   -> notify, advance backoff

    Update state in-place. Return (notify, avg_fps).
    """
    now  = time.time()
    prev = state.get(source) or {"samples": [], "next_at": 0.0, "step": 0}

    samples = (prev["samples"] + [fps])[-MAX_SAMPLES:]
    prev["samples"] = samples
    state[source]   = prev

    avg = sum(samples) / len(samples)

    if len(samples) < MIN_SAMPLES:
        return False, avg

    if avg >= LOW_FPS_THRESHOLD:
        prev["next_at"] = 0.0
        prev["step"]    = 0
        return False, avg

    if prev["next_at"] == 0.0 or now >= prev["next_at"]:
        step = prev.get("step", 0)
        prev["next_at"] = now + BACKOFF_H[min(step, len(BACKOFF_H) - 1)] * 3600
        prev["step"]    = min(step + 1, len(BACKOFF_H) - 1)
        return True, avg

    return False, avg


# ---------- main ----------
def main() -> int:
    data  = get("/api/monitors.json")
    state = load_state()
    new_state: dict[str, dict] = {}         # rebuilt from live cameras only

    to_notify: dict[str, dict] = {}

    for m in data.get("monitors", []):
        row = extract(m)
        if row is None:
            continue
        source, res, fps, bw_kb = row

        # carry over previous samples if any
        new_state[source] = state.get(source) or {"samples": [], "next_at": 0.0, "step": 0}

        notify, avg_fps = should_notify(new_state, source, fps)
        print(f'{source:<60}  {res:<11}  '
              f'raw={fps:>6.2f}  avg={avg_fps:>6.2f}  {bw_kb:>8.1f} KB/s')

        if notify:
            to_notify[source] = {"res": res, "avg_fps": avg_fps, "bw_kb": bw_kb}

    save_state(new_state)                   # cameras removed from ZM drop out here

    if not to_notify:
        print("\nNothing to notify.")
        return 0

    ts    = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        f"Cameras with avg FPS < {LOW_FPS_THRESHOLD:g} "
        f"(over last {MAX_SAMPLES} samples, checked at {ts})",
        "-" * 70,
    ]
    for source, c in to_notify.items():
        lines += [
            f"Source     : {source}",
            f"Resolution : {c['res']}",
            f"Avg FPS    : {c['avg_fps']:.2f}",
            f"Bandwidth  : {c['bw_kb']:.1f} KB/s",
            "",
        ]

    send_gmail(
        username=EMAIL_FROM,
        app_password=EMAIL_PASS,
        to=EMAIL_TO,
        subject=f"[NVR] {len(to_notify)} camera(s) below {LOW_FPS_THRESHOLD:g} fps",
        body="\n".join(lines),
        html=False,
        from_name="NVR Monitor",
    )
    print(f"\nEmail sent for {len(to_notify)} camera(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
