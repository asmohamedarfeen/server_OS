#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Arfeen Cloud is designed to run on an Ubuntu Server."
  echo "This installer can still generate configuration here, but host management needs Linux."
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Engine and the Compose plugin, then run this script again." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  JWT_VALUE="$(openssl rand -hex 32)"
  SETUP_VALUE="$(openssl rand -hex 24)"
  cat > "$ENV_FILE" <<EOF
CLOUD_BIND=127.0.0.1
CLOUD_PORT=8080
JWT_SECRET=$JWT_VALUE
SETUP_TOKEN=$SETUP_VALUE
COOKIE_SECURE=false
EOF
  chmod 600 "$ENV_FILE"
  echo "Created private environment file: $ENV_FILE"
  echo
  echo "One-time administrator setup key (save it now):"
  echo "$SETUP_VALUE"
  echo
else
  echo "Using existing $ENV_FILE. Existing secrets were not changed."
fi

cd "$ROOT_DIR"
docker compose up -d --build
APP_PORT="$(awk -F= '$1 == "CLOUD_PORT" { print $2 }' "$ENV_FILE" | tail -n 1)"
echo
echo "Arfeen Cloud is starting on 127.0.0.1:${APP_PORT:-8080}."
echo "For private remote HTTPS access, run: sudo tailscale serve --bg http://127.0.0.1:${APP_PORT:-8080}"
echo "Check service startup with: docker compose ps"
