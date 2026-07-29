#!/usr/bin/env python3
"""Minimal Epson ES-60W physical-button-to-SANE proof receiver."""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SCANNER_IP = "192.168.6.134"
LOCAL_IP = "192.168.6.180"
SCANNER_PORT = 1865
EVENT_GROUP = "239.255.255.253"
EVENT_PORT = 2968
EVENT_MARKER = b"service:NetScanMonitor-agent"
DEVICE = f"epsonds:net:{SCANNER_IP}"
TRANSACTION_RETENTION_SECONDS = 120.0
REACHABILITY_INTERVAL = 2.0
SCAN_START_DELAY_SECONDS = 0.75
MAX_ZERO_BYTE_ATTEMPTS = 3
ZERO_BYTE_RETRY_DELAY_SECONDS = 1.0
POST_SCAN_SUPPRESSION_SECONDS = 3.0
OUTPUT_DIR = Path("/opt/es60w-lab/output")
LOG_FILE = Path("/opt/es60w-lab/logs/es60w-listener.log")

stop_event = threading.Event()
scan_running = False
reachable: bool | None = None
last_reachability_check = float("-inf")
recent_transactions: dict[bytes, float] = {}
last_successful_scan_completed = float("-inf")


def configure_logging() -> logging.Logger:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)sZ level=%(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    logger = logging.getLogger("es60w-listener")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


LOGGER = logging.getLogger("es60w-listener")
LOGGER.addHandler(logging.NullHandler())


def update_reachability(force: bool = False) -> bool:
    global last_reachability_check, reachable
    now = time.monotonic()
    if not force and now - last_reachability_check < REACHABILITY_INTERVAL:
        return bool(reachable)
    last_reachability_check = now
    try:
        with socket.create_connection((SCANNER_IP, SCANNER_PORT), timeout=1):
            current = True
    except OSError:
        current = False
    if reachable is None:
        # If the daemon starts while the scanner is already on, there was no
        # observed power transition, so do not discard the first real press.
        reachable = current
        LOGGER.info(
            "scanner_reachable=%s state=initial",
            str(current).lower(),
        )
    elif current != reachable:
        LOGGER.info(
            "scanner_reachable=%s transition=%s",
            str(current).lower(),
            "available" if current else "unavailable",
        )
        reachable = current
    return current


def output_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return OUTPUT_DIR / f"{timestamp}_ES-60W.png"


def acquire_one_page(event_source: str) -> None:
    global last_successful_scan_completed, scan_running
    if scan_running:
        LOGGER.info("debounce_decision=reject reason=scan_already_running")
        return
    scan_running = True
    started = time.monotonic()
    final_path = output_path()
    partial_path = final_path.with_suffix(".png.partial")
    command = [
        "scanimage",
        "-d",
        DEVICE,
        "--format=png",
        "--source",
        "ADF Front",
        "--mode",
        "Color",
        "--resolution",
        "300",
        "-x",
        "215.9",
        "-y",
        "355.6",
    ]
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "scan_scheduled event_source=%s delay_seconds=%.2f output=%s",
            event_source,
            SCAN_START_DELAY_SECONDS,
            final_path,
        )
        time.sleep(SCAN_START_DELAY_SECONDS)
        for attempt in range(1, MAX_ZERO_BYTE_ATTEMPTS + 1):
            partial_path.unlink(missing_ok=True)
            LOGGER.info(
                "scan_started event_source=%s device=%s output=%s attempt=%d",
                event_source,
                DEVICE,
                final_path,
                attempt,
            )
            with partial_path.open("wb") as output:
                result = subprocess.run(
                    command,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    check=False,
                )
            elapsed = time.monotonic() - started
            byte_count = partial_path.stat().st_size
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and byte_count > 0:
                os.replace(partial_path, final_path)
                LOGGER.info(
                    "scan_completed output=%s byte_count=%d elapsed_seconds=%.3f "
                    "attempt=%d backend_warning=%r",
                    final_path,
                    byte_count,
                    elapsed,
                    attempt,
                    stderr,
                )
                last_successful_scan_completed = time.monotonic()
                return
            if byte_count == 0 and attempt < MAX_ZERO_BYTE_ATTEMPTS:
                partial_path.unlink(missing_ok=True)
                LOGGER.warning(
                    "failure=transient_zero_byte_scan returncode=%d attempt=%d "
                    "elapsed_seconds=%.3f retry_reason=zero_byte_device_io "
                    "retry_delay_seconds=%.1f stderr=%r",
                    result.returncode,
                    attempt,
                    elapsed,
                    ZERO_BYTE_RETRY_DELAY_SECONDS,
                    stderr,
                )
                time.sleep(ZERO_BYTE_RETRY_DELAY_SECONDS)
                continue
            LOGGER.error(
                "failure=scan_failed returncode=%d bytes=%d attempt=%d "
                "elapsed_seconds=%.3f retry_reason=next_button_event stderr=%r",
                result.returncode,
                byte_count,
                attempt,
                elapsed,
                stderr,
            )
            partial_path.unlink(missing_ok=True)
            return
    except subprocess.TimeoutExpired as error:
        partial_path.unlink(missing_ok=True)
        LOGGER.error(
            "failure=scan_timeout elapsed_seconds=%.3f retry_reason=next_button_event "
            "detail=%r",
            time.monotonic() - started,
            error,
        )
    except OSError as error:
        partial_path.unlink(missing_ok=True)
        LOGGER.exception(
            "failure=scan_os_error elapsed_seconds=%.3f retry_reason=next_button_event "
            "detail=%r",
            time.monotonic() - started,
            error,
        )
    finally:
        scan_running = False


