from __future__ import annotations

from helpers.api import ApiHandler, Request, Response
from plugins._strategy.helpers import services


class Strategy(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        action=str(input.get("action") or "dashboard").lower()
        actor="web"
        try:
            if action == "dashboard": return {"ok":True,"data":services.public_dashboard(input.get("filters"))}
            if action == "create_node": return {"ok":True,"node":services.create_node(input.get("node") or {},actor)}
            if action == "update_node": return {"ok":True,"node":services.update_node(str(input.get("id") or ""),input.get("node") or {},actor)}
            if action == "archive_node": services.repository().archive_node(str(input.get("id") or ""),actor=actor); return {"ok":True}
            if action == "create_metric": return {"ok":True,"metric":services.repository().create_metric(input.get("metric") or {},actor=actor)}
            if action == "checkin": return {"ok":True,"checkin":services.repository().create_checkin(input.get("checkin") or {},actor=actor)}
            if action == "sync": return {"ok":True,"sync":services.process_sync(),"imported":services.sync_projects()}
        except KeyError as error: return Response(str(error),404)
        except ValueError as error: return Response(str(error),400)
        except RuntimeError as error: return Response(str(error),503)
        return Response(f"Unsupported strategy action: {action}",400)
