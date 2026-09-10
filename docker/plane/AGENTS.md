# Plane Deployment DOX

## Purpose

Own the checked-in, image-pinned Plane v1.4.2 production manifest used by the independent Plane deploy workflow.

## Ownership

`docker-compose.plane.yml` owns Plane services, persistent named volumes, and the shared `plane-integration` network. `.github/workflows/deploy-plane-server.yml` writes its protected `.env` file on the server.

## Local Contracts

- Never commit `plane.env`, database dumps, uploads, or credentials.
- Image references must be digests verified from the existing v1.4.2 local deployment.
- `api` uses alias `plane-api`; `worker` reaches DarkOffice over the shared network to deliver webhooks.
- Keep volumes outside releases and keep database restore separate from application deployment.

## Work Guidance

Update all related digests together when upgrading Plane. Preserve `WEBHOOK_ALLOWED_HOSTS=darkoffice` unless the DarkOffice container alias changes.

## Verification

Run `docker compose -f docker/plane/docker-compose.plane.yml config` with placeholder environment values and run the manual Plane deploy workflow against a non-production restore before cutover.

## Child DOX Index

None.
