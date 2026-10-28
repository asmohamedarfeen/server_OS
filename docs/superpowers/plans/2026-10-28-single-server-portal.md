# Single-server portal Implementation Plan

> **For agentic workers:** Use the approved spec and test-driven development. The parallel-agent workflow isolates server backend, pipeline backend, and frontend file ownership; the root agent integrates and verifies all three.

**Goal:** Implement the approved Azure-style app, pipeline, and server management portal on the current server.
**Architecture:** Preserve Docker/FastAPI/SQLite and existing deployment workers. Add separate server-control and pipeline modules with authenticated APIs, then connect URL-backed portal pages to them.
**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, SQLite, Docker SDK, existing Python unittest and Playwright checks.
**Spec:** `docs/superpowers/specs/2026-10-28-single-server-azure-portal-design.md` (approved by user).

## Global constraints

- Only the existing managed server; preserve existing resources and uncommitted work.
- Keep management APIs authenticated. Never run real destructive server operations during verification.
- Use additive database migrations and existing single serialized deployment worker.
- Retain metrics for 24 hours; runtime/build logs remain distinct.
- No new Azure dependency, production deployment, push, or live host service mutation.
- Work on `feat/single-server-portal` in the existing checkout; no commit is required for the user's review.

## Review focus

- Reload/back/direct resource links retain navigation state.
- Failed/cancelled tests or builds preserve the running application.
- Secrets never appear in activity metadata or errors.
- Host controls fail closed when unsupported and report real capabilities.
- Timers/pollers stop on teardown and bounded histories survive page navigation.

## Task 1: Server/control foundation (parallel owner: server backend)

Files: new `backend/app/services/control.py`, `backend/app/api/control.py`, `tests/test_control.py`; optionally existing `containers.py`, `resources.py`, `system.py` for activity/host accuracy. Do not edit `main.py`, `core/db.py`, or deployment files.

Interfaces: authenticated `/api/control/overview`, `/disks`, `/network`, `/services`, `/activity?resource_id=...`, `/metrics?resource_id=server`, `/operations`, POST `/services/{name}/restart` and `/reboot`; GET `/operations/{id}`. `control.initialize()`, `control.start()`, `control.stop()` lifecycle. Shared `control.record_activity(action, resource_id, resource_name, status, actor='administrator', message='', correlation_id=None)` must sanitize and retain no secret values. Overview returns server metrics plus capabilities. Metrics returns timestamped samples. Host actions require hostname confirmation and return durable operation IDs.

- [x] Write failing auth, activity, metric retention, capability, host-adapter and confirmation tests; run them and observe failure.
- [x] Implement tables, bounded sampler, host inspection, allowlisted command adapter, separate action worker and operation recovery.
- [x] Add activity hooks to owned lifecycle endpoints; protect system resources.
- [x] Run tests with fake host/engine only; report exact API response shapes to root.

## Task 2: Pipeline and application backend (parallel owner: pipeline backend)

Files: new `services/pipelines.py`, `api/pipelines.py`, `tests/test_pipelines.py`; own changes to `services/deployment_jobs.py`, `api/applications.py`, `api/deployment_jobs.py`. Do not edit `main.py` or `core/db.py`.

Interfaces: authenticated GET/POST `/api/pipelines`, GET/PATCH `/api/pipelines/{id}`, POST `/{id}/run`, POST `/{id}/run-zip`, GET `/{id}/runs`, GET `/api/pipelines/runs/{run_id}`, POST `/runs/{run_id}/cancel`; existing deployment-job log endpoint remains. Pipeline config `{name,app_id,enabled,test_command,test_timeout,poll_enabled}` with app-linked GitHub/ZIP source. Run details include durable stage records, commit, image artifact, job/app IDs; job uses existing deployment worker. Application GET `/api/apps/{id}/metrics` and GET/PATCH `/api/apps/{id}/readiness` (`{path,expected_status,timeout}`), source config PATCH `/api/apps/{id}/source` if required. Lifecycle `pipelines.initialize/start/stop`. Activity hook imports control lazily to avoid cross-owner dependencies.

