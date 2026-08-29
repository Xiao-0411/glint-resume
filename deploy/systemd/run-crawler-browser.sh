#!/usr/bin/env bash
set -euo pipefail

cdp_port="${BOSS_SCRAPER_CDP_PORT:-9222}"
profile_dir="${CRAWLER_CHROME_PROFILE_DIR:-${HOME}/.boss-zhipin-scraper/chrome-profile}"

browser=""
for candidate in google-chrome-stable google-chrome chromium chromium-browser ungoogled-chromium; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    browser="$(command -v "${candidate}")"
    break
  fi
done

if [[ -z "${browser}" ]]; then
  echo "No supported Chrome/Chromium executable was found." >&2
  exit 1
fi

mkdir -p "${profile_dir}"

exec "${browser}" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="${cdp_port}" \
  --user-data-dir="${profile_dir}" \
  --no-first-run \
  --no-default-browser-check \
  --password-store=basic \
  --remote-allow-origins='*' \
  --disable-dev-shm-usage \
  --disable-background-mode \
  --disable-crash-reporter \
  --window-size=1920,1080 \
  about:blank
