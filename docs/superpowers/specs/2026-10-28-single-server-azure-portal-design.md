# Azure-style management for the existing server

Status: approved by the user and implemented on `feat/single-server-portal`. Local automated verification is recorded in the implementation plan; live Ubuntu/Docker validation remains a deployment-environment check.

## Intent and agreed scope

The user wants all three experiences discussed—App Service, DevOps Pipelines, and Virtual Machines—modeled in this application. All execution targets the single server already managed by the dashboard. The UI should closely resemble the interaction and layout of Azure's management tools. Keep the Arfeen Cloud name and the existing administrator account.

This means working local equivalents of the relevant management workflows, rather than reproducing every Azure service. Azure documentation describes the external reference; the existing Docker/Ubuntu stack remains the execution platform. No Microsoft account, Azure subscription, or Azure infrastructure is required.

## Existing implementation

- Next.js 15 / React 19 frontend; FastAPI backend; SQLite metadata; Docker Engine; Traefik; Ubuntu host accessed through the existing host mount.
- GitHub public/private and ZIP deployments, framework/Dockerfile detection, a serialized background build queue, saved build output, rollback, environment configuration, and application start/stop/restart APIs already exist.
- Container lifecycle, container shell, images, volumes, networks, databases, files, host terminal, process inspection, and current host metrics already exist.
- The preceding task added an application URL/open/copy control and a runtime log viewer. Preserve those uncommitted changes.
- Gaps include resource detail navigation, real global search, a unified resource inventory, structured pipeline definitions and stage records, server detail pages, persistent activity events, application CPU/memory metrics, and reliable readiness reporting.
- The current `running` state may only confirm a live container. Host identity is currently obtained inside the backend container, and several metrics need verification against the host before relabeling them as host facts.

## Approaches

1. **Integrated Azure-style portal (recommended).** Persistent global header, resource navigation, contextual resource menus, command bars, and connected detail pages. Apps, pipelines, and server management share real resources and operation history. This best matches the user's request to model all three experiences on one server.
2. **Three independent workspaces.** Each can resemble its Microsoft counterpart more literally, but duplicate navigation and separate operation views make one server harder to manage. Not recommended.
3. **Restyle existing cards only.** Lowest effort, but leaves the missing workflows and does not fulfill the requested functional change. Not recommended.

Recommendation is the integrated portal. The single-server scope and all-three direction are user decisions; the structure and defaults below are proposed implementation choices.

## Product and visual design

An administrator manages a private Ubuntu server from a desktop browser, switching between deployments and troubleshooting. Use a compact, light resource workspace with a blue global header, neutral navigation, blue links/selection, Segoe UI with system fallbacks, thin separators, small corner radii, and readable 12–14px interface text. Match Azure's hierarchy and interaction patterns while retaining Arfeen branding. Avoid decorative cards where a table or properties list is more useful.

Global header: navigation toggle, Arfeen Cloud identity, actual resource/service search, terminal shortcut, operation notifications, settings, account menu.

Primary navigation: Home, All resources, App Services, Pipelines, Server, Containers, Databases, Storage, Monitor, Activity log, Settings. Keep existing functionality available under these destinations rather than removing it during redesign. No menu item may appear functional while opening a placeholder.

Resources open in a normal navigable detail workspace: breadcrumb, resource name/type/status, contextual command bar, left service menu, main pane. Use URL-backed navigation so reload, browser back, and direct links preserve the selected resource and tab. Narrow screens collapse the menus into accessible drawers; command bars wrap and wide tables scroll within their own container.

## Working features in the first complete implementation

### Home and all resources

- Searchable/filterable inventory of the managed server, applications, containers, databases, images, volumes, and networks, with accurate types and states.
- Home summarizes server reachability, Docker availability, application states, active builds, recent resources, and recent operation results.
- Search opens actual destinations/resources and supports the advertised keyboard shortcut. Notifications reflect real operations, not synthetic status messages.

### App Services equivalent

Application detail menu: Overview, Deployment Center, Log stream, Configuration, Metrics, Activity log, Console.

