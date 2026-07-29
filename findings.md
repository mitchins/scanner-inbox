# Findings

All timestamps are UTC unless explicitly stated otherwise.

## 2026-07-29 — Initial VM inspection

- Ubuntu reports version `24.04.4 LTS` (Noble).
- Active interface: `eth0`, IPv4 `192.168.6.180/21`.
- Connected route: `192.168.0.0/21` via `eth0`.
- Default gateway: `192.168.1.1`.
- Passwordless `sudo` is available to the `codex` user.

## Established facts supplied before this lab

- The scanner advertises `_scanner._tcp.local`, instance
  `EPSON ES-60W [5CF370524CB2]`, host `EPSON524CB2.local`, TCP port `1865`.
- It has not been observed advertising eSCL/AirScan services such as
  `_uscan._tcp` or `_uscans._tcp`.
- mDNS re-announcement around a physical press is an observation, not yet a
  proven button event.
- The scanner has emitted ARP requests for `192.168.2.16`; the meaning is
  unknown and no address alias will be assigned without further evidence and
  an unused-address check.

## Open questions

- Linux network acquisition: **resolved yes** with stock SANE `epsonds`.
- Physical button visibility: **resolved yes** as an Epson-specific multicast
  transaction, subject to the reliability gate below.
- Does TCP 1865 expose an event or sensor state? No option was exposed through
  SANE; direct state-query semantics were not established.
- Is `192.168.2.16` related to power-on, a press, or neither?

## 2026-07-29 — Baseline tooling

- Requested baseline packages were installed from Ubuntu Noble repositories.
- SANE backend version: `1.2.1`.
- `sane-airscan` version: `0.99.29` (installed as an Ubuntu dependency; its
  presence is not evidence that this scanner supports eSCL).
- Avahi daemon is active, version `0.8`.
- TShark version: `4.2.2`.
- Nmap version: `7.94SVN`.
- Exact package versions and full APT output are retained under `logs/`.

## 2026-07-29 — Network baseline

- `ping`, `.local` resolution, TCP 1865, and `_scanner._tcp` discovery all
  succeeded.
- The advertised TXT record exactly included `scannerAvailable=1`.
- A scanner-only full TCP scan found:
  - TCP 80: Mongoose 6.5 HTTP server; `/` returned an empty HTTP 404.
  - TCP 1865: proprietary binary service. A connection receives 17 bytes
    beginning `49 53 80 00 10 0c`.
  - TCP 3911: gSOAP 2.8.
  - TCP 53048: gSOAP 2.8 during that scan; this high port may be dynamic.
- No conclusion about eSCL was drawn from mDNS. Stock `sane-airscan`
  nevertheless found a WSD endpoint.
- In this session the only scanner ARP captured near the first physical-button
  test targeted the default gateway `192.168.1.1`. No ARP for
  `192.168.2.16` was captured, so no temporary address alias was justified or
  assigned.

Raw evidence:

- `logs/ping-192.168.6.134-20260729.txt`
- `logs/avahi-scanner-20260729.txt`
- `logs/nmap-full-tcp-192.168.6.134-20260729.*`
- `logs/nmap-services-192.168.6.134-20260729.*`

## 2026-07-29 — Linux acquisition

`scanimage -L` discovered both:

```text
epsonds:net:192.168.6.134
airscan:w1:EPSON ES-60W [5CF370524CB2]
```

The native device identified as `Epson ES-60W ESC/I-2`. Its options include
ADF Front, Color/Gray/Lineart, 200/300/400/600 dpi, geometry, load/eject, skew
correction, and crop. It exposes no button, event, paper-present, or
wait-for-button option.

Manual acquisition succeeded using:

```sh
scanimage -d 'epsonds:net:192.168.6.134' \
  --format=png --source 'ADF Front' --mode Color --resolution 300 \
  -x 215.9 -y 355.6
```

Evidence:

- Output: `output/manual-test-20260729-093100.png`
- Size: 12,376,470 bytes
- Dimensions: 2544 x 4193 RGB PNG
- Duration: 7.713 seconds
- SHA256:
  `3034f6acc81d4485114f43fa213154c136938ab7ebd788c8b14642012f361fbd`
- Protocol capture: `captures/manual-epsonds-scan_20260729-093100.pcap`
- The decoder emitted a JPEG restart-marker warning, but `scanimage` returned
  zero and the resulting PNG was structurally valid and visually verified.

Because stock SANE passed the first acquisition criterion, no Epson Linux
package was needed for acquisition.

## 2026-07-29 — Physical-button semantics

The useful button signal is not the mDNS announcement. A physical Start/Send
press emits an Epson-specific UDP multicast burst:

- Source: `192.168.6.134:2968`
- Destination: `239.255.255.253:2968`
- Two identical 102-byte UDP payloads per physical press
- Duplicate spacing observed: 0.512 to 0.571 seconds
- Payload contains:
  - `service:NetScanMonitor-agent`
  - `PID 016E`
  - `Ver,ClientName,IPAddress,EventPort,Group`
- Bytes 10–11 form a per-press transaction identifier in every controlled
  sample.

A controlled three-press test produced exactly six packets:

| Press | Transaction | Duplicate gap |
|---|---:|---:|
| 1 | `ca19` | 0.516 s |
| 2 | `8cb7` | 0.517 s |
| 3 | `364b` | 0.571 s |

