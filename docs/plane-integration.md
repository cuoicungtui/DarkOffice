# Plane Integration

DarkOffice owns strategy and outcomes. Plane remains the execution system. The two systems communicate through Plane REST, a durable SQLite webhook inbox, local Plane projections, an execution ledger at `usr/strategy/strategy.sqlite3`, and Plane webhooks.

## Runtime configuration

Set these only in the server environment file, never in the repository:

```dotenv
PLANE_API_BASE_URL=http://plane-api:8000/api/v1
PLANE_PUBLIC_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=darkoffice
PLANE_API_KEY=...
PLANE_WEBHOOK_SECRET=...
PLANE_DARKOFFICE_NETWORK=plane-integration
# Plane MCP receives the instance root, not the REST /api/v1 suffix.
PLANE_BASE_URL=http://plane-api:8000
```

Create the shared Docker network before bringing up DarkOffice:

```sh
docker network create plane-integration
```

Attach the Plane API and webhook-delivery service to that external network with aliases `plane-api` and `plane`. The DarkOffice service receives alias `darkoffice`. In Plane configure the webhook URL as `http://darkoffice/api/plane_webhook` and set Plane's `WEBHOOK_ALLOWED_HOSTS=darkoffice`. Register a secret for HMAC-SHA256 signatures.

The connector stores only `env:PLANE_API_KEY` and `env:PLANE_WEBHOOK_SECRET` references. It never saves a credential in SQLite.

## Cutover from the local Plane server

1. Stop new Plane writes and take a consistent PostgreSQL dump plus MinIO/uploads backup from the current v1.4.2 deployment.
2. Deploy the same pinned Plane v1.4.2 Compose release on the server, restore PostgreSQL and object storage, then verify project, work-item, relation, and attachment counts before allowing writes.
3. Point the public Plane URL and MCP configuration at the server, create a new PAT and webhook, then configure the DarkOffice variables above.
4. Run the `sync` operation from the project-work screen. Verify the recorded sync time, queue depth, and sample work-item state before turning off the local server.

Plane and DarkOffice can release independently. Back up the SQLite database with SQLite's backup API before a strategy schema migration. Restoring strategy data is a separate operation from rolling back application code.

## Delivery CLI and optional MCP compatibility

The default agent integration is the single `darkoffice-strategy-delivery` skill.
It calls the internal CLI and does not require Plane or Strategy MCP schemas in
the agent context:

```sh
sh /a0/plugins/_strategy/scripts/darkoffice delivery inspect
sh /a0/plugins/_strategy/scripts/darkoffice delivery prepare --spec-file delivery.json
sh /a0/plugins/_strategy/scripts/darkoffice delivery apply --confirmation-token TOKEN
```

`prepare` checks `ready_for_handoff` and returns an application sheet plus a
short-lived confirmation token. Only use `apply` after the user confirms that
exact sheet. `resume` continues the same durable execution run without creating
duplicate Plane work items. The CLI emits JSON with stable error codes and reads
credentials only from the injected runtime environment.

MCP remains a legacy, optional compatibility path. Do not register the template
below for the default agent profile.

DarkOffice uses two local stdio MCP servers. The committed template is
[`plugins/_strategy/mcp/strategy-mcp.json`](../plugins/_strategy/mcp/strategy-mcp.json).
It deliberately contains no credential: local MCP processes inherit container
environment variables and Plane reads `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`,
and `PLANE_BASE_URL`.

Install Plane MCP in the runtime image or container before enabling the config:

```sh
uvx plane-mcp-server stdio
```

Then configure the JSON through DarkOffice Settings -> MCP/A2A and restart the
MCP client. The wrapper at `plugins/_strategy/scripts/run-plane-mcp.sh` validates
the required variables before launching Plane MCP.

Install the user-owned agent skill once after deploying strategy source:

```sh
python -m plugins._strategy.bootstrap_skills
```

The installer writes `usr/skills/darkoffice-strategy-delivery` and records
source hashes. It retires only an unchanged managed copy of the old execution
skill; locally edited skills are preserved. A later upgrade refuses to overwrite
a locally edited delivery skill; use `--force` only when deliberately replacing it.

Objective creation never creates a representative Plane task. An accepted Work
Chart creates a run ledger and one Plane task for each chart item. The webhook
worker treats every event as a signal and re-reads the current Plane project
before updating local projections.
