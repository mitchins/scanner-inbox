#!/usr/bin/env python3
"""Headless Epson ES-60W physical-button-to-SANE receiver."""

from __future__ import annotations

import ipaddress
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

EVENT_MARKER = b"service:NetScanMonitor-agent"
SUPPORTED_OUTPUT_FORMATS = frozenset({"jpeg", "png", "pnm", "tiff"})


def _env_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_float(
    environ: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
) -> float:
    raw = environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric, got {raw!r}") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _ipv4(value: str, name: str, *, multicast: bool = False) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise ValueError(f"{name} must be an IPv4 address, got {value!r}") from error
    if multicast and not address.is_multicast:
        raise ValueError(f"{name} must be a multicast IPv4 address")
    return str(address)


def _absolute_path(value: str, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path, got {value!r}")
    return path


@dataclass(frozen=True)
class Settings:
    scanner_ip: str
    local_ip: str
    scanner_port: int
    event_group: str
    event_port: int
    sane_device: str
    scanimage_binary: str
    raw_scan: Path
    log_file: Path | None
    log_level: str
    output_format: str
    scan_source: str
    scan_mode: str
    resolution: int
    page_width_mm: float
    page_height_mm: float
    transaction_retention_seconds: float
    reachability_interval_seconds: float
    scan_start_delay_seconds: float
    max_zero_byte_attempts: int
    zero_byte_retry_delay_seconds: float
    post_scan_suppression_seconds: float
    scan_timeout_seconds: float

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        scanner_ip = _ipv4(
            env.get("ES60W_SCANNER_IP", "192.168.6.134"),
            "ES60W_SCANNER_IP",
        )
        local_ip = _ipv4(
            env.get("ES60W_LOCAL_IP", "0.0.0.0"),
            "ES60W_LOCAL_IP",
        )
        event_group = _ipv4(
            env.get("ES60W_EVENT_GROUP", "239.255.255.253"),
            "ES60W_EVENT_GROUP",
            multicast=True,
        )
        output_format = env.get("ES60W_OUTPUT_FORMAT", "png").lower()
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            supported = ", ".join(sorted(SUPPORTED_OUTPUT_FORMATS))
            raise ValueError(
                f"ES60W_OUTPUT_FORMAT must be one of {supported}, "
                f"got {output_format!r}"
            )
        log_level = env.get("ES60W_LOG_LEVEL", "INFO").upper()
        if not isinstance(getattr(logging, log_level, None), int):
            raise ValueError(f"ES60W_LOG_LEVEL is invalid: {log_level!r}")
        log_file_raw = env.get(
            "ES60W_LOG_FILE",
            "/opt/es60w-lab/logs/es60w-listener.log",
        )
        log_file = (
            _absolute_path(log_file_raw, "ES60W_LOG_FILE")
            if log_file_raw
            else None
        )
        sane_device = env.get(
            "ES60W_SANE_DEVICE",
            f"epsonds:net:{scanner_ip}",
        )
        return cls(
            scanner_ip=scanner_ip,
            local_ip=local_ip,
            scanner_port=_env_int(
                env, "ES60W_SCANNER_PORT", 1865, 1, 65535
            ),
            event_group=event_group,
            event_port=_env_int(env, "ES60W_EVENT_PORT", 2968, 1, 65535),
            sane_device=sane_device,
            scanimage_binary=env.get(
                "ES60W_SCANIMAGE_BINARY", "/usr/bin/scanimage"
            ),
            raw_scan=_absolute_path(
                env.get("RAW_SCAN", "/opt/es60w-lab/output"),
                "RAW_SCAN",
            ),
            log_file=log_file,
            log_level=log_level,
            output_format=output_format,
            scan_source=env.get("ES60W_SCAN_SOURCE", "ADF Front"),
            scan_mode=env.get("ES60W_SCAN_MODE", "Color"),
            resolution=_env_int(
                env, "ES60W_RESOLUTION", 300, 1, 9600
            ),
            page_width_mm=_env_float(
                env, "ES60W_PAGE_WIDTH_MM", 215.9, 1.0
            ),
            page_height_mm=_env_float(
                env, "ES60W_PAGE_HEIGHT_MM", 355.6, 1.0
            ),
            transaction_retention_seconds=_env_float(
                env, "ES60W_TRANSACTION_RETENTION_SECONDS", 120.0, 1.0
            ),
            reachability_interval_seconds=_env_float(
                env, "ES60W_REACHABILITY_INTERVAL_SECONDS", 2.0, 0.1
            ),
            scan_start_delay_seconds=_env_float(
                env, "ES60W_SCAN_START_DELAY_SECONDS", 0.75, 0.0
            ),
            max_zero_byte_attempts=_env_int(
                env, "ES60W_MAX_ZERO_BYTE_ATTEMPTS", 3, 1, 20
            ),
            zero_byte_retry_delay_seconds=_env_float(
                env, "ES60W_ZERO_BYTE_RETRY_DELAY_SECONDS", 1.0, 0.0
            ),
            post_scan_suppression_seconds=_env_float(
                env, "ES60W_POST_SCAN_SUPPRESSION_SECONDS", 3.0, 0.0
            ),
            scan_timeout_seconds=_env_float(
                env, "ES60W_SCAN_TIMEOUT_SECONDS", 120.0, 1.0
            ),
        )


stop_event = threading.Event()
scan_running = False
reachable: bool | None = None
last_reachability_check = float("-inf")
recent_transactions: dict[bytes, float] = {}
last_successful_scan_completed = float("-inf")


def configure_logging(settings: Settings) -> logging.Logger:
    formatter = logging.Formatter(
        "%(asctime)sZ level=%(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    logger = logging.getLogger("es60w-listener")
    logger.setLevel(getattr(logging, settings.log_level))
    logger.handlers.clear()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_file is not None:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(settings.log_file))
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


LOGGER = logging.getLogger("es60w-listener")
LOGGER.addHandler(logging.NullHandler())


def reset_runtime_state() -> None:
    global last_reachability_check, last_successful_scan_completed
    global reachable, recent_transactions, scan_running
    stop_event.clear()
    scan_running = False
    reachable = None
    last_reachability_check = float("-inf")
    recent_transactions = {}
    last_successful_scan_completed = float("-inf")


def update_reachability(settings: Settings, force: bool = False) -> bool:
    global last_reachability_check, reachable
    now = time.monotonic()
    if (
        not force
        and now - last_reachability_check
        < settings.reachability_interval_seconds
    ):
        return bool(reachable)
    last_reachability_check = now
    try:
        with socket.create_connection(
            (settings.scanner_ip, settings.scanner_port), timeout=1
        ):
            current = True
    except OSError:
        current = False
    if reachable is None:
        reachable = current
        LOGGER.info("scanner_reachable=%s state=initial", str(current).lower())
    elif current != reachable:
        LOGGER.info(
            "scanner_reachable=%s transition=%s",
            str(current).lower(),
            "available" if current else "unavailable",
        )
        reachable = current
    return current


def output_path(settings: Settings, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(timezone.utc)).strftime(
        "%Y-%m-%d_%H-%M-%S_%f"
    )
    return (
        settings.raw_scan
        / f"{timestamp}_ES-60W.{settings.output_format}"
    )


def partial_output_path(final_path: Path) -> Path:
    """Return the non-published sibling used while a scan is being written."""
    return final_path.with_name(f".{final_path.name}.part")


def fsync_directory(directory: Path) -> None:
    """Persist a rename in *directory* before reporting the scan as complete."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def scan_command(settings: Settings) -> list[str]:
    return [
        settings.scanimage_binary,
        "-d",
        settings.sane_device,
        f"--format={settings.output_format}",
        "--source",
        settings.scan_source,
        "--mode",
        settings.scan_mode,
        "--resolution",
        str(settings.resolution),
        "-x",
        str(settings.page_width_mm),
        "-y",
        str(settings.page_height_mm),
    ]


def acquire_one_page(settings: Settings, event_source: str) -> None:
    global last_successful_scan_completed, scan_running
    if scan_running:
        LOGGER.info("debounce_decision=reject reason=scan_already_running")
        return
    scan_running = True
    started = time.monotonic()
    final_path = output_path(settings)
    partial_path = partial_output_path(final_path)
    command = scan_command(settings)
    try:
        settings.raw_scan.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "scan_scheduled event_source=%s delay_seconds=%.2f output=%s",
            event_source,
            settings.scan_start_delay_seconds,
            final_path,
        )
        time.sleep(settings.scan_start_delay_seconds)
        for attempt in range(1, settings.max_zero_byte_attempts + 1):
            partial_path.unlink(missing_ok=True)
            LOGGER.info(
                "scan_started event_source=%s device=%s output=%s attempt=%d",
                event_source,
                settings.sane_device,
                final_path,
                attempt,
            )
            with partial_path.open("wb") as output:
                result = subprocess.run(
                    command,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=settings.scan_timeout_seconds,
                    check=False,
                )
                # A final extension is a publication signal to external
                # consumers.  Do not publish it until scanimage has exited,
                # its output is flushed, and the file contents are durable.
                output.flush()
                os.fsync(output.fileno())
            elapsed = time.monotonic() - started
            byte_count = partial_path.stat().st_size
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and byte_count > 0:
                os.replace(partial_path, final_path)
                fsync_directory(settings.raw_scan)
                LOGGER.info(
                    "scan_completed output=%s byte_count=%d elapsed_seconds=%.3f "
                    "attempt=%d publication=atomic_rename backend_warning=%r",
                    final_path,
                    byte_count,
                    elapsed,
                    attempt,
                    stderr,
                )
                last_successful_scan_completed = time.monotonic()
                return
            if (
                byte_count == 0
                and attempt < settings.max_zero_byte_attempts
            ):
                partial_path.unlink(missing_ok=True)
                LOGGER.warning(
                    "failure=transient_zero_byte_scan returncode=%d attempt=%d "
                    "elapsed_seconds=%.3f retry_reason=zero_byte_device_io "
                    "retry_delay_seconds=%.1f stderr=%r",
                    result.returncode,
                    attempt,
                    elapsed,
                    settings.zero_byte_retry_delay_seconds,
                    stderr,
                )
                time.sleep(settings.zero_byte_retry_delay_seconds)
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


def event_socket(settings: Settings) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", settings.event_port))
    membership = socket.inet_aton(settings.event_group) + socket.inet_aton(
        settings.local_ip
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.settimeout(2)
    return sock


def handle_signal(signum: int, _frame: object) -> None:
    LOGGER.info("shutdown_signal=%d", signum)
    stop_event.set()


def main(environ: Mapping[str, str] | None = None) -> int:
    global LOGGER
    try:
        settings = Settings.from_env(environ)
    except ValueError as error:
        print(f"configuration_error={error}", file=sys.stderr)
        return 2
    reset_runtime_state()
    LOGGER = configure_logging(settings)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    LOGGER.info(
        "configuration_loaded=true scanner_ip=%s local_ip=%s "
        "event_group=%s event_port=%d sane_device=%s raw_scan=%s "
        "output_format=%s log_file=%s",
        settings.scanner_ip,
        settings.local_ip,
        settings.event_group,
        settings.event_port,
        settings.sane_device,
        settings.raw_scan,
        settings.output_format,
        settings.log_file or "stdout_only",
    )
    LOGGER.info("scanner_reachable=false state=required_starting_assumption")
    update_reachability(settings, force=True)
    try:
        with event_socket(settings) as sock:
            LOGGER.info(
                "listener_ready event_source=udp_multicast group=%s port=%d "
                "marker=%r",
                settings.event_group,
                settings.event_port,
                EVENT_MARKER,
            )
            while not stop_event.is_set():
                try:
                    payload, address = sock.recvfrom(4096)
                except socket.timeout:
                    update_reachability(settings)
                    continue
                source_ip, source_port = address
                if (
                    source_ip != settings.scanner_ip
                    or EVENT_MARKER not in payload
                ):
                    continue
                update_reachability(settings, force=True)
                now = time.monotonic()
                for transaction, seen_at in list(recent_transactions.items()):
                    if (
                        now - seen_at
                        > settings.transaction_retention_seconds
                    ):
                        del recent_transactions[transaction]
                transaction = payload
                transaction_id = payload[10:12].hex()
                LOGGER.info(
                    "discovery_event=true event_source=udp/%d source=%s:%d "
                    "payload_bytes=%d transaction_id=%s",
                    settings.event_port,
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
                if since_scan < settings.post_scan_suppression_seconds:
                    LOGGER.info(
                        "candidate_button_event=false debounce_decision=reject "
                        "reason=post_scan_rapid_repeat transaction_id=%s "
                        "seconds_since_scan=%.3f window_seconds=%.1f",
                        transaction_id,
                        since_scan,
                        settings.post_scan_suppression_seconds,
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
                acquire_one_page(
                    settings,
                    f"udp/{settings.event_port}:NetScanMonitor-agent",
                )
    except OSError as error:
        LOGGER.exception("failure=listener_socket detail=%r", error)
        return 1
    finally:
        stop_event.set()
        LOGGER.info("listener_stopped=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
