from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PlaneGateway(Protocol):
    def list_projects(self) -> list[dict[str, Any]]: ...
    def list_work_items(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_modules(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_cycles(self, project_id: str) -> list[dict[str, Any]]: ...
    def list_states(self, project_id: str) -> list[dict[str, Any]]: ...
    def create_work_item(self, project_id: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def get_work_item_by_external_id(self, project_id: str, external_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class HttpPlaneGateway:
    api_base_url: str
    workspace_slug: str
    api_key: str

    @classmethod
    def from_environment(cls) -> "HttpPlaneGateway | None":
        base=os.environ.get("PLANE_API_BASE_URL", "").rstrip("/")
        workspace=os.environ.get("PLANE_WORKSPACE_SLUG", "")
        token=os.environ.get("PLANE_API_KEY", "")
        return cls(base,workspace,token) if base and workspace and token else None

    def list_projects(self) -> list[dict[str, Any]]:
        return self._get(f"/workspaces/{self.workspace_slug}/projects/")

    def list_work_items(self, project_id: str) -> list[dict[str, Any]]:
        return self._get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/")

    def list_modules(self, project_id: str) -> list[dict[str, Any]]:
        return self._get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/modules/")

    def list_cycles(self, project_id: str) -> list[dict[str, Any]]:
        return self._get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/cycles/")

    def list_states(self, project_id: str) -> list[dict[str, Any]]:
        return self._get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/states/")

    def get_work_item_by_external_id(self, project_id: str, external_id: str) -> dict[str, Any] | None:
        query=urlencode({"external_source":"darkoffice_strategy","external_id":external_id})
        try:
            rows=self._get(f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/?{query}")
        except RuntimeError as error:
            # Plane CE v1.4.2 does not accept custom external-ID filters here.
            # Fall back to the project listing so retry/idempotency still work.
            if "Plane API 404:" not in str(error):
                raise
            rows=self.list_work_items(project_id)
        rows=[item for item in rows if item.get("external_source")=="darkoffice_strategy" and item.get("external_id")==external_id]
        return rows[0] if rows else None

    def create_work_item(self, project_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST",f"/workspaces/{self.workspace_slug}/projects/{project_id}/work-items/",values)

    def _get(self, path: str) -> list[dict[str, Any]]:
        result=self._request("GET",path)
        return result.get("results",[]) if isinstance(result,dict) else result if isinstance(result,list) else []

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url=f"{self.api_base_url}{path}"
        data=json.dumps(body).encode() if body is not None else None
        request=Request(url,data=data,method=method,headers={"x-api-key":self.api_key,"Content-Type":"application/json"})
        try:
            with urlopen(request,timeout=15) as response:
                return json.loads(response.read().decode() or "{}")
        except HTTPError as error:
            detail=error.read().decode(errors="replace")
            raise RuntimeError(f"Plane API {error.code}: {detail[:500]}") from error
        except URLError as error:
            raise RuntimeError(f"Plane API unavailable: {error.reason}") from error
