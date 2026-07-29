# Reliability run started 2026-07-29 09:57:11 UTC

Planned: 10 one-sheet, one-press scans through the installed systemd service.

Observed before scanner battery depletion:

- 9 distinct accepted transaction IDs.
- 9 completed non-empty PNG files.
- 0 acquisition failures.
- 0 zero-byte automatic retries.
- All 9 completed on acquisition attempt 1.
- Scanner became unreachable at 09:59:26 UTC.
- User reported uncertainty around paper seating during nominal scan 6 and
  scanner battery depletion at the end.
- Extra physical attempts with improperly seated paper emitted no new
  transaction and therefore did not request acquisition.

Result: **9/9 emitted intended scan transactions passed; the planned 10-scan
gate remains incomplete at 9 because the scanner battery depleted.**

Important duplicate behavior:

- Normal second copies of each transaction arrived after scan completion,
  approximately 7–8 seconds after the first packet.
- Transactions `41ad` and `3a9a` were retransmitted again approximately 32
  seconds after their initial events.
- The 120-second full-payload transaction cache rejected these delayed
  retransmissions. No phantom files were created.

Evidence:

- `tests/reliability-10scan-final.log`
- `tests/reliability-10scan-output-files.txt`
- `captures/reliability-10scan_20260729T095711Z.pcap`
- PCAP SHA256:
  `0bea21351930c71c16230ff64112284cdd36b51fb1428b95bf5bc6937f5c3410`
