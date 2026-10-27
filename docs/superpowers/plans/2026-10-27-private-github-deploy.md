# Private GitHub Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the single Arfeen Cloud administrator connect a fine-grained GitHub token, select private repositories and branches, and deploy or redeploy them from the dashboard.

**Architecture:** Store a GitHub token encrypted in the existing SQLite settings table using a dedicated key in `.env`. Add authenticated GitHub API endpoints for token validation, repository listing, and branch listing; use the saved token only in backend clone operations. Persist the selected source type and branch with each application so redeploy uses the same repository and ref.

**Tech Stack:** FastAPI, SQLite, Python cryptography (AES-GCM), GitHub REST API, Next.js/React, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-27-private-github-deploy-design.md`

## Global Constraints

- Only the authenticated administrator may manage the GitHub connection or deploy private repositories.
- The token is encrypted at rest with a separate key and never echoed after saving.
- Clone operations use only HTTPS GitHub hosts and validated repository paths.
- Recommend a token limited to contents read access and selected repositories.
- Do not add an unauthenticated webhook endpoint in this release.
- Preserve public GitHub URL deployment and ZIP upload behavior.
- SQLite schema changes are additive and preserve existing app and deployment data.
- Do not add or run tests in this implementation; keep changes reviewable and describe available manual verification steps.

## Review Focus

- **Invalid or revoked token:** connection test reports an actionable error and does not replace a valid saved credential.
- **Token absent or encryption key missing:** private-repo endpoints fail closed without exposing secrets or storing plaintext.
- **Repository and ref path injection:** owner, repository, and branch values are validated/encoded before GitHub API and Git use.
- **Token leakage:** no token in source URLs, API response bodies, process command arguments, deployment history, or error text.
- **Failed redeploy:** a failed clone/build does not stop or remove the currently running app container.

---

### Task 1: Add encrypted GitHub credential storage

**Files:**
- Create: `backend/app/services/github.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`
- Modify: `scripts/install.sh`
- Modify: `.env.example`

**Interfaces:**
- `encrypt_github_token(token: str) -> str`
- `decrypt_github_token(ciphertext: str) -> str`
- `github_token() -> str | None`
- `save_github_token(token: str) -> None`
- `delete_github_token() -> None`
- `GITHUB_CREDENTIALS_KEY` is a stable, dedicated 32-byte key encoded as URL-safe base64 in the environment.

- [x] Add a dedicated encryption key to backend config and use authenticated AES-GCM with a fresh nonce for each stored token.
- [x] Persist ciphertext under a fixed settings key; keep token plaintext only in request memory and clone subprocess environment.
- [x] Extend installer secret generation to create the encryption key only when missing, preserving existing keys and `.env` permissions.
- [x] Document that the installer generates the encryption key and it must remain stable.
- [x] Review the change for plaintext fallback paths; missing/invalid key must fail closed.

### Task 2: Add authenticated GitHub connection and repository APIs

**Files:**
- Modify: `backend/app/api/settings.py` or create `backend/app/api/github.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/github.py`

**Interfaces:**
- `PUT /api/github/connection` accepts `{ "token": string }`, validates access before saving, and returns only `{ "connected": true }`.
- `GET /api/github/connection` returns connection state only.
- `DELETE /api/github/connection` removes the saved ciphertext.
- `GET /api/github/repositories` returns bounded, paginated repository summaries `{ owner, name, full_name, private, default_branch }`.
- `GET /api/github/repositories/{owner}/{repo}/branches` returns branch names and commit SHAs.

- [x] Implement GitHub REST requests with a fixed API host, bearer authorization, timeouts, bounded pagination, and sanitized error mapping.
- [x] Ensure all endpoints except connection status are protected by the existing administrator dependency.
- [x] Validate owner/repository path segments and branch refs before using them.
- [x] Return only minimal repository data and never return the token or authorization headers.
- [x] Add `/api/github` router to the FastAPI app.

### Task 3: Persist branch-aware GitHub sources and use them for deploy/redeploy

**Files:**
- Modify: `backend/app/core/db.py`
- Modify: `backend/app/api/applications.py`

**Interfaces:**
- Additive application columns: `host_port INTEGER`, `source_type TEXT NOT NULL DEFAULT 'github'`, and `source_ref TEXT NOT NULL DEFAULT ''` (empty means use the repository default branch).
- `clone_github_repository(url: str, ref: str, destination: Path, token: str | None) -> None` shallow-clones a validated GitHub repository without embedding credentials in the URL or arguments.
- `POST /api/apps/github` accepts `{ name, url?, owner?, repo?, ref?, domain?, environment? }`; private selection requires a saved token.
- `POST /api/apps/{app_id}/redeploy/github` uses the stored source type/ref and saved token when needed.
- GitHub build attempts are stored in `deployment_attempts` with app ID, status, stage, safe message, creation time, and image; failed attempts appear in the existing history views.

- [x] Add additive SQLite migrations for `host_port`, source type, and ref, classifying existing ZIP source records without losing rows.
- [x] Extract and validate the repository/ref fetch logic so initial deploy and redeploy share it.
- [x] Use an ephemeral askpass helper and environment variable for token authentication; remove helper and workspace in `finally` on every exit path.
- [x] Save canonical credential-free GitHub URL, source type, and branch on the application record.
- [x] Keep the old container running until the replacement image has built and the replacement container starts successfully.
- [x] Keep the old container if starting the replacement fails.
- [x] Persist stage-specific GitHub attempts and expose failed attempts in deployment history with credential-redacted errors.

### Task 4: Add GitHub connection UI and private repository picker

**Files:**
- Modify: `frontend/components/resource-pages.tsx`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Settings shows GitHub connection state, an input to connect a fine-grained token, access feedback, and disconnect action.
- Deploy modal GitHub tab supports connected repository selection, branch selection, app name, domain, environment variables, and build/deploy action.
- Public repository URL entry remains available when no GitHub connection exists.
- Private GitHub applications use the same Redeploy action and fetch their stored branch.

- [x] Add GitHub status/connect/disconnect/repository/branch API calls using the existing authenticated `api` helper.
- [x] Keep the token only in the connect form state; clear it after the server confirms success and never prefill it from API data.
- [x] Add loading, empty, and permission-error states for repository and branch selectors.
- [x] Submit the selected owner, repository, and branch to the existing deploy endpoint.
- [x] Update the Applications page's redeploy behavior to support both public and private GitHub source types.
- [x] Show failed GitHub attempts in per-application and global deployment history; render rollback only for successful deployments.

### Task 5: Document token setup and deploy workflow

**Files:**
- Modify: `README.md`
- Modify: `web_server.md` only if its user-facing deployment instructions need to stay aligned.

- [x] Document fine-grained PAT setup, repository selection, minimum read permissions, connecting it in Settings, and deploying/redeploying a branch.
- [x] Explain token revocation and the requirement to preserve `GITHUB_CREDENTIALS_KEY` across updates and backups.
- [x] Clarify that this release deploys from the dashboard and does not receive automatic push webhooks.
- [x] Include manual review steps: connect a restricted token, list a private repo and branch, deploy it, redeploy it, revoke the token, and verify failures do not leak credentials or stop the current app.

## Implementation rulings and validation

- The existing SQLite schema omitted `host_port`, although deployment code already writes and reads it. Additive migration creates the nullable column required for app records; the column can remain empty for installations with no pre-existing host-port data. If this diagnosis is wrong, the migration is harmless but extra.
- Fine-grained GitHub tokens cannot call GitHub's authenticated-user endpoint, so connection status reports only whether a credential is saved. If account identity is required later, use a GitHub App flow or another supported endpoint.
- The selected release uses dashboard-triggered deploys; push webhooks are deferred because the current service is private to Tailscale.
- Validation completed: Python syntax compilation, Next.js production build, Docker Compose configuration, and `git diff --check` passed. No tests were added or run, and the private-token flow was not exercised against a live GitHub account.
