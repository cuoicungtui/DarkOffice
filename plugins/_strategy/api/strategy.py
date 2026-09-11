from __future__ import annotations

from helpers.api import ApiHandler, Request, Response
from plugins._strategy.helpers import services


class Strategy(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action=str(input.get("action") or "dashboard").lower()
        actor="web"
        try:
            if action == "dashboard": return {"ok":True,"data":services.public_dashboard(input.get("filters"))}
            if action == "get_project_context": return {"ok":True,"context":services.project_context(input.get("agent_project_name"))}
            if action == "list_nodes":
                filters = dict(input.get("filters") or {})
                if input.get("agent_project_name"):
                    filters["agent_project_name"] = input["agent_project_name"]
                return {"ok":True,"nodes":services.repository().list_nodes(filters)}
            if action == "plane_projects": return {"ok":True,"projects":services.list_available_plane_projects(input.get("agent_project_name"))}
            if action == "execution_status": return {"ok":True,"data":services.execution_status(str(input.get("objective_id") or ""))}
            if action == "project_execution_health": return {"ok":True,"data":services.project_execution_health(input.get("project_id"), input.get("agent_project_name"))}
            if action == "sync_status": return {"ok":True,"data":services.repository().sync_status()}
            if action == "list_strategies": return {"ok":True,"strategies":services.list_strategies(input.get("agent_project_name"))}
            if action == "list_plane_workspaces": return {"ok":True,"workspaces":services.list_plane_workspaces()}
            if action == "get_active_strategy": return {"ok":True,"strategy":services.get_active_strategy(input.get("agent_project_name"))}
            if action == "create_strategy": return {"ok":True,"strategy":services.create_strategy(input.get("strategy") or {},actor)}
            if action == "clone_strategy": return {"ok":True,"strategy":services.clone_strategy(str(input.get("strategy_id") or ""),actor)}
            if action == "activate_strategy": return {"ok":True,"strategy":services.activate_strategy(str(input.get("strategy_id") or ""),actor)}
            if action == "create_node": return {"ok":True,"node":services.create_node(input.get("node") or {},actor)}
            if action == "update_node": return {"ok":True,"node":services.update_node(str(input.get("id") or ""),input.get("node") or {},actor)}
            if action == "archive_node": services.repository().archive_node(str(input.get("id") or ""),actor=actor); return {"ok":True}
            if action == "create_metric": return {"ok":True,"metric":services.repository().create_metric(input.get("metric") or {},actor=actor)}
            if action == "checkin": return {"ok":True,"checkin":services.repository().create_checkin(input.get("checkin") or {},actor=actor)}
            if action == "link_objective": return {"ok":True,"node":services.link_objective_to_plane_project(str(input.get("id") or ""),str(input.get("plane_project_ref_id") or ""),input.get("version"),actor)}
            if action == "create_execution_run": return {"ok":True,"run":services.start_execution_run(input.get("run") or {},actor)}
            if action == "record_execution_item": return {"ok":True,"item":services.record_execution_item(str(input.get("run_id") or ""),str(input.get("work_chart_item_id") or ""),str(input.get("plane_work_item_ref_id") or ""),actor)}
            if action == "complete_execution_run": return {"ok":True,"run":services.complete_execution_run(str(input.get("run_id") or ""),actor,input.get("error"))}
            if action == "sync": return {"ok":True,"sync":services.process_sync(),"imported":services.sync_projects(input.get("agent_project_name"))}
        except KeyError as error: return Response(str(error),404)
        except ValueError as error: return Response(str(error),400)
        except RuntimeError as error: return Response(str(error),503)
        return Response(f"Unsupported strategy action: {action}",400)
