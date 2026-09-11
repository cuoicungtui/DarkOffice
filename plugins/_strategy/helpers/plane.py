from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PlaneNotFoundError(RuntimeError):
    """Raised when Plane confirms an object does not exist."""


class PlaneGateway(Protocol):
    def list_projects(self) -> list[dict[str, Any]]: ...
    def get_project(self, project_id: str) -> dict[str, Any]: ...
    def create_project(self, values: dict[str, Any]) -> dict[str, Any]: ...
    def list_work_items(self, project_id: str) -> list[dict[str, Any]]: ...
    def get_work_item(self, project_id: str, work_item_id: str) -> dict[str, Any]: ...
    def list_modules(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_cycles(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_states(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_labels(self, project_id: str) -> list[dict[str, Any]]: ...
    def create_work_item(self, project_id: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def update_work_item(self, project_id: str, work_item_id: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def create_work_item_comment(self, project_id: str, work_item_id: str, comment_html: str) -> dict[str, Any]: ...
    def create_work_item_relation(self, project_id: str, from_id: str, to_id: str, relation_type: str) -> dict[str, Any]: ...
    def get_work_item_by_external_id(self, project_id: str, external_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class HttpPlaneGateway:
    api_base_url: str
    workspace_slug: str
    api_key: str

    @classmethod
    def from_environment(cls) -> "HttpPlaneGateway | None":
        base = os.environ.get("PLANE_API_BASE_URL", "").rstrip("/")
        workspace = os.environ.get("PLANE_WORKSPACE_SLUG", "")
        token = os.environ.get("PLANE_API_KEY", "")
        return cls(base, workspace, token) if base and workspace and token else None

    def list_projects(self) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/")

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/workspaces/{self.workspace_slug}/projects/{project_id}/")

    def create_project(self, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/workspaces/{self.workspace_slug}/projects/", values)

    def list_work_items(self, project_id: str) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/")

    def get_work_item(self, project_id: str, work_item_id: str) -> dict[str, Any]:
        return self._request("GET", f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/{work_item_id}/")

    def list_modules(self, project_id: str) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/modules/")

    def list_cycles(self, project_id: str) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/cycles/")

    def list_states(self, project_id: str) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/states/")

    def list_labels(self, project_id: str) -> list[dict[str, Any]]:
        return self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/labels/")

    def get_work_item_by_external_id(self, project_id: str, external_id: str) -> dict[str, Any] | None:
        query = urlencode({"external_source": "darkoffice_strategy", "external_id": external_id})
        try:
            rows = self._list(f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/?{query}")
        except RuntimeError as error:
            if "Plane API 404:" not in str(error):
                raise
            rows = self.list_work_items(project_id)
        marker = f"darkoffice-work-chart:{external_id}"
        for item in rows:
            if item.get("external_source") == "darkoffice_strategy" and item.get("external_id") == external_id:
                return item
            if marker in str(item.get("description_html") or item.get("description") or ""):
                return item
        return None

    def create_work_item(self, project_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/", values)

    def update_work_item(self, project_id: str, work_item_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/{work_item_id}/", values)

    def create_work_item_comment(self, project_id: str, work_item_id: str, comment_html: str) -> dict[str, Any]:
        return self._request("POST", f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/{work_item_id}/comments/", {"comment_html": comment_html})

    def create_work_item_relation(self, project_id: str, from_id: str, to_id: str, relation_type: str) -> dict[str, Any]:
        return self._request("POST", f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/{from_id}/relations/", {"related_work_item_id": to_id, "relation_type": relation_type})

    def _list(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_path: str | None = path
        while next_path:
            payload = self._request("GET", next_path)
            if isinstance(payload, list):
                rows.extend(item for item in payload if isinstance(item, dict))
                break
            if not isinstance(payload, dict):
                break
            rows.extend(item for item in payload.get("results", []) if isinstance(item, dict))
            next_value = payload.get("next")
            if not next_value:
                break
            next_path = str(next_value)
            if next_path.startswith(self.api_base_url):
                next_path = next_path[len(self.api_base_url):]
        return rows

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith(("http://", "https://")) else f"{self.api_base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        request = Request(url, data=data, method=method, headers={"x-api-key": self.api_key, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode() or "{}")
        except HTTPError as error:
            detail = error.read().decode(errors="replace")
            if error.code == 404:
                raise PlaneNotFoundError(f"Plane API 404: {detail[:500]}") from error
            raise RuntimeError(f"Plane API {error.code}: {detail[:500]}") from error
        except URLError as error:
            raise RuntimeError(f"Plane API unavailable: {error.reason}") from error
