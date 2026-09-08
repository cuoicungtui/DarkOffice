# DarkOffice Deployment

DarkOffice currently uses a pull-mount deployment model. The runtime container is
the existing `agent0ai/agent-zero:latest` image, while this repository is mounted
into the container at `/a0`. This keeps the first deployment path fast and avoids
building or publishing a DarkOffice image until Docker runtime changes require it.

## Local Docker Dev

Pull the runtime image and start the local container:

```bash
docker pull agent0ai/agent-zero:latest
docker compose -f docker/run/docker-compose.darkoffice.yml up -d
```

The default local URL is:

```text
http://127.0.0.1:5080
```

Check health and login:

```bash
curl -fsS http://127.0.0.1:5080/api/health
curl -fsS http://127.0.0.1:5080/login >/dev/null
```

Stop the local container:

```bash
docker compose -f docker/run/docker-compose.darkoffice.yml down
```

Local defaults can be overridden with environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DARKOFFICE_BASE_IMAGE` | `agent0ai/agent-zero:latest` | Runtime image to pull. |
| `DARKOFFICE_CONTAINER_NAME` | `darkoffice` | Container name. |
| `DARKOFFICE_SOURCE_DIR` | `../..` | Host source mounted at `/a0`. |
| `DARKOFFICE_DATA_DIR` | `../../usr` | Persistent data mounted at `/a0/usr`. |
| `DARKOFFICE_HTTP_PORT` | `5080` | Host HTTP port mapped to container port `80`. |
| `AUTH_LOGIN` | empty | Optional WebUI username. Empty disables login. |
| `AUTH_PASSWORD` | empty | Optional WebUI password. Empty disables login. |

## Gitflow

- `main`: production-stable source.
- `develop`: integration branch for active work.
- `feature/<short-name>`: feature work branched from `develop`.
- `release/vX.Y.Z`: release hardening branched from `develop`.
- `hotfix/<short-name>`: urgent production fixes branched from `main` and merged
  back to both `main` and `develop`.
- `vX.Y.Z`: annotated production release tags used for rollback.

Do not rewrite shared history or force-push protected branches.

## GitHub Actions

- `DarkOffice CI` runs on pull requests into `develop`, pushes to `develop`,
  `release/*`, and `main`, and manual dispatch.
- CI pulls `agent0ai/agent-zero:latest`, validates
  `docker/run/docker-compose.darkoffice.yml`, runs focused pytest checks inside
  the runtime image, compiles core Python sources, and smoke-tests the mounted
  WebUI.
- `Deploy DarkOffice Server` is manual. It checks out the selected ref, runs the
  same focused checks, uploads source to the server, switches the active release,
  restarts Docker Compose, and checks `/api/health`.
- `Rollback DarkOffice Server` is manual. It accepts a git tag, commit, or branch
  and redeploys that exact ref.

## GitHub Secrets

These SSH secrets are required for server deploy. Auth secrets are optional for
the current no-login rollout:

| Secret | Purpose |
| --- | --- |
| `SERVER_HOST` | Server IP or host. |
| `SERVER_PORT` | App HTTP port exposed on the server. Use `5080` for the current no-domain deploy. |
| `SERVER_USER` | SSH user used by the workflow. |
| `SERVER_SSH_KEY` | Private SSH key for that user. |
| `SERVER_SSH_PORT` | Optional SSH port. Defaults to `22` when not set. |
| `AUTH_LOGIN` | Optional WebUI username. Used only when `enable_auth` is true. |
| `AUTH_PASSWORD` | Optional WebUI password. Used only when `enable_auth` is true. |

No `GHCR_USER` or `GHCR_TOKEN` secret is required for this pull-mount phase.

For the first server deployment, set `SERVER_PORT` to `5080` and leave
`enable_auth` unchecked. The workflow uses SSH port `22` unless the optional
`SERVER_SSH_PORT` secret exists. It writes empty `AUTH_LOGIN` and `AUTH_PASSWORD`
values so the WebUI does not require login. Enable auth later only after the
server URL, port, and deploy flow are verified.

`SERVER_SSH_KEY` must be a private key whose public key is present in
`~/.ssh/authorized_keys` for `SERVER_USER` on `SERVER_HOST`. The deploy workflow
uses non-interactive public-key SSH only; it will not reuse WebUI auth secrets as
an SSH password.

## Server Runtime Layout

The workflows manage this layout:

```text
/opt/darkoffice/
  .env
  docker-compose.yml
  current -> /opt/darkoffice/releases/<sha>
  releases/
    <sha>/
  usr/
```

`current` points at the release currently mounted into `/a0`. `usr` is persistent
runtime data and is not replaced during deploy or rollback.

The app is exposed at:

```text
http://<SERVER_HOST>:5080
```

The server `.env` is generated from GitHub Secrets by the workflow and should not
be committed to source.

## Deploy

Use GitHub Actions, select `Deploy DarkOffice Server`, and provide the git ref to
deploy. The default ref is `main`. Leave `enable_auth` unchecked for the current
no-login server deployment.

The deploy workflow performs these steps:

1. Check out the requested ref.
2. Pull `agent0ai/agent-zero:latest`.
3. Validate compose and run focused tests.
4. Upload the source archive to `/opt/darkoffice/releases/<sha>`.
5. Write `/opt/darkoffice/.env` from workflow inputs and GitHub Secrets, with
   auth disabled unless `enable_auth` is checked. `SERVER_PORT` controls the
   exposed app port; SSH uses `SERVER_SSH_PORT` or port `22`.
6. Switch `/opt/darkoffice/current`.
7. Run Docker Compose and smoke-test `http://127.0.0.1:5080/api/health` on the
   server.

## Rollback

Create annotated production tags before deploy:

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

To roll back, run the `Rollback DarkOffice Server` workflow and enter the tag or
commit to restore, for example:

```text
v0.1.0
```

Rollback deploys that exact source revision and preserves `/opt/darkoffice/usr`.
