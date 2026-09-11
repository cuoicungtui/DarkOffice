from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins._strategy.helpers.repository import SqliteStrategyRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqliteStrategyRepository:
    return SqliteStrategyRepository(str(tmp_path / "strategy.sqlite3"))


def test_objective_requires_plane_project(repository: SqliteStrategyRepository) -> None:
    with pytest.raises(ValueError, match="Plane project"):
        repository.create_node({"kind": "objective", "title": "Grow"}, actor="test")


def test_only_one_active_north_star_is_allowed(repository: SqliteStrategyRepository) -> None:
    repository.create_node({"kind": "north_star", "title": "One direction"}, actor="test")

    with pytest.raises(ValueError, match="one active North Star"):
        repository.create_node({"kind": "north_star", "title": "Another direction"}, actor="test")


def test_each_agent_project_gets_its_own_active_strategy(repository: SqliteStrategyRepository) -> None:
    first = repository.ensure_connection({"agent_project_name": "Project A", "api_base_url": "http://plane-a", "public_base_url": "http://plane-a", "workspace_slug": "workspace-a"})
    second = repository.ensure_connection({"agent_project_name": "Project B", "api_base_url": "http://plane-b", "public_base_url": "http://plane-b", "workspace_slug": "workspace-b"})

    strategy_a = repository.get_active_strategy("Project A")
    strategy_b = repository.get_active_strategy("Project B")
    assert strategy_a and strategy_b and strategy_a["id"] != strategy_b["id"]

    north_a = repository.create_node({"agent_project_name": "Project A", "kind": "north_star", "title": "A direction"}, actor="test")
    north_b = repository.create_node({"agent_project_name": "Project B", "kind": "north_star", "title": "B direction"}, actor="test")
    assert north_a["strategy_id"] == strategy_a["id"]
    assert north_b["strategy_id"] == strategy_b["id"]
    assert first["agent_project_name"] == "Project A"
    assert second["agent_project_name"] == "Project B"

    with pytest.raises(ValueError, match="already linked"):
        repository.ensure_connection({"agent_project_name": "Project B", "api_base_url": "http://plane-a", "public_base_url": "http://plane-a", "workspace_slug": "workspace-a"})


def test_list_nodes_can_isolate_agent_project(repository: SqliteStrategyRepository) -> None:
    repository.ensure_connection({"agent_project_name": "Project A", "api_base_url": "http://plane-a", "public_base_url": "http://plane-a", "workspace_slug": "workspace-a"})
    repository.ensure_connection({"agent_project_name": "Project B", "api_base_url": "http://plane-b", "public_base_url": "http://plane-b", "workspace_slug": "workspace-b"})
    node_a = repository.create_node({"agent_project_name": "Project A", "kind": "north_star", "title": "A"}, actor="test")
    node_b = repository.create_node({"agent_project_name": "Project B", "kind": "north_star", "title": "B"}, actor="test")

    assert [node["id"] for node in repository.list_nodes({"agent_project_name": "Project A"})] == [node_a["id"]]
    assert [node["id"] for node in repository.list_nodes({"agent_project_name": "Project B"})] == [node_b["id"]]


def test_nested_objective_requires_its_own_plane_project_without_enqueuing_work(repository: SqliteStrategyRepository) -> None:
    north = repository.create_node({"kind": "north_star", "title": "North"}, actor="test")
    pillar = repository.create_node({"kind": "pillar", "title": "Growth", "parent_id": north["id"]}, actor="test")
    parent = repository.create_node({"kind": "objective", "title": "Parent", "parent_id": pillar["id"], "plane_project_ref_id": "plane-project"}, actor="test")
    with pytest.raises(ValueError, match="Objective requires a Plane project"):
        repository.create_node({"kind": "objective", "title": "Child", "parent_id": parent["id"]}, actor="test")
    child = repository.create_node({"kind": "objective", "title": "Child", "parent_id": parent["id"], "plane_project_ref_id": "another-plane-project"}, actor="test")
    assert child["plane_project_ref_id"] == "another-plane-project"
    assert repository.claim_outbox() == []


def test_plane_project_can_belong_to_only_one_active_objective(repository: SqliteStrategyRepository) -> None:
    first = repository.create_node({"kind": "objective", "title": "First", "plane_project_ref_id": "plane-project"}, actor="test")
    with pytest.raises(ValueError, match="only one active Objective"):
        repository.create_node({"kind": "objective", "title": "Second", "plane_project_ref_id": "plane-project"}, actor="test")
    second = repository.create_node({"kind": "objective", "title": "Second", "plane_project_ref_id": "another-project"}, actor="test")
    with pytest.raises(ValueError, match="only one active Objective"):
        repository.update_node(second["id"], {"plane_project_ref_id": "plane-project", "version": second["version"]}, actor="test")
    assert repository.get_node(first["id"])["plane_project_ref_id"] == "plane-project"


