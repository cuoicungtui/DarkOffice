"""Create the repeatable Vietnamese hierarchy used to validate Strategy views.

Run inside the DarkOffice runtime after Plane integration is configured:
    python3 scripts/seed_strategy_ui_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# A direct script invocation starts with scripts/ on sys.path, not the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins._strategy.helpers import services
from plugins._strategy.helpers.plane import HttpPlaneGateway


PREFIX = "[Kiểm thử giao diện]"
PROJECT_TITLE = "DarkOffice Execution"


def find_or_create_node(kind: str, title: str, parent_id: str | None = None, project_id: str | None = None) -> dict:
    repository = services.repository()
    for node in repository.list_nodes():
        if node["kind"] == kind and node["title"] == title and node.get("parent_id") == parent_id:
            return node
    values = {"kind": kind, "title": title, "parent_id": parent_id, "lifecycle": "on_track"}
    if project_id:
        values["plane_project_ref_id"] = project_id
    return services.create_node(values, "ui-test-seed")


def find_or_create_work_item(gateway: HttpPlaneGateway, project_id: str, external_id: str, title: str, parent_id: str | None) -> dict:
    for item in gateway.list_work_items(project_id):
        if item.get("external_source") == "darkoffice_ui_test" and item.get("external_id") == external_id:
            return item
    values = {"name": title, "external_source": "darkoffice_ui_test", "external_id": external_id}
    if parent_id:
        values["parent"] = parent_id
    return gateway.create_work_item(project_id, values)


def main() -> None:
    gateway = HttpPlaneGateway.from_environment()
    if not gateway:
        raise RuntimeError("Plane integration environment is not configured")
    services.sync_projects()
    dashboard = services.public_dashboard()
    project = next((item for item in dashboard["plane_objects"] if item["kind"] == "project" and item["title"] == PROJECT_TITLE), None)
    if not project:
        raise RuntimeError(f"Plane project {PROJECT_TITLE!r} was not found")
    project_id = project["remote_id"]

    north = find_or_create_node("north_star", f"{PREFIX} Tăng trưởng bền vững")
    pillars = [find_or_create_node("pillar", f"{PREFIX} Trụ cột {index}: Năng lực {index}", north["id"]) for index in range(1, 4)]
    objectives = [find_or_create_node("objective", f"{PREFIX} Mục tiêu {index}: Hoàn thiện năng lực", pillars[0]["id"], project_id) for index in range(1, 4)]
    key_results = [find_or_create_node("key_result", f"{PREFIX} Kết quả then chốt {index}: Đo lường hiệu quả", objectives[0]["id"]) for index in range(1, 4)]
    for index in range(1, 4):
        find_or_create_node("initiative", f"{PREFIX} Sáng kiến {index}: Thực thi cải tiến", key_results[0]["id"], project_id)

    # Create a separate Plane tree with three branches at each displayed level.
    parents: list[str | None] = [None]
    for depth in range(1, 6):
        parent_id = parents[0]
        current = []
        for branch in range(1, 4):
            item = find_or_create_work_item(
                gateway,
                project_id,
                f"strategy-ui-depth-{depth}-branch-{branch}",
                f"{PREFIX} Công việc cấp {depth} - nhánh {branch}",
                parent_id,
            )
            current.append(item["id"])
        parents = current

    services.process_sync(limit=100)
    services.sync_projects()
    print("Đã tạo hoặc xác nhận dữ liệu kiểm thử 5 tầng, 3 nhánh cho Chiến lược và Plane.")


if __name__ == "__main__":
    main()
