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

From the Mac, create and copy a new archive using the commands in step 4. The archive excludes `.env` and `storage/`, so it will not replace the server secrets or managed files. On Ubuntu:

```bash
cd "$HOME/arfeen-cloud"
tar -xzf /tmp/arfeen-cloud.tar.gz -C "$HOME/arfeen-cloud"
sudo docker compose up -d --build
sudo docker compose ps
```

The named `arfeen_data` Docker volume and the server’s `storage/` directory are preserved when the stack is rebuilt or stopped with `docker compose down`.

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
- Public GitHub HTTPS and ZIP deployments, framework detection, image builds, environment variables, redeploy, and rollback.
- PostgreSQL, MySQL, and Redis containers with persistent Docker volumes on a private network.
- File uploads, downloads, folder creation, rename, and delete in the project’s `storage/` directory.

## Important security and MVP notes

- The backend has Docker socket access and a host filesystem mount for the requested root terminal. The dashboard can perform host-level administration. Keep access restricted to your trusted Tailscale devices.
- Arfeen stores its SQLite metadata and deployment environment values in a Docker volume. Database passwords are shown once when created. Back up the `.env` file, the `arfeen_data` Docker volume, and `storage/`.
- Git deployment currently supports public GitHub HTTPS URLs. Private GitHub authentication, webhook builds, automatic public-domain certificate issuance, scheduled backups, and plugin installation are not implemented.
- The current guide provides private remote access through Tailscale. Making the dashboard publicly accessible to any browser through a custom domain requires a separate HTTPS and firewall configuration; do not expose the current HTTP port directly.

## References

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Install Tailscale on Linux](https://tailscale.com/docs/install/linux)
- [Install Tailscale on macOS](https://tailscale.com/docs/install/mac)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Enable HTTPS certificates for a tailnet](https://tailscale.com/docs/how-to/set-up-https-certificates)