- [x] Write failing tests for auth/config validation, duplicate triggers, test-before-deploy failure, cleanup, cancellation, readiness path restrictions, and stage timing.
- [x] Implement definition schema, stage recording, optional isolated test stage with timeout/exit code, readiness verification, safe-boundary cancellation and persistent GitHub polling cursor.
- [x] Hook initial/manual redeploy paths to stage recording; retain existing deployment API compatibility.
- [x] Implement real container metrics and readiness config; record lifecycle/config/deploy events without secrets.
- [x] Run backend suite and document concrete response shapes for frontend integration.

## Task 3: Portal shell and resource pages (root)

Files: new `frontend/components/portal.tsx`, `portal-pages.tsx`, `portal-app.tsx`, `portal-pipelines.tsx`, `portal-server.tsx`, `portal-shared.tsx`, `frontend/app/portal.css`; modify root page to use portal; retain existing pages/forms through exported components. New `tests/ui_portal.py` uses controlled API fixtures.

- [x] Write browser test for URL navigation, inventory/search, app lifecycle/logs/config, pipeline stage selection, server services/confirmation, activity and small-screen layout; observe failure against existing UI.
- [x] Build Azure-style shell with real search, notifications, URL-backed resource navigation and responsive menus.
- [x] Connect Home/All resources/App Services to real inventory; app detail uses lifecycle, logs, config, metrics, activity and current-container terminal.
- [x] Connect pipeline list/create/edit/manual run/ZIP/run details/stage logs/cancellation and trigger config.
- [x] Connect server overview/metrics/processes/disks/network/services/terminal/activity and capability-aware confirmation controls; preserve infrastructure and settings destinations.

## Task 4: Integration, review and delivery (root)

Files: `backend/app/main.py`, README, tests and targeted integration fixes.

- [x] Wire schemas, startup/shutdown sampler and trigger workers, routers, actor-aware activity for remaining database/file/resource operations.
- [x] Run full Python unittest suite, shell regression checks, production frontend build, new and existing browser tests. Check screenshots of Home, App Overview, Pipeline Run and Server Overview at desktop and mobile sizes.
- [x] Request independent whole-change code review, fix material issues and repeat affected checks.
- [x] Record completion and limitations in this plan/README; leave reviewable code in working branch, no production mutation.

## Progress

- Preflight: Task 1 and Task 2 share only documented control activity hook; lazy import and independently initialized tables avoid file conflicts. Root owns main lifecycle/router integration. Frontend consumes stable API contracts; adapt concrete response shapes during integration.
- Ruling: User explicitly approved implementation; proceed through this plan without further approval gates. Use the existing checkout with a feature branch to retain prior work.

- Task 1 complete: authenticated control API, host-aware capability adapter, durable operations, activity, and 24-hour server/application sampling. Confirmed host identity avoids the backend UTS namespace.
- Task 2 complete: app-linked pipelines, actual commit reconciliation, isolated image tests, HTTP readiness, atomic cancellation boundary and queue/lifecycle resource locks. Domain routing uses the same verified candidate with exact proxy-network probing and atomic file-provider handoff; working instance remains until routing acknowledgement and DB commit.
- Task 3 complete: Azure-style portal shell, global search, direct/back/reload resource navigation, responsive accessible menus, app/pipeline/server detail pages, actual selected infrastructure resources and settings/log workflows.
- Verification: 83 backend tests passed. All three production browser suites passed (portal, deployment console, runtime logs); portal regression also protects configuration against failed initial loads, active-deployment conflicts, and navigation scroll reset. Production build/type checks, Compose config with non-secret validation values, and diff checks passed. Deployment shell suite passed; real flock concurrency case skipped because flock is unavailable on this Mac.
- Independent backend/frontend reviews completed; material findings fixed with regressions. Final route-ack review confirmed exact proxy endpoint/status checks resolve the last availability finding.
- Limitations: Docker daemon is unavailable locally. Live Ubuntu/Docker/Traefik deployment, service restarts and reboot have not been exercised; automated tests use controlled adapters/fixtures. Existing core.db.init_db emits SQLite connection ResourceWarnings under Python 3.13; tests still pass. No production mutations, commits, merges, or pushes performed.
- Delivery: source remains in the existing workspace on feat/single-server-portal, including prior URL/runtime work. User can deploy via the existing updater or rebuild Compose after transferring updated source.
