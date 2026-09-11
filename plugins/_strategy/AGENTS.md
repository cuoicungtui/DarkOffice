# Strategy Plugin DOX

## Purpose

Own DarkOffice's strategy model, Plane projections, durable synchronisation queues, and the strategy/project-work UI surface.

## Ownership

- `helpers/repository.py`: ports, SQLite adapter, schema, transactions, audit log.
- `helpers/services.py`: application services and sync orchestration.
- `helpers/plane.py`: Plane REST gateway only.
- `api/`, `tools/`, and `mcp_server.py`: delivery adapters; they do not contain domain SQL.
- `extensions/`: menu entries and the content surface without changing the core sidebar or chat layout.

## Local Contracts

- Callers use services and DTO dictionaries, never SQLite cursors.
- Secrets stay in environment variables; database records store references only.
- Strategy nodes never create Plane work automatically. The approved Work Chart execution skill creates Plane work through Plane MCP, while the strategy execution ledger records idempotent mappings after each external operation.
- Plane work status is read-only to DarkOffice; strategy title, description, and hierarchy remain owned here.

## Work Guidance

Keep schema upgrades in `repository.py` migration versions and preserve UUIDs for future export/import and PostgreSQL adapters. Keep webhook processing idempotent.

## Verification

Run `pytest tests/test_strategy.py tests/test_strategy_skill_bootstrap.py` and `python -m compileall plugins/_strategy api/strategy.py api/plane_webhook.py`.

## Child DOX Index

None.
