"""JSON CLI used by the strategy-delivery skill without loading MCP schemas."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .helpers import services
from .helpers.delivery import DeliveryError, from_environment


def _spec(value: str | None, path: str | None) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8") if path else value
    if not raw:
        raise DeliveryError("SPEC_REQUIRED", "Cần --spec hoặc --spec-file")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DeliveryError("SPEC_INVALID_JSON", f"Delivery specification JSON không hợp lệ: {error.msg}") from error
    if not isinstance(loaded, dict):
        raise DeliveryError("SPEC_INVALID", "Delivery specification phải là JSON object")
    return loaded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darkoffice delivery", description="DarkOffice Strategy to Plane delivery CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--objective-id")
    inspect.add_argument("--run-id")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--spec")
    prepare.add_argument("--spec-file")
    apply = commands.add_parser("apply")
    apply.add_argument("--confirmation-token", required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    commands.add_parser("reconcile")
    task = commands.add_parser("task-update")
    task.add_argument("--confirmation-token", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        orchestrator = from_environment(services.repository())
        if args.command == "inspect":
            result = orchestrator.inspect(args.objective_id, args.run_id)
        elif args.command == "prepare":
            result = orchestrator.prepare(_spec(args.spec, args.spec_file), actor="strategy-delivery-cli")
        elif args.command == "apply":
            result = orchestrator.apply(args.confirmation_token, actor="strategy-delivery-cli")
        elif args.command == "resume":
            result = orchestrator.resume(args.run_id, actor="strategy-delivery-cli")
        elif args.command == "reconcile":
            result = {"schema_version": 1, **services.reconcile_plane()}
        else:
            result = orchestrator.apply(args.confirmation_token, actor="strategy-delivery-cli")
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, default=str))
        return 0
    except DeliveryError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyError as error:
        print(json.dumps({"ok": False, "error": {"code": "NOT_FOUND", "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 3
    except Exception as error:
        print(json.dumps({"ok": False, "error": {"code": "DELIVERY_FAILED", "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
