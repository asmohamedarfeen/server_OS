#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_SCRIPT="$PROJECT_ROOT/scripts/deploy-production.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/arfeen-deploy-test.XXXXXX")"
TEST_COUNT=0

cleanup() {
  rm -rf -- "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_equals() {
  local expected="$1"
  local actual="$2"
  local message="$3"
  [[ "$actual" == "$expected" ]] || fail "$message (expected '$expected', got '$actual')"
}

assert_file_contains() {
  local path="$1"
  local expected="$2"
  [[ -f "$path" ]] || fail "missing file: $path"
  grep -Fqx -- "$expected" "$path" || fail "$path did not contain '$expected'"
}

assert_path_absent() {
  local path="$1"
  [[ ! -e "$path" ]] || fail "path should be absent: $path"
}

make_fake_commands() {
  local fake_bin="$1"
  mkdir -p "$fake_bin"

  cat >"$fake_bin/sudo" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$@"
EOF

  cat >"$fake_bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >>"$MOCK_COMMAND_LOG"

case "$*" in
  "compose config --quiet")
    exit 0
    ;;
  "compose config --services")
    printf '%s\n' traefik backend frontend
    ;;
  "compose ps --services --status running")
    printf '%s\n' traefik backend frontend
    ;;
  "compose up -d --build --remove-orphans")
    count=0
    [[ -f "$MOCK_UP_COUNT" ]] && count="$(cat "$MOCK_UP_COUNT")"
    count=$((count + 1))
    printf '%s\n' "$count" >"$MOCK_UP_COUNT"
    if [[ "${MOCK_FAIL_FIRST_UP:-false}" == "true" && "$count" -eq 1 ]]; then
      exit 23
    fi
    ;;
  *)
    echo "unexpected docker command: $*" >&2
    exit 64
    ;;
esac
EOF

  cat >"$fake_bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "curl $*" >>"$MOCK_COMMAND_LOG"
[[ "${MOCK_HEALTH_FAIL:-false}" != "true" ]]
EOF

  cat >"$fake_bin/flock" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[[ "${MOCK_LOCK_FAIL:-false}" != "true" ]]
EOF

  chmod +x "$fake_bin/sudo" "$fake_bin/docker" "$fake_bin/curl" "$fake_bin/flock"
}

setup_case() {
  local name="$1"
  MOCK_FAIL_FIRST_UP=false
  MOCK_HEALTH_FAIL=false
  MOCK_LOCK_FAIL=false
  TEST_GITHUB_SHA=''
  export MOCK_FAIL_FIRST_UP MOCK_HEALTH_FAIL MOCK_LOCK_FAIL
  unset TEST_GITHUB_SHA

  CASE_ROOT="$TEST_ROOT/$name"
  SOURCE_DIR="$CASE_ROOT/source"
  LIVE_DIR="$CASE_ROOT/live"
  BACKUP_ROOT="$CASE_ROOT/backups"
  LOCK_FILE="$CASE_ROOT/deploy.lock"
  FAKE_BIN="$CASE_ROOT/bin"
  MOCK_COMMAND_LOG="$CASE_ROOT/commands.log"
  MOCK_UP_COUNT="$CASE_ROOT/up-count"
  OUTPUT_FILE="$CASE_ROOT/output.log"

  mkdir -p "$SOURCE_DIR" "$LIVE_DIR/storage" "$BACKUP_ROOT"
  printf '%s\n' 'new source' >"$SOURCE_DIR/README.md"
  printf '%s\n' 'new file' >"$SOURCE_DIR/new-file.txt"
  printf '%s\n' 'old source' >"$LIVE_DIR/README.md"
  printf '%s\n' 'old file' >"$LIVE_DIR/obsolete.txt"
  printf '%s\n' 'protected secret' >"$LIVE_DIR/.env"
  printf '%s\n' 'persistent upload' >"$LIVE_DIR/storage/upload.txt"
  : >"$MOCK_COMMAND_LOG"

  git -C "$SOURCE_DIR" init -q
  git -C "$SOURCE_DIR" config user.name 'Deployment Test'
  git -C "$SOURCE_DIR" config user.email 'deploy-test@example.invalid'
  git -C "$SOURCE_DIR" add README.md new-file.txt
  git -C "$SOURCE_DIR" commit -qm 'test fixture'
  SOURCE_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD)"

  make_fake_commands "$FAKE_BIN"
  export MOCK_COMMAND_LOG MOCK_UP_COUNT
}

