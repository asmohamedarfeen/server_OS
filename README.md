# Arfeen Cloud

Arfeen Cloud is a self-hosted control panel for one Ubuntu server. This guide takes you from your Mac to a running dashboard, then makes it reachable worldwide over a private Tailscale connection.

> **Recommended access model:** Tailscale private access. The dashboard is reachable only from devices signed in to your tailnet. The guide does not open the dashboard to the public internet or require router port forwarding.

## What you need

- An Ubuntu Server with a stable local network connection.
- SSH access to that server from your Mac, at least for the initial setup.
- An account you can use to sign in to Tailscale on the Ubuntu server and your Mac.
- A Mac copy of this project at `~/Desktop/project/server_v2` (adjust the path below if yours is different).

The dashboard port will be bound to `127.0.0.1` on Ubuntu. Tailscale Serve will provide the private HTTPS address. You can change `CLOUD_BIND` in `.env` if you also want direct local-network access.

## 1. Connect from your Mac to Ubuntu

Open Terminal on your Mac and connect using the SSH username and LAN address for your Ubuntu server:

```bash
ssh <ubuntu-username>@<ubuntu-lan-ip>
```

Enter the SSH password when prompted, if your server uses password authentication. Do not put the password in the command. Once connected, check the server:

```bash
lsb_release -a
sudo systemctl is-active docker
sudo docker compose version
```

If Docker and the Compose plugin are already installed, continue to step 2. Otherwise, install Docker Engine from Docker’s official Ubuntu package repository.

## 2. Install Docker Engine if it is missing

Run these commands in the Ubuntu SSH session. If Docker is already installed, skip this section. If the server has an existing Docker installation, do not remove packages until you understand how its containers and data are managed.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Add Docker’s package repository:

```bash
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

Install and start Docker:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run hello-world
sudo docker compose version
```

Arfeen’s backend needs Docker Engine access to manage the host. The install steps below use `sudo`; avoid adding an account to the `docker` group unless you intend to grant it root-equivalent control. See [Docker’s Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/) for details and supported releases.

## 3. Install Tailscale on Ubuntu

Keep the SSH session open. In the Ubuntu session, install and start Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

The command prints a sign-in URL. Open it on your Mac and authorize the Ubuntu server in your Tailscale account. Then check that it joined your tailnet:

```bash
tailscale status
tailscale ip -4
```

Write down the server’s Tailscale IP address (usually starts with `100.`).

