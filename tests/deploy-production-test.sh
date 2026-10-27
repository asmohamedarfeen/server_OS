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

assert_directory_not_symlink() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" ]] || fail "expected a real directory: $path"
}

commit_source_change() {
  git -C "$SOURCE_DIR" add -A
  git -C "$SOURCE_DIR" commit -qm 'update test fixture'
  SOURCE_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
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
    count=0
    [[ -f "$MOCK_PS_COUNT" ]] && count="$(cat "$MOCK_PS_COUNT")"
    count=$((count + 1))
    printf '%s\n' "$count" >"$MOCK_PS_COUNT"
    if [[ "${MOCK_STOP_SERVICES_AFTER_FIRST:-false}" == "true" && "$count" -gt 1 ]]; then
      printf '%s\n' traefik frontend
    else
      printf '%s\n' traefik backend frontend
    fi
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
[[ "${MOCK_HEALTH_FAIL:-false}" != "true" ]] || exit 22
if [[ "${MOCK_API_HEALTH_FAIL:-false}" == "true" && "$*" == *'/api/health'* ]]; then
  exit 22
fi
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
  MOCK_API_HEALTH_FAIL=false
  MOCK_STOP_SERVICES_AFTER_FIRST=false
  MOCK_LOCK_FAIL=false
  TEST_GITHUB_SHA=''
  export MOCK_FAIL_FIRST_UP MOCK_HEALTH_FAIL MOCK_API_HEALTH_FAIL MOCK_STOP_SERVICES_AFTER_FIRST MOCK_LOCK_FAIL
  unset TEST_GITHUB_SHA

  CASE_ROOT="$TEST_ROOT/$name"
  SOURCE_DIR="$CASE_ROOT/source"
  LIVE_DIR="$CASE_ROOT/live"
  BACKUP_ROOT="$CASE_ROOT/backups"
  LOCK_FILE="$CASE_ROOT/deploy.lock"
  FAKE_BIN="$CASE_ROOT/bin"
  MOCK_COMMAND_LOG="$CASE_ROOT/commands.log"
  MOCK_UP_COUNT="$CASE_ROOT/up-count"
  MOCK_PS_COUNT="$CASE_ROOT/ps-count"
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
  export MOCK_COMMAND_LOG MOCK_UP_COUNT MOCK_PS_COUNT
}

run_deploy() {
  local output_file="${1:-$OUTPUT_FILE}"
  env \
    PATH="$FAKE_BIN:$PATH" \
    GITHUB_WORKSPACE="$SOURCE_DIR" \
    GITHUB_ACTIONS=true \
    GITHUB_SHA="${TEST_GITHUB_SHA:-$SOURCE_SHA}" \
    ARFEEN_DEPLOY_DIR="$LIVE_DIR" \
    ARFEEN_LOCK_FILE="$LOCK_FILE" \
    ARFEEN_BACKUP_ROOT="$BACKUP_ROOT" \
    ARFEEN_HEALTH_URL='http://127.0.0.1:8080/' \
    ARFEEN_API_HEALTH_URL='http://127.0.0.1:8080/api/health' \
    ARFEEN_HEALTH_ATTEMPTS=2 \
    ARFEEN_HEALTH_INTERVAL=0 \
    MOCK_FAIL_FIRST_UP="${MOCK_FAIL_FIRST_UP:-false}" \
    MOCK_HEALTH_FAIL="${MOCK_HEALTH_FAIL:-false}" \
    MOCK_API_HEALTH_FAIL="${MOCK_API_HEALTH_FAIL:-false}" \
    MOCK_STOP_SERVICES_AFTER_FIRST="${MOCK_STOP_SERVICES_AFTER_FIRST:-false}" \
    MOCK_LOCK_FAIL="${MOCK_LOCK_FAIL:-false}" \
    bash "$DEPLOY_SCRIPT" >"$output_file" 2>&1
}

pass() {
  TEST_COUNT=$((TEST_COUNT + 1))
  echo "PASS: $1"
}