run_deploy() {
  env \
    PATH="$FAKE_BIN:$PATH" \
    GITHUB_WORKSPACE="$SOURCE_DIR" \
    GITHUB_ACTIONS=true \
    GITHUB_SHA="${TEST_GITHUB_SHA:-$SOURCE_SHA}" \
    ARFEEN_DEPLOY_DIR="$LIVE_DIR" \
    ARFEEN_LOCK_FILE="$LOCK_FILE" \
    ARFEEN_BACKUP_ROOT="$BACKUP_ROOT" \
    ARFEEN_HEALTH_URL='http://127.0.0.1:8080/' \
    ARFEEN_HEALTH_ATTEMPTS=2 \
    ARFEEN_HEALTH_INTERVAL=0 \
    MOCK_FAIL_FIRST_UP="${MOCK_FAIL_FIRST_UP:-false}" \
    MOCK_HEALTH_FAIL="${MOCK_HEALTH_FAIL:-false}" \
    MOCK_LOCK_FAIL="${MOCK_LOCK_FAIL:-false}" \
    bash "$DEPLOY_SCRIPT" >"$OUTPUT_FILE" 2>&1
}

pass() {
  TEST_COUNT=$((TEST_COUNT + 1))
  echo "PASS: $1"
}

test_success_preserves_protected_paths() {
  setup_case success
  run_deploy || fail "successful deployment exited non-zero: $(cat "$OUTPUT_FILE")"

  assert_file_contains "$LIVE_DIR/README.md" 'new source'
  assert_file_contains "$LIVE_DIR/new-file.txt" 'new file'
  assert_path_absent "$LIVE_DIR/obsolete.txt"
  assert_file_contains "$LIVE_DIR/.env" 'protected secret'
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '1' "$(cat "$MOCK_UP_COUNT")" 'Compose should start once'
  pass test_success_preserves_protected_paths
}

test_failed_compose_restores_previous_source() {
  setup_case compose-failure
  MOCK_FAIL_FIRST_UP=true
  export MOCK_FAIL_FIRST_UP

  if run_deploy; then
    fail 'deployment should fail when the first Compose start fails'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_file_contains "$LIVE_DIR/obsolete.txt" 'old file'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_file_contains "$LIVE_DIR/.env" 'protected secret'
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '2' "$(cat "$MOCK_UP_COUNT")" 'rollback should attempt Compose start'
  pass test_failed_compose_restores_previous_source
}

test_health_timeout_restores_previous_source() {
  setup_case health-failure
  MOCK_HEALTH_FAIL=true
  export MOCK_HEALTH_FAIL

  if run_deploy; then
    fail 'deployment should fail after health checks time out'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_file_contains "$LIVE_DIR/obsolete.txt" 'old file'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_file_contains "$LIVE_DIR/.env" 'protected secret'
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '2' "$(cat "$MOCK_UP_COUNT")" 'health failure should restart the restored stack'
  assert_equals '2' "$(grep -c '^curl ' "$MOCK_COMMAND_LOG")" "health check attempt count; command log: $(tr '\n' ';' <"$MOCK_COMMAND_LOG")"
  pass test_health_timeout_restores_previous_source
}

test_lock_prevents_concurrent_deploy() {
  setup_case lock-contention
  MOCK_LOCK_FAIL=true
  export MOCK_LOCK_FAIL

  if run_deploy; then
    fail 'deployment should fail while another process holds the lock'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_equals '' "$(cat "$MOCK_COMMAND_LOG")" 'locked deployment should not call external services'
  unset MOCK_LOCK_FAIL
  pass test_lock_prevents_concurrent_deploy
}

test_sha_mismatch_stops_before_sync() {
  setup_case sha-mismatch
  TEST_GITHUB_SHA='0000000000000000000000000000000000000000'
  export TEST_GITHUB_SHA

  if run_deploy; then
    fail 'deployment should reject a checkout that differs from GITHUB_SHA'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_equals '' "$(cat "$MOCK_COMMAND_LOG")" 'SHA mismatch should not call external services'
  unset TEST_GITHUB_SHA
  pass test_sha_mismatch_stops_before_sync
}

[[ -f "$DEPLOY_SCRIPT" ]] || fail "missing deployment script: $DEPLOY_SCRIPT"

test_success_preserves_protected_paths
test_failed_compose_restores_previous_source
test_health_timeout_restores_previous_source
test_lock_prevents_concurrent_deploy
test_sha_mismatch_stops_before_sync

echo "All $TEST_COUNT deployment tests passed."
