# ES-60W physical-button-to-file acceptance report

Date: 2026-07-29 UTC

## Result

**PASS** for the requested physical-button-to-file acquisition gate.

The deployed systemd service received Epson `NetScanMonitor-agent`
transactions from the scanner's physical Start/Send button and created one
valid local PNG for each of ten clean post-mitigation intended scans.

## Ten-scan gate

All ten scans used the unprivileged headless listener, stock SANE device
`epsonds:net:192.168.6.134`, 300 dpi color, and one physical Start/Send press
per loaded sheet.

| # | Transaction | Output bytes | Elapsed | Attempt |
|---:|---:|---:|---:|---:|
| 1 | `beb4` | 10,737,366 | 7.323 s | 1 |
| 2 | `c096` | 10,589,277 | 7.675 s | 1 |
| 3 | `41ad` | 10,998,258 | 7.466 s | 1 |
| 4 | `3a9a` | 10,991,901 | 7.640 s | 1 |
| 5 | `f8ab` | 10,992,290 | 7.399 s | 1 |
| 6 | `24af` | 10,975,954 | 7.464 s | 1 |
| 7 | `8e71` | 10,650,744 | 7.421 s | 1 |
| 8 | `a223` | 10,751,058 | 7.426 s | 1 |
| 9 | `5a0a` | 10,583,578 | 8.025 s | 1 |
| 10 | `0340` | 10,738,404 | 8.233 s | 1 |

The scanner battery depleted after scan 9. Scan 10 was intentionally
completed after charging, a VM reboot, more than one hour unavailable, and
scanner power-on. This strengthens rather than weakens the recovery evidence.

Result: 10/10 non-empty files, 0 failures, 0 automatic retries, and no extra
files.

## Duplicate and phantom protection

- Each press normally sends two identical UDP/2968 packets.
- The full payload, including its per-press transaction ID, is cached for 120
  seconds.
- Normal duplicates after scan completion were rejected.
- Additional delayed retransmissions of transactions `41ad` and `3a9a` about
  32 seconds later were rejected.
- No mDNS announcement is used as a trigger.
- Three separate power-on-only controls produced no button transaction, scan
  attempt, or file.
- A one-sheet, three-rapid-press test emitted one transaction (`8a4c`), two
  duplicate packets, and exactly one 11,168,399-byte file. The scanner
  firmware ignored/coalesced the extra presses.

## Recovery gates

Three scanner unavailable/off-on recovery periods passed:

1. Scanner unavailable at 09:44:01, available at 09:45:07, no power-on
   phantom, then transaction `d763` scanned successfully.
2. Scanner unavailable at 09:59:26 through battery charging and VM reboot,
   available at 11:13:29, no power-on phantom, then clean-gate transaction
   `0340` scanned successfully.
3. Scanner unavailable at 11:15:58, available at 11:16:45, no power-on
   phantom, then transaction `cf33` scanned successfully. A later two-second
   reachability flap also recovered without intervention.

Daemon restart while the scanner was unavailable:

- PID changed from 10288 to 10838.
- Replacement service stayed active and logged initial unreachable state.

VM reboot:

- Pre-reboot boot ID:
  `4aaf84a0-bb5c-4f98-a76b-d4a4b490a92a`
- Post-reboot boot ID:
  `5139e756-752f-4925-be4e-735e09ad3f02`
- Service auto-started at 10:03:23 UTC as user/group `es60w:es60w`.
- It remained active through a 69-minute scanner outage and later scanned
  successfully.

## Final validation

- Unit is enabled and active.
- Runtime is unprivileged (`es60w:es60w`).
- Checked-in and installed unit hashes match.
- Python compilation and unit tests pass.
- 17 total lab PNGs exist (manual, development, formal, and recovery tests).
- All 17 are non-empty, recognized as 2544 x 4193 RGB PNG files.
- Zero `.partial` files remain.
- No post-mitigation `failure=` log entries were found.

## Preserved evidence

- Listener: `src/es60w_listener.py`
- Unit: `config/es60w-listener.service`
- Findings and exact commands: `findings.md`, `commands.md`
- Formal run log: `tests/reliability-10scan-final.log`
- Final tenth scan: `tests/post-reboot-power-button.log`
- Power-cycle 3: `tests/power-cycle-3-service.log`
- Rapid triple press: `tests/rapid-triple-service.log`,
  `tests/rapid-triple-udp2968.tsv`
- Final validation: `tests/final-validation.txt`
- Output hashes: `tests/output-sha256-manifest.txt`
- Full PCAPs and adjacent metadata: `captures/`

No OCR, classification, filing, CIFS publishing, tax workflow, GUI
automation, or alternate button UX was introduced.