- Overview: endpoint/open/copy, source/ref, framework, deployed image, current container, published/internal ports, created time, current deployment, runtime state, and health/readiness distinction.
- Command bar: browse, start, stop, restart, deploy/redeploy, rollback, refresh, and delete. Disable actions while an incompatible operation is active. Destructive actions name the affected resource.
- Deployment Center: source configuration, manual deployment, deployment history, and links to the corresponding pipeline runs. Preserve private GitHub and ZIP workflows.
- Log stream: current runtime stdout/stderr, pause/follow/copy/download, clear error/empty/disconnected states. Keep build logs separate.
- Configuration: existing environment settings with masked values by default, deliberate reveal/edit, explicit save-and-restart behavior, and no secret values in activity events.
- Metrics: real current container CPU/memory/network samples, timestamp and missing-data state. Charts only claim history that the server has actually collected.
- Console: existing authenticated shell targeting the application's current container.
- Readiness: show Docker health status when configured. For apps without a health check, say `Running · readiness not configured`. Add an optional configured HTTP readiness path/expected status/timeout, checked from the backend against the managed container; do not accept arbitrary remote probe URLs. Keep the previous working deployment until the replacement meets the configured verification policy where topology permits; published-port replacements may require a brief stop/start.

### Pipelines equivalent

Pipeline definition: named source (existing GitHub connection or ZIP), branch/ref, linked application, optional test configuration, and enabled/disabled state. One serialized local worker remains the execution agent.

- Pipeline list and detail pages, manual Run, queued/running/completed/failed/interrupted status, run timestamps/duration, source commit for GitHub, application target, image artifact, and error summary.
- Stages: Source → Configure → Build → Test → Deploy → Verify. Store each stage's status/start/end rather than inferring past timing from a single current-stage string.
- Optional test stage runs a configured command in an ephemeral container made from the built image, with explicit timeout and recorded exit code; it must not execute repository scripts directly in the backend/host process. Show `Skipped` when not configured. Test failure prevents deployment.
- Run detail: selectable stages and associated saved logs, stage timing, image artifact metadata, resulting application, retry as a new run, and downloadable build logs.
- Queue/run controls support cancellation only at implemented safe boundaries; do not expose a misleading instant-cancel control for an uncancellable Docker operation. Preserve the current app on failed/cancelled pre-deploy work and clean temporary resources.
- Automatic triggers are a separately explicit configuration: offer an opt-in GitHub branch polling trigger suitable for the private Tailscale setup, with persistent last-observed commit, duplicate suppression, and one active run per application. ZIP pipelines remain manual. No public webhook exposure is required. No scheduled trigger or Azure YAML compatibility is implied.

### Server equivalent

One resource represents the actual managed Ubuntu host; do not present it as an Azure VM or fabricate a region, VM size, subscription, or billing data.

Server menu: Overview, Metrics, Processes, Disks, Networking, Services, Terminal, Activity log.

- Actual host identity, OS/kernel, uptime, CPU/memory/load, disk usage, network rates, Docker state/version, and sample freshness.
- Disk inventory/usage and network interface/address/listening-port inspection are read-only. Existing Docker volume/network controls stay available under infrastructure resources. Firewall editing, partitioning, and arbitrary system service control are excluded from this initial implementation.
- Services shows an allowlisted set of platform-related host services such as Docker, containerd, and tailscaled. A narrow host adapter reports capabilities and uses fixed argument vectors with timeouts, not interpolated shell commands. Restarting a service that would cut off the dashboard requires an explicit impact confirmation. Unsupported operations display the reason.
- Host reboot is a separately confirmed operation: display affected apps and loss of dashboard access, require the hostname, record the request before execution, schedule the fixed host action, and reconnect after restart. Do not execute it during development or automated tests. Shutdown is excluded because this dashboard cannot power its own host back on; ordinary app/container start/stop remains fully supported.
- A separate host action queue must not share a build worker that can be occupied for minutes. The operation record must distinguish requested, dispatched, reconnecting, succeeded, failed, and unknown-after-disconnect. A returned HTTP response alone does not prove a reboot succeeded.

