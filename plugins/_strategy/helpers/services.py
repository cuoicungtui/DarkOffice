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
    repo=repository(); gateway=HttpPlaneGateway.from_environment(); processed={"inbox":0,"outbox":0}
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
    if not gateway: return processed
    connection=repo.connection()
    if not connection: return processed
    for command in repo.claim_outbox(limit):
        try:
            payload=json.loads(command["payload_json"]); node=repo.get_node(payload["node_id"])
            if not node: raise RuntimeError("Strategy node no longer exists")
            existing=gateway.get_work_item_by_external_id(node["plane_project_ref_id"],node["id"])
            values={"name":node["title"],"external_source":"darkoffice_strategy","external_id":node["id"]}
            if node["description"].strip():
                values["description_html"]=node["description"]
            parent_remote=repo.representative_remote_id(node["parent_id"]) if node.get("parent_id") else None
            if parent_remote: values["parent"]=parent_remote
            remote=existing or gateway.create_work_item(node["plane_project_ref_id"],values)
            plane_object=repo.upsert_plane_object(connection["id"],remote,"work_item")
            repo.link_node_to_plane(node["id"],plane_object["id"])
            repo.finish_outbox(command["id"]); processed["outbox"]+=1
        except Exception as error:
            repo.finish_outbox(command["id"],str(error))
    return processed


def sync_projects() -> int:
    repo=repository(); gateway=HttpPlaneGateway.from_environment(); connection=repo.connection()
    if not gateway or not connection: return 0
    count=0
    for project in gateway.list_projects():
        repo.upsert_plane_object(connection["id"],project,"project"); count+=1
        for item in gateway.list_work_items(project["id"]):
            repo.upsert_plane_object(connection["id"],item,"work_item"); count+=1
        for module in gateway.list_modules(project["id"]):
            repo.upsert_plane_object(connection["id"],module,"module"); count+=1
        for cycle in gateway.list_cycles(project["id"]):
            repo.upsert_plane_object(connection["id"],cycle,"cycle"); count+=1
    return count


def public_dashboard(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    return repository().dashboard(filters)
