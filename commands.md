# Command log

Commands are grouped by experiment. Raw outputs are saved under `logs/` when
they are evidence-bearing.

## 2026-07-29 — VM inspection and project initialization

```sh
pwd
id
uname -a
cat /etc/os-release
ip -brief address
ip route
sudo -n true
find /opt -maxdepth 2 -type d -name es60w-lab -print

sudo install -d -o codex -g codex \
  /opt/es60w-lab/{captures,logs,output,packages,config,src,tests}
sudo chown codex:codex /opt/es60w-lab
git init /opt/es60w-lab
git -C /opt/es60w-lab config user.name "ES-60W Lab"
git -C /opt/es60w-lab config user.email "es60w-lab@localhost"
```

Note: the first `git init` attempt failed because `install -d` left the
top-level directory owned by root. Ownership of only the project top-level was
corrected, then initialization succeeded.

## 2026-07-29 — Baseline packages

```sh
dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Abbrev}\n' \
  avahi-utils sane-utils tcpdump tshark nmap netcat-openbsd socat \
  python3 python3-venv python3-pip jq curl wget unzip git ripgrep

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  avahi-utils sane-utils tcpdump tshark nmap netcat-openbsd socat \
  python3 python3-venv python3-pip jq curl wget unzip git ripgrep

dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Abbrev}\n' \
  avahi-utils sane-utils tcpdump tshark nmap netcat-openbsd socat \
  python3 python3-venv python3-pip jq curl wget unzip git ripgrep \
  libsane1 libsane-common sane-airscan \
  | sort | tee logs/package-versions-20260729.tsv
systemctl is-active avahi-daemon
avahi-daemon --version
tshark --version
scanimage --version
nmap --version
```

Raw APT logs:

- `logs/apt-update-20260729.log`
- `logs/apt-install-baseline-20260729.log`
- `logs/package-versions-20260729.tsv`

## 2026-07-29 — Network baseline

```sh
ping -c 3 -W 2 192.168.6.134
getent hosts EPSON524CB2.local
nc -vz -w 3 192.168.6.134 1865
timeout 15s avahi-browse -rt _scanner._tcp

sudo nmap -Pn -sT -T3 --max-retries 2 -p- --reason \
  192.168.6.134 -oA logs/nmap-full-tcp-192.168.6.134-20260729
sudo nmap -Pn -sT -sV --version-all --reason \
  -p 80,1865,3911,53048 192.168.6.134 \
  -oA logs/nmap-services-192.168.6.134-20260729
curl --max-time 10 --dump-header logs/http-80-headers-20260729.txt \
  --output logs/http-80-body-20260729.bin http://192.168.6.134/
```

## 2026-07-29 — Controlled captures

Capture filter used for broad controlled experiments:

```sh
sudo tcpdump -i eth0 -s 0 -U -w captures/EXPERIMENT_TIMESTAMP.pcap \
  'host 192.168.6.134 or port 5353 or port 137 or port 138 or port 1865'
sha256sum captures/EXPERIMENT_TIMESTAMP.pcap
capinfos captures/EXPERIMENT_TIMESTAMP.pcap
```

The button-focused filter also included `port 2968`.

Representative decode commands:

```sh
tshark -r captures/E-physical-button_20260729T092806Z.pcap \
  -Y 'ip.src == 192.168.6.134 && udp.port == 2968' -V
tshark -r captures/E-physical-button_20260729T092806Z.pcap \
  -Y 'eth.src == 5c:f3:70:52:4c:b2 && arp' \
  -T fields -e frame.time -e arp.src.proto_ipv4 -e arp.dst.proto_ipv4
tshark -r captures/repeated-send-events_20260729T093528Z.pcap \
  -T fields -e frame.time -e frame.time_relative -e data.data
```

Every PCAP has adjacent metadata with UTC bounds, packet count, and SHA256.

## 2026-07-29 — SANE acquisition

```sh
scanimage -L
sane-find-scanner
scanimage -d 'epsonds:net:192.168.6.134' --all-options
scanimage -d 'airscan:w1:EPSON ES-60W [5CF370524CB2]' --all-options

scanimage -d 'epsonds:net:192.168.6.134' \
  --format=png --source 'ADF Front' --mode Color --resolution 300 \
  -x 215.9 -y 355.6 \
  > output/manual-test-20260729-093100.png
```

## 2026-07-29 — Official Epson package

```sh
curl -L --fail --show-error \
  --output packages/ES60W_EScan2_67810_AM.exe \
  https://ftp.epson.com/drivers/ES60W_EScan2_67810_AM.exe
sha256sum packages/ES60W_EScan2_67810_AM.exe \
  | tee packages/ES60W_EScan2_67810_AM.exe.sha256
file packages/ES60W_EScan2_67810_AM.exe
```

The package was inspected as a PE32 executable and was not installed.

```sh
sudo apt-get install -y innoextract
innoextract --list packages/ES60W_EScan2_67810_AM.exe
innoextract --extract \
  --output-dir packages/ES60W_EScan2_67810_AM.outer \
  packages/ES60W_EScan2_67810_AM.exe
file 'packages/ES60W_EScan2_67810_AM.outer/code$MyTemp/cm$MDL/ES60W_EScan2_67810_AM.exe'
sha256sum 'packages/ES60W_EScan2_67810_AM.outer/code$MyTemp/cm$MDL/ES60W_EScan2_67810_AM.exe'
```

