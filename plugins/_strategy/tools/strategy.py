from __future__ import annotations

import json
from typing import Any

from helpers.tool import Response, Tool
from plugins._strategy.helpers import services


class StrategyTool(Tool):
    async def execute(self, action: str = "dashboard", **kwargs: Any) -> Response:
        action=str(action or self.args.get("action") or "dashboard").lower()
        try:
            if action in {"dashboard","list"}:
                data=services.public_dashboard(); return Response(json.dumps(data,ensure_ascii=False),False)
            if action == "create":
                node=services.create_node(kwargs or self.args,"agent")
                return Response(f"Created {node['kind']}: {node['title']}",False)
            if action == "sync":
                return Response(json.dumps(services.process_sync(),ensure_ascii=False),False)
        except (ValueError,RuntimeError,KeyError) as error:
            return Response(str(error),False)
        return Response("Supported strategy actions: dashboard, list, create, sync.",False)
