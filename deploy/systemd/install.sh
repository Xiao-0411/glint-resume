#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root (use sudo only when the current account is not root)." >&2
  exit 1
fi

if [[ "$#" -ne 2 ]]; then
  echo "Usage: bash deploy/systemd/install.sh /actual/project/path actual-service-user" >&2
  echo "Find both values first by following deploy/CRAWLER.md; do not copy placeholder paths." >&2
  exit 1
fi

app_dir="$(readlink -f "$1")"
service_user="$2"

if [[ "${app_dir}" != /* || "${app_dir}" =~ [[:space:]] ]]; then
  echo "The project path must be absolute and contain no spaces: ${app_dir}" >&2
  exit 1
fi
if ! id "${service_user}" >/dev/null 2>&1; then
  echo "Service user does not exist: ${service_user}" >&2
  exit 1
fi
if [[ ! -f "${app_dir}/backend/run_crawler.py" ]]; then
  echo "backend/run_crawler.py was not found under ${app_dir}" >&2
  exit 1
fi
if [[ ! -x "${app_dir}/backend/.venv/bin/python" ]]; then
  echo "Create backend/.venv and install requirements before running this installer." >&2
  exit 1
fi
if ! command -v Xvfb >/dev/null 2>&1; then
  echo "Xvfb is missing." >&2
  if command -v dnf >/dev/null 2>&1; then
    echo "OpenCloudOS/RHEL command: dnf install -y xorg-x11-server-Xvfb" >&2
  elif command -v yum >/dev/null 2>&1; then
    echo "RHEL-compatible command: yum install -y xorg-x11-server-Xvfb" >&2
  elif command -v apt-get >/dev/null 2>&1; then
    echo "Ubuntu/Debian command: apt-get install -y xvfb" >&2
  fi
  exit 1
fi
if ! command -v x11vnc >/dev/null 2>&1; then
  echo "x11vnc is missing. It is required for the initial interactive login." >&2
  if command -v dnf >/dev/null 2>&1; then
    echo "OpenCloudOS/RHEL command: dnf install -y x11vnc" >&2
  elif command -v apt-get >/dev/null 2>&1; then
    echo "Ubuntu/Debian command: apt-get install -y x11vnc" >&2
  fi
  exit 1
fi

browser_found=false
for candidate in google-chrome-stable google-chrome chromium chromium-browser ungoogled-chromium; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    browser_found=true
    break
  fi
done
if [[ "${browser_found}" != true ]]; then
  echo "No supported Chrome/Chromium executable was found." >&2
  echo "OpenCloudOS EPOL option: dnf install -y ungoogled-chromium" >&2
  exit 1
fi

service_home="$(getent passwd "${service_user}" | cut -d: -f6)"
if [[ -z "${service_home}" || "${service_home}" != /* ]]; then
  echo "Could not resolve the home directory for ${service_user}." >&2
  exit 1
fi

service_group="$(id -gn "${service_user}")"
install -d -m 0700 -o "${service_user}" -g "${service_group}" "${service_home}"
install -d -m 0700 -o "${service_user}" -g "${service_group}" \
  "${service_home}/.boss-zhipin-scraper" \
  "${service_home}/.boss-zhipin-scraper/chrome-profile"

cat > /etc/systemd/system/glint-crawler-display.service <<EOF
[Unit]
Description=Glint crawler virtual display
After=network.target

[Service]
Type=simple
User=${service_user}
ExecStart=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -ac
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/glint-crawler-browser.service <<EOF
[Unit]
Description=Glint crawler Chrome CDP browser
Requires=glint-crawler-display.service
After=glint-crawler-display.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${service_user}
Environment=HOME=${service_home}
Environment=DISPLAY=:99
Environment=BOSS_SCRAPER_CDP_PORT=9222
ExecStart=/bin/bash ${app_dir}/deploy/systemd/run-crawler-browser.sh
Restart=always
RestartSec=5
TimeoutStopSec=20
KillMode=control-group
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/glint-crawler.service <<EOF
[Unit]
Description=Glint recruitment crawler scheduler
Requires=glint-crawler-browser.service
After=glint-crawler-browser.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${service_user}
WorkingDirectory=${app_dir}/backend
Environment=PYTHONUNBUFFERED=1
ExecStartPre=${app_dir}/backend/.venv/bin/python ${app_dir}/deploy/systemd/wait_for_cdp.py --port 9222 --timeout 60
ExecStart=${app_dir}/backend/.venv/bin/python ${app_dir}/backend/run_crawler.py
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30
PrivateTmp=true
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable glint-crawler-display.service glint-crawler-browser.service

echo "Installed all three services and enabled the display and browser services."
echo "Enable glint-crawler.service after the initial three-site login is complete."
echo "Continue with deploy/CRAWLER.md."