The presses were separated by 5.5–5.7 seconds. This permits exact
transaction-based duplicate rejection without suppressing separate presses.

An early trace was initially intended as an idle control but the scanner was
awakened during it. That trace also contains the multicast and is retained as
`B-awakening-transition`; it is not a valid pure power-on control.

A later controlled full off/on cycle produced:

- a recorded TCP reachability transition to unavailable;
- a recorded transition back to available;
- no UDP/2968 candidate for more than one minute after power-on;
- no scan and no output file until Start/Send was subsequently pressed.

Therefore the current evidence supports treating a new UDP/2968 transaction
as the Start/Send signal. Power-on-only testing must still be repeated during
the formal reliability gate.

Raw decode evidence:

- `logs/button-candidate-decode-20260729.txt`
- `logs/control-vs-button-tshark-20260729.txt`
- `logs/repeated-send-events-decode-20260729.tsv`
- `captures/A-idle-no-button_20260729T092717Z.pcap`
- `captures/E-physical-button_20260729T092806Z.pcap`
- `captures/repeated-send-events_20260729T093528Z.pcap`

## 2026-07-29 — Button-to-file proof

`src/es60w_listener.py` joins multicast group `239.255.255.253` on UDP 2968,
requires the expected scanner source IP and payload marker, and de-duplicates
the full transaction payload. It then runs the proven native SANE command.

Successful automatic button-to-file trials include:

| UTC button event | Transaction | Bytes | Scan elapsed |
|---|---:|---:|---:|
| 09:42:33 | `03ff` | 10,424,969 | 6.680 s |
| 09:47:40 | `d763` | 10,259,026 | 6.679 s |
| 09:49:52 | `280c` | 10,478,594 | 6.416 s |
| 09:54:21 | `8db7` | 10,539,066 | 7.425 s |

At 09:49:45 a distinct earlier press (`fcd4`) was detected but the immediate
SANE open failed in 0.022 seconds with zero bytes and `Error during device
I/O`; a second physical press was required. This trial is a reliability
failure, not a pass.

The receiver was changed to wait 0.75 seconds after the event and retry up to
three times only for zero-byte failures. Partial/nonzero transfers are never
blindly retried. The next single-press service test (`8db7`) succeeded on its
first delayed attempt.

## 2026-07-29 — Headless service

- Unit: `/etc/systemd/system/es60w-listener.service`
- Checked-in source: `config/es60w-listener.service`
- Runtime user/group: `es60w:es60w` (system account, no login shell)
- Enabled at boot and currently managed by systemd.
- Uses `Restart=on-failure`, explicit `network-online.target` ordering, a
  strict read-only filesystem sandbox, and write access only to lab logs and
  output.
- Logs go to both journald and `logs/es60w-listener.log`.

Operational commands:

```sh
systemctl status es60w-listener
journalctl -u es60w-listener -f
```

## 2026-07-29 — Authoritative Epson package retained

For proprietary-component inspection, the current official Windows Epson
Scan 2 package was downloaded but not installed:

- URL:
  `https://ftp.epson.com/drivers/ES60W_EScan2_67810_AM.exe`
- Filename/version: `ES60W_EScan2_67810_AM.exe`, Epson Scan 2 `6.7.81.0`
- Size: 80,871,192 bytes
- SHA256:
  `62719e2c554496ac57a10ad9c78e89c2b9349e4db2e32eae3c89896ba3f01279`

Epson's support FAQ says Wi-Fi Start-button operation requires the scanner to
be paired in Epson ScanSmart and both ScanSmart and Scan 2 to be installed.
This is consistent with the observed `NetScanMonitor-agent` discovery
payload. No proprietary component was run on Linux.

Package inspection, without execution, showed an Inno Setup 6.1 wrapper
containing a nested 78,281,096-byte InstallShield self-extracting Epson Scan 2
installer. The nested installer SHA256 is
`5d57ce327325a9de26282eb1d27b62cb21d6187f8cd92977e1f259bfd39c9a10`.
Top-level and UTF-16 string inspection did not expose a
`NetScanMonitor-agent` implementation. Since the Linux receiver already works,
no Windows component was installed or run.

## Reliability gate status

The requested physical-button-to-file reliability gate **passed**:

- 4 successful automatic physical-button scans were recorded during
  development, followed by a formal post-mitigation run.
- 1 physical-button trial failed and required a second press before the
  delayed/retry mitigation was added.
- Formal run: 9 distinct emitted transactions produced 9 non-empty files,
  with 0 failures and 0 retries. The scanner battery depleted before the tenth
  transaction. After charging, VM reboot, and power recovery, transaction
  `0340` completed the clean post-mitigation result at 10/10.
- Delayed retransmissions of old transaction IDs were observed around 32
  seconds and correctly rejected; no phantom files were created.
- 3 scanner unavailable/off-on recovery periods completed. Power-on-only
  controls produced no transaction, scan, or file; each subsequent button
  scan succeeded.
- Systemd start and post-install scan completed.
- One clean daemon restart while the scanner was unavailable completed; the
  replacement process stayed active and reported initial unreachable state.
- VM reboot changed boot ID, auto-started the enabled service, sustained a
  69-minute scanner outage, and later scanned successfully.
- One sheet plus three rapid physical presses emitted one transaction and
  created exactly one file, with no failure or extra output.

OCR, classification, filing, CIFS, and tax workflows have not been started.
