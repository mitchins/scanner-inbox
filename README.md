# Epson ES-60W headless physical-button lab

This repository records experiments toward one narrow acceptance gate:

> Power on the Epson ES-60W, insert one sheet, press the scanner's physical
> Start/Send button once, and receive exactly one local scan file without any
> other interaction.

Scanner:

- Model: Epson ES-60W
- IPv4: `192.168.6.134`
- mDNS host: `EPSON524CB2.local`
- MAC: `5c:f3:70:52:4c:b2`
- Observed service: `_scanner._tcp.local` on TCP port `1865`

VM:

- IPv4: `192.168.6.180/21`
- Gateway: `192.168.1.1`
- OS: Ubuntu 24.04

## Layout

- `findings.md`: evidence, interpretations, and open questions
- `commands.md`: reproducible command log
- `captures/`: packet captures and capture-side metadata
- `logs/`: raw tool and daemon logs
- `output/`: acquired scan files
- `packages/`: authoritative vendor downloads
- `config/`: scanner/backend configuration
- `src/`: proof receiver source
- `tests/`: test evidence

No claim that an mDNS announcement represents a button press will be made
without comparing it with no-button controls.

## Current proof status

- Manual Linux Wi-Fi acquisition works through stock SANE device
  `epsonds:net:192.168.6.134`.
- The physical button emits a repeatable Epson `NetScanMonitor-agent`
  multicast transaction on UDP 2968.
- Both the original unprivileged systemd listener and its Docker replacement
  have converted physical button presses into valid local PNG files.
- The formal 10-scan, 3-cycle, daemon-restart, rapid-repeat, and VM-reboot
  reliability gate passed on 2026-07-29.
- The Docker deployment passed physical scans before and after a Docker daemon
  restart, then auto-started and scanned successfully after a full VM reboot.
- See `tests/acceptance-report.md` for exact transactions and evidence.

## Service operations

```sh
sudo docker compose --env-file config/compose.env.lab ps
sudo docker compose --env-file config/compose.env.lab logs -f
```

Files arrive as:

```text
/opt/es60w-lab/output/YYYY-MM-DD_HH-MM-SS_ES-60W.png
```

## Runtime configuration

The receiver reads configuration from environment variables. The important
portable settings are:

| Variable | Default | Purpose |
|---|---|---|
| `RAW_SCAN` | `/opt/es60w-lab/output` | Writable destination for completed scans |
| `ES60W_SCANNER_IP` | `192.168.6.134` | Scanner IPv4 address |
| `ES60W_LOCAL_IP` | `0.0.0.0` | Local interface address used to join the multicast group |
| `ES60W_SANE_DEVICE` | derived from scanner IP | SANE device passed to `scanimage` |
| `ES60W_LOG_FILE` | lab log path | File log; set empty for stdout/journald only |
| `ES60W_LOG_LEVEL` | `INFO` | Python log level |

`config/es60w-listener.env.example` contains every supported setting and
container-oriented defaults. `config/es60w-listener.env.systemd` is the
concrete configuration proven on this VM and is installed at
`/etc/default/es60w-listener`.

After changing the systemd environment:

```sh
sudo systemctl restart es60w-listener
journalctl -u es60w-listener -n 30 --no-pager
```

The checked-in systemd sandbox permits writes only under the current lab
`output/` and `logs/` directories. If `RAW_SCAN` is moved elsewhere in the
host deployment, add that absolute directory to `ReadWritePaths` in the unit.

## Docker deployment

The image contains Ubuntu 24.04's stock `scanimage`, SANE `epsonds` backend,
Python runtime, and the listener. The build context admits only the Dockerfile
and listener source; acquired scans, packet captures, logs, packages, and Git
metadata are excluded by `.dockerignore`.

The Compose service uses Linux host networking because it must:

- receive UDP multicast `239.255.255.253:2968`; and
- connect to scanner TCP `192.168.6.134:1865`.

It runs unprivileged, drops every Linux capability, enables
`no-new-privileges`, uses a read-only root filesystem, and writes only through
the `RAW_SCAN` bind mount.

For this VM:

```sh
sudo docker compose --env-file config/compose.env.lab build
sudo systemctl stop es60w-listener.service
sudo docker compose --env-file config/compose.env.lab up -d

sudo docker compose --env-file config/compose.env.lab ps
sudo docker compose --env-file config/compose.env.lab logs -f
```

For another host, copy `config/compose.env.example`, set `RAW_SCAN_HOST`,
`ES60W_SCANNER_IP`, `ES60W_LOCAL_IP`, `PUID`, and `PGID`, then pass the copied
file through Compose's `--env-file` option.

Never run the native systemd listener and container listener together. Both
would receive the same physical-button transaction and could race to acquire
the page.

The native unit remains installed as a rollback path but is disabled. To roll
back safely:

```sh
sudo docker compose --env-file config/compose.env.lab down
sudo systemctl enable --now es60w-listener.service
```
