from __future__ import annotations

import hashlib
import hmac
import json
import os

from flask import Response as FlaskResponse
from helpers.api import ApiHandler, Request, Response
from plugins._strategy.helpers import services


class PlaneWebhook(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool: return False

    @classmethod
    def requires_csrf(cls) -> bool: return False

    async def process(self, input: dict, request: Request) -> dict | Response:
        secret=os.environ.get("PLANE_WEBHOOK_SECRET", "")
        raw=request.get_data(cache=True)
        signature=request.headers.get("X-Plane-Signature", "").removeprefix("sha256=")
        if not secret or not signature:
            return FlaskResponse("Webhook authentication is not configured",401)
        expected=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature): return FlaskResponse("Invalid Plane webhook signature",403)
        try: payload=json.loads(raw)
        except json.JSONDecodeError: return FlaskResponse("Invalid JSON",400)
        connection=services.repository().connection()
        workspace=payload.get("workspace") if isinstance(payload.get("workspace"),dict) else {}
        webhook=payload.get("webhook") if isinstance(payload.get("webhook"),dict) else {}
        webhook_workspace=webhook.get("workspace") if isinstance(webhook.get("workspace"),dict) else {}
        workspace_slug=payload.get("workspace_slug") or workspace.get("slug") or webhook_workspace.get("slug")
        if not connection or workspace_slug != connection.get("workspace_slug"):
            return FlaskResponse("Unknown Plane workspace",403)
        accepted=services.repository().receive_webhook(connection["id"],request.headers.get("X-Plane-Delivery"),str(payload.get("event") or ""),payload)
        return {"ok":True,"accepted":accepted}
