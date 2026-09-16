#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/Telegram-unzip}"
REPO_URL="${REPO_URL:-https://github.com/galaxyuniversity900-oss/Telegram-unzip.git}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required. Install Docker Engine + Compose plugin first." >&2
  exit 1
}

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" reset --hard origin/main
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Created $APP_DIR/.env. Set TELEGRAM_BOT_TOKEN to a newly generated token, then rerun this script."
  exit 0
fi

install -m 0644 "$APP_DIR/deploy/tuzsbot.service" /etc/systemd/system/tuzsbot.service
systemctl daemon-reload
systemctl enable tuzsbot.service
systemctl restart tuzsbot.service

echo "TuzsBot is installed as a restart-safe Docker service."
echo "Status: systemctl status tuzsbot.service"
echo "Logs:   docker compose -f $APP_DIR/docker-compose.yml logs -f"
