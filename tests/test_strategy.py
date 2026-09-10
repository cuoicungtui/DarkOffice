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


def test_nested_objective_inherits_plane_project_and_enqueues(repository: SqliteStrategyRepository) -> None:
    north = repository.create_node({"kind": "north_star", "title": "North"}, actor="test")
    pillar = repository.create_node({"kind": "pillar", "title": "Growth", "parent_id": north["id"]}, actor="test")
    parent = repository.create_node({"kind": "objective", "title": "Parent", "parent_id": pillar["id"], "plane_project_ref_id": "plane-project"}, actor="test")
    child = repository.create_node({"kind": "objective", "title": "Child", "parent_id": parent["id"]}, actor="test")
    assert child["plane_project_ref_id"] == "plane-project"
    assert len(repository.claim_outbox()) == 2


def test_sync_status_reports_pending_outbox_without_payload(repository: SqliteStrategyRepository) -> None:
    repository.create_node({"kind": "objective", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test")

    status = repository.sync_status()

    assert len(status["outbox"]) == 1
    assert "payload_json" not in status["outbox"][0]


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


def test_migration_converts_known_sample_titles_to_vietnamese(tmp_path: Path) -> None:
    path = tmp_path / "strategy.sqlite3"
    repository = SqliteStrategyRepository(str(path))
    repository.create_node(
        {"kind": "north_star", "title": "Dieu hanh muc tieu va thuc thi thong nhat"},
        actor="test",
    )

    migrated = SqliteStrategyRepository(str(path))

    assert migrated.list_nodes()[0]["title"] == "Điều hành mục tiêu và thực thi thống nhất"