def test_sync_status_has_no_automatic_work_item_outbox(repository: SqliteStrategyRepository) -> None:
    repository.create_node({"kind": "objective", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test")

    status = repository.sync_status()

    assert status["outbox"] == []


def test_invalid_parent_kind_is_rejected(repository: SqliteStrategyRepository) -> None:
    initiative = repository.create_node({"kind": "initiative", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test")
    with pytest.raises(ValueError, match="cannot be placed"):
        repository.create_node({"kind": "objective", "title": "Invalid", "parent_id": initiative["id"]}, actor="test")


def test_webhook_payload_is_idempotent(repository: SqliteStrategyRepository) -> None:
    connection = repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    payload = {"event": "issue", "data": {"id": "issue-1"}}
    assert repository.receive_webhook(connection["id"], "delivery-1", "issue", payload)
    assert not repository.receive_webhook(connection["id"], "delivery-2", "issue", payload)


def test_dashboard_returns_latest_metric_checkin(repository: SqliteStrategyRepository) -> None:
    node = repository.create_node({"kind": "north_star", "title": "Sustainable growth"}, actor="test")
    metric = repository.create_metric({"node_id": node["id"], "name": "Revenue", "unit": "%"}, actor="test")
    repository.create_checkin({"metric_id": metric["id"], "value": 42, "observed_at": "2026-09-10T00:00:00Z"}, actor="test")

    dashboard = repository.dashboard()

    assert len(dashboard["metrics"]) == 1
    assert dashboard["metrics"][0]["current_value"] == 42.0
    assert dashboard["metrics"][0]["last_checkin_at"] == "2026-09-10T00:00:00Z"


def test_plane_work_item_uses_projected_state_group(repository: SqliteStrategyRepository) -> None:
    connection = repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    repository.upsert_plane_object(connection["id"], {"id": "done-state", "name": "Done", "group": "completed"}, "state")

    item = repository.upsert_plane_object(connection["id"], {"id": "work-item", "name": "Finish", "state": "done-state"}, "work_item")

    assert item["state_group"] == "completed"


def test_execution_run_is_idempotent_and_records_chart_to_plane_mapping(repository: SqliteStrategyRepository) -> None:
    objective = repository.create_node(
        {"kind": "objective", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test"
    )
    values = {
        "work_chart_id": "chart-1",
        "work_chart_version": "6",
        "objective_id": objective["id"],
        "work_chart_item_ids": ["item-a", "item-b"],
    }

    first = repository.create_execution_run(values, actor="test")
    second = repository.create_execution_run(values, actor="test")
    item = repository.record_execution_item(first["id"], "item-a", "plane-work-a", actor="test")

    assert second["id"] == first["id"]
    assert item["plane_work_item_ref_id"] == "plane-work-a"
    assert item["status"] == "complete"
    with pytest.raises(ValueError, match="different Plane"):
        repository.record_execution_item(first["id"], "item-a", "plane-work-other", actor="test")
    with pytest.raises(ValueError, match="different Work Chart item"):
        repository.create_execution_run({**values, "work_chart_item_ids": ["item-a"]}, actor="test")


def test_execution_status_counts_only_leaf_non_cancelled_work_items(repository: SqliteStrategyRepository) -> None:
    connection = repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    objective = repository.create_node(
        {"kind": "objective", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test"
    )
    repository.upsert_plane_object(connection["id"], {"id": "parent", "project": "plane-project", "name": "Parent", "state_group": "started"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "done", "project": "plane-project", "name": "Done", "parent": "parent", "state_group": "completed"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "cancelled", "project": "plane-project", "name": "Cancelled", "parent": "parent", "state_group": "cancelled"}, "work_item")

    status = repository.execution_status(objective["id"])

    assert status["progress"] == 100.0
    assert status["counts"] == {"total": 1, "completed": 1, "cancelled": 1}


def test_project_execution_health_classifies_operational_alerts(repository: SqliteStrategyRepository) -> None:
    connection = repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    repository.upsert_plane_object(connection["id"], {"id": "project-1", "name": "E2E", "updated_at": "2026-09-11T00:00:00Z"}, "project")
    repository.upsert_plane_object(connection["id"], {"id": "late", "project": "project-1", "name": "Late", "state_group": "completed", "target_date": "2026-09-10", "completed_at": "2026-09-11T01:00:00Z"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "overdue", "project": "project-1", "name": "Overdue", "state_group": "started", "target_date": "2026-09-10"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "no-date", "project": "project-1", "name": "No date", "state_group": "todo"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "parent", "project": "project-1", "name": "Parent", "state_group": "started"}, "work_item")
    repository.upsert_plane_object(connection["id"], {"id": "child", "project": "project-1", "name": "Child", "parent": "parent", "state_group": "backlog", "target_date": "2026-09-20"}, "work_item")
    health = repository.project_execution_health("project-1")["projects"][0]

    assert health["total"] == 4
    assert health["done"] == 1
    assert health["overdue"] == 1
    assert health["late_completed"] == 1
    assert health["without_due_date"] == 1
    assert health["not_started"] == 1


def test_migration_converts_known_sample_titles_to_vietnamese(tmp_path: Path) -> None:
    path = tmp_path / "strategy.sqlite3"
    repository = SqliteStrategyRepository(str(path))
    repository.create_node(
        {"kind": "north_star", "title": "Dieu hanh muc tieu va thuc thi thong nhat"},
        actor="test",
    )

    migrated = SqliteStrategyRepository(str(path))

    assert migrated.list_nodes()[0]["title"] == "Điều hành mục tiêu và thực thi thống nhất"