The outer Inno wrapper extracted successfully. Its nested InstallShield
installer was identified and hashed but not executed.

## 2026-07-29 — Listener and systemd

```sh
python3 -m py_compile src/es60w_listener.py
python3 -m unittest discover -s tests -v

sudo useradd --system --no-create-home --home-dir /nonexistent \
  --shell /usr/sbin/nologin --user-group es60w
sudo chown -R es60w:es60w /opt/es60w-lab/logs /opt/es60w-lab/output
sudo setfacl -m u:codex:rwx,u:es60w:rwx,d:u:codex:rwx,d:u:es60w:rwx \
  /opt/es60w-lab/logs /opt/es60w-lab/output
sudo install -o root -g root -m 0644 config/es60w-listener.service \
  /etc/systemd/system/es60w-listener.service
sudo systemd-analyze verify /etc/systemd/system/es60w-listener.service
sudo systemctl daemon-reload
sudo systemctl enable --now es60w-listener.service

systemctl status es60w-listener.service
journalctl -u es60w-listener.service -f
```

## 2026-07-29 — Reliability and reboot checks

```sh
# Count accepted transactions, completed scans, and failures for a bounded run.
journalctl -u es60w-listener.service \
  --since '2026-07-29 09:57:11 UTC' --no-pager -o cat \
  | tee tests/reliability-10scan-final.log
rg -c 'debounce_decision=accept' tests/reliability-10scan-final.log
rg -c 'scan_completed' tests/reliability-10scan-final.log
rg -c 'failure=' tests/reliability-10scan-final.log

# Restart while the scanner is unavailable.
systemctl show es60w-listener.service -p MainPID
sudo systemctl restart es60w-listener.service
systemctl show es60w-listener.service \
  -p ActiveState -p SubState -p NRestarts -p MainPID

# Record the boot ID, reboot, and verify a changed ID and automatic service
# startup after reconnecting.
cat /proc/sys/kernel/random/boot_id
systemctl is-enabled es60w-listener.service
sudo systemctl reboot
cat /proc/sys/kernel/random/boot_id
systemctl status es60w-listener.service
journalctl -b -u es60w-listener.service --no-pager

# Final artifact checks.
find output -maxdepth 1 -type f -name '*.png' -size 0
find output -maxdepth 1 -type f -name '*.partial'
find output -maxdepth 1 -type f -name '*.png' -print0 \
  | sort -z | xargs -0 file
sha256sum output/*.png | sort -k2 > tests/output-sha256-manifest.txt
```

## 2026-07-29 — Environment-configurable service

```sh
python3 -m py_compile src/es60w_listener.py
python3 -m unittest discover -s tests -v
git diff --check
systemd-analyze verify config/es60w-listener.service

sudo install -o root -g root -m 0644 \
  config/es60w-listener.env.systemd /etc/default/es60w-listener
sudo install -o root -g root -m 0644 \
  config/es60w-listener.service \
  /etc/systemd/system/es60w-listener.service
sudo systemctl daemon-reload
sudo systemctl restart es60w-listener.service

systemctl show es60w-listener.service \
  -p ActiveState -p SubState -p MainPID -p User
journalctl -u es60w-listener.service -n 30 --no-pager -o cat
```

## 2026-07-29 — Official Docker CE installation

Docker Engine is installed from Docker's signed upstream APT repository, not
Ubuntu's `docker.io` package:

```sh
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg \
  --output packages/docker.asc
sha256sum packages/docker.asc

sudo install -m 0755 -d /etc/apt/keyrings
sudo install -o root -g root -m 0644 \
  packages/docker.asc /etc/apt/keyrings/docker.asc
sudo install -o root -g root -m 0644 \
  config/docker.sources /etc/apt/sources.list.d/docker.sources

sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

docker version
docker compose version
```

## 2026-07-29 — Container build and cutover

```sh
sudo docker compose --env-file config/compose.env.lab config
sudo docker compose --env-file config/compose.env.lab build --pull

# Non-hardware validation: runtime, SANE backend, user, bind mount, and
# read-only root filesystem.
sudo docker run --rm --network none --entrypoint /bin/sh \
  scanner-inbox:local -c \
  'id; python3 --version; scanimage --version'
sudo docker compose --env-file config/compose.env.lab run \
  --rm --no-deps --entrypoint /bin/sh es60w-listener

# Exactly one receiver may run during a physical-button test.
sudo systemctl stop es60w-listener.service
sudo docker compose --env-file config/compose.env.lab up -d --no-build
sudo docker compose --env-file config/compose.env.lab ps
sudo docker compose --env-file config/compose.env.lab logs -f

# Make Docker the sole boot-time receiver after the first successful scan.
sudo systemctl disable --now es60w-listener.service
sudo systemctl restart docker.service
sudo docker compose --env-file config/compose.env.lab ps

# Full boot recovery check.
cat /proc/sys/kernel/random/boot_id
sudo systemctl reboot
cat /proc/sys/kernel/random/boot_id
systemctl is-enabled es60w-listener.service
sudo docker compose --env-file config/compose.env.lab ps
```
