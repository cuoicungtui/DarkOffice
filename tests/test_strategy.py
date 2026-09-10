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


def test_nested_objective_inherits_plane_project_and_enqueues(repository: SqliteStrategyRepository) -> None:
    north = repository.create_node({"kind": "north_star", "title": "North"}, actor="test")
    pillar = repository.create_node({"kind": "pillar", "title": "Growth", "parent_id": north["id"]}, actor="test")
    parent = repository.create_node({"kind": "objective", "title": "Parent", "parent_id": pillar["id"], "plane_project_ref_id": "plane-project"}, actor="test")
    child = repository.create_node({"kind": "objective", "title": "Child", "parent_id": parent["id"]}, actor="test")
    assert child["plane_project_ref_id"] == "plane-project"
    assert len(repository.claim_outbox()) == 2


def test_invalid_parent_kind_is_rejected(repository: SqliteStrategyRepository) -> None:
    initiative = repository.create_node({"kind": "initiative", "title": "Deliver", "plane_project_ref_id": "plane-project"}, actor="test")
    with pytest.raises(ValueError, match="cannot be placed"):
        repository.create_node({"kind": "objective", "title": "Invalid", "parent_id": initiative["id"]}, actor="test")


def test_webhook_payload_is_idempotent(repository: SqliteStrategyRepository) -> None:
    connection = repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    payload = {"event": "issue", "data": {"id": "issue-1"}}
    assert repository.receive_webhook(connection["id"], "delivery-1", "issue", payload)
    assert not repository.receive_webhook(connection["id"], "delivery-2", "issue", payload)