run_test() {
  local name="$1"
  if [[ -z "${TEST_FILTER:-}" || "$TEST_FILTER" == "$name" ]]; then
    "$name"
  fi
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

test_incoming_storage_symlink_preserves_directory() {
  setup_case storage-symlink
  ln -s /tmp/attacker-target "$SOURCE_DIR/storage"
  commit_source_change

  run_deploy || fail "storage symlink deployment exited non-zero: $(cat "$OUTPUT_FILE")"

  assert_directory_not_symlink "$LIVE_DIR/storage"
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  pass test_incoming_storage_symlink_preserves_directory
}

test_incoming_storage_file_survives_failed_deploy() {
  setup_case storage-file-rollback
  printf '%s\n' 'replacement file' >"$SOURCE_DIR/storage"
  commit_source_change
  MOCK_FAIL_FIRST_UP=true
  export MOCK_FAIL_FIRST_UP

  if run_deploy; then
    fail 'deployment should fail when Compose fails with an incoming storage file'
  fi

  assert_directory_not_symlink "$LIVE_DIR/storage"
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '2' "$(cat "$MOCK_UP_COUNT")" 'failed deployment should perform exactly one rollback start'
  pass test_incoming_storage_file_survives_failed_deploy
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

test_api_health_failure_restores_previous_source() {
  setup_case api-health-failure
  MOCK_API_HEALTH_FAIL=true
  export MOCK_API_HEALTH_FAIL

  if run_deploy; then
    fail 'deployment should fail when the API health endpoint is unavailable'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '2' "$(cat "$MOCK_UP_COUNT")" 'API health failure should restart the restored stack once'
  assert_equals '4' "$(grep -c '^curl ' "$MOCK_COMMAND_LOG")" 'dashboard and API health probes should run on every attempt'
  pass test_api_health_failure_restores_previous_source
}

test_service_exit_after_health_probe_restores_previous_source() {
  setup_case stale-service-status
  MOCK_STOP_SERVICES_AFTER_FIRST=true
  export MOCK_STOP_SERVICES_AFTER_FIRST

  if run_deploy; then
    fail 'deployment should fail when a Compose service exits after the initial status check'
  fi

  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_file_contains "$LIVE_DIR/storage/upload.txt" 'persistent upload'
  assert_equals '2' "$(cat "$MOCK_UP_COUNT")" 'stale service status should trigger one rollback start'
  assert_equals '2' "$(cat "$MOCK_PS_COUNT")" 'service state should be checked before and after health probes'
  pass test_service_exit_after_health_probe_restores_previous_source
}

test_overlapping_backup_path_is_rejected() {
  setup_case backup-overlap
  BACKUP_ROOT="$SOURCE_DIR/backups"

  if run_deploy; then
    fail 'deployment should reject a backup directory nested inside the source checkout'
  fi

  grep -Fq 'backup directory may not overlap source or deployment directories' "$OUTPUT_FILE" || fail 'missing unsafe backup-path diagnostic'
  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_equals '' "$(cat "$MOCK_COMMAND_LOG")" 'unsafe backup path should fail before external services'
  pass test_overlapping_backup_path_is_rejected
}

test_lock_path_inside_live_directory_is_rejected() {
  setup_case lock-overlap
  LOCK_FILE="$LIVE_DIR/.deploy.lock"

  if run_deploy; then
    fail 'deployment should reject a lock file inside the live deployment directory'
  fi

  grep -Fq 'lock file may not be inside source, deployment, or backup directories' "$OUTPUT_FILE" || fail 'missing unsafe lock-path diagnostic'
  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_path_absent "$LIVE_DIR/.deploy.lock"
  assert_equals '' "$(cat "$MOCK_COMMAND_LOG")" 'unsafe lock path should fail before external services'
  pass test_lock_path_inside_live_directory_is_rejected
}

test_root_alias_is_rejected() {
  setup_case root-alias
  BACKUP_ROOT='//'

  if run_deploy; then
    fail 'deployment should reject a canonical filesystem-root backup path'
  fi

  grep -Fq 'ARFEEN_BACKUP_ROOT may not be the filesystem root' "$OUTPUT_FILE" || fail 'missing canonical root-path diagnostic'
  assert_file_contains "$LIVE_DIR/README.md" 'old source'
  assert_path_absent "$LIVE_DIR/new-file.txt"
  assert_equals '' "$(cat "$MOCK_COMMAND_LOG")" 'root alias should fail before external services'
  pass test_root_alias_is_rejected
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

test_real_flock_rejects_second_process() {
  local system_flock
  system_flock="$(PATH='/usr/bin:/bin' command -v flock 2>/dev/null || true)"
  if [[ -z "$system_flock" ]]; then
    echo 'SKIP: test_real_flock_rejects_second_process (flock unavailable on this host)'
    return
  fi

  setup_case real-lock-contention
  rm -f -- "$FAKE_BIN/flock"
  LOCK_ENTERED="$CASE_ROOT/lock-entered"
  LOCK_RELEASE="$CASE_ROOT/lock-release"
  export LOCK_ENTERED LOCK_RELEASE

  cat >"$FAKE_BIN/mktemp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
created="$(/usr/bin/mktemp "$@")"
printf '%s\n' "$created"
touch "$LOCK_ENTERED"
while [[ ! -e "$LOCK_RELEASE" ]]; do
  sleep 0.05
done
EOF
  chmod +x "$FAKE_BIN/mktemp"

  first_output="$CASE_ROOT/first-output.log"
  second_output="$CASE_ROOT/second-output.log"
  run_deploy "$first_output" &
  first_pid=$!

  for _ in $(seq 1 100); do
    [[ -e "$LOCK_ENTERED" ]] && break
    sleep 0.05
  done
  [[ -e "$LOCK_ENTERED" ]] || fail 'first deployment did not reach the locked section'

  if run_deploy "$second_output"; then
    touch "$LOCK_RELEASE"
    wait "$first_pid" || true
    fail 'second deployment should fail while the real flock is held'
  fi
  grep -Fq 'another production deployment is already running' "$second_output" || fail 'second deployment did not report lock contention'
  assert_file_contains "$LIVE_DIR/README.md" 'old source'

  touch "$LOCK_RELEASE"
  wait "$first_pid" || fail "first deployment failed after lock release: $(cat "$first_output")"
  assert_file_contains "$LIVE_DIR/README.md" 'new source'
  pass test_real_flock_rejects_second_process
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

test_workflow_contract() {
  local workflow="$PROJECT_ROOT/.github/workflows/deploy-production.yml"
  [[ -f "$workflow" ]] || fail "missing production workflow: $workflow"

  ruby -ryaml -e '
    workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: false)
    triggers = workflow.fetch("on")
    raise "unexpected triggers" unless triggers.keys.sort == ["push", "workflow_dispatch"]
    raise "push must target main only" unless triggers.fetch("push").fetch("branches") == ["main"]
    raise "workflow permissions must be read-only" unless workflow.fetch("permissions") == {"contents" => "read"}
    concurrency = workflow.fetch("concurrency")
    raise "wrong concurrency group" unless concurrency.fetch("group") == "arfeen-production"
    raise "deployments may not cancel in progress" unless concurrency.fetch("cancel-in-progress") == false
    jobs = workflow.fetch("jobs")
    raise "expected one deploy-production job" unless jobs.keys == ["deploy-production"]
    job = jobs.fetch("deploy-production")
    raise "manual dispatch must be limited to main" unless job.fetch("if") == "github.ref == '\''refs/heads/main'\''"
    raise "wrong runner labels" unless job.fetch("runs-on") == ["self-hosted", "linux", "x64", "arfeen-production"]
    raise "wrong timeout" unless job.fetch("timeout-minutes") == 45
    steps = job.fetch("steps")
    checkout = steps.fetch(0)
    raise "checkout must be pinned" unless checkout.fetch("uses") == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    raise "checkout credentials must not persist" unless checkout.fetch("with").fetch("persist-credentials") == false
    raise "checkout must use triggering SHA" unless checkout.fetch("with").fetch("ref") == "${{ github.sha }}"
    deploy = steps.fetch(1)
    raise "unexpected deploy command" unless deploy.fetch("run") == "bash scripts/deploy-production.sh"
  ' "$workflow" || fail 'production workflow violates its deployment contract'

  pass test_workflow_contract
}

[[ -f "$DEPLOY_SCRIPT" ]] || fail "missing deployment script: $DEPLOY_SCRIPT"

run_test test_success_preserves_protected_paths
run_test test_incoming_storage_symlink_preserves_directory
run_test test_incoming_storage_file_survives_failed_deploy
run_test test_failed_compose_restores_previous_source
run_test test_health_timeout_restores_previous_source
run_test test_api_health_failure_restores_previous_source
run_test test_service_exit_after_health_probe_restores_previous_source
run_test test_lock_prevents_concurrent_deploy
run_test test_real_flock_rejects_second_process
run_test test_overlapping_backup_path_is_rejected
run_test test_lock_path_inside_live_directory_is_rejected
run_test test_root_alias_is_rejected
run_test test_sha_mismatch_stops_before_sync
run_test test_workflow_contract

echo "All $TEST_COUNT deployment tests passed."
