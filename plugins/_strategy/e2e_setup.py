"""Create the Plane E2E monitoring matrix without touching operational projects."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .helpers.plane import HttpPlaneGateway


MARKER = "darkoffice-e2e-monitoring"


def _find(rows: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    return next((row for row in rows if MARKER in str(row.get("description") or row.get("description_html") or "") or row.get("name") == title), None)


def setup() -> dict[str, Any]:
    gateway = HttpPlaneGateway.from_environment()
    if not gateway:
        raise RuntimeError("Thiếu PLANE_API_BASE_URL, PLANE_WORKSPACE_SLUG hoặc PLANE_API_KEY")
    projects = gateway.list_projects()
    project = next((row for row in projects if row.get("identifier") == "E2EDV"), None)
    if not project:
        project = gateway.create_project({"name": "[Kiểm thử E2E] DevOps Pipeline", "identifier": "E2EDV", "description": MARKER})
    project_id = str(project["id"])
    today = date.today()
    cycles = gateway.list_cycles(project_id)
    cycle = _find(cycles, "E2E - Theo dõi tiến độ") or gateway.create_cycle(project_id, {"name": "E2E - Theo dõi tiến độ", "start_date": today.isoformat(), "end_date": (today + timedelta(days=7)).isoformat(), "description": MARKER})
    modules = gateway.list_modules(project_id)
    module = _find(modules, "Vận hành CI/CD E2E") or gateway.create_module(project_id, {"name": "Vận hành CI/CD E2E", "description": MARKER})
    states = {str(row.get("group") or row.get("name") or "").lower(): row.get("id") for row in gateway.list_states(project_id)}
    state = lambda name: states.get(name) or states.get({"in_progress": "started", "done": "completed", "cancelled": "cancelled"}.get(name, name))
    existing = gateway.list_work_items(project_id)
    parent = _find(existing, "Chuẩn bị phát hành CI/CD")
    if not parent:
        parent = gateway.create_work_item(project_id, {"name": "Chuẩn bị phát hành CI/CD", "description_html": MARKER, "state": state("todo")})
    specs = [
        ("Rà soát bảo mật pipeline", "backlog", today - timedelta(days=3), None),
        ("Chuẩn bị tài liệu bàn giao", "todo", None, None),
        ("Viết Dockerfile", "in_progress", today + timedelta(days=3), today),
        ("Cấu hình CI pipeline", "done", today - timedelta(days=1), today - timedelta(days=2)),
        ("Kiểm tra rollback", "done", today - timedelta(days=2), today + timedelta(days=1)),
        ("Dọn cấu hình thử nghiệm", "cancelled", today - timedelta(days=1), today - timedelta(days=1)),
    ]
    created = []
    item_ids: dict[str, str] = {}
    for title, group, target, completed in specs:
        found = _find(existing, title)
        if found:
            item_ids[title] = str(found["id"])
            continue
        values = {"name": title, "description_html": MARKER, "state": state(group), "parent": parent["id"], "cycle_id": cycle.get("id"), "module_ids": [module.get("id")], "target_date": target.isoformat() if target else None, "start_date": today.isoformat() if group == "in_progress" else None, "completed_at": completed.isoformat() if completed else None}
        item = gateway.create_work_item(project_id, values)
        item_ids[title] = str(item["id"])
        created.append(item["id"])
    for predecessor, successor in (("Rà soát bảo mật pipeline", "Viết Dockerfile"), ("Viết Dockerfile", "Cấu hình CI pipeline"), ("Cấu hình CI pipeline", "Kiểm tra rollback")):
        if item_ids.get(predecessor) and item_ids.get(successor):
            gateway.create_work_item_relation(project_id, item_ids[predecessor], item_ids[successor], "blocks")
    return {"project_id": project_id, "project_identifier": "E2EDV", "cycle_id": cycle.get("id"), "module_id": module.get("id"), "created_work_item_ids": created, "marker": MARKER}


if __name__ == "__main__":
    import json
    print(json.dumps(setup(), ensure_ascii=False))
