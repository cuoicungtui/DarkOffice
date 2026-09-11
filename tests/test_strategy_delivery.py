from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from plugins._strategy.helpers.delivery import DeliveryError, ExecutionOrchestrator
from plugins._strategy.helpers.plane import HttpPlaneGateway
from plugins._strategy.helpers.repository import SqliteStrategyRepository
from plugins._strategy.helpers import services


class FakePlane:
    def __init__(self) -> None:
        self.projects: dict[str, dict] = {}
        self.work_items: dict[str, dict] = {}
        self.relations: list[tuple[str, str, str]] = []

    def get_project(self, project_id: str) -> dict:
        return self.projects[project_id]

    def create_project(self, values: dict) -> dict:
        project = {"id": f"project-{len(self.projects) + 1}", **values}
        self.projects[project["id"]] = project
        return project

    def get_work_item_by_external_id(self, project_id: str, external_id: str) -> dict | None:
        return next((item for item in self.work_items.values() if item.get("external_id") == external_id), None)

    def create_work_item(self, project_id: str, values: dict) -> dict:
        item = {"id": f"work-{len(self.work_items) + 1}", "project": project_id, **values}
        self.work_items[item["id"]] = item
        return item

    def create_work_item_relation(self, project_id: str, from_id: str, to_id: str, relation_type: str) -> dict:
        self.relations.append((from_id, to_id, relation_type))
        return {"id": str(len(self.relations))}

    def update_work_item(self, project_id: str, work_item_id: str, values: dict) -> dict:
        self.work_items[work_item_id].update(values)
        return self.work_items[work_item_id]

    def create_work_item_comment(self, project_id: str, work_item_id: str, comment_html: str) -> dict:
        return {"id": "comment-1", "comment_html": comment_html}


@pytest.fixture
def delivery(tmp_path: Path) -> tuple[SqliteStrategyRepository, FakePlane, ExecutionOrchestrator]:
    repository = SqliteStrategyRepository(str(tmp_path / "strategy.sqlite3"))
    repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    plane = FakePlane()
    return repository, plane, ExecutionOrchestrator(repository, plane)  # type: ignore[arg-type]


def specification() -> dict:
    return {
        "objective": {"title": "Ra mắt sản phẩm", "description": "Bản phát hành quý"},
        "project": {"name": "Ra mắt sản phẩm", "identifier": "LAUNCH"},
        "work_chart": {
            "id": "chart-1",
            "version": "1",
            "status": "ready_for_handoff",
            "items": [
                {"id": "research", "title": "Nghiên cứu"},
                {"id": "build", "title": "Xây dựng", "depends_on": ["research"]},
            ],
        },
    }


def test_prepare_requires_approved_work_chart(delivery: tuple[SqliteStrategyRepository, FakePlane, ExecutionOrchestrator]) -> None:
    _, _, orchestrator = delivery
    invalid = specification()
    invalid["work_chart"]["status"] = "draft"
    with pytest.raises(DeliveryError, match="ready_for_handoff"):
        orchestrator.prepare(invalid, actor="test")


def test_apply_creates_one_project_and_task_per_chart_item_then_resumes_without_duplicates(
    delivery: tuple[SqliteStrategyRepository, FakePlane, ExecutionOrchestrator],
) -> None:
    repository, plane, orchestrator = delivery
    prepared = orchestrator.prepare(specification(), actor="test")
    result = orchestrator.apply(prepared["preparation"]["token"], actor="test")

    assert len(plane.projects) == 1
    assert len(plane.work_items) == 2
    assert len(plane.relations) == 1
    assert result["run"]["status"] == "complete"
    resumed = orchestrator.resume(result["run"]["id"], actor="test")
    assert resumed["created"] == []
    assert len(repository.list_execution_items(result["run"]["id"])) == 2


def test_objective_relink_keeps_project_history(delivery: tuple[SqliteStrategyRepository, FakePlane, ExecutionOrchestrator]) -> None:
    repository, plane, orchestrator = delivery
    first = orchestrator.apply(orchestrator.prepare(specification(), actor="test")["preparation"]["token"], actor="test")
    second_project = plane.create_project({"name": "Ra mắt sản phẩm 2", "identifier": "LAUNCH2"})
    changed = specification()
    changed["objective"] = {"id": first["objective"]["id"]}
    changed["project"] = {"id": second_project["id"]}
    changed["work_chart"]["version"] = "2"
    token = orchestrator.prepare(changed, actor="test")["preparation"]["token"]
    orchestrator.apply(token, actor="test")
    with repository._connect() as connection:  # Verify durable history, not presentation output.
        history = connection.execute("SELECT status FROM strategy_objective_project_history ORDER BY linked_at").fetchall()
    assert [row["status"] for row in history] == ["closed", "active"]


def test_task_update_requires_preparation_token(delivery: tuple[SqliteStrategyRepository, FakePlane, ExecutionOrchestrator]) -> None:
    _, plane, orchestrator = delivery
    plane.projects["project-1"] = {"id": "project-1", "name": "Project"}
    plane.work_items["work-1"] = {"id": "work-1", "project": "project-1", "name": "Task"}
    prepared = orchestrator.prepare(
        {"operation": "task_update", "project_id": "project-1", "work_item_id": "work-1", "changes": {"priority": "high"}},
        actor="test",
    )
    with pytest.raises(DeliveryError, match="confirmation token"):
        orchestrator.apply("unknown", actor="test")
    result = orchestrator.apply(prepared["preparation"]["token"], actor="test")
    assert result["work_item"]["priority"] == "high"


def test_gateway_follows_pagination() -> None:
    gateway = HttpPlaneGateway("http://plane/api/v1", "darkoffice", "token")
    responses = iter([
        {"results": [{"id": "first"}], "next": "http://plane/api/v1/page-2"},
        {"results": [{"id": "second"}], "next": None},
    ])
    object.__setattr__(gateway, "_request", lambda *_args, **_kwargs: next(responses))
    assert [row["id"] for row in gateway.list_projects()] == ["first", "second"]


def test_webhook_rejects_invalid_hmac_and_accepts_signed_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("webcolors")
    from api.plane_webhook import PlaneWebhook

    repository = SqliteStrategyRepository(str(tmp_path / "strategy.sqlite3"))
    repository.ensure_connection({"api_base_url": "http://plane", "public_base_url": "http://plane", "workspace_slug": "darkoffice"})
    monkeypatch.setattr(services, "_repository", repository)
    monkeypatch.setenv("PLANE_WEBHOOK_SECRET", "secret")
    raw = json.dumps({"event": "issue", "workspace_slug": "darkoffice", "data": {"id": "work-1"}}).encode()

    class Request:
        def __init__(self, signature: str) -> None:
            self.headers = {"X-Plane-Signature": signature, "X-Plane-Delivery": "delivery-1"}

        def get_data(self, cache: bool = True) -> bytes:
            return raw

    handler = PlaneWebhook(None, None)
    rejected = asyncio.run(handler.process({}, Request("wrong")))
    assert rejected.status_code == 403
    signature = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    accepted = asyncio.run(handler.process({}, Request(f"sha256={signature}")))
    assert accepted == {"ok": True, "accepted": True}
