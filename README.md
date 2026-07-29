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
- The installed unprivileged systemd listener has converted physical button
  presses into valid local PNG files.
- The formal 10-scan, 3-cycle, daemon-restart, rapid-repeat, and VM-reboot
  reliability gate passed on 2026-07-29.
- See `tests/acceptance-report.md` for exact transactions and evidence.

## Service operations

```sh
systemctl status es60w-listener
journalctl -u es60w-listener -f
```

Files arrive as:

```text
/opt/es60w-lab/output/YYYY-MM-DD_HH-MM-SS_ES-60W.png
```