On your Mac, install the [Tailscale macOS app](https://tailscale.com/download/mac), sign in to the same account, and confirm the server appears as connected. From now on, you can SSH to the server over Tailscale, even when your Mac is away from home:

```bash
ssh <ubuntu-username>@<server-tailscale-ip>
```

Tailscale clients are also available for phones and tablets. Install the client and sign in to the same tailnet before opening Arfeen Cloud there.

## 4. Copy the project from your Mac to Ubuntu

On your Mac, open a **second Terminal window**. Create an archive from the project directory. This command deliberately excludes `.env`, Git data, build output, stored files, and the local server credentials document.

```bash
cd "$HOME/Desktop/project/server_v2"
tar -czf "$HOME/arfeen-cloud.tar.gz" \
  --exclude='./.git' \
  --exclude='./.env' \
  --exclude='./server details.md' \
  --exclude='./storage' \
  --exclude='./node_modules' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/.next' \
  --exclude='./backend/.venv' \
  .
```

Copy the archive to Ubuntu over Tailscale:

```bash
scp "$HOME/arfeen-cloud.tar.gz" <ubuntu-username>@<server-tailscale-ip>:/tmp/
```

Back in the Ubuntu SSH session, unpack the project:

```bash
mkdir -p "$HOME/arfeen-cloud"
tar -xzf /tmp/arfeen-cloud.tar.gz -C "$HOME/arfeen-cloud"
mkdir -p "$HOME/arfeen-cloud/storage"
cd "$HOME/arfeen-cloud"
```

## 5. Install and start Arfeen Cloud

Run the installer as root so it can access Docker. It creates `.env` with random secrets, binds the dashboard to localhost, builds the Docker images, and starts the services:

```bash
sudo ./scripts/install.sh
```

The installer prints a **one-time administrator setup key**. Copy it into your password manager or another private place. You will need it for the first login. The key is also stored in the server’s `.env` file, which the installer creates with restricted file permissions.

Check that the services started:

```bash
sudo docker compose ps
```

The installer may take several minutes the first time while Docker downloads base images and builds the dashboard and API.

## 6. Enable private HTTPS access

Tailscale Serve proxies the local dashboard over HTTPS to your tailnet. In the Tailscale admin console, open **DNS** and enable **MagicDNS** and **HTTPS Certificates** if they are not already enabled. Tailscale HTTPS certificates publish the server’s machine name and tailnet DNS name in the public Certificate Transparency log, even though access to the dashboard remains restricted to your tailnet. Avoid using a sensitive machine name.

In the Ubuntu SSH session, start the HTTPS proxy:

```bash
sudo tailscale serve --bg http://127.0.0.1:8080
sudo tailscale serve status
```

Use the `https://…ts.net` URL shown by `tailscale serve status`. If you changed `CLOUD_PORT` in `.env`, replace `8080` in the Serve command with that port.

Now enable secure cookies for the HTTPS dashboard:

```bash
cd "$HOME/arfeen-cloud"
sudo nano .env
```

Change this line:

```dotenv
COOKIE_SECURE=false
```

to:

```dotenv
COOKIE_SECURE=true
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano), then apply the setting:

```bash
sudo docker compose up -d
```

No router port forwarding is needed. **Do not use Tailscale Funnel** for this private setup; Funnel makes a service publicly reachable.

## 7. Create your administrator account

On your Mac, open the `https://…ts.net` address from the previous step. Create the administrator account using:

1. The one-time setup key printed by the installer.
2. A username of at least 3 characters.
3. A unique password of at least 12 characters.

After setup, Arfeen Cloud opens the dashboard. The browser terminal provides root-level access to the Ubuntu host. Treat your Tailscale account, setup key, and administrator password as powerful server credentials. Enable multi-factor authentication on the identity provider used by Tailscale, and keep the tailnet limited to devices and people you trust.

## 8. Verify remote access

1. Disconnect your Mac from the home Wi-Fi and use a different network, such as a phone hotspot.
2. Confirm Tailscale is connected on the Mac.
3. Open the same `https://…ts.net` address.
4. Sign in to Arfeen Cloud and confirm the dashboard and terminal load.

This works from anywhere your device can connect to Tailscale. A device without Tailscale access cannot reach the dashboard.

## Updating Arfeen Cloud

### Automatic production deployments

Production follows the GitHub repository's `main` branch. Every push to `main` queues the **Deploy production** workflow in `.github/workflows/deploy-production.yml`. A repository-scoped self-hosted runner on the Ubuntu server checks out the exact triggering commit and runs `scripts/deploy-production.sh`. Pushes to other branches do not deploy production.

You can also redeploy `main` without creating a commit:

1. Open the repository on GitHub.
2. Select **Actions**, then **Deploy production**.
3. Select **Run workflow**, leave the branch set to `main`, and confirm.

The production runner is a security boundary. A workflow revision merged into `main` can execute commands on the server with the `md` account's Docker and passwordless-sudo access. Protect GitHub accounts with two-factor authentication, review workflow changes before they reach `main`, and never route pull-request or fork workflows to the `arfeen-production` runner.

The deployment script serializes updates, snapshots the previous application source, synchronizes the new commit, rebuilds the Compose stack, and checks the local dashboard. It excludes `.env`, `storage/`, Git data, local dependency/build directories, and Docker named volumes. It never runs `docker compose down` or a Docker prune command. If source synchronization, build, startup, or health verification fails after the snapshot, the script restores the previous source and attempts to restart its Compose stack before the workflow reports failure.

Check runner and application status on Ubuntu with:

```bash
systemctl status 'actions.runner.*'
sudo journalctl -u actions.runner.asmohamedarfeen-server_OS.mastercontrol-production.service --since '30 minutes ago'
cd /home/md/arfeen-cloud
sudo docker compose ps
sudo docker compose logs --tail=100 traefik backend frontend
curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null
```

When a deployment fails, inspect its GitHub Actions log first, then check the runner service, Compose status, and recent service logs. Confirm the current dashboard still responds before rerunning the workflow. Do not replace the server's `.env` or `storage/` directory while recovering; automatic source rollback deliberately leaves both untouched.

### Manual archive update

From the Mac, create and copy a new archive using the commands in step 4. The archive excludes `.env` and `storage/`, so it will not replace the server secrets or managed files. On Ubuntu:

```bash
cd "$HOME/arfeen-cloud"
tar -xzf /tmp/arfeen-cloud.tar.gz -C "$HOME/arfeen-cloud"
sudo ./scripts/install.sh
sudo docker compose ps
```

The installer preserves existing `.env` secrets and adds `GITHUB_CREDENTIALS_KEY` if it is missing. The named `arfeen_data` Docker volume and the server’s `storage/` directory are preserved when the stack is rebuilt or stopped with `docker compose down`.

## Useful server commands

Run these from the Ubuntu project directory:

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 traefik backend frontend
sudo docker compose up -d --build
sudo docker compose down
sudo tailscale serve status
```

If the dashboard is unavailable, check `sudo docker compose ps` and the service logs first. Confirm Tailscale is connected with `tailscale status` and the Serve proxy is active with `sudo tailscale serve status`.

If Traefik logs report `client version 1.24 is too old` or that Docker requires API `1.44`, update the Traefik image and recreate only its container:

```bash
sudo sed -i 's/traefik:v3.3/traefik:v3.7.16/' docker-compose.yml
sudo docker compose pull traefik
sudo docker compose up -d --force-recreate traefik
sudo docker compose logs --tail=40 traefik
```

## Local-network-only option

If you want devices on your home LAN to open the dashboard directly over HTTP, edit `.env` and set:

```dotenv
CLOUD_BIND=0.0.0.0
```

Then run `sudo docker compose up -d` and open `http://<ubuntu-lan-ip>:8080` from that LAN. Keep remote access on Tailscale; do not forward port `8080` from your router. Direct LAN access uses HTTP, so the private HTTPS Tailscale URL is the preferred address.

## What is included in this MVP

- Single administrator setup and sign-in with an Argon2 password hash and HTTP-only session cookie.
- Host CPU, memory, disk, network, process count, uptime, and temperature metrics.
- Docker container lifecycle controls, logs, image and volume views, networks, and browser terminal.
- Public and private GitHub repository and ZIP deployments, branch selection, framework detection, image builds, environment variables, redeploy, and rollback.
- PostgreSQL, MySQL, and Redis containers with persistent Docker volumes on a private network.
- File uploads, downloads, folder creation, rename, and delete in the project’s `storage/` directory.

## Important security and MVP notes

- The backend has Docker socket access and a host filesystem mount for the requested root terminal. The dashboard can perform host-level administration. Keep access restricted to your trusted Tailscale devices.
- Arfeen stores its SQLite metadata, encrypted GitHub token, and deployment environment values in a Docker volume. The key used to encrypt the GitHub token is in `.env`; back up `.env`, the `arfeen_data` Docker volume, and `storage/` together. Database passwords are shown once when created.
- GitHub builds can start manually or through an explicitly enabled pipeline branch-polling trigger. Public GitHub webhooks, automatic public-domain certificate issuance, scheduled backups, and plugin installation are not implemented.
- The current guide provides private remote access through Tailscale. Making the dashboard publicly accessible to any browser through a custom domain requires a separate HTTPS and firewall configuration; do not expose the current HTTP port directly.

## Live deployment output

Clicking **Build and deploy** creates a background job and opens the deployment workspace immediately. The workspace shows source download/unpacking, framework detection, Docker build output, container startup, and verification. Logs update about every 1.5 seconds and include timestamps and failure details. **Follow logs**, **Copy logs**, and **Download logs** are available in the console.

Use **Continue in background** to close the workspace without stopping the build. Reopen it from **Build activity** in App Services or an application's Deployment Center; those lists refresh automatically. GitHub, ZIP, and redeploy flows all use the same worker. A single build runs at a time; additional deployments queue, and duplicate submissions for the same application point to its existing job.

Logs and job results persist in the existing SQLite data volume. Tokens and environment values are redacted before log storage. Each job keeps up to 8 MiB of output; the console displays the latest 2,000 entries, while Download provides the full retained output. A backend restart marks unfinished jobs as **interrupted** rather than silently resuming a potentially partial deployment. Check the application state before retrying an interrupted job.

Open an application from **App Services** to see its **Application URL** with copy and open controls. A configured domain uses `http://<domain>`; otherwise the URL uses the dashboard hostname and the application's published host port, for example `http://<server-tailscale-ip>:53834`. The app's port must be reachable from your device; dashboard HTTPS through Tailscale Serve does not automatically proxy these application ports or enable HTTPS on them.

Choose **Log stream** or **Live logs** in the application workspace to view its current container's timestamped stdout and stderr. The viewer refreshes every two seconds while open and shows the latest 2,000 lines. **Pause updates**, **Follow logs**, **Copy logs**, and **Download logs** let you inspect and save the displayed output. Scrolling up turns off following so updates do not pull you away from earlier output. The viewer follows replacement containers after redeploys, retains previous output during connection errors, and stops polling when closed. These runtime logs are separate from saved deployment build output; older output depends on Docker's log retention, and files written inside the container are not included.

For backend regression tests, install `backend/requirements-dev.txt` into a Python 3.11+ virtual environment and run `python -m unittest discover -s tests -v`. Optional frontend browser checks are in `tests/ui_portal.py`, `tests/ui_deployment_console.py`, and `tests/ui_application_runtime.py`; they use Playwright, installed Chrome, a local frontend on port 3100, and controlled API fixtures.

## Single-server management portal

The portal combines App Service, pipeline, and server-management workflows for the Ubuntu host already running Arfeen Cloud. Global search (Ctrl/Cmd+K), All resources, resource detail menus, command bars, notifications, and browser back/reload work across the portal. Existing container, database, storage, image, network, file, and terminal tools remain available. Resource links open the selected resource.

- **App Services:** Create from GitHub or ZIP; browse/copy the endpoint; start, stop, restart, redeploy, and roll back. Deployment Center shows source configuration and build history. Configuration hides environment values until deliberately revealed, saves with restart, and supports an optional internal HTTP readiness path. Running without a Docker or configured HTTP health check is explicitly distinguished from readiness verification.
- **Pipelines:** Link an existing app, configure an optional test command/timeout, then run manually or upload a ZIP. Source, Configure, Build, Test, Deploy, and Verify record separate statuses and timings. Tests run in temporary image containers without host mounts, network access, extra capabilities, or the Docker socket. Failed tests leave the current app in place. Run details expose the actual source commit, image artifact, selected-stage output, and complete retained log download. Cancellation is cooperative at safe boundaries; it is unavailable after replacement begins.
- **Automatic GitHub runs:** Enable branch polling explicitly in pipeline settings. The local worker checks the branch every 60 seconds, uses the saved connection for private repositories, persists the actual observed/deployed commit, and suppresses duplicate active deployments. Enabling polling queues a first run when no prior commit has been observed. ZIP sources remain manual.
- **Server:** Inspect actual mounted-host identity, OS/kernel, processes, disks, interfaces/listening ports, Docker state, and allowlisted systemd services. Metrics history is collected by one backend sampler every 60 seconds, retained for 24 hours, and shared across browsers. Null measurements and missing permissions are shown as unavailable rather than guessed from the backend container. Host inspection requires the existing Linux `/host`, `/proc`, and `/sys` mounts; unsupported environments disable those controls.
- **Host operations:** Reboot and restart of allowlisted services require the exact managed hostname and acknowledgement that apps/dashboard access may be interrupted. A separate action worker records durable operation state. Reboot success requires an observed changed host boot ID; a disconnected or unknown outcome is never called successful merely because a request was accepted. The dashboard cannot power on an offline server. No shutdown control is exposed.
- **Activity log:** Persistent, bounded operation history includes actor, resource, status, time, and correlation IDs. It excludes request bodies, secret values, and raw exception text. Platform containers, volumes, and images remain protected from self-destruction.

Domain-routed applications use [Traefik's watched file provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/others/file/) for an atomic route handoff: a replacement container is verified while the old instance remains available, then the route switches to that same verified container before retiring the old instance. The `arfeen_routes` named volume is shared read-only with Traefik and writable by the backend; routing files are regenerated from the application database on backend startup. Include the Compose changes when updating the server. Published-port apps require a brief stop/start to release their port, and failed replacement verification restores the prior container.

The portal manages this one host and Docker workloads. It does not provision Azure VMs, resize physical hardware, manage cloud billing, issue TLS certificates, or change host firewall rules. Server mutations and production deployment must be verified in the intended Ubuntu environment; automated tests use fake host/Docker adapters and browser API fixtures.

## Deploying a private GitHub repository

1. In GitHub, create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new). Limit repository access to the repositories Arfeen Cloud should deploy. Grant **Contents: Read-only**; GitHub also requires **Metadata: Read-only** to list repositories and branches. If GitHub asks for organization approval, complete that approval before connecting.
2. Update Arfeen Cloud using the instructions in **Updating Arfeen Cloud**. The installer adds `GITHUB_CREDENTIALS_KEY` to an existing `.env` file when needed. Keep this key stable: changing or losing it makes the saved token unreadable.
3. Sign in to Arfeen Cloud, open **Settings → GitHub**, paste the token, and choose **Connect GitHub**. Arfeen validates the token before saving it encrypted in its database. The browser does not receive the saved token back.
4. Open **App Services → Create → GitHub → Connected repositories**. Select a repository and branch, enter the application name and any environment variables, then choose **Build and deploy**.
5. Use **Deploy** in the application command bar to deploy the latest commit from the same branch. For automatic runs, create a linked pipeline and explicitly enable GitHub branch polling.

To revoke access, disconnect GitHub in Settings and revoke the token in GitHub. Existing containers keep running; private repository redeploys need a connected token.

## References

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Install Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Install Tailscale on macOS](https://tailscale.com/docs/install/mac)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Enable HTTPS certificates for a tailnet](https://tailscale.com/docs/how-to/set-up-https-certificates)
- [GitHub fine-grained personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
