"""Optional stdio Strategy MCP server backed by the same application services."""

from __future__ import annotations

import json

from .helpers import services


def dashboard() -> str:
    return json.dumps(services.public_dashboard(), ensure_ascii=False)


def create_node(kind: str, title: str, parent_id: str | None = None, plane_project_ref_id: str | None = None) -> str:
    node = services.create_node({"kind": kind, "title": title, "parent_id": parent_id, "plane_project_ref_id": plane_project_ref_id}, "strategy-mcp")
    return json.dumps(node, ensure_ascii=False)


def check_in(metric_id: str, value: float, note: str = "") -> str:
    checkin = services.repository().create_checkin({"metric_id": metric_id, "value": value, "note": note}, actor="strategy-mcp")
    return json.dumps(checkin, ensure_ascii=False)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise SystemExit("Install the MCP runtime before starting Strategy MCP.") from error
    server = FastMCP("DarkOffice Strategy")
    server.tool()(dashboard)
    server.tool()(create_node)
    server.tool()(check_in)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