def event_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", EVENT_PORT))
    membership = socket.inet_aton(EVENT_GROUP) + socket.inet_aton(LOCAL_IP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.settimeout(2)
    return sock


def handle_signal(signum: int, _frame: object) -> None:
    LOGGER.info("shutdown_signal=%d", signum)
    stop_event.set()


def main() -> int:
    global LOGGER
    LOGGER = configure_logging()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    LOGGER.info("scanner_reachable=false state=required_starting_assumption")
    update_reachability(force=True)
    try:
        with event_socket() as sock:
            LOGGER.info(
                "listener_ready event_source=udp_multicast group=%s port=%d "
                "marker=%r",
                EVENT_GROUP,
                EVENT_PORT,
                EVENT_MARKER,
            )
            while not stop_event.is_set():
                try:
                    payload, address = sock.recvfrom(4096)
                except socket.timeout:
                    update_reachability()
                    continue
                source_ip, source_port = address
                if source_ip != SCANNER_IP or EVENT_MARKER not in payload:
                    continue
                update_reachability(force=True)
                now = time.monotonic()
                for transaction, seen_at in list(recent_transactions.items()):
                    if now - seen_at > TRANSACTION_RETENTION_SECONDS:
                        del recent_transactions[transaction]
                transaction = payload
                transaction_id = payload[10:12].hex()
                LOGGER.info(
                    "discovery_event=true event_source=udp/%d source=%s:%d "
                    "payload_bytes=%d transaction_id=%s",
                    EVENT_PORT,
                    source_ip,
                    source_port,
                    len(payload),
                    transaction_id,
                )
                if transaction in recent_transactions:
                    LOGGER.info(
                        "candidate_button_event=false debounce_decision=reject "
                        "reason=duplicate_transaction transaction_id=%s "
                        "seconds_since_candidate=%.3f",
                        transaction_id,
                        now - recent_transactions[transaction],
                    )
                    continue
                recent_transactions[transaction] = now
                since_scan = now - last_successful_scan_completed
                if since_scan < POST_SCAN_SUPPRESSION_SECONDS:
                    LOGGER.info(
                        "candidate_button_event=false debounce_decision=reject "
                        "reason=post_scan_rapid_repeat transaction_id=%s "
                        "seconds_since_scan=%.3f window_seconds=%.1f",
                        transaction_id,
                        since_scan,
                        POST_SCAN_SUPPRESSION_SECONDS,
                    )
                    continue
                LOGGER.info(
                    "candidate_button_event=true "
                    "event_source=NetScanMonitor-agent transaction_id=%s",
                    transaction_id,
                )
                LOGGER.info(
                    "debounce_decision=accept reason=new_transaction_while_reachable "
                    "transaction_id=%s",
                    transaction_id,
                )
                acquire_one_page("udp/2968:NetScanMonitor-agent")
    except OSError as error:
        LOGGER.exception("failure=listener_socket detail=%r", error)
        return 1
    finally:
        stop_event.set()
        LOGGER.info("listener_stopped=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