### Monitor and activity

- Store bounded, sampled metrics on the backend so history survives page navigation; retain 24 hours initially, label chart ranges accurately, and prune old records. Samples belong to a single backend sampler, not each open browser.
- Persist activity events for pipeline runs, deployments, app/container lifecycle actions, configuration changes, resource deletion, and host actions. Record actor, resource, action, correlation/run ID, timestamps, result, and sanitized error summary.
- Resource activity pages filter the same event store. Long operations have durable IDs; UI polls their state and can reconnect after reload.
- Protect platform containers, volumes, and networks from self-destruction through general resource controls. Continue using existing administrator authentication; this design does not introduce tenants or roles.

## Implementation boundaries and compatibility

- Work within current Next.js, FastAPI, Docker, SQLite, and Traefik. Use additive/idempotent database migrations, preserve existing IDs and data, and keep compatibility with deployed source types.
- Introduce focused modules for the portal shell/navigation, resource pages, pipeline definitions/stages/worker, metrics sampling, activity recording, and the narrow host adapter. Split the oversized resource component as needed to support this work.
- Authentication remains required for every management API and terminal connection. Never write credentials, environment values, raw request bodies, or access tokens to activity records. Runtime logs remain private administrator data.
- A new portal does not itself provide custom-domain DNS, TLS certificates, managed identity, physical capacity expansion, hypervisor VM provisioning, cloud billing, or the ability to power on an offline host. Existing application endpoint reachability constraints remain visible and documented.
- No live host reboot, service restart, firewall mutation, production deployment, or resource destruction is part of local implementation verification.

## Delivery sequence and acceptance

Implement as one coherent project in this order: shared operation/activity and metrics foundations; portal shell/navigation/search; application resource pages; pipeline definitions/run details/test stage/triggers; server resource and capability-aware controls; integration and visual verification. All three areas must be functional before declaring the agreed implementation complete.

Acceptance includes existing deployment regressions, authenticated API tests, database migration/recovery checks, pipeline failure/cancellation cleanup and secret masking, fake-host adapter tests that cannot affect the real host, URL/back/reload navigation checks, keyboard/small-screen checks, live log polling/reconnect cleanup, production frontend build, and screenshots of Home, App Overview, Pipeline Run, and Server Overview. Use controlled fixtures for destructive host scenarios. Run real read-only Docker/Ubuntu checks in an appropriate test environment where available and report any unverified production behavior.

## Decisions left to the builder

Choose route/component organization, CSS implementation, indexes, bounded sampling interval, pagination, exact command adapter implementation, and test fixtures. Keep the scope above; surface any change that would require new privileges or alter the deployment/network model.

## References

- Azure portal anatomy, global/service menus and command bars: https://learn.microsoft.com/en-us/azure/azure-portal/azure-portal-overview
- App Service source and deployment configuration: https://learn.microsoft.com/en-us/azure/app-service/deploy-continuous-deployment
- App Service runtime log stream and deployment log distinction: https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs
- Pipelines, stages, jobs, steps, runs and artifacts: https://learn.microsoft.com/en-us/azure/devops/pipelines/get-started/key-pipelines-concepts?view=azure-devops
- Pipeline stage/task log review: https://learn.microsoft.com/en-us/azure/devops/pipelines/troubleshooting/review-logs?view=azure-devops
- Azure VM power states (reference for clear state naming, not a claim that this host is a VM): https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing

## Implementation decision: domain handoff

Docker routing labels are immutable. To keep the verified candidate itself alive through cutover, Compose now enables Traefik's watched file provider with a shared `arfeen_routes` volume. The backend verifies the candidate on its exact proxy-network address, atomically publishes a YAML route, and checks the candidate header and HTTP status through Traefik before retiring the previous instance. This adds no host capability or network and keeps the existing proxy/internal network topology. Published-port apps retain stop/start replacement because a port cannot be bound by both containers.
