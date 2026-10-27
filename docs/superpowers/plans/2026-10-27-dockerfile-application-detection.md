# Dockerfile Application Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Arfeen Cloud deploy repositories whose root application contract is an existing production Dockerfile with one numeric TCP port exposed by its final build stage.

**Architecture:** Extend the existing `detect_framework(root)` boundary so it recognizes a root Dockerfile before conventional framework markers. A small parser will inspect only the final Dockerfile stage, accept exactly one unique numeric TCP port, return the existing `(framework, port, kind)` contract, and otherwise raise an actionable 422 response; the established image build and container startup path remains unchanged.

**Tech Stack:** Python 3.12, FastAPI `HTTPException`, standard-library `unittest`, Dockerfile syntax subset, Docker Compose

**Spec:** `docs/superpowers/specs/2026-10-27-dockerfile-application-detection-design.md`

## Global Constraints

- Prefer a repository's existing root `Dockerfile`; never rewrite it.
- Preserve all current detection behavior when no root Dockerfile exists.
- Accept only a literal numeric TCP port from the final Dockerfile stage.
- Reject missing, variable, invalid, or ambiguous exposed ports with HTTP 422 and an actionable message.
- Do not add dependencies or change GitHub authentication, Docker Compose support, or deployment pipeline behavior.

## Review Focus

- A multi-stage Dockerfile exposes a builder port and a different runtime port: use only the runtime stage; covered by `test_dockerfile_detection_uses_final_stage_exposed_port`.
- A runtime instruction uses lowercase directives, comments, whitespace, or `/tcp`: recognize the single literal TCP port; covered by `test_dockerfile_detection_accepts_case_whitespace_comments_and_tcp_suffix`.
- A runtime `EXPOSE` uses `${PORT}` or `$PORT`: reject it with an actionable 422; covered by `test_dockerfile_detection_rejects_variable_port`.
- The final stage exposes no port or only UDP: reject it with an actionable 422; covered by `test_dockerfile_detection_rejects_missing_tcp_port`.
- The final stage exposes multiple distinct TCP ports: reject the ambiguity rather than choosing silently; covered by `test_dockerfile_detection_rejects_multiple_tcp_ports`.

---

### Task 1: Detect existing Dockerfile applications

**Files:**
- Create: `tests/test_application_detection.py`
- Modify: `backend/app/api/applications.py:52-74`
- Modify: `docs/superpowers/specs/2026-10-27-dockerfile-application-detection-design.md`
- Create: `docs/superpowers/plans/2026-10-27-dockerfile-application-detection.md`

**Interfaces:**
- Consumes: `detect_framework(root: pathlib.Path) -> tuple[str, int, str]` and FastAPI `HTTPException`.
- Produces: `dockerfile_tcp_port(path: pathlib.Path) -> int`; Dockerfile detection returns `("Dockerfile", port, "dockerfile")`.

- [ ] **Step 1: Write failing Dockerfile detection tests**

Create standard-library unit tests named:

- `test_dockerfile_detection_uses_final_stage_exposed_port`, asserting a builder `EXPOSE 3000` plus runtime `EXPOSE 8000` returns `("Dockerfile", 8000, "dockerfile")`.
- `test_dockerfile_detection_accepts_case_whitespace_comments_and_tcp_suffix`, asserting a final `expose  8000/tcp # application` returns port `8000`.
- `test_dockerfile_detection_rejects_variable_port`, asserting `EXPOSE ${PORT}` raises `HTTPException` with status 422 and mentions `EXPOSE <port>`.
- `test_dockerfile_detection_rejects_missing_tcp_port`, asserting no final TCP `EXPOSE` (including UDP-only input) raises the same actionable 422.
- `test_dockerfile_detection_rejects_multiple_tcp_ports`, asserting distinct final ports such as `EXPOSE 8000 9000` raise 422 and mention that one TCP port is required.
- `test_existing_framework_detection_is_unchanged_without_dockerfile`, asserting a root FastAPI `requirements.txt` still returns `("FastAPI", 8000, "python")`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m unittest discover -s tests -p 'test_application_detection.py' -v`

Expected: the Dockerfile tests fail because `dockerfile_tcp_port` and Dockerfile-first detection do not exist; the existing FastAPI fallback test passes.

- [ ] **Step 3: Implement `dockerfile_tcp_port(path: Path) -> int` and Dockerfile-first detection**

In `backend/app/api/applications.py`, inspect instructions after the final case-insensitive `FROM`, strip inline comments for the supported literal syntax, gather literal ports from `EXPOSE`, accept only `/tcp` or no protocol suffix, validate the range `1..65535`, and require exactly one unique TCP port. Raise `HTTPException(422, ...)` with `EXPOSE <port>` guidance for no usable port and a one-port message for ambiguity. Call it before existing framework checks when `root / "Dockerfile"` exists.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python3 -m unittest discover -s tests -p 'test_application_detection.py' -v`

Expected: all six tests pass with no warnings or errors.

- [ ] **Step 5: Run project verification**

Run:

- `bash tests/deploy-production-test.sh`
- `python3 -m compileall -q backend/app`
- `npm run build --prefix frontend`
- `JWT_SECRET=test SETUP_TOKEN=test docker compose --env-file /dev/null config --quiet`
- `/tmp/actionlint-1.7.12/actionlint -ignore 'label "arfeen-production" is unknown' .github/workflows/deploy-production.yml`
- `git diff --check`

Expected: all commands exit 0; the deployment test reports all applicable tests passed and the frontend reports a successful production build.

- [ ] **Step 6: Commit the tested change**

```bash
git add backend/app/api/applications.py tests/test_application_detection.py docs/superpowers/specs/2026-10-27-dockerfile-application-detection-design.md docs/superpowers/plans/2026-10-27-dockerfile-application-detection.md
git commit -m "feat: deploy Dockerfile-based applications"
```

### Task 2: Deploy and validate production behavior

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: the existing GitHub Actions `main` push workflow and the new `detect_framework` behavior.
- Produces: a production Arfeen Cloud backend that recognizes the CardioVision root Dockerfile as port `8000`.

- [ ] **Step 1: Push the verified commit**

Run: `git push origin main`

Expected: the push succeeds without force and starts `deploy-production`.

- [ ] **Step 2: Verify the production pipeline**

Check the GitHub Actions run and the runner journal until the exact pushed commit completes with `Succeeded`.

- [ ] **Step 3: Verify live services and Dockerfile detection**

On the server, confirm all three Arfeen services are running and dashboard/backend health return HTTP 200. In the live backend container, run `detect_framework` against a temporary Dockerfile matching CardioVision's multi-stage/final `EXPOSE 8000` shape and assert the result is `("Dockerfile", 8000, "dockerfile")`; do not print or modify stored credentials.

- [ ] **Step 4: Retry CardioVision deployment**

Use the existing connected repository and `main` branch in Arfeen Cloud. Confirm the deployment advances beyond `detect` into `build`; if the application build itself fails, report the recorded build error separately rather than treating it as framework-detection regression.

- [ ] **Step 5: Final verification and handoff**

Confirm `main` matches `origin/main`, the worktree is clean, protected `.env` permissions remain `root:root 600`, the GitHub encryption key remains configured without exposing it, and persistent volumes remain present. Report the application URL only if the CardioVision image builds and its container stays running.

