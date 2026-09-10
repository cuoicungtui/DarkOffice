# Plane Integration

DarkOffice owns strategy and outcomes. Plane remains the execution system. The two systems communicate through Plane REST, a durable SQLite inbox/outbox at `usr/strategy/strategy.sqlite3`, and Plane webhooks.

## Runtime configuration

Set these only in the server environment file, never in the repository:

```dotenv
PLANE_API_BASE_URL=http://plane-api:8000/api/v1
PLANE_PUBLIC_BASE_URL=https://plane.example.com
PLANE_WORKSPACE_SLUG=darkoffice
PLANE_API_KEY=...
PLANE_WEBHOOK_SECRET=...
PLANE_DARKOFFICE_NETWORK=plane-integration
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

## MCP

DarkOffice agents have the bundled `StrategyTool`. An external stdio server can be started with:

```sh
python -m plugins._strategy.mcp_server
```

It exposes dashboard, node creation, and metric check-ins using the same service and outbox as the UI. Keep the existing Plane MCP for detailed task operations.
