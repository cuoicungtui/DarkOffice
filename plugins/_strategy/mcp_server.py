"""Stdio MCP server for DarkOffice strategy application services."""

from __future__ import annotations

import json

from .helpers import services


ACTOR = "strategy-mcp"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _confirmed(confirmed: bool) -> None:
    if not confirmed:
        raise ValueError("This structural change requires an explicit user confirmation.")


def get_strategy_dashboard(filters: dict | None = None) -> str:
    """Read strategy structure, measured outcomes, and Plane execution projections."""
    return _json(services.public_dashboard(filters))


def list_strategy_nodes(filters: dict | None = None) -> str:
    """List active strategy nodes without changing the strategy."""
    return _json(services.repository().list_nodes(filters))


def get_strategy_node(identifier: str) -> str:
    """Read one strategy node."""
    node = services.repository().get_node(identifier)
    if not node:
        raise KeyError("Strategy node not found")
    return _json(node)


def list_available_plane_projects() -> str:
    """List Plane projects already projected into DarkOffice."""
    return _json(services.list_available_plane_projects())


def get_execution_status(objective_id: str) -> str:
    """Return Objective progress from completed leaf work items in its Plane project."""
    return _json(services.execution_status(objective_id))


def get_sync_status() -> str:
    """Read sync queue diagnostics without exposing webhook or PAT secrets."""
    return _json(services.repository().sync_status())


def create_strategy_node(
    kind: str,
    title: str,
    parent_id: str | None = None,
    plane_project_ref_id: str | None = None,
    description: str = "",
    confirmed: bool = False,
) -> str:
    """Create a strategy node only after the user approved the displayed change sheet."""
    _confirmed(confirmed)
    return _json(services.create_node({"kind": kind, "title": title, "parent_id": parent_id, "plane_project_ref_id": plane_project_ref_id, "description": description}, ACTOR))


def update_strategy_node(identifier: str, changes: dict, confirmed: bool = False) -> str:
    """Update a strategy node only after explicit user confirmation."""
    _confirmed(confirmed)
    return _json(services.update_node(identifier, changes, ACTOR))


def archive_strategy_node(identifier: str, confirmed: bool = False) -> str:
    """Archive a strategy node only after explicit user confirmation."""
    _confirmed(confirmed)
    services.repository().archive_node(identifier, actor=ACTOR)
    return _json({"ok": True, "id": identifier})


def link_objective_to_plane_project(
    objective_id: str, plane_project_ref_id: str, version: int | None = None, confirmed: bool = False
) -> str:
    """Link one Objective to one Plane project after explicit user confirmation."""
    _confirmed(confirmed)
    return _json(services.link_objective_to_plane_project(objective_id, plane_project_ref_id, version, ACTOR))


def create_metric(metric: dict, confirmed: bool = False) -> str:
    """Create a measurable outcome definition after explicit user confirmation."""
    _confirmed(confirmed)
    return _json(services.repository().create_metric(metric, actor=ACTOR))


def record_metric_checkin(metric_id: str, value: float, note: str = "", confirmed: bool = False) -> str:
    """Record a manual metric observation after explicit user confirmation."""
    _confirmed(confirmed)
    return _json(services.repository().create_checkin({"metric_id": metric_id, "value": value, "note": note}, actor=ACTOR))


def refresh_plane_projection(confirmed: bool = False) -> str:
    """Refresh Plane project and task projections after explicit user confirmation."""
    _confirmed(confirmed)
    return _json({"imported": services.sync_projects(), "processed": services.process_sync()})


def create_execution_run(
    work_chart_id: str, work_chart_version: str, objective_id: str, work_chart_item_ids: list[str], confirmed: bool = False
) -> str:
    """Create the idempotency ledger before the agent creates Work Chart tasks in Plane."""
    _confirmed(confirmed)
    return _json(services.start_execution_run({"work_chart_id": work_chart_id, "work_chart_version": work_chart_version, "objective_id": objective_id, "work_chart_item_ids": work_chart_item_ids}, ACTOR))


def record_execution_item(run_id: str, work_chart_item_id: str, plane_work_item_ref_id: str, confirmed: bool = False) -> str:
    """Record the Plane work item created for one Work Chart item."""
    _confirmed(confirmed)
    return _json(services.record_execution_item(run_id, work_chart_item_id, plane_work_item_ref_id, ACTOR))


def complete_execution_run(run_id: str, error: str | None = None, confirmed: bool = False) -> str:
    """Mark an execution ledger complete or failed after explicit user confirmation."""
    _confirmed(confirmed)
    return _json(services.complete_execution_run(run_id, ACTOR, error))


# Compatibility aliases kept for existing MCP clients. New agents should use the
# explicit names above so the safety requirement remains visible in prompts.
def dashboard() -> str:
    return get_strategy_dashboard()


def create_node(kind: str, title: str, parent_id: str | None = None, plane_project_ref_id: str | None = None, confirmed: bool = False) -> str:
    return create_strategy_node(kind, title, parent_id, plane_project_ref_id, confirmed=confirmed)


def check_in(metric_id: str, value: float, note: str = "", confirmed: bool = False) -> str:
    return record_metric_checkin(metric_id, value, note, confirmed)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise SystemExit("Install the MCP runtime before starting Strategy MCP.") from error
    server = FastMCP("DarkOffice Strategy")
    for tool in (
        get_strategy_dashboard, list_strategy_nodes, get_strategy_node,
        list_available_plane_projects, get_execution_status, get_sync_status,
        create_strategy_node, update_strategy_node, archive_strategy_node,
        link_objective_to_plane_project, create_metric, record_metric_checkin,
        refresh_plane_projection, create_execution_run, record_execution_item,
        complete_execution_run, dashboard, create_node, check_in,
    ):
        server.tool()(tool)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
