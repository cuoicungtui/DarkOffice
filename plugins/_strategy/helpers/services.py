from __future__ import annotations

import json
import os
from typing import Any

from .plane import HttpPlaneGateway
from .repository import SqliteStrategyRepository


_repository: SqliteStrategyRepository | None = None


def repository() -> SqliteStrategyRepository:
    global _repository
    if _repository is None:
        _repository=SqliteStrategyRepository()
        gateway=HttpPlaneGateway.from_environment()
        if gateway:
            _repository.ensure_connection({"api_base_url":gateway.api_base_url,"public_base_url":os.environ.get("PLANE_PUBLIC_BASE_URL",gateway.api_base_url),"workspace_slug":gateway.workspace_slug,"credential_ref":"env:PLANE_API_KEY","webhook_secret_ref":"env:PLANE_WEBHOOK_SECRET"})
    return _repository


def create_node(values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().create_node(values, actor=actor)


def update_node(identifier: str, values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().update_node(identifier, values, actor=actor)


def process_sync(limit: int = 20) -> dict[str, int]:
    repo=repository(); processed={"inbox":0,"outbox":0}
    for message in repo.claim_inbox(limit):
        try:
            payload=json.loads(message["payload_json"])
            data=payload.get("data") or {}
            kind={"issue":"work_item","module":"module","cycle":"cycle","project":"project"}.get(message["event"],message["event"])
            if data.get("id"):
                repo.upsert_plane_object(message["connection_id"],data,kind)
            repo.finish_inbox(message["id"]); processed["inbox"]+=1
        except Exception as error:
            repo.finish_inbox(message["id"],str(error))
    if processed["inbox"]:
        repo.capture_execution_snapshots()
    return processed


def sync_projects() -> int:
    repo=repository(); gateway=HttpPlaneGateway.from_environment(); connection=repo.connection()
    if not gateway or not connection: return 0
    count=0
    for project in gateway.list_projects():
        repo.upsert_plane_object(connection["id"],project,"project"); count+=1
        for state in gateway.list_states(project["id"]):
            repo.upsert_plane_object(connection["id"],state,"state"); count+=1
        for item in gateway.list_work_items(project["id"]):
            repo.upsert_plane_object(connection["id"],item,"work_item"); count+=1
        for module in gateway.list_modules(project["id"]):
            repo.upsert_plane_object(connection["id"],module,"module"); count+=1
        for cycle in gateway.list_cycles(project["id"]):
            repo.upsert_plane_object(connection["id"],cycle,"cycle"); count+=1
    repo.capture_execution_snapshots()
    return count


def public_dashboard(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    return repository().dashboard(filters)


def list_available_plane_projects() -> list[dict[str, Any]]:
    return repository().list_plane_projects()


def execution_status(objective_id: str) -> dict[str, Any]:
    return repository().execution_status(objective_id)


def link_objective_to_plane_project(
    objective_id: str, plane_project_ref_id: str, version: int | None, actor: str
) -> dict[str, Any]:
    # Refresh first so a project just created through Plane MCP can be validated
    # against the local projection before the one-to-one link is persisted.
    sync_projects()
    project_ids = {project["remote_id"] for project in repository().list_plane_projects()}
    if plane_project_ref_id not in project_ids:
        raise ValueError("Plane project is not available in the current projection")
    changes: dict[str, Any] = {"plane_project_ref_id": plane_project_ref_id}
    if version is not None:
        changes["version"] = version
    return update_node(objective_id, changes, actor)


def start_execution_run(values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().create_execution_run(values, actor=actor)


def record_execution_item(
    run_id: str, work_chart_item_id: str, plane_work_item_ref_id: str, actor: str
) -> dict[str, Any]:
    return repository().record_execution_item(run_id, work_chart_item_id, plane_work_item_ref_id, actor=actor)


def complete_execution_run(run_id: str, actor: str, error: str | None = None) -> dict[str, Any]:
    return repository().complete_execution_run(run_id, actor=actor, error=error)
