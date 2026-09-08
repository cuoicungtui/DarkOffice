---
name: darkoffice-gitflow
description: DarkOffice project workflow for Agent Zero fork verification, Gitflow, GitHub Actions, Docker deploy, and rollback. Use before changing branches, CI/CD, deployment, release tags, Docker image policy, or production-facing GitHub automation in DarkOffice.
triggers:
  - "DarkOffice gitflow"
  - "DarkOffice GitHub Actions"
  - "DarkOffice deploy"
  - "DarkOffice rollback"
  - "Agent Zero fork deploy"
---

# DarkOffice Gitflow

Use this skill for DarkOffice repository workflow, CI/CD, Docker deployment, release, and rollback work. The goal is to keep DarkOffice easy to rebase from upstream Agent Zero while preventing unverified production deploys.

## Mandatory Repo Check

Before changing files, branches, tags, workflows, or deployment config:

Confirm the repository is the DarkOffice fork of Agent Zero:

```bash
git remote -v
git status --short --branch
```

## Scope Discipline

- Keep core Agent Zero logic changes separate from DarkOffice customization.
- UI branding changes must be isolated from CI/CD, Docker, or backend logic changes.
- Do not rewrite git history, force-push, delete branches, or push production changes unless the user explicitly approves the exact action.
- Do not hard-code secrets, server IPs, registry tokens, SSH keys, passwords, or private runtime paths into source.
- Respect the applicable `AGENTS.md` chain before edits.

## Docker Operating Model

DarkOffice starts from Agent Zero's Docker model. Prefer this order:

1. Pull the existing full upstream runtime image to verify Docker, Compose, auth, ports, and host access:

```bash
docker pull agent0ai/agent-zero:latest
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

2. Run DarkOffice with pull-mount by mounting the checked-out source at `/a0` and persistent runtime data at `/a0/usr`:

```bash
docker compose -f docker/run/docker-compose.darkoffice.yml up -d
```

3. Use an existing running container for smoke checks when one is already present and owned by the current work. Discover the port from Docker, then check:

```bash
curl -fsS http://127.0.0.1:<port>/api/health
curl -fsS http://127.0.0.1:<port>/login | grep -i "<title>"
```

4. Build a DarkOffice runtime image only when Dockerfiles, runtime filesystem, or image publication policy changed. Use the prebuilt base image unless `docker/base/` changed:

```bash
docker build -f DockerfileLocal -t darkoffice-local:smoke --build-arg CACHE_DATE="$(date -u +%Y-%m-%d:%H:%M:%S)" .
```

5. Do not rebuild or publish a DarkOffice base image unless files under `docker/base/` changed and the user approved that broader work.

Observed local lesson: even with `agent0ai/agent-zero-base:latest`, building the runtime image may download many large Python wheels and consume significant disk/time. CI should free disk space and use cache-aware Docker Buildx settings.

## Branch Model

DarkOffice uses Gitflow:

- `main`: production stable only.
- `develop`: integration and development branch.
- `feature/<short-name>`: branch from `develop`; merge back by PR.
- `release/vX.Y.Z`: branch from `develop`; staging build, smoke test, release hardening.
- `hotfix/<short-name>`: branch from `main`; merge back to both `main` and `develop`.

Recommended first setup:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b develop
git push -u origin develop
```

Use protected branches for `main` and `develop`: require PRs, passing checks, and no force-pushes.

## Versioning And Rollback

- Tag every production release with an annotated semver tag, for example `v0.1.0`.
- In the current pull-mount deploy model, the git tag or commit SHA is the release source of truth.
- Server deploy stores releases under `/opt/darkoffice/releases/<sha>`, switches `/opt/darkoffice/current`, and keeps `/opt/darkoffice/usr` persistent.
- Rollback should redeploy the requested git ref or switch to an existing release directory for that ref without rewriting source history:

```bash
git fetch --tags origin
git checkout v0.1.0
docker compose -f docker/run/docker-compose.darkoffice.yml up -d
```

If DarkOffice later publishes its own image, image tags must include both the git tag and immutable commit SHA; `latest` must never be the only rollback target.

## GitHub Actions Policy

Design workflows around gates:

- PR into `develop`: pull the runtime image, validate compose, run focused pytest/static checks, and smoke-test the mounted repository.
- Push to `develop`, `release/*`, or `main`: run the same CI gate before any server action.
- Manual server deploy: check out the selected git ref, run checks, upload source to `/opt/darkoffice/releases/<sha>`, switch `/opt/darkoffice/current`, and restart Docker Compose over SSH.
- Manual rollback: accept a git tag, commit, or branch and redeploy without modifying source history.

Do not require `GHCR_USER` or `GHCR_TOKEN` while DarkOffice uses pull-mount deploy from `agent0ai/agent-zero:latest`.

## Deployment Secrets

Expected GitHub Secrets for SSH deploy:

- `SERVER_HOST`
- `SERVER_PORT`
- `SERVER_USER`
- `SERVER_SSH_KEY`
- `AUTH_LOGIN`
- `AUTH_PASSWORD`

`AUTH_LOGIN` and `AUTH_PASSWORD` are optional during the first server rollout. Deploy and rollback workflows must default to no WebUI login and use those secrets only when an explicit auth input is enabled.

Do not add registry secrets for the current pull-mount model. If DarkOffice later switches to publishing its own image, document the registry policy and add the required secrets in the same change.

Server deploy should create or update runtime `.env` on the server from secrets, not from committed files.

## Required Documentation

When changing deploy behavior, update `docs/deployment.md` with:

- Local Docker smoke path.
- Branch and release flow.
- GitHub Actions behavior.
- Required secrets and variables.
- Server Docker Compose layout.
- Rollback command examples by git tag or commit.

## Closeout Checklist

Report:

- Repo verification result.
- Files changed.
- Docker/runtime checks performed and their discovered port/image/tag.
- Git branch/tag changes performed or intentionally not performed.
- CI/CD and deployment verification run.
- Any skipped checks and the reason.
