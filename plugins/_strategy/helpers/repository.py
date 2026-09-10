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

    SCHEMA_VERSION = "1"

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
        ]
        checksum = hashlib.sha256("\n".join(statements).encode()).hexdigest()
        with self._lock:
            connection = self._connect()
            try:
                for statement in statements:
                    connection.execute(statement)
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
            self._validate_parent(connection, node["parent_id"], kind, identifier)
            if kind in {"objective", "initiative"} and not node["plane_project_ref_id"]:
                inherited = self._inherited_project(connection, node["parent_id"])
                if not inherited:
                    raise ValueError("Objective and Initiative require a Plane project")
                node["plane_project_ref_id"] = inherited
            connection.execute("INSERT INTO strategy_nodes(id,parent_id,kind,title,description,period_id,org_unit_id,owner_ref,sort_order,lifecycle,plane_project_ref_id,created_at,updated_at) VALUES (:id,:parent_id,:kind,:title,:description,:period_id,:org_unit_id,:owner_ref,:sort_order,:lifecycle,:plane_project_ref_id,:created_at,:updated_at)", node)
            if kind in {"objective", "initiative"}:
                self._enqueue(connection, identifier, "create_work_item", {"node_id": identifier})
            self._audit(connection, actor, "strategy_node.created", "strategy_node", identifier, node)
            return self._row(connection.execute("SELECT * FROM strategy_nodes WHERE id=?", (identifier,)).fetchone())

    def update_node(self, identifier: str, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        allowed = {"title", "description", "lifecycle", "owner_ref", "sort_order", "period_id", "org_unit_id", "parent_id"}
        changes = {key: value for key, value in values.items() if key in allowed}
        with self.transaction() as connection:
            current = connection.execute("SELECT * FROM strategy_nodes WHERE id=?", (identifier,)).fetchone()
            if not current:
                raise KeyError("Strategy node not found")
            if "parent_id" in changes:
                self._validate_parent(connection, changes["parent_id"] or None, current["kind"], identifier)
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

    def upsert_plane_object(self, connection_id: str, remote: dict[str, Any], kind: str) -> dict[str, Any]:
        remote_id=str(remote.get("id") or "")
        if not remote_id:
            raise ValueError("Plane object has no id")
        timestamp=now()
        with self.transaction() as connection:
            existing=connection.execute("SELECT id FROM plane_objects WHERE connection_id=? AND kind=? AND remote_id=?",(connection_id,kind,remote_id)).fetchone()
            values=(remote.get("project") or remote.get("project_id"),str(remote.get("name") or remote.get("title") or ""),self._state_group(remote),remote.get("start_date"),remote.get("target_date"),remote.get("completed_at"),remote.get("updated_at"),timestamp,json.dumps(remote,separators=(",",":")))
            if existing:
                connection.execute("UPDATE plane_objects SET project_ref_id=?,title=?,state_group=?,start_date=?,target_date=?,completed_at=?,source_updated_at=?,synced_at=?,raw_json=?,deleted_at=NULL WHERE id=?",(*values,existing["id"]))
                identifier=existing["id"]
            else:
                identifier=new_id()
                connection.execute("INSERT INTO plane_objects(id,connection_id,remote_id,kind,project_ref_id,title,state_group,start_date,target_date,completed_at,source_updated_at,synced_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(identifier,connection_id,remote_id,kind,*values))
            return self._row(connection.execute("SELECT * FROM plane_objects WHERE id=?",(identifier,)).fetchone())

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
    def _state_group(remote: dict[str, Any]) -> str | None:
        state=remote.get("state")
        return str(state.get("group") or state.get("name") or "").lower() if isinstance(state,dict) else str(state or remote.get("state_group") or "").lower() or None

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any]:
        return dict(row) if row else {}

    def _audit(self, connection: sqlite3.Connection, actor: str, action: str, entity_type: str, entity_id: str, changes: dict[str, Any]) -> None:
        connection.execute("INSERT INTO audit_events(id,actor_ref,action,entity_type,entity_id,changes_json,created_at) VALUES (?,?,?,?,?,?,?)",(new_id(),actor,action,entity_type,entity_id,json.dumps(changes,separators=(",",":"),default=str),now()))
