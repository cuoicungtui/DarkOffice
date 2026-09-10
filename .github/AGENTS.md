# GitHub Automation DOX

## Purpose

- Own repository automation that runs on GitHub, including workflows and release-planning scripts.
- Keep CI, Docker publishing, stale issue handling, and release-note generation aligned with repository release rules.

## Ownership

- `workflows/` contains GitHub Actions workflow definitions.
- `scripts/` contains Python helpers called by workflows.
- This file owns release automation rules; user-facing release documentation belongs under `docs/`.

## Local Contracts

- DarkOffice deployment automation uses the pull-mount model in
  `workflows/ci.yml`, `workflows/deploy-server.yml`, and `workflows/rollback.yml`:
  pull `agent0ai/agent-zero:latest`, verify this repository source mounted at
  `/a0`, and deploy the tested source over SSH to Docker Compose on the server.
- DarkOffice server deploys keep source releases under `/opt/darkoffice/releases/`,
  switch `/opt/darkoffice/current`, and preserve runtime data under
  `/opt/darkoffice/usr`.
- DarkOffice deploy and rollback workflows default to no WebUI login; write
  `AUTH_LOGIN` and `AUTH_PASSWORD` only when their explicit workflow auth input
  is enabled.
- Docker publishing lives in `workflows/docker-publish.yml` and delegates planning to `scripts/docker_release_plan.py`.
- `workflows/docker-publish.yml` is the upstream Agent Zero image-publishing path;
  do not adapt it for DarkOffice server deploy unless the project intentionally
  switches from pull-mount deploy to publishing its own image.
- Releasable tags are `vX.Y` tags at or above `v1.0`, matching the workflow environment.
- On `main`, the newest eligible tag publishes both the version tag and `latest`, then creates or updates its GitHub release after the image push succeeds; other allowed branches publish only their branch tag.
- Manual dispatch without a tag backfills missing Docker Hub tags. Manual dispatch with a tag rebuilds that target and refreshes `latest` and the GitHub release only when it remains the newest eligible tag on `main`.
- Release-note generation reads `scripts/openrouter_release_notes_system_prompt.md` from the repository root and requires OpenRouter credentials from workflow environment variables.
- Release notes compare against the previous published GitHub release tag and fall back to `No release notes.` when no meaningful summary is generated.
- Keep workflow secrets in GitHub Actions secrets or environment variables. Do not commit credentials, tokens, or generated release bodies containing private data.
- Plane deployment and its one-time data cutover are independent from the
  DarkOffice release workflow. The workflow may pass Plane integration values
  only from server secrets; migration backups are never uploaded to git.
- `workflows/deploy-plane-server.yml` deploys the checked-in Plane image
  manifest manually and requires a public Plane URL as an explicit input.
- The Plane deploy workflow supports both Docker Compose v2 and legacy
  `docker-compose` v1. For the legacy path, it removes containers before `up`
  to avoid the Docker Engine `ContainerConfig` recreate defect; named volumes
  must never be passed to `down -v`.
- The DarkOffice deploy workflow also removes legacy Compose containers by the
  `com.docker.compose.service=darkoffice` label. Container names are not a
  reliable migration key on existing server releases.
- Workflow scripts must fail loudly with actionable messages when required environment variables or git refs are missing.

## Work Guidance

- Prefer deterministic, testable Python for workflow planning logic instead of complex inline shell in YAML.
- Preserve manual dispatch behavior when changing Docker publishing.
- Keep branch, tag, and release behavior synchronized between workflow YAML, release scripts, tests, and user-facing release documentation.

## Verification

- Run `docker compose -f docker/run/docker-compose.darkoffice.yml config` after
  changing DarkOffice pull-mount deploy configuration.
- Run the focused runtime-image test command from `workflows/ci.yml` after changing
  DarkOffice CI, deploy, rollback, or compose behavior.
- Run `pytest tests/test_docker_release_plan.py` after changing Docker publish planning or release workflow behavior.
- Run targeted tests for any changed script that already has coverage.

## Child DOX Index

No child DOX files.
