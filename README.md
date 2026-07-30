# Scanner inbox

Put a page in an Epson ES-60W and press its physical Start/Send button. This
service puts the raw scan in a local directory.

That is the whole job. It does not OCR, rename documents by their contents,
upload anything, or run a document-management system. Those are good jobs for
other tools; this one is the dependable boundary between the scanner and the
rest of your setup.

## What arrives

By default, each completed scan is a PNG in `RAW_SCAN`:

```text
2026-07-30_14-05-09_123456_ES-60W.png
```

The receiver talks to the scanner through the standard SANE `epsonds` backend.
It listens for the scanner's physical-button multicast event and then acquires
one page. The tested scanner is an Epson ES-60W; settings are available for
the scanner address, resolution, source, mode, and output format.

## A file appearing means it is complete

`RAW_SCAN` is a small filesystem handoff protocol, not just an output folder.
The listener never writes a visible final filename. For a PNG named
`document.png`, it does this in the same directory:

```text
.document.png.part  write scan output
                    flush and fsync file
document.png         atomic rename, then fsync directory
```

So a consumer that considers only `*.png` will never open a file while this
service is still writing it. Watch for a move into the directory (`IN_MOVED_TO`
on Linux) rather than a create or modify event. Ignore dotfiles and `*.part`.

The temporary and final names must be in the same filesystem. Keep `RAW_SCAN`
as one ordinary writable directory (the Docker bind mount already does this).
The directory `fsync` makes the rename durable across a crash on filesystems
that support it; it does not turn a network filesystem with weak cache
semantics into a transactional queue.

Downstream software is deliberately outside this project. If you add OCR,
Paperless, or reporting later, let each stage use the same rule: claim a
published input by atomic rename, write its own hidden temporary output,
validate it, then atomically publish its next artefact. Do not use "unchanged
for N seconds" as the correctness check.

## Run it with Docker

Copy the example Compose environment file and set the scanner and host output
directory:

```sh
cp config/compose.env.example config/compose.env
# edit config/compose.env
sudo docker compose --env-file config/compose.env build
sudo docker compose --env-file config/compose.env up -d
sudo docker compose --env-file config/compose.env logs -f
```

`RAW_SCAN_HOST` is the directory on the host where completed scans appear.
Ensure it is writable by `PUID:PGID`. The container uses host networking so it
can receive the scanner's multicast event and connect back to the scanner.

Do not run the container and the native systemd service at the same time:
both will hear one button press and both may scan the page.

## Configuration

The portable defaults live in
[`config/es60w-listener.env.example`](config/es60w-listener.env.example).
The settings most people change are:

| Variable | Purpose |
|---|---|
| `RAW_SCAN` | Writable directory for completed raw scans |
| `ES60W_SCANNER_IP` | Scanner IPv4 address |
| `ES60W_LOCAL_IP` | Interface address for joining multicast (`0.0.0.0` usually works) |
| `ES60W_RESOLUTION` | Scan resolution; default `300` |
| `ES60W_SCAN_SOURCE` | Scanner source; default `ADF Front` |
| `ES60W_SCAN_MODE` | Colour mode; default `Color` |
| `ES60W_OUTPUT_FORMAT` | `png`, `jpeg`, `pnm`, or `tiff`; default `png` |

For a native systemd deployment, use
[`config/es60w-listener.service`](config/es60w-listener.service) with its
environment file. If you change `RAW_SCAN`, add that absolute directory to
`ReadWritePaths` in the unit as well.

## Notes and evidence

This repository also retains the working notes and test evidence that got the
physical button working: `findings.md`, `commands.md`, `captures/`, `logs/`,
and `tests/`. They are useful when changing scanner behaviour, but they are not
required reading to use the inbox. The current acceptance record is in
[`tests/acceptance-report.md`](tests/acceptance-report.md).
