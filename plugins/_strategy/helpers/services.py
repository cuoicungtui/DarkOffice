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
            _repository.ensure_connection({"api_base_url":gateway.api_base_url,"public_base_url":os.environ.get("PLANE_PUBLIC_BASE_URL",gateway.api_base_url),"workspace_slug":gateway.workspace_slug,"agent_project_name":os.environ.get("DARKOFFICE_AGENT_PROJECT_NAME", "default"),"credential_ref":"env:PLANE_API_KEY","webhook_secret_ref":"env:PLANE_WEBHOOK_SECRET"})
    return _repository


def create_node(values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().create_node(values, actor=actor)


def list_strategies(agent_project_name: str | None = None) -> list[dict[str, Any]]:
    return repository().list_strategies(agent_project_name or os.environ.get("DARKOFFICE_AGENT_PROJECT_NAME", "default"))


def list_plane_workspaces() -> list[dict[str, Any]]:
    return repository().list_plane_workspaces()


def get_active_strategy(agent_project_name: str | None = None) -> dict[str, Any] | None:
    return repository().get_active_strategy(agent_project_name or os.environ.get("DARKOFFICE_AGENT_PROJECT_NAME", "default"))


def activate_strategy(strategy_id: str, actor: str) -> dict[str, Any]:
    return repository().activate_strategy(strategy_id, actor=actor)


def create_strategy(values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().create_strategy(values, actor=actor)


def clone_strategy(strategy_id: str, actor: str) -> dict[str, Any]:
    return repository().clone_strategy(strategy_id, actor=actor)


def update_node(identifier: str, values: dict[str, Any], actor: str) -> dict[str, Any]:
    return repository().update_node(identifier, values, actor=actor)


def process_sync(limit: int = 20) -> dict[str, int]:
    repo=repository(); gateway=HttpPlaneGateway.from_environment(); processed={"inbox":0,"outbox":0}
    for message in repo.claim_inbox(limit):
        try:
            payload=json.loads(message["payload_json"])
            data=payload.get("data") or {}
            kind={"issue":"work_item","module":"module","cycle":"cycle","project":"project"}.get(message["event"],message["event"])
            project_id = data.get("project") or data.get("project_id")
            if isinstance(project_id,dict): project_id=project_id.get("id")
            if kind == "project": project_id=data.get("id")
            # Webhooks are signals only. Re-read the current project state so an
            # old or abbreviated event can never overwrite the projection.
            connection = repo.connection_by_id(message["connection_id"])
            scoped_gateway = _gateway_for_connection(connection) if connection else gateway
            if scoped_gateway and project_id:
                _sync_project(repo,scoped_gateway,message["connection_id"],str(project_id))
            elif data.get("id"):
                repo.upsert_plane_object(message["connection_id"],data,kind)
            repo.finish_inbox(message["id"]); processed["inbox"]+=1
        except Exception as error:
            repo.finish_inbox(message["id"],str(error))
    if processed["inbox"]:
        repo.capture_execution_snapshots()
    return processed


def sync_projects(agent_project_name: str | None = None) -> int:
    repo=repository()
    connection = repo.connection_by_agent_project(agent_project_name) if agent_project_name else repo.connection()
    gateway = _gateway_for_connection(connection) if connection else None
    if not gateway or not connection: return 0
    count=0
    projects=gateway.list_projects()
    for project in projects:
        count += _sync_project(repo,gateway,connection["id"],str(project["id"]),project)
    repo.mark_missing_plane_objects(connection["id"],"project",{str(project["id"]) for project in projects})
    repo.capture_execution_snapshots()
    return count


def _gateway_for_connection(connection: dict[str, Any] | None) -> HttpPlaneGateway | None:
    if not connection:
        return None
    api_key = os.environ.get("PLANE_API_KEY", "")
    return HttpPlaneGateway(connection["api_base_url"].rstrip("/"), connection["workspace_slug"], api_key) if api_key else None


def reconcile_plane(agent_project_name: str | None = None) -> dict[str, Any]:
    result = {"processed": process_sync(), "imported": sync_projects(agent_project_name), "broken_execution_mappings": repository().broken_execution_mappings()}
    result["project_health"] = repository().project_execution_health(agent_project_name=agent_project_name)
    result["alerts"] = result["project_health"]["alerts"]
    return result


def _sync_project(repo: SqliteStrategyRepository, gateway: HttpPlaneGateway, connection_id: str, project_id: str, project: dict[str, Any] | None = None) -> int:
    project = project or gateway.get_project(project_id)
    repo.upsert_plane_object(connection_id,project,"project")
    count=1
    for kind, values in (
        ("state", gateway.list_states(project_id)),
        ("work_item", gateway.list_work_items(project_id)),
        ("module", gateway.list_modules(project_id)),
        ("cycle", gateway.list_cycles(project_id)),
    ):
        remote_ids: set[str] = set()
        for value in values:
            value.setdefault("project",project_id)
            repo.upsert_plane_object(connection_id,value,kind); count+=1
            remote_ids.add(str(value["id"]))
        if kind != "state":
            repo.mark_missing_plane_objects(connection_id,kind,remote_ids,project_id)
    return count


def public_dashboard(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    return repository().dashboard(filters)


def list_available_plane_projects(agent_project_name: str | None = None) -> list[dict[str, Any]]:
    return repository().list_plane_projects(agent_project_name)


def project_context(agent_project_name: str | None) -> dict[str, Any]:
    if not agent_project_name:
        return {"agent_project": None, "plane_workspace": None, "active_strategy": None, "plane_projects": []}
    workspace = next((item for item in repository().list_plane_workspaces() if item["agent_project_name"] == agent_project_name and item["enabled"]), None)
    return {"agent_project": {"name": agent_project_name}, "plane_workspace": workspace, "active_strategy": get_active_strategy(agent_project_name), "plane_projects": list_available_plane_projects(agent_project_name)}


def connection_by_workspace(workspace_slug: str) -> dict[str, Any] | None:
    return repository().connection_by_workspace(workspace_slug)


def execution_status(objective_id: str) -> dict[str, Any]:
    return repository().execution_status(objective_id)


def project_execution_health(project_id: str | None = None, agent_project_name: str | None = None) -> dict[str, Any]:
    return repository().project_execution_health(project_id, agent_project_name)


def link_objective_to_plane_project(
    objective_id: str, plane_project_ref_id: str, version: int | None, actor: str
) -> dict[str, Any]:
    # Refresh first so a project just created through Plane MCP can be validated
    # against the local projection before the one-to-one link is persisted.
    objective = repository().get_node(objective_id)
    if not objective:
        raise KeyError("Strategy node not found")
    strategy = repository().get_strategy(objective["strategy_id"])
    agent_project_name = strategy["agent_project_name"]
    sync_projects(agent_project_name)
    project_ids = {project["remote_id"] for project in repository().list_plane_projects(agent_project_name)}
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
