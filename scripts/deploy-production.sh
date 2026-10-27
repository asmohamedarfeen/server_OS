#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="${GITHUB_WORKSPACE:-}"
DEPLOY_DIR="${ARFEEN_DEPLOY_DIR:-/home/md/arfeen-cloud}"
LOCK_FILE="${ARFEEN_LOCK_FILE:-/home/md/.arfeen-deploy.lock}"
BACKUP_ROOT="${ARFEEN_BACKUP_ROOT:-/home/md/.arfeen-deploy-backups}"
HEALTH_URL="${ARFEEN_HEALTH_URL:-http://127.0.0.1:8080/}"
HEALTH_ATTEMPTS="${ARFEEN_HEALTH_ATTEMPTS:-30}"
HEALTH_INTERVAL="${ARFEEN_HEALTH_INTERVAL:-2}"

BACKUP_DIR=''
ROLLBACK_ARMED=false

RSYNC_EXCLUDES=(
  --exclude='/.env'
  --exclude='/storage/'
  --exclude='/.git/'
  --exclude='/frontend/node_modules/'
  --exclude='/frontend/.next/'
  --exclude='/backend/.venv/'
  --exclude='__pycache__/'
  --exclude='*.py[cod]'
  --exclude='/.DS_Store'
  --exclude='/._*'
)

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  if [[ "$ROLLBACK_ARMED" == true ]]; then
    handle_failure 1
  fi
  exit 1
}

validate_absolute_path() {
  local name="$1"
  local value="$2"
  [[ "$value" == /* ]] || die "$name must be an absolute path"
  [[ "$value" != '/' ]] || die "$name may not be the filesystem root"
}

cleanup() {
  if [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" && "$BACKUP_DIR" == "$BACKUP_ROOT/"* ]]; then
    rm -rf -- "$BACKUP_DIR"
  fi
}

restore_previous_release() {
  local rollback_failed=false

  log 'Restoring the previous application source.'
  if ! rsync -a --checksum --delete "${RSYNC_EXCLUDES[@]}" "$BACKUP_DIR/" "$DEPLOY_DIR/"; then
    rollback_failed=true
    printf '[deploy] ERROR: source rollback failed.\n' >&2
  fi

  if [[ "$rollback_failed" == false ]]; then
    if ! (cd "$DEPLOY_DIR" && sudo docker compose up -d --build --remove-orphans); then
      rollback_failed=true
      printf '[deploy] ERROR: restored Compose stack failed to start.\n' >&2
    fi
  fi

  if [[ "$rollback_failed" == true ]]; then
    printf '[deploy] ERROR: automatic rollback was incomplete.\n' >&2
  else
    log 'Previous application source and Compose stack restored.'
  fi
}

handle_failure() {
  local original_status="${1:-1}"
  [[ "$original_status" -ne 0 ]] || original_status=1
  trap - ERR INT TERM
  set +e

  if [[ "$ROLLBACK_ARMED" == true ]]; then
    ROLLBACK_ARMED=false
    restore_previous_release
  fi

  exit "$original_status"
}

trap cleanup EXIT
trap 'handle_failure $?' ERR
trap 'handle_failure 130' INT
trap 'handle_failure 143' TERM

for required_command in git rsync flock sudo docker curl mktemp; do
  command -v "$required_command" >/dev/null 2>&1 || die "required command is missing: $required_command"
done

[[ -n "$SOURCE_DIR" ]] || die 'GITHUB_WORKSPACE is required'
validate_absolute_path GITHUB_WORKSPACE "$SOURCE_DIR"
validate_absolute_path ARFEEN_DEPLOY_DIR "$DEPLOY_DIR"
validate_absolute_path ARFEEN_LOCK_FILE "$LOCK_FILE"
validate_absolute_path ARFEEN_BACKUP_ROOT "$BACKUP_ROOT"
[[ "$SOURCE_DIR" != "$DEPLOY_DIR" ]] || die 'source and deployment directories must differ'
[[ -d "$SOURCE_DIR/.git" ]] || die 'GITHUB_WORKSPACE must be a Git checkout'
[[ -d "$DEPLOY_DIR" ]] || die "deployment directory does not exist: $DEPLOY_DIR"
[[ "$HEALTH_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || die 'ARFEEN_HEALTH_ATTEMPTS must be a positive integer'
[[ "$HEALTH_INTERVAL" =~ ^[0-9]+([.][0-9]+)?$ ]] || die 'ARFEEN_HEALTH_INTERVAL must be a non-negative number'

DEPLOY_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
if [[ "${GITHUB_ACTIONS:-false}" == true ]]; then
  [[ -n "${GITHUB_SHA:-}" ]] || die 'GITHUB_SHA is required in GitHub Actions'
  [[ "$DEPLOY_SHA" == "$GITHUB_SHA" ]] || die "checked-out commit does not match the triggering commit"
fi

mkdir -p -- "$(dirname "$LOCK_FILE")" "$BACKUP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || die 'another production deployment is already running'

BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/deploy-backup.XXXXXX")"
log 'Snapshotting the current application source.'
rsync -a --checksum --delete "${RSYNC_EXCLUDES[@]}" "$DEPLOY_DIR/" "$BACKUP_DIR/"
ROLLBACK_ARMED=true

log "Synchronizing commit $DEPLOY_SHA into production."
rsync -a --checksum --delete "${RSYNC_EXCLUDES[@]}" "$SOURCE_DIR/" "$DEPLOY_DIR/"

log 'Validating and starting the Docker Compose stack.'
(
  cd "$DEPLOY_DIR"
  sudo docker compose config --quiet
  sudo docker compose up -d --build --remove-orphans
)

expected_services="$(cd "$DEPLOY_DIR" && sudo docker compose config --services | LC_ALL=C sort)"
running_services="$(cd "$DEPLOY_DIR" && sudo docker compose ps --services --status running | LC_ALL=C sort)"
[[ -n "$expected_services" && "$running_services" == "$expected_services" ]] || die 'not all Compose services are running'

health_ok=false
for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt += 1)); do
  if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null; then
    health_ok=true
    break
  fi
  if ((attempt < HEALTH_ATTEMPTS)); then
    sleep "$HEALTH_INTERVAL"
  fi
done
[[ "$health_ok" == true ]] || die "health check failed after $HEALTH_ATTEMPTS attempts"

ROLLBACK_ARMED=false
log "Deployment succeeded for commit $DEPLOY_SHA."
