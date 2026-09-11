from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


NODE_KINDS = {"north_star", "pillar", "objective", "key_result", "initiative"}
LIFECYCLES = {"draft", "active", "on_track", "at_risk", "complete", "archived"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


class StrategyRepository(ABC):
    """Storage contract used by services, tools, APIs, and the sync worker."""

    @abstractmethod
    def create_node(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]: ...

    @abstractmethod
    def list_nodes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def dashboard(self, filters: dict[str, Any] | None = None) -> dict[str, Any]: ...

    @abstractmethod
    def sync_status(self) -> dict[str, list[dict[str, Any]]]: ...

    @abstractmethod
    def get_node(self, identifier: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_plane_projects(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execution_status(self, node_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def create_execution_run(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]: ...

    @abstractmethod
    def record_execution_item(self, run_id: str, item_id: str, plane_work_item_ref_id: str, *, actor: str) -> dict[str, Any]: ...

    @abstractmethod
    def complete_execution_run(self, run_id: str, *, actor: str, error: str | None = None) -> dict[str, Any]: ...


class UnitOfWork(ABC):
    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class SqliteUnitOfWork(UnitOfWork):
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


class SqliteStrategyRepository(StrategyRepository):
    """SQLite implementation. No caller receives a SQLite cursor or connection."""

    SCHEMA_VERSION = "3"

    def __init__(self, database_path: str | None = None):
        default = Path(os.environ.get("DARKOFFICE_STRATEGY_DB", "usr/strategy/strategy.sqlite3"))
        self.path = Path(database_path or default).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def migrate(self) -> None:
        statements = [
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS org_units (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES org_units(id), name TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS strategy_periods (id TEXT PRIMARY KEY, name TEXT NOT NULL, start_date TEXT, end_date TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS strategy_nodes (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES strategy_nodes(id), kind TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', period_id TEXT REFERENCES strategy_periods(id), org_unit_id TEXT REFERENCES org_units(id), owner_ref TEXT, sort_order INTEGER NOT NULL DEFAULT 0, lifecycle TEXT NOT NULL DEFAULT 'draft', plane_project_ref_id TEXT, version INTEGER NOT NULL DEFAULT 1, archived_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS idx_strategy_nodes_parent ON strategy_nodes(parent_id, sort_order)",
            "CREATE TABLE IF NOT EXISTS strategy_alignments (id TEXT PRIMARY KEY, from_node_id TEXT NOT NULL REFERENCES strategy_nodes(id), to_node_id TEXT NOT NULL REFERENCES strategy_nodes(id), relation_type TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(from_node_id, to_node_id, relation_type))",
            "CREATE TABLE IF NOT EXISTS metric_definitions (id TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES strategy_nodes(id), name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT '', direction TEXT NOT NULL DEFAULT 'increase', baseline REAL, target REAL, source_mode TEXT NOT NULL DEFAULT 'manual', aggregation TEXT NOT NULL DEFAULT 'latest', weight REAL NOT NULL DEFAULT 1, expected_method TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS metric_checkins (id TEXT PRIMARY KEY, metric_id TEXT NOT NULL REFERENCES metric_definitions(id), observed_at TEXT NOT NULL, value REAL NOT NULL, health TEXT, note TEXT NOT NULL DEFAULT '', actor_ref TEXT, source_event_key TEXT, created_at TEXT NOT NULL, UNIQUE(metric_id, source_event_key))",
            "CREATE TABLE IF NOT EXISTS plane_connections (id TEXT PRIMARY KEY, api_base_url TEXT NOT NULL, public_base_url TEXT NOT NULL, workspace_id TEXT, workspace_slug TEXT NOT NULL, credential_ref TEXT, webhook_secret_ref TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS plane_objects (id TEXT PRIMARY KEY, connection_id TEXT NOT NULL REFERENCES plane_connections(id), remote_id TEXT NOT NULL, kind TEXT NOT NULL, project_ref_id TEXT, title TEXT NOT NULL DEFAULT '', state_group TEXT, start_date TEXT, target_date TEXT, completed_at TEXT, source_updated_at TEXT, synced_at TEXT NOT NULL, deleted_at TEXT, raw_json TEXT NOT NULL DEFAULT '{}', UNIQUE(connection_id, kind, remote_id))",
            "CREATE TABLE IF NOT EXISTS plane_object_relations (id TEXT PRIMARY KEY, from_object_id TEXT NOT NULL REFERENCES plane_objects(id), to_object_id TEXT NOT NULL REFERENCES plane_objects(id), relation_type TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(from_object_id, to_object_id, relation_type))",
            "CREATE TABLE IF NOT EXISTS strategy_plane_links (id TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES strategy_nodes(id), plane_object_id TEXT NOT NULL REFERENCES plane_objects(id), role TEXT NOT NULL, metric_id TEXT REFERENCES metric_definitions(id), sync_state TEXT NOT NULL DEFAULT 'linked', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(node_id, plane_object_id, role))",
            "CREATE TABLE IF NOT EXISTS progress_snapshots (id TEXT PRIMARY KEY, node_id TEXT REFERENCES strategy_nodes(id), plane_object_id TEXT REFERENCES plane_objects(id), captured_at TEXT NOT NULL, outcome_progress REAL, execution_progress REAL, counts_json TEXT NOT NULL DEFAULT '{}', calculation_version TEXT NOT NULL, CHECK((node_id IS NOT NULL) != (plane_object_id IS NOT NULL)))",
            "CREATE TABLE IF NOT EXISTS sync_inbox (id TEXT PRIMARY KEY, connection_id TEXT NOT NULL REFERENCES plane_connections(id), delivery_id TEXT, payload_hash TEXT NOT NULL, event TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, lease_until TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(connection_id, payload_hash))",
            "CREATE TABLE IF NOT EXISTS sync_outbox (id TEXT PRIMARY KEY, node_id TEXT REFERENCES strategy_nodes(id), operation TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL, depends_on TEXT REFERENCES sync_outbox(id), status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL, lease_until TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS sync_runs (id TEXT PRIMARY KEY, connection_id TEXT REFERENCES plane_connections(id), scope TEXT NOT NULL, cursor TEXT, status TEXT NOT NULL, stats_json TEXT NOT NULL DEFAULT '{}', started_at TEXT NOT NULL, finished_at TEXT)",
            "CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, actor_ref TEXT NOT NULL, action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, changes_json TEXT NOT NULL DEFAULT '{}', correlation_id TEXT, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS strategy_execution_runs (id TEXT PRIMARY KEY, work_chart_id TEXT NOT NULL, work_chart_version TEXT NOT NULL, objective_id TEXT NOT NULL REFERENCES strategy_nodes(id), plane_project_ref_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', request_hash TEXT NOT NULL, error TEXT, started_at TEXT NOT NULL, completed_at TEXT, UNIQUE(work_chart_id, work_chart_version, objective_id))",
            "CREATE TABLE IF NOT EXISTS strategy_execution_items (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES strategy_execution_runs(id), work_chart_item_id TEXT NOT NULL, plane_work_item_ref_id TEXT, status TEXT NOT NULL DEFAULT 'pending', error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(run_id, work_chart_item_id))",
            "CREATE TABLE IF NOT EXISTS strategy_objective_project_history (id TEXT PRIMARY KEY, objective_id TEXT NOT NULL REFERENCES strategy_nodes(id), plane_project_ref_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', linked_at TEXT NOT NULL, unlinked_at TEXT, actor_ref TEXT NOT NULL, UNIQUE(objective_id, plane_project_ref_id, linked_at))",
            "CREATE TABLE IF NOT EXISTS strategy_delivery_preparations (token TEXT PRIMARY KEY, payload_json TEXT NOT NULL, request_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'prepared', expires_at TEXT NOT NULL, created_at TEXT NOT NULL, applied_at TEXT)",
            "CREATE TABLE IF NOT EXISTS strategy_execution_payloads (run_id TEXT PRIMARY KEY REFERENCES strategy_execution_runs(id), payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
        ]
        checksum = hashlib.sha256("\n".join(statements).encode()).hexdigest()
        with self._lock:
            connection = self._connect()
            try:
                for statement in statements:
                    connection.execute(statement)
                # Convert only known, early sample labels.  This is idempotent and
                # leaves user-created titles and Plane-sourced project names intact.
                for old_title, new_title in {
                    "Dieu hanh muc tieu va thuc thi thong nhat": "Điều hành mục tiêu và thực thi thống nhất",
                    "Nen tang van hanh DarkOffice": "Nền tảng vận hành DarkOffice",
                    "Dong bo chien luoc voi Plane": "Đồng bộ chiến lược với Plane",
                    "Tien do thuc thi tich hop Plane": "Tiến độ thực thi tích hợp Plane",
                    "Van hanh webhook tien do Plane": "Vận hành webhook tiến độ Plane",
                }.items():
                    connection.execute(
                        "UPDATE strategy_nodes SET title=?, updated_at=? WHERE title=?",
                        (new_title, now(), old_title),
                    )
                # Earlier releases automatically queued representative tasks for
                # Objectives and Initiatives. Keep the audit rows, but never let
                # the worker create those tasks after the Work Chart workflow took
                # ownership of task creation.
                connection.execute(
                    "UPDATE sync_outbox SET status='complete', error='superseded by Work Chart execution', updated_at=? "
                    "WHERE operation='create_work_item' AND status!='complete'",
                    (now(),),
                )
                connection.execute("INSERT OR REPLACE INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)", (self.SCHEMA_VERSION, checksum, now()))
            finally:
                connection.close()

    def ensure_connection(self, values: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            existing = connection.execute("SELECT * FROM plane_connections WHERE workspace_slug = ?", (values["workspace_slug"],)).fetchone()
            timestamp = now()
            if existing:
                connection.execute("UPDATE plane_connections SET api_base_url=?, public_base_url=?, enabled=?, updated_at=? WHERE id=?", (values["api_base_url"], values["public_base_url"], int(values.get("enabled", True)), timestamp, existing["id"]))
                return self._row(connection.execute("SELECT * FROM plane_connections WHERE id=?", (existing["id"],)).fetchone())
            identifier = new_id()
            connection.execute("INSERT INTO plane_connections(id, api_base_url, public_base_url, workspace_slug, credential_ref, webhook_secret_ref, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (identifier, values["api_base_url"], values["public_base_url"], values["workspace_slug"], values.get("credential_ref"), values.get("webhook_secret_ref"), int(values.get("enabled", True)), timestamp, timestamp))
            return self._row(connection.execute("SELECT * FROM plane_connections WHERE id=?", (identifier,)).fetchone())

    def connection(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM plane_connections WHERE enabled=1 ORDER BY updated_at DESC LIMIT 1").fetchone()
            return self._row(row) if row else None

    def create_node(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        kind = str(values.get("kind", "")).strip().lower()
        title = str(values.get("title", "")).strip()
        if kind not in NODE_KINDS or not title:
            raise ValueError("A supported strategy kind and title are required")
        lifecycle = str(values.get("lifecycle") or "draft").lower()
        if lifecycle not in LIFECYCLES:
            raise ValueError("Unsupported lifecycle")
        identifier, timestamp = new_id(), now()
        node = {"id": identifier, "parent_id": values.get("parent_id") or None, "kind": kind, "title": title, "description": str(values.get("description") or ""), "period_id": values.get("period_id") or None, "org_unit_id": values.get("org_unit_id") or None, "owner_ref": values.get("owner_ref") or None, "sort_order": int(values.get("sort_order") or 0), "lifecycle": lifecycle, "plane_project_ref_id": values.get("plane_project_ref_id") or None, "created_at": timestamp, "updated_at": timestamp}
        with self.transaction() as connection:
            if kind == "north_star" and connection.execute(
                "SELECT 1 FROM strategy_nodes WHERE kind='north_star' AND archived_at IS NULL"
            ).fetchone():
                raise ValueError("Only one active North Star is allowed")
            self._validate_parent(connection, node["parent_id"], kind, identifier)
            if kind == "objective" and not node["plane_project_ref_id"]:
                raise ValueError("Objective requires a Plane project")
            if kind == "initiative" and not node["plane_project_ref_id"]:
                inherited = self._inherited_project(connection, node["parent_id"])
                if not inherited:
                    raise ValueError("Initiative requires a Plane project")
                node["plane_project_ref_id"] = inherited
            if kind == "objective":
                self._assert_objective_project_available(connection, node["plane_project_ref_id"], identifier)
            connection.execute("INSERT INTO strategy_nodes(id,parent_id,kind,title,description,period_id,org_unit_id,owner_ref,sort_order,lifecycle,plane_project_ref_id,created_at,updated_at) VALUES (:id,:parent_id,:kind,:title,:description,:period_id,:org_unit_id,:owner_ref,:sort_order,:lifecycle,:plane_project_ref_id,:created_at,:updated_at)", node)
            if kind == "objective":
                self._record_objective_project_history(connection, identifier, str(node["plane_project_ref_id"]), actor)
            self._audit(connection, actor, "strategy_node.created", "strategy_node", identifier, node)
            return self._row(connection.execute("SELECT * FROM strategy_nodes WHERE id=?", (identifier,)).fetchone())

    def update_node(self, identifier: str, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        allowed = {"title", "description", "lifecycle", "owner_ref", "sort_order", "period_id", "org_unit_id", "parent_id", "plane_project_ref_id"}
        changes = {key: value for key, value in values.items() if key in allowed}
        with self.transaction() as connection:
            current = connection.execute("SELECT * FROM strategy_nodes WHERE id=?", (identifier,)).fetchone()
            if not current:
                raise KeyError("Strategy node not found")
            if "parent_id" in changes:
                self._validate_parent(connection, changes["parent_id"] or None, current["kind"], identifier)
            if "plane_project_ref_id" in changes and current["kind"] not in {"objective", "initiative"}:
                raise ValueError("Only Objectives and Initiatives can link to a Plane project")
            if "plane_project_ref_id" in changes and not changes["plane_project_ref_id"]:
                raise ValueError("Objective and Initiative require a Plane project")
            if "plane_project_ref_id" in changes and current["kind"] == "objective":
                self._assert_objective_project_available(connection, changes["plane_project_ref_id"], identifier)
            if "lifecycle" in changes and changes["lifecycle"] not in LIFECYCLES:
                raise ValueError("Unsupported lifecycle")
            expected = int(values.get("version", current["version"]))
            parts, params = [], []
            for key, value in changes.items():
                parts.append(f"{key}=?")
                params.append(value)
            parts.extend(["version=version+1", "updated_at=?"])
            params.extend([now(), identifier, expected])
            if connection.execute(f"UPDATE strategy_nodes SET {', '.join(parts)} WHERE id=? AND version=?", params).rowcount != 1:
                raise ValueError("The strategy node was changed by another request")
            if current["kind"] == "objective" and "plane_project_ref_id" in changes and changes["plane_project_ref_id"] != current["plane_project_ref_id"]:
                connection.execute(
                    "UPDATE strategy_objective_project_history SET status='closed', unlinked_at=? WHERE objective_id=? AND status='active'",
                    (now(), identifier),
                )
                self._record_objective_project_history(connection, identifier, str(changes["plane_project_ref_id"]), actor)
            updated = self._row(connection.execute("SELECT * FROM strategy_nodes WHERE id=?", (identifier,)).fetchone())
            self._audit(connection, actor, "strategy_node.updated", "strategy_node", identifier, changes)
            return updated

    def archive_node(self, identifier: str, *, actor: str) -> None:
        with self.transaction() as connection:
            if connection.execute("UPDATE strategy_nodes SET lifecycle='archived', archived_at=?, version=version+1, updated_at=? WHERE id=?", (now(), now(), identifier)).rowcount != 1:
                raise KeyError("Strategy node not found")
            self._audit(connection, actor, "strategy_node.archived", "strategy_node", identifier, {})

    def list_nodes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        clauses, params = ["archived_at IS NULL"], []
        for field in ("period_id", "org_unit_id", "kind", "lifecycle"):
            if filters.get(field):
                clauses.append(f"{field}=?")
                params.append(filters[field])
        with self._connect() as connection:
            return [self._row(row) for row in connection.execute(f"SELECT * FROM strategy_nodes WHERE {' AND '.join(clauses)} ORDER BY sort_order, created_at", params).fetchall()]

    def create_checkin(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        metric_id = str(values.get("metric_id") or "")
        try:
            value = float(values["value"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("A numeric metric value is required")
        identifier, timestamp = new_id(), now()
        with self.transaction() as connection:
            if not connection.execute("SELECT 1 FROM metric_definitions WHERE id=?", (metric_id,)).fetchone():
                raise KeyError("Metric not found")
            connection.execute("INSERT INTO metric_checkins(id,metric_id,observed_at,value,health,note,actor_ref,source_event_key,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (identifier, metric_id, values.get("observed_at") or timestamp, value, values.get("health"), str(values.get("note") or ""), actor, values.get("source_event_key"), timestamp))
            self._audit(connection, actor, "metric.checked_in", "metric_checkin", identifier, {"metric_id": metric_id, "value": value})
            return self._row(connection.execute("SELECT * FROM metric_checkins WHERE id=?", (identifier,)).fetchone())

    def create_metric(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        node_id, name = str(values.get("node_id") or ""), str(values.get("name") or "").strip()
        if not node_id or not name:
            raise ValueError("Metric node and name are required")
        identifier, timestamp = new_id(), now()
        with self.transaction() as connection:
            if not connection.execute("SELECT 1 FROM strategy_nodes WHERE id=?", (node_id,)).fetchone():
                raise KeyError("Strategy node not found")
            connection.execute("INSERT INTO metric_definitions(id,node_id,name,unit,direction,baseline,target,source_mode,aggregation,weight,expected_method,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (identifier,node_id,name,str(values.get("unit") or ""),str(values.get("direction") or "increase"),values.get("baseline"),values.get("target"),str(values.get("source_mode") or "manual"),str(values.get("aggregation") or "latest"),float(values.get("weight") or 1),values.get("expected_method"),timestamp,timestamp))
            self._audit(connection, actor, "metric.created", "metric", identifier, {"node_id": node_id, "name": name})
            return self._row(connection.execute("SELECT * FROM metric_definitions WHERE id=?", (identifier,)).fetchone())

    def receive_webhook(self, connection_id: str, delivery_id: str | None, event: str, payload: dict[str, Any]) -> bool:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest, timestamp = hashlib.sha256(encoded.encode()).hexdigest(), now()
        with self.transaction() as connection:
            try:
                connection.execute("INSERT INTO sync_inbox(id,connection_id,delivery_id,payload_hash,event,payload_json,next_attempt_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (new_id(),connection_id,delivery_id,digest,event,encoded,timestamp,timestamp,timestamp))
                return True
            except sqlite3.IntegrityError:
                return False

    def claim_inbox(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM sync_inbox WHERE status='pending' AND next_attempt_at<=? ORDER BY created_at LIMIT ?", (now(), limit)).fetchall()
            result = []
            for row in rows:
                connection.execute("UPDATE sync_inbox SET status='running', attempts=attempts+1, lease_until=?, updated_at=? WHERE id=?", (now(), now(), row["id"]))
                result.append(self._row(row))
            return result

    def finish_inbox(self, identifier: str, error: str | None = None) -> None:
        with self.transaction() as connection:
            status = "complete" if not error else "pending"
            row=connection.execute("SELECT attempts FROM sync_inbox WHERE id=?", (identifier,)).fetchone()
            delay=min(900,2 ** min(int(row["attempts"]) if row else 1,9)) if error else 0
            next_at=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
            connection.execute("UPDATE sync_inbox SET status=?, error=?, next_attempt_at=?, lease_until=NULL, updated_at=? WHERE id=?", (status,error,next_at,now(),identifier))

    def claim_outbox(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM sync_outbox WHERE status='pending' AND next_attempt_at<=? AND (depends_on IS NULL OR depends_on IN (SELECT id FROM sync_outbox WHERE status='complete')) ORDER BY created_at LIMIT ?", (now(), limit)).fetchall()
            result=[]
            for row in rows:
                connection.execute("UPDATE sync_outbox SET status='running',attempts=attempts+1,lease_until=?,updated_at=? WHERE id=?", (now(),now(),row["id"]))
                result.append(self._row(row))
            return result

    def finish_outbox(self, identifier: str, error: str | None = None) -> None:
        with self.transaction() as connection:
            status = "complete" if not error else "pending"
            row=connection.execute("SELECT attempts FROM sync_outbox WHERE id=?", (identifier,)).fetchone()
            delay=min(900,2 ** min(int(row["attempts"]) if row else 1,9)) if error else 0
            next_at=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
            connection.execute("UPDATE sync_outbox SET status=?,error=?,next_attempt_at=?,lease_until=NULL,updated_at=? WHERE id=?", (status,error,next_at,now(),identifier))

    def get_node(self, identifier: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM strategy_nodes WHERE id=?",(identifier,)).fetchone()
            return self._row(row) if row else None

    def list_plane_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                self._row(row)
                for row in connection.execute(
                    "SELECT * FROM plane_objects WHERE kind='project' AND deleted_at IS NULL ORDER BY title"
                ).fetchall()
            ]

    def execution_status(self, node_id: str) -> dict[str, Any]:
        node = self.get_node(node_id)
        if not node:
            raise KeyError("Strategy node not found")
        if node["kind"] != "objective":
            raise ValueError("Execution progress is available only for Objectives")
        project_id = node.get("plane_project_ref_id")
        if not project_id:
            return {"objective_id": node_id, "plane_project_ref_id": None, "progress": None, "counts": {"total": 0, "completed": 0, "cancelled": 0}}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT remote_id,state_group,raw_json FROM plane_objects "
                "WHERE kind='work_item' AND project_ref_id=? AND deleted_at IS NULL",
                (project_id,),
            ).fetchall()
        items = [self._row(row) for row in rows]
        parent_ids: set[str] = set()
        for item in items:
            try:
                raw = json.loads(item["raw_json"])
            except (TypeError, ValueError):
                raw = {}
            parent = raw.get("parent") or raw.get("parent_id")
            if isinstance(parent, dict):
                parent = parent.get("id")
            if parent:
                parent_ids.add(str(parent))
        leaves = [item for item in items if item["remote_id"] not in parent_ids]
        valid = [item for item in leaves if (item.get("state_group") or "").lower() not in {"cancelled", "canceled"}]
        completed = [item for item in valid if (item.get("state_group") or "").lower() in {"completed", "done"}]
        cancelled = len(leaves) - len(valid)
        progress = round((len(completed) / len(valid)) * 100, 2) if valid else None
        return {
            "objective_id": node_id,
            "plane_project_ref_id": project_id,
            "progress": progress,
            "counts": {"total": len(valid), "completed": len(completed), "cancelled": cancelled},
        }

    def capture_execution_snapshots(self) -> int:
        objectives = [node for node in self.list_nodes({"kind": "objective"}) if node.get("plane_project_ref_id")]
        captured = 0
        with self.transaction() as connection:
            for objective in objectives:
                status = self.execution_status(objective["id"])
                connection.execute(
                    "INSERT INTO progress_snapshots(id,node_id,captured_at,execution_progress,counts_json,calculation_version) VALUES (?,?,?,?,?,?)",
                    (new_id(), objective["id"], now(), status["progress"], json.dumps(status["counts"], separators=(",", ":")), "execution-v2"),
                )
                captured += 1
        return captured

    def create_execution_run(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        chart_id = str(values.get("work_chart_id") or "").strip()
        chart_version = str(values.get("work_chart_version") or "").strip()
        objective_id = str(values.get("objective_id") or "").strip()
        item_ids = [str(item).strip() for item in values.get("work_chart_item_ids") or [] if str(item).strip()]
        if not chart_id or not chart_version or not objective_id:
            raise ValueError("Work Chart id, version, and Objective are required")
        objective = self.get_node(objective_id)
        if not objective or objective["kind"] != "objective" or not objective.get("plane_project_ref_id"):
            raise ValueError("Execution runs require an Objective linked to a Plane project")
        request_hash = hashlib.sha256(json.dumps(sorted(item_ids), separators=(",", ":")).encode()).hexdigest()
        timestamp = now()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM strategy_execution_runs WHERE work_chart_id=? AND work_chart_version=? AND objective_id=?",
                (chart_id, chart_version, objective_id),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("The existing execution run has a different Work Chart item set")
                return self._row(existing)
            identifier = new_id()
            connection.execute(
                "INSERT INTO strategy_execution_runs(id,work_chart_id,work_chart_version,objective_id,plane_project_ref_id,status,request_hash,started_at) VALUES (?,?,?,?,?,?,?,?)",
                (identifier, chart_id, chart_version, objective_id, objective["plane_project_ref_id"], "running", request_hash, timestamp),
            )
            for item_id in item_ids:
                connection.execute(
                    "INSERT INTO strategy_execution_items(id,run_id,work_chart_item_id,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (new_id(), identifier, item_id, "pending", timestamp, timestamp),
                )
            self._audit(connection, actor, "strategy_execution.started", "strategy_execution_run", identifier, {"work_chart_id": chart_id, "work_chart_version": chart_version, "objective_id": objective_id, "item_count": len(item_ids)})
            return self._row(connection.execute("SELECT * FROM strategy_execution_runs WHERE id=?", (identifier,)).fetchone())

    def record_execution_item(self, run_id: str, item_id: str, plane_work_item_ref_id: str, *, actor: str) -> dict[str, Any]:
        with self.transaction() as connection:
            current = connection.execute(
                "SELECT * FROM strategy_execution_items WHERE run_id=? AND work_chart_item_id=?", (run_id, item_id)
            ).fetchone()
            if not current:
                raise KeyError("Work Chart item is not part of the execution run")
            if current["plane_work_item_ref_id"] and current["plane_work_item_ref_id"] != plane_work_item_ref_id:
                raise ValueError("Work Chart item is already mapped to a different Plane work item")
            if connection.execute(
                "UPDATE strategy_execution_items SET plane_work_item_ref_id=?,status='complete',error=NULL,updated_at=? WHERE run_id=? AND work_chart_item_id=?",
                (plane_work_item_ref_id, now(), run_id, item_id),
            ).rowcount != 1:
                raise KeyError("Work Chart item is not part of the execution run")
            row = connection.execute(
                "SELECT * FROM strategy_execution_items WHERE run_id=? AND work_chart_item_id=?", (run_id, item_id)
            ).fetchone()
            self._audit(connection, actor, "strategy_execution.item_recorded", "strategy_execution_item", row["id"], {"plane_work_item_ref_id": plane_work_item_ref_id})
            return self._row(row)

    def complete_execution_run(self, run_id: str, *, actor: str, error: str | None = None) -> dict[str, Any]:
        with self.transaction() as connection:
            status = "failed" if error else "complete"
            if connection.execute(
                "UPDATE strategy_execution_runs SET status=?,error=?,completed_at=? WHERE id=?",
                (status, error, now(), run_id),
            ).rowcount != 1:
                raise KeyError("Execution run not found")
            row = connection.execute("SELECT * FROM strategy_execution_runs WHERE id=?", (run_id,)).fetchone()
            self._audit(connection, actor, "strategy_execution.completed", "strategy_execution_run", run_id, {"status": status, "error": error})
            return self._row(row)

    def get_execution_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM strategy_execution_runs WHERE id=?", (run_id,)).fetchone()
            return self._row(row) if row else None

    def list_execution_items(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [self._row(row) for row in connection.execute("SELECT * FROM strategy_execution_items WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()]

    def save_execution_payload(self, run_id: str, payload: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO strategy_execution_payloads(run_id,payload_json,created_at) VALUES (?,?,?)",
                (run_id, json.dumps(payload, separators=(",", ":"), sort_keys=True), now()),
            )

    def get_execution_payload(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM strategy_execution_payloads WHERE run_id=?", (run_id,)).fetchone()
            return json.loads(row["payload_json"]) if row else None

    def broken_execution_mappings(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT r.id AS run_id,r.objective_id,i.work_chart_item_id,i.plane_work_item_ref_id "
                "FROM strategy_execution_items i JOIN strategy_execution_runs r ON r.id=i.run_id "
                "LEFT JOIN plane_objects po ON po.kind='work_item' AND po.remote_id=i.plane_work_item_ref_id "
                "WHERE i.plane_work_item_ref_id IS NOT NULL AND (po.id IS NULL OR po.deleted_at IS NOT NULL) "
                "ORDER BY r.started_at,i.created_at"
            ).fetchall()
            return [self._row(row) for row in rows]

    def prepare_delivery(self, token: str, payload: dict[str, Any], *, actor: str, expires_at: str) -> dict[str, Any]:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO strategy_delivery_preparations(token,payload_json,request_hash,expires_at,created_at) VALUES (?,?,?,?,?)",
                (token, encoded, hashlib.sha256(encoded.encode()).hexdigest(), expires_at, now()),
            )
            self._audit(connection, actor, "strategy_delivery.prepared", "strategy_delivery_preparation", token, {"expires_at": expires_at})
            return {"token": token, "expires_at": expires_at, "status": "prepared"}

    def consume_delivery_preparation(self, token: str, *, actor: str) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM strategy_delivery_preparations WHERE token=?", (token,)).fetchone()
            if not row:
                raise KeyError("Delivery preparation not found")
            if row["status"] != "prepared":
                raise ValueError("Delivery preparation was already applied")
            if row["expires_at"] <= now():
                raise ValueError("Delivery preparation has expired")
            connection.execute("UPDATE strategy_delivery_preparations SET status='applying', applied_at=? WHERE token=?", (now(), token))
            self._audit(connection, actor, "strategy_delivery.applying", "strategy_delivery_preparation", token, {})
            result = self._row(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result

    def finish_delivery_preparation(self, token: str, *, actor: str, error: str | None = None) -> None:
        with self.transaction() as connection:
            status = "failed" if error else "complete"
            connection.execute("UPDATE strategy_delivery_preparations SET status=? WHERE token=?", (status, token))
            self._audit(connection, actor, f"strategy_delivery.{status}", "strategy_delivery_preparation", token, {"error": error})

    def upsert_plane_object(self, connection_id: str, remote: dict[str, Any], kind: str) -> dict[str, Any]:
        remote_id=str(remote.get("id") or "")
        if not remote_id:
            raise ValueError("Plane object has no id")
        timestamp=now()
        with self.transaction() as connection:
            existing=connection.execute("SELECT id FROM plane_objects WHERE connection_id=? AND kind=? AND remote_id=?",(connection_id,kind,remote_id)).fetchone()
            values=(remote.get("project") or remote.get("project_id"),str(remote.get("name") or remote.get("title") or ""),self._state_group(connection,remote),remote.get("start_date"),remote.get("target_date"),remote.get("completed_at"),remote.get("updated_at"),timestamp,json.dumps(remote,separators=(",",":")))
            if existing:
                connection.execute("UPDATE plane_objects SET project_ref_id=?,title=?,state_group=?,start_date=?,target_date=?,completed_at=?,source_updated_at=?,synced_at=?,raw_json=?,deleted_at=NULL WHERE id=?",(*values,existing["id"]))
                identifier=existing["id"]
            else:
                identifier=new_id()
                connection.execute("INSERT INTO plane_objects(id,connection_id,remote_id,kind,project_ref_id,title,state_group,start_date,target_date,completed_at,source_updated_at,synced_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(identifier,connection_id,remote_id,kind,*values))
            return self._row(connection.execute("SELECT * FROM plane_objects WHERE id=?",(identifier,)).fetchone())

    def mark_missing_plane_objects(
        self, connection_id: str, kind: str, remote_ids: set[str], project_ref_id: str | None = None
    ) -> int:
        clauses = ["connection_id=?", "kind=?", "deleted_at IS NULL"]
        params: list[Any] = [connection_id, kind]
        if project_ref_id is not None:
            clauses.append("project_ref_id=?")
            params.append(project_ref_id)
        if remote_ids:
            clauses.append(f"remote_id NOT IN ({','.join('?' for _ in remote_ids)})")
            params.extend(sorted(remote_ids))
        with self.transaction() as connection:
            return connection.execute(
                f"UPDATE plane_objects SET deleted_at=?, synced_at=? WHERE {' AND '.join(clauses)}",
                [now(), now(), *params],
            ).rowcount

    def link_node_to_plane(self, node_id: str, object_id: str, role: str = "representative") -> None:
        with self.transaction() as connection:
            timestamp=now()
            connection.execute("INSERT OR IGNORE INTO strategy_plane_links(id,node_id,plane_object_id,role,created_at,updated_at) VALUES (?,?,?,?,?,?)",(new_id(),node_id,object_id,role,timestamp,timestamp))

    def representative_remote_id(self, node_id: str) -> str | None:
        with self._connect() as connection:
            row=connection.execute("SELECT po.remote_id FROM strategy_plane_links spl JOIN plane_objects po ON po.id=spl.plane_object_id WHERE spl.node_id=? AND spl.role='representative' AND po.deleted_at IS NULL ORDER BY spl.created_at DESC LIMIT 1",(node_id,)).fetchone()
            return str(row["remote_id"]) if row else None

    def dashboard(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        nodes=self.list_nodes(filters)
        with self._connect() as connection:
            metrics=[self._row(row) for row in connection.execute("SELECT m.*, (SELECT max(x.observed_at) FROM metric_checkins x WHERE x.metric_id=m.id) AS last_checkin_at, (SELECT x.value FROM metric_checkins x WHERE x.metric_id=m.id ORDER BY x.observed_at DESC LIMIT 1) AS current_value FROM metric_definitions m").fetchall()]
            objects=[self._row(row) for row in connection.execute("SELECT * FROM plane_objects WHERE deleted_at IS NULL ORDER BY synced_at DESC").fetchall()]
            links=[self._row(row) for row in connection.execute("SELECT * FROM strategy_plane_links").fetchall()]
            queues={"inbox_pending":connection.execute("SELECT count(*) FROM sync_inbox WHERE status!='complete'").fetchone()[0],"outbox_pending":connection.execute("SELECT count(*) FROM sync_outbox WHERE status!='complete'").fetchone()[0]}
        work_items=[item for item in objects if item["kind"]=="work_item"]
        states={}
        for item in work_items: states[item.get("state_group") or "unknown"]=states.get(item.get("state_group") or "unknown",0)+1
        return {"nodes":nodes,"metrics":metrics,"plane_objects":objects,"links":links,"work_item_states":states,"sync":queues,"generated_at":now()}

    def sync_status(self) -> dict[str, list[dict[str, Any]]]:
        """Return queue diagnostics without exposing payloads or credentials."""
        with self._connect() as connection:
            inbox=[self._row(row) for row in connection.execute("SELECT status,attempts,error,updated_at FROM sync_inbox WHERE status!='complete' ORDER BY updated_at").fetchall()]
            outbox=[self._row(row) for row in connection.execute("SELECT status,attempts,error,updated_at FROM sync_outbox WHERE status!='complete' ORDER BY updated_at").fetchall()]
        return {"inbox":inbox,"outbox":outbox}

    def _enqueue(self, connection: sqlite3.Connection, node_id: str, operation: str, payload: dict[str, Any], depends_on: str | None = None) -> str:
        identifier,timestamp=new_id(),now()
        connection.execute("INSERT INTO sync_outbox(id,node_id,operation,idempotency_key,payload_json,depends_on,next_attempt_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",(identifier,node_id,operation,f"{operation}:{node_id}",json.dumps(payload,separators=(",",":")),depends_on,timestamp,timestamp,timestamp))
        return identifier

    def _validate_parent(self, connection: sqlite3.Connection, parent_id: str | None, kind: str, identifier: str) -> None:
        if not parent_id: return
        parent=connection.execute("SELECT id,kind,parent_id,plane_project_ref_id FROM strategy_nodes WHERE id=? AND archived_at IS NULL",(parent_id,)).fetchone()
        if not parent: raise ValueError("Strategy parent not found")
        if parent_id==identifier: raise ValueError("A strategy node cannot be its own parent")
        allowed={"north_star":{"pillar"},"pillar":{"pillar","objective"},"objective":{"objective","key_result","initiative"},"key_result":{"initiative"},"initiative":set()}
        if kind not in allowed.get(parent["kind"],set()): raise ValueError("That node type cannot be placed below this parent")
        cursor=parent
        while cursor and cursor["parent_id"]:
            if cursor["parent_id"]==identifier: raise ValueError("The move would create a strategy cycle")
            cursor=connection.execute("SELECT id,parent_id FROM strategy_nodes WHERE id=?",(cursor["parent_id"],)).fetchone()

    def _inherited_project(self, connection: sqlite3.Connection, parent_id: str | None) -> str | None:
        while parent_id:
            row=connection.execute("SELECT parent_id,plane_project_ref_id FROM strategy_nodes WHERE id=?",(parent_id,)).fetchone()
            if not row: return None
            if row["plane_project_ref_id"]: return str(row["plane_project_ref_id"])
            parent_id=row["parent_id"]
        return None

    @staticmethod
    def _assert_objective_project_available(
        connection: sqlite3.Connection, project_id: str, node_id: str
    ) -> None:
        existing = connection.execute(
            "SELECT id FROM strategy_nodes WHERE kind='objective' AND plane_project_ref_id=? "
            "AND archived_at IS NULL AND id!=? LIMIT 1",
            (project_id, node_id),
        ).fetchone()
        if existing:
            raise ValueError("A Plane project can belong to only one active Objective")

    @staticmethod
    def _record_objective_project_history(
        connection: sqlite3.Connection, objective_id: str, project_id: str, actor: str
    ) -> None:
        connection.execute(
            "INSERT INTO strategy_objective_project_history(id,objective_id,plane_project_ref_id,status,linked_at,actor_ref) VALUES (?,?,?,?,?,?)",
            (new_id(), objective_id, project_id, "active", now(), actor),
        )

    @staticmethod
    def _state_group(connection: sqlite3.Connection, remote: dict[str, Any]) -> str | None:
        state=remote.get("state")
        if isinstance(state,dict):
            return str(state.get("group") or state.get("name") or "").lower() or None
        state_id=str(state or remote.get("state_group") or "")
        if not state_id:
            return None
        row=connection.execute("SELECT raw_json FROM plane_objects WHERE kind='state' AND remote_id=? AND deleted_at IS NULL ORDER BY synced_at DESC LIMIT 1",(state_id,)).fetchone()
        if row:
            definition=json.loads(row["raw_json"])
            return str(definition.get("group") or definition.get("name") or state_id).lower()
        return state_id.lower()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any]:
        return dict(row) if row else {}

    def _audit(self, connection: sqlite3.Connection, actor: str, action: str, entity_type: str, entity_id: str, changes: dict[str, Any]) -> None:
        connection.execute("INSERT INTO audit_events(id,actor_ref,action,entity_type,entity_id,changes_json,created_at) VALUES (?,?,?,?,?,?,?)",(new_id(),actor,action,entity_type,entity_id,json.dumps(changes,separators=(",",":"),default=str),now()))
