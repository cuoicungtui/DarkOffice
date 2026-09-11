from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .plane import HttpPlaneGateway, PlaneGateway
from .repository import SqliteStrategyRepository


class DeliveryError(ValueError):
    """A machine-readable CLI failure that is safe to return to an agent."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _expires_at(minutes: int = 15) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds").replace("+00:00", "Z")


class ExecutionOrchestrator:
    """Confirmation-gated saga from an approved Work Chart to Plane execution."""

    def __init__(self, repository: SqliteStrategyRepository, gateway: PlaneGateway):
        self.repository = repository
        self.gateway = gateway

    def inspect(self, objective_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": 1, "dashboard": self.repository.dashboard(), "sync": self.repository.sync_status()}
        if objective_id:
            result["objective"] = self.repository.get_node(objective_id)
            result["execution"] = self.repository.execution_status(objective_id)
        if run_id:
            result["run"] = self.repository.get_execution_run(run_id)
            result["items"] = self.repository.list_execution_items(run_id)
        return result

    def prepare(self, specification: dict[str, Any], *, actor: str) -> dict[str, Any]:
        operation = str(specification.get("operation") or "work_chart_delivery")
        if operation != "work_chart_delivery":
            planned = self._validated_task_operation(specification, operation)
            token = secrets.token_urlsafe(24)
            preparation = self.repository.prepare_delivery(token, planned, actor=actor, expires_at=_expires_at())
            return {"schema_version": 1, "preparation": preparation, "application_sheet": planned}
        chart = self._validated_chart(specification)
        objective = specification.get("objective") or {}
        project = specification.get("project") or {}
        objective_id = str(objective.get("id") or "")
        if objective_id:
            current = self.repository.get_node(objective_id)
            if not current or current.get("kind") != "objective":
                raise DeliveryError("OBJECTIVE_NOT_FOUND", "Objective không tồn tại hoặc không hợp lệ")
        elif not str(objective.get("title") or "").strip():
            raise DeliveryError("OBJECTIVE_TITLE_REQUIRED", "Cần tiêu đề Objective mới")
        if not str(project.get("id") or "") and not str(project.get("identifier") or "").strip():
            raise DeliveryError("PROJECT_IDENTIFIER_REQUIRED", "Plane Project mới cần identifier")
        item_ids = [item["id"] for item in chart["items"]]
        planned = {
            "objective": objective,
            "project": project,
            "work_chart": chart,
            "impact": {
                "work_item_count": len(item_ids),
                "dependency_count": sum(len(item.get("depends_on") or []) for item in chart["items"]),
                "objective_progress_source": "leaf_work_items_in_linked_plane_project",
            },
        }
        token = secrets.token_urlsafe(24)
        preparation = self.repository.prepare_delivery(token, planned, actor=actor, expires_at=_expires_at())
        return {"schema_version": 1, "preparation": preparation, "application_sheet": planned}

    def apply(self, confirmation_token: str, *, actor: str) -> dict[str, Any]:
        try:
            prepared = self.repository.consume_delivery_preparation(confirmation_token, actor=actor)
        except KeyError as error:
            raise DeliveryError("CONFIRMATION_REQUIRED", "Cần confirmation token hợp lệ từ prepare") from error
        try:
            result = self._apply_payload(prepared["payload"], actor=actor)
        except Exception as error:
            self.repository.finish_delivery_preparation(confirmation_token, actor=actor, error=str(error))
            raise
        self.repository.finish_delivery_preparation(confirmation_token, actor=actor)
        return {"schema_version": 1, **result}

    def resume(self, run_id: str, *, actor: str) -> dict[str, Any]:
        run = self.repository.get_execution_run(run_id)
        payload = self.repository.get_execution_payload(run_id)
        if not run or not payload:
            raise DeliveryError("RUN_NOT_FOUND", "Không tìm thấy execution run hoặc delivery specification")
        result = self._execute_items(run, payload, actor=actor)
        return {"schema_version": 1, **result}

    def update_work_item(self, project_id: str, work_item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        if not changes:
            raise DeliveryError("TASK_CHANGES_REQUIRED", "Cần trường cập nhật work item")
        return {"schema_version": 1, "work_item": self.gateway.update_work_item(project_id, work_item_id, changes)}

    def _apply_payload(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        operation = str(payload.get("operation") or "work_chart_delivery")
        if operation == "task_update":
            return {"operation": operation, "work_item": self.gateway.update_work_item(payload["project_id"], payload["work_item_id"], payload["changes"])}
        if operation == "task_comment":
            return {"operation": operation, "comment": self.gateway.create_work_item_comment(payload["project_id"], payload["work_item_id"], payload["comment_html"])}
        if operation == "task_dependency":
            return {"operation": operation, "relation": self.gateway.create_work_item_relation(payload["project_id"], payload["from_work_item_id"], payload["to_work_item_id"], payload.get("relation_type") or "blocks")}
        objective_spec = payload["objective"]
        project_spec = payload["project"]
        project_id = str(project_spec.get("id") or "")
        if project_id:
            project = self.gateway.get_project(project_id)
        else:
            project = self.gateway.create_project(
                {
                    "name": project_spec.get("name") or objective_spec.get("title"),
                    "identifier": project_spec["identifier"],
                    "description": project_spec.get("description") or objective_spec.get("description") or "",
                }
            )
            project_id = str(project.get("id") or "")
            if not project_id:
                raise DeliveryError("PROJECT_CREATE_INVALID_RESPONSE", "Plane không trả về ID Project mới")
        connection = self.repository.connection()
        if not connection:
            raise DeliveryError("PLANE_CONNECTION_MISSING", "Thiếu cấu hình kết nối Plane")
        self.repository.upsert_plane_object(connection["id"], project, "project")

        objective_id = str(objective_spec.get("id") or "")
        if objective_id:
            current = self.repository.get_node(objective_id)
            if not current:
                raise DeliveryError("OBJECTIVE_NOT_FOUND", "Objective không tồn tại")
            if current.get("plane_project_ref_id") != project_id:
                self.repository.update_node(objective_id, {"plane_project_ref_id": project_id, "version": current["version"]}, actor=actor)
            objective = self.repository.get_node(objective_id) or current
        else:
            objective = self.repository.create_node(
                {
                    "kind": "objective",
                    "title": objective_spec["title"],
                    "description": objective_spec.get("description") or "",
                    "parent_id": objective_spec.get("parent_id") or None,
                    "org_unit_id": objective_spec.get("org_unit_id") or None,
                    "plane_project_ref_id": project_id,
                    "lifecycle": objective_spec.get("lifecycle") or "active",
                },
                actor=actor,
            )
            objective_id = objective["id"]
        chart = payload["work_chart"]
        run = self.repository.create_execution_run(
            {
                "work_chart_id": chart["id"],
                "work_chart_version": str(chart["version"]),
                "objective_id": objective_id,
                "work_chart_item_ids": [item["id"] for item in chart["items"]],
            },
            actor=actor,
        )
        self.repository.save_execution_payload(run["id"], payload)
        result = self._execute_items(run, payload, actor=actor)
        result.update({"objective": objective, "plane_project": project})
        return result

    def _execute_items(self, run: dict[str, Any], payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        chart = payload["work_chart"]
        project_id = run["plane_project_ref_id"]
        recorded = {item["work_chart_item_id"]: item for item in self.repository.list_execution_items(run["id"])}
        created: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for item in chart["items"]:
            item_id = item["id"]
            existing = recorded.get(item_id, {})
            if existing.get("plane_work_item_ref_id"):
                continue
            external_id = f"{chart['id']}:{chart['version']}:{item_id}"
            try:
                work_item = self.gateway.get_work_item_by_external_id(project_id, external_id)
                if not work_item:
                    work_item = self._create_work_item(project_id, item, external_id)
                remote_id = str(work_item.get("id") or "")
                if not remote_id:
                    raise DeliveryError("WORK_ITEM_CREATE_INVALID_RESPONSE", "Plane không trả về ID work item")
                self.repository.record_execution_item(run["id"], item_id, remote_id, actor=actor)
                created.append({"work_chart_item_id": item_id, "plane_work_item_id": remote_id})
            except Exception as error:
                failures.append({"work_chart_item_id": item_id, "error": str(error)})

        mappings = {item["work_chart_item_id"]: item.get("plane_work_item_ref_id") for item in self.repository.list_execution_items(run["id"])}
        relation_warnings: list[dict[str, str]] = []
        for item in chart["items"]:
            for predecessor in item.get("depends_on") or []:
                if not mappings.get(item["id"]) or not mappings.get(predecessor):
                    continue
                try:
                    self.gateway.create_work_item_relation(project_id, str(mappings[predecessor]), str(mappings[item["id"]]), "blocks")
                except Exception as error:
                    relation_warnings.append({"work_chart_item_id": item["id"], "depends_on": str(predecessor), "error": str(error)})
        error_message = "; ".join(item["error"] for item in failures) or None
        completed = self.repository.complete_execution_run(run["id"], actor=actor, error=error_message)
        return {"run": completed, "created": created, "failures": failures, "relation_warnings": relation_warnings, "progress": self.repository.execution_status(run["objective_id"])}

    @staticmethod
    def _validated_chart(specification: dict[str, Any]) -> dict[str, Any]:
        chart = specification.get("work_chart") or {}
        if chart.get("status") != "ready_for_handoff":
            raise DeliveryError("WORK_CHART_NOT_READY", "Work Chart phải có trạng thái ready_for_handoff")
        if not str(chart.get("id") or "") or not str(chart.get("version") or ""):
            raise DeliveryError("WORK_CHART_ID_REQUIRED", "Work Chart cần id và version")
        items = chart.get("items") or []
        ids = [str(item.get("id") or "") for item in items if isinstance(item, dict)]
        if not ids or len(ids) != len(items) or len(set(ids)) != len(ids):
            raise DeliveryError("WORK_CHART_ITEMS_INVALID", "Work Chart cần item ID duy nhất")
        known = set(ids)
        for item in items:
            if not str(item.get("title") or "").strip():
                raise DeliveryError("WORK_CHART_ITEM_TITLE_REQUIRED", "Mỗi Work Chart item cần tiêu đề")
            unknown = set(item.get("depends_on") or []) - known
            if unknown:
                raise DeliveryError("WORK_CHART_DEPENDENCY_INVALID", "Dependency không thuộc Work Chart")
        return {"id": str(chart["id"]), "version": str(chart["version"]), "status": chart["status"], "items": items}

    @staticmethod
    def _validated_task_operation(specification: dict[str, Any], operation: str) -> dict[str, Any]:
        project_id = str(specification.get("project_id") or "")
        work_item_id = str(specification.get("work_item_id") or "")
        if operation not in {"task_update", "task_comment", "task_dependency"}:
            raise DeliveryError("OPERATION_UNSUPPORTED", "Delivery operation không được hỗ trợ")
        if operation == "task_dependency":
            if not project_id or not str(specification.get("from_work_item_id") or "") or not str(specification.get("to_work_item_id") or ""):
                raise DeliveryError("TASK_DEPENDENCY_INVALID", "Dependency cần project_id, from_work_item_id và to_work_item_id")
            return {"operation": operation, "project_id": project_id, "from_work_item_id": str(specification["from_work_item_id"]), "to_work_item_id": str(specification["to_work_item_id"]), "relation_type": str(specification.get("relation_type") or "blocks")}
        if not project_id or not work_item_id:
            raise DeliveryError("TASK_REFERENCE_REQUIRED", "Cần project_id và work_item_id")
        if operation == "task_update":
            changes = specification.get("changes")
            if not isinstance(changes, dict) or not changes:
                raise DeliveryError("TASK_CHANGES_REQUIRED", "Cần changes để cập nhật work item")
            return {"operation": operation, "project_id": project_id, "work_item_id": work_item_id, "changes": changes}
        comment_html = str(specification.get("comment_html") or "").strip()
        if not comment_html:
            raise DeliveryError("TASK_COMMENT_REQUIRED", "Cần comment_html")
        return {"operation": operation, "project_id": project_id, "work_item_id": work_item_id, "comment_html": comment_html}

    def _create_work_item(self, project_id: str, item: dict[str, Any], external_id: str) -> dict[str, Any]:
        marker = f"<!-- darkoffice-work-chart:{external_id} -->"
        values = {
            "name": item["title"],
            "description_html": f"{item.get('description_html') or item.get('description') or ''}{marker}",
            "priority": item.get("priority") or "none",
            "external_source": "darkoffice_strategy",
            "external_id": external_id,
        }
        try:
            return self.gateway.create_work_item(project_id, values)
        except RuntimeError as error:
            if "Plane API 400:" not in str(error):
                raise
            values.pop("external_source")
            values.pop("external_id")
            return self.gateway.create_work_item(project_id, values)


def from_environment(repository: SqliteStrategyRepository) -> ExecutionOrchestrator:
    gateway = HttpPlaneGateway.from_environment()
    if not gateway:
        raise DeliveryError("PLANE_CONNECTION_MISSING", "Thiếu PLANE_API_BASE_URL, PLANE_WORKSPACE_SLUG hoặc PLANE_API_KEY")
    return ExecutionOrchestrator(repository, gateway)
