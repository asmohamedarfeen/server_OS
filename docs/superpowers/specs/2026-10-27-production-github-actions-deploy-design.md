# Production GitHub Actions deployment design

## Intent

Deploy Arfeen Cloud automatically to the existing Ubuntu server whenever a commit reaches the repository's `main` branch. Keep the server private, preserve its secrets and persistent data, and make every production deployment visible in GitHub Actions.

## Goals

- Treat `main` as the only automatic production-deployment branch.
- Run deployments through a repository-scoped self-hosted GitHub Actions runner on `md@192.168.29.245`.
- Update the existing `/home/md/arfeen-cloud` Docker Compose installation without replacing `.env`, `storage/`, or named Docker volumes.
- Prevent overlapping deployments.
- Build and start the Compose stack, then verify that the dashboard responds before reporting success.
- Retain the previous application source long enough to restore it if deployment or verification fails.
- Allow an authenticated operator to start the same production workflow manually from GitHub.

## Non-goals

- Preview deployments for pull requests or feature branches.
- Public webhooks, public SSH access, or router port forwarding.
- Publishing images to a container registry.
- Zero-downtime blue/green deployment.
- Automatically applying Ubuntu or Docker upgrades.

## Constraints and current state

- The GitHub repository is `asmohamedarfeen/server_OS`.
- Production follows `main`; the current working branch is `feat/private-github-deploy`, which is two commits ahead of `main` and will need to be promoted deliberately before the pipeline can deploy that work.
- The live Compose project is `arfeen-cloud` at `/home/md/arfeen-cloud`.
- The live `.env` is root-owned with mode `0600`; it must not be read into GitHub Actions output or replaced.
- `storage/` and the `arfeen_data` and `deploy_workspace` Docker volumes are persistent production data.
- Docker and Docker Compose are installed, the `md` account can use Docker, and passwordless `sudo` is available.
- The server is reachable on a private LAN/Tailscale network, so GitHub-hosted runners cannot SSH to its LAN address directly.

## Approaches considered

1. **Repository-scoped self-hosted GitHub Actions runner (selected).** The server maintains an outbound connection to GitHub and accepts only jobs targeting its explicit production label. This gives immediate push-triggered deployments and GitHub-native logs without opening inbound ports. Repository workflow code can execute on the server, so write access and `main` must be tightly controlled.
2. **Server-side polling with systemd.** A timer could fetch `main` and deploy periodically. It avoids a GitHub runner but produces weaker status reporting, delayed deploys, and more custom state handling.
3. **GitHub-hosted runner joined through Tailscale.** This isolates workflow execution from the server but adds OAuth credentials, tailnet ACLs, ephemeral-node setup, and SSH key management that are unnecessary for one private server.

## Design

### Repository workflow

Add `.github/workflows/deploy-production.yml`. It runs only for pushes to `main` and manual `workflow_dispatch` events. The job targets a dedicated label set such as `[self-hosted, linux, x64, arfeen-production]`, uses a concurrency group with cancellation disabled, checks out the exact triggering commit, and invokes the repository-owned production deployment script.

The workflow grants only `contents: read`. It does not store the Ubuntu password, production `.env`, GitHub personal tokens, or application secrets in repository or Actions secrets. The runner receives its short-lived registration token only during one-time setup.

### Runner installation and trust boundary

Install the official GitHub Actions runner under `/home/md/actions-runner` and register it only with `asmohamedarfeen/server_OS`. Add the custom `arfeen-production` label and install it as a systemd service running as `md`. The runner connects outbound to GitHub; no inbound firewall or router change is needed.

The runner is production infrastructure. Any workflow revision that reaches `main` can execute with `md`'s access, including Docker access and passwordless sudo. Enable GitHub two-factor authentication and protect `main` from unreviewed workflow changes. Do not enable pull-request workflows on this runner, especially for forks.

### Deployment script

Add `scripts/deploy-production.sh`, intended to run only from a GitHub Actions checkout. It will:

1. Validate that required tools and paths exist and that the checkout commit matches `GITHUB_SHA` when running in Actions.
2. Acquire an exclusive `flock` lock so manual and push-triggered deployments cannot overlap.
3. Create a temporary backup of the currently deployed tracked application files, excluding `.env`, `storage/`, Git metadata, build output, and runtime data.
4. Synchronize the triggering checkout into `/home/md/arfeen-cloud` with the same exclusions. Deletions of obsolete tracked source files are allowed, but protected paths are never deleted or overwritten.
5. Run `docker compose config` and then `docker compose up -d --build --remove-orphans` from the live directory.
6. Wait for Compose services to be running and verify the local dashboard endpoint at `http://127.0.0.1:8080/` using the configured `CLOUD_PORT` without printing `.env` contents.
7. On failure, restore the previous source snapshot, rebuild/restart the previous stack, report rollback status, and exit non-zero. Backup and lock resources are cleaned up on every path.

The script will not run `docker compose down`, prune images or volumes, or delete application data. A build may briefly replace containers, so this is a safe rollback-oriented deployment rather than a zero-downtime deployment.

### One-time activation

Commit and push the workflow and script through the existing feature branch, then deliberately merge/fast-forward that branch into `main`. Create the repository runner registration token in GitHub's Settings UI, install the runner on the server, and start its service. Registration tokens and credentials will be entered interactively and will not be committed or echoed in documentation.

Before relying on automatic pushes, manually dispatch the production workflow once. Verify the runner service, workflow result, container status, and dashboard response. Then make a harmless documentation commit to `main` (or use a controlled workflow rerun) to confirm the push trigger.

## Failure behavior

- If the runner is offline, the GitHub job remains queued and production is unchanged.
- If validation or source synchronization fails, Compose is not changed.
- If build, startup, or health verification fails, the script restores the prior source and attempts to restore the prior Compose stack.
- If rollback also fails, the workflow reports both failures and leaves logs available in GitHub; it never deletes `.env`, `storage/`, or volumes.
- A later push waits for the active deployment rather than cancelling it mid-update.

## Acceptance criteria

- A push to `main` creates exactly one production deployment job on the labeled server runner.
- Pushes to other branches do not deploy production.
- A manual production dispatch works for the selected `main` commit.
- Successful deployment rebuilds and runs the `arfeen-cloud` stack from the triggering commit and the local dashboard responds.
- `.env`, `storage/`, database state, and named volumes survive a deployment unchanged.
- Two closely timed jobs cannot update the live directory concurrently.
- A deliberately invalid Compose change fails and restores the prior working source and service where feasible.
- No server password, runner token, `.env` value, or application credential is committed or printed in workflow logs.

## Operator documentation

Update the README with the production branch, workflow location, runner service checks, manual dispatch procedure, and the safe recovery commands. Document that changing workflow files is equivalent to changing production server code and that runner removal/re-registration must be performed through GitHub repository settings and the server service.
