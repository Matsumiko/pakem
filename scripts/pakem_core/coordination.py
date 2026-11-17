"""Pakem Multi-Agent Coordination primitives.

The module coordinates cooperative agents through a shared task board, leases,
explicit handoffs, and independent review. It does not authenticate agent IDs,
spawn agents, merge branches, or execute commands; a trusted host runtime must
bind caller identity and enforce the returned state/policy.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA_VERSION = 1
TASK_STATES = {"open", "claimed", "review", "done", "blocked"}
COORDINATION_EVENTS = {
    "team.agent.registered", "team.task.created", "team.task.assigned",
    "team.task.claimed", "team.task.heartbeat", "team.task.released",
    "team.task.handed_off", "team.task.submitted", "team.task.reviewed",
    "team.task.blocked", "team.task.unblocked",
}
AGENT_ROLES = {"worker", "reviewer", "lead", "coordinator", "observer"}
RISKS = {"low", "medium", "high", "critical"}
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{label} must be 1-64 characters: letters, digits, dot, underscore, or hyphen")
    return value


def _text(value: object, label: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} is required")
    if len(value) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    return value


def _string_list(values: object, label: str, maximum: int = 100) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > maximum:
        raise ValueError(f"{label} must be an array with at most {maximum} items")
    result = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 500:
            raise ValueError(f"item {label} must be non-empty text of at most 500 characters")
        item = value.strip()
        if item not in result:
            result.append(item)
    return result


def team_dir(root: Path) -> Path:
    return root / ".pakem" / "team"


def board_path(root: Path) -> Path:
    return team_dir(root) / "board.json"


def events_path(root: Path) -> Path:
    return team_dir(root) / "events.jsonl"


def storage_config_path(root: Path) -> Path:
    return team_dir(root) / "storage.json"


def sqlite_path(root: Path) -> Path:
    return team_dir(root) / "team.sqlite3"


def _storage_backend(root: Path) -> str:
    path = storage_config_path(root)
    if path.is_symlink():
        raise ValueError("team storage config must not be a symlink")
    if not path.is_file():
        return "jsonl"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"team storage config is invalid: {exc}") from exc
    if not isinstance(config, dict) or config.get("schemaVersion") != 1:
        raise ValueError("team storage config must use schemaVersion 1")
    backend = config.get("backend")
    if backend not in {"jsonl", "sqlite"}:
        raise ValueError("team storage backend must be jsonl or sqlite")
    if backend == "sqlite" and config.get("backupFilesRetained") is not True:
        raise ValueError("SQLite storage config must mark JSON backups as retained")
    return backend


def _sqlite_connect(root: Path, create: bool = True) -> sqlite3.Connection:
    path = sqlite_path(root)
    if path.is_symlink():
        raise ValueError("team SQLite database must not be a symlink")
    if not create and not path.is_file():
        raise ValueError("SQLite backend is configured but the database is missing; restore from backup before continuing")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("""CREATE TABLE IF NOT EXISTS pakem_state (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        board_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS pakem_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        occurred_at TEXT NOT NULL,
        event_name TEXT NOT NULL,
        event_json TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_pakem_events_name ON pakem_events(event_name)")
    # Team records may contain task descriptions and operational metadata.
    # Keep the database and SQLite sidecar files private on POSIX systems.
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if candidate.exists():
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                pass
    return connection


def _make_coordination_event(event: str, payload: dict) -> dict:
    if event not in COORDINATION_EVENTS:
        raise ValueError(f"unknown coordination event: {event}")
    actor_name = (payload.get("actorId") or payload.get("by") or payload.get("reviewerId")
                  or payload.get("fromAgent") or payload.get("agentId") or "pakem-team")
    return {
        "protocol": "pakem", "protocol_version": "1.0", "event_id": str(uuid.uuid4()),
        "event": event, "occurred_at": now(), "session_id": None,
        "actor": {"type": "system" if actor_name == "pakem-team" else "agent", "name": str(actor_name)},
        "payload": payload,
    }


@contextlib.contextmanager
def _board_lock(root: Path):
    """Cross-process advisory lock (flock on POSIX, msvcrt on Windows)."""
    directory = team_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".board.lock"
    stream = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if stream.read(1) == b"":
                stream.seek(0)
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _default_board() -> dict:
    stamp = now()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "boardId": str(uuid.uuid4()),
        "revision": 1,
        "createdAt": stamp,
        "updatedAt": stamp,
        "agents": {},
        "tasks": {},
    }


def _load_board_unlocked(root: Path, create: bool = False) -> dict | None:
    if _storage_backend(root) == "sqlite":
        connection = _sqlite_connect(root, create=create)
        try:
            row = connection.execute("SELECT board_json FROM pakem_state WHERE singleton=1").fetchone()
            if row is None:
                if not create:
                    return None
                board = _default_board()
                connection.execute("INSERT INTO pakem_state(singleton, board_json, updated_at) VALUES(1, ?, ?)",
                                   (json.dumps(board, ensure_ascii=False), board["updatedAt"]))
                return board
            try:
                board = json.loads(row["board_json"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid SQLite team board: {exc}") from exc
            errors = validate_board(board)
            if errors:
                raise ValueError("invalid SQLite team board: " + "; ".join(errors))
            return board
        finally:
            connection.close()
    path = board_path(root)
    if not path.is_file():
        if not create:
            return None
        board = _default_board()
        _atomic_json(path, board)
        return board
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid team board: {exc}") from exc
    errors = validate_board(board)
    if errors:
        raise ValueError("invalid team board: " + "; ".join(errors))
    return board


def validate_board(board: object) -> list[str]:
    if not isinstance(board, dict):
        return ["board must be an object"]
    errors = []
    if board.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1")
    if not isinstance(board.get("boardId"), str) or not board.get("boardId"):
        errors.append("boardId is required")
    if not isinstance(board.get("revision"), int) or isinstance(board.get("revision"), bool) or board.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")
    for key in ("agents", "tasks"):
        if not isinstance(board.get(key), dict):
            errors.append(f"{key} must be an object")
    if errors:
        return errors
    for agent_id, agent in board["agents"].items():
        try:
            _safe_id(agent_id, "agent ID")
        except ValueError as exc:
            errors.append(str(exc))
        if not isinstance(agent, dict) or agent.get("agentId") != agent_id:
            errors.append(f"invalid agent {agent_id}")
            continue
        if agent.get("role") not in AGENT_ROLES:
            errors.append(f"invalid role for agent {agent_id}")
        capabilities = agent.get("capabilities", [])
        if not isinstance(capabilities, list) or any(not isinstance(x, str) for x in capabilities):
            errors.append(f"capabilities for agent {agent_id} must be an array of strings")
    for task_id, task in board["tasks"].items():
        try:
            _safe_id(task_id, "task ID")
        except ValueError as exc:
            errors.append(str(exc))
        if not isinstance(task, dict) or task.get("taskId") != task_id:
            errors.append(f"invalid task {task_id}")
            continue
        if task.get("state") not in TASK_STATES:
            errors.append(f"invalid state for task {task_id}")
        if task.get("risk", "medium") not in RISKS:
            errors.append(f"invalid risk for task {task_id}")
        dependencies = task.get("dependsOn", [])
        if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
            errors.append(f"dependsOn for task {task_id} must be an array of strings")
    for task_id, task in board["tasks"].items():
        if not isinstance(task, dict):
            continue
        for dependency in task.get("dependsOn", []):
            if isinstance(dependency, str) and dependency not in board["tasks"]:
                errors.append(f"dependency {dependency} for {task_id} not found")
        assigned = task.get("assignedAgent")
        owner = task.get("ownerAgent")
        if assigned is not None and assigned not in board["agents"]:
            errors.append(f"assignedAgent {assigned} for {task_id} is not registered")
        if owner is not None and owner not in board["agents"]:
            errors.append(f"ownerAgent {owner} for {task_id} is not registered")
        if task.get("state") == "claimed":
            if not owner or not task.get("leaseExpiresAt"):
                errors.append(f"claimed task {task_id} must have ownerAgent and leaseExpiresAt")
            elif isinstance(task.get("leaseExpiresAt"), str):
                try:
                    _parse_time(task["leaseExpiresAt"])
                except (TypeError, ValueError):
                    errors.append(f"leaseExpiresAt for {task_id} is not a valid date-time")
        elif owner is not None or task.get("leaseExpiresAt") is not None:
            errors.append(f"non-claimed task {task_id} must not have an active owner/lease")
        if task.get("state") == "review" and not isinstance(task.get("submission"), dict):
            errors.append(f"review task {task_id} must have a submission")
        if task.get("state") == "done":
            review = task.get("lastReview")
            if not isinstance(task.get("submission"), dict) or not isinstance(review, dict) or review.get("decision") != "approve":
                errors.append(f"done task {task_id} must have a submission and an approve review")
    if not errors:
        try:
            _validate_dependency_graph(board["tasks"])
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return errors


def _event_unlocked(root: Path, event: str, payload: dict) -> None:
    record = _make_coordination_event(event, payload)
    data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    path = events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("event ledger write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _commit(root: Path, board: dict, event: str, payload: dict) -> dict:
    board["revision"] += 1
    board["updatedAt"] = now()
    if _storage_backend(root) == "sqlite":
        record = _make_coordination_event(event, payload)
        connection = _sqlite_connect(root, create=False)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""INSERT INTO pakem_state(singleton, board_json, updated_at)
                VALUES(1, ?, ?) ON CONFLICT(singleton) DO UPDATE SET
                board_json=excluded.board_json, updated_at=excluded.updated_at""",
                (json.dumps(board, ensure_ascii=False, separators=(",", ":")), board["updatedAt"]))
            connection.execute("INSERT INTO pakem_events(event_id, occurred_at, event_name, event_json) VALUES(?, ?, ?, ?)",
                               (record["event_id"], record["occurred_at"], event,
                                json.dumps(record, ensure_ascii=False, separators=(",", ":"))))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return board
    _atomic_json(board_path(root), board)
    try:
        _event_unlocked(root, event, payload)
    except OSError as exc:
        raise RuntimeError(f"state was saved, but the event ledger write failed: {exc}") from exc
    return board


def storage_info(root: Path) -> dict:
    backend = _storage_backend(root)
    result = {"backend": backend, "supported_backends": ["jsonl", "sqlite"],
              "transactional_state_and_events": backend == "sqlite"}
    if backend == "sqlite":
        result["database"] = sqlite_path(root).relative_to(root).as_posix()
        connection = _sqlite_connect(root, create=False)
        try:
            result["event_count"] = connection.execute("SELECT COUNT(*) FROM pakem_events").fetchone()[0]
        finally:
            connection.close()
    else:
        result["board"] = board_path(root).relative_to(root).as_posix()
        result["event_ledger"] = events_path(root).relative_to(root).as_posix()
    return result


def backup_sqlite(root: Path, output: str | Path, force: bool = False) -> dict:
    """Create a consistent SQLite online backup without stopping the coordinator."""
    if _storage_backend(root) != "sqlite":
        raise ValueError("online SQLite backup is only available when the sqlite backend is active")
    destination = Path(output).expanduser().resolve()
    if destination == sqlite_path(root).resolve():
        raise ValueError("backup output must not be the active database")
    if destination.exists() and not force:
        raise ValueError(f"backup file already exists: {destination}; use --force to replace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    os.unlink(temp_name)
    temporary = Path(temp_name)
    try:
        with _board_lock(root):
            source_connection = _sqlite_connect(root, create=False)
            target_connection = sqlite3.connect(temporary)
            try:
                source_connection.backup(target_connection)
                target_connection.commit()
            finally:
                target_connection.close()
                source_connection.close()
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"created": True, "path": str(destination), "backend": "sqlite", "consistent_snapshot": True}


def migrate_storage(root: Path, target: str = "sqlite") -> dict:
    """Migrate the local JSON board/ledger to SQLite without deleting originals."""
    if target != "sqlite":
        raise ValueError("only migration to sqlite is supported; the original JSON files are retained as backup")
    with _board_lock(root):
        current = _storage_backend(root)
        if current == "sqlite":
            return {"migrated": False, "backend": "sqlite", "reason": "already_using_sqlite"}
        board = _load_board_unlocked(root, create=True)
        event_source = read_events(root, limit=0)
        old_events = event_source.get("events", [])
        skipped_corrupt_events = len(event_source.get("corruptLines", []))
        db_path = sqlite_path(root)
        if db_path.exists() and db_path.stat().st_size:
            raise ValueError(f"SQLite database already exists; not overwritten: {db_path}")
        connection = _sqlite_connect(root)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR REPLACE INTO pakem_state(singleton, board_json, updated_at) VALUES(1, ?, ?)",
                               (json.dumps(board, ensure_ascii=False, separators=(",", ":")), board["updatedAt"]))
            for record in old_events:
                connection.execute("INSERT OR IGNORE INTO pakem_events(event_id, occurred_at, event_name, event_json) VALUES(?, ?, ?, ?)",
                                   (record.get("event_id") or str(uuid.uuid4()), record.get("occurred_at") or now(),
                                    record["event"], json.dumps(record, ensure_ascii=False, separators=(",", ":"))))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        try:
            _atomic_json(storage_config_path(root), {"schemaVersion": 1, "backend": "sqlite",
                                                        "migratedAt": now(), "backupFilesRetained": True})
        except OSError as exc:
            # The JSON source remains authoritative until the backend marker is durable.
            for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
            raise RuntimeError(f"database migration was created but the backend marker write failed; JSON files remain authoritative: {exc}") from exc
        return {"migrated": True, "backend": "sqlite", "agents": len(board["agents"]),
                "tasks": len(board["tasks"]), "events": len(old_events),
                "corrupt_events_skipped": skipped_corrupt_events,
                "database": db_path.relative_to(root).as_posix(),
                "json_backups_retained": [x.relative_to(root).as_posix() for x in (board_path(root), events_path(root)) if x.exists()]}


def initialize(root: Path) -> dict:
    with _board_lock(root):
        board = _load_board_unlocked(root, create=True)
        return board


def status(root: Path) -> dict:
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None:
            return {"initialized": False, "agents": [], "tasks": [], "summary": {"open": 0, "claimed": 0, "review": 0, "done": 0, "blocked": 0}}
        instant = datetime.now(timezone.utc)
        tasks = []
        counts = {state: 0 for state in TASK_STATES}
        for item in board["tasks"].values():
            task = dict(item)
            expired = bool(task.get("leaseExpiresAt") and _parse_time(task["leaseExpiresAt"]) <= instant)
            task["leaseExpired"] = expired
            tasks.append(task)
            counts[task["state"]] += 1
        return {
            "initialized": True,
            "boardId": board["boardId"],
            "revision": board["revision"],
            "updatedAt": board["updatedAt"],
            "agents": sorted(board["agents"].values(), key=lambda x: x["agentId"]),
            "tasks": sorted(tasks, key=lambda x: x["taskId"]),
            "summary": counts,
            "note": "Tasks in state claimed with leaseExpired=true can be re-claimed; status is read without mutation.",
        }


def register_agent(root: Path, agent_id: str, role: str = "worker", display_name: str = "",
                   capabilities: list[str] | None = None, fingerprint: str | None = None) -> dict:
    agent_id = _safe_id(agent_id, "agent ID")
    if role not in AGENT_ROLES:
        raise ValueError("role must be worker, reviewer, lead, coordinator, or observer")
    display_name = _text(display_name or agent_id, "display name", 120)
    caps = _string_list(capabilities or [], "capabilities")
    if fingerprint is not None:
        fingerprint = str(fingerprint).strip().lower()
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("identity fingerprint must be 64 hex characters")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=True)
        existing = board["agents"].get(agent_id)
        stamp = now()
        agent = {
            "agentId": agent_id,
            "displayName": display_name,
            "role": role,
            "capabilities": caps,
            "status": "active",
            "registeredAt": existing.get("registeredAt", stamp) if existing else stamp,
            "lastSeenAt": stamp,
        }
        if fingerprint:
            agent["fingerprint"] = fingerprint
        board["agents"][agent_id] = agent
        _commit(root, board, "team.agent.registered", {"agentId": agent_id, "role": role, "capabilities": caps})
        return agent


def _require_agent(board: dict, agent_id: str) -> dict:
    agent_id = _safe_id(agent_id, "agent ID")
    agent = board["agents"].get(agent_id)
    if not agent or agent.get("status") != "active":
        raise ValueError(f"agent {agent_id} is not registered as active; run team register")
    return agent


def _validate_dependency_graph(tasks: dict) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str):
        if task_id in visiting:
            raise ValueError(f"dependency cycle detected at task {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        task = tasks.get(task_id, {})
        for dep in task.get("dependsOn", []):
            if dep not in tasks:
                raise ValueError(f"dependency {dep} for {task_id} not found")
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for item in tasks:
        visit(item)


def add_task(root: Path, task_id: str, title: str, description: str = "", depends_on: list[str] | None = None,
             files: list[str] | None = None, risk: str = "medium", required_capabilities: list[str] | None = None) -> dict:
    task_id = _safe_id(task_id, "task ID")
    title = _text(title, "title", 200)
    description = _text(description, "description", 2000, required=False)
    deps = [_safe_id(x, "dependency ID") for x in (depends_on or [])]
    if task_id in deps or len(deps) != len(set(deps)):
        raise ValueError("dependencies must not self-reference or duplicate")
    file_list = _string_list(files or [], "files")
    for file_name in file_list:
        normalized = file_name.replace("\\", "/")
        path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(file_name)
        if path.is_absolute() or windows_path.is_absolute() or windows_path.drive or ".." in path.parts or not path.parts or "\x00" in file_name:
            raise ValueError(f"file scope must be a relative path without '..' or an absolute drive: {file_name}")
    if risk not in RISKS:
        raise ValueError("risk must be low, medium, high, or critical")
    caps = _string_list(required_capabilities or [], "required capabilities")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=True)
        if task_id in board["tasks"]:
            raise ValueError(f"task {task_id} already exists")
        missing = [dep for dep in deps if dep not in board["tasks"]]
        if missing:
            raise ValueError("dependencies not present yet: " + ", ".join(missing))
        stamp = now()
        task = {
            "taskId": task_id,
            "title": title,
            "description": description,
            "state": "open",
            "dependsOn": deps,
            "files": file_list,
            "risk": risk,
            "requiredCapabilities": caps,
            "assignedAgent": None,
            "ownerAgent": None,
            "leaseExpiresAt": None,
            "createdAt": stamp,
            "updatedAt": stamp,
            "submission": None,
            "lastReview": None,
            "lastHandoff": None,
            "blockedReason": None,
        }
        board["tasks"][task_id] = task
        _validate_dependency_graph(board["tasks"])
        _commit(root, board, "team.task.created", {"taskId": task_id, "dependsOn": deps, "risk": risk})
        return task


def assign_task(root: Path, task_id: str, agent_id: str, by: str) -> dict:
    task_id, agent_id, by = _safe_id(task_id, "task ID"), _safe_id(agent_id, "agent ID"), _safe_id(by, "coordinator ID")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        coordinator = _require_agent(board, by)
        if coordinator["role"] not in {"lead", "coordinator"}:
            raise ValueError("only agents with role lead/coordinator may assign tasks")
        agent = _require_agent(board, agent_id)
        task = board["tasks"][task_id]
        if task["state"] == "claimed":
            expiry = _parse_time(task["leaseExpiresAt"]) if task.get("leaseExpiresAt") else datetime.now(timezone.utc)
            if expiry > datetime.now(timezone.utc):
                raise ValueError(f"task still has an active lease until {task['leaseExpiresAt']}")
            task.update({"state": "open", "ownerAgent": None, "leaseExpiresAt": None})
        elif task["state"] not in {"open", "blocked"}:
            raise ValueError(f"task cannot be assigned while state={task['state']}")
        missing_caps = sorted(set(task.get("requiredCapabilities", [])) - set(agent.get("capabilities", [])))
        if missing_caps:
            raise ValueError("agent is missing capabilities: " + ", ".join(missing_caps))
        task["assignedAgent"] = agent_id
        task["updatedAt"] = now()
        _commit(root, board, "team.task.assigned", {"taskId": task_id, "agentId": agent_id, "by": by})
        return task


def _deps_ready(board: dict, task: dict) -> list[str]:
    return [dep for dep in task.get("dependsOn", []) if board["tasks"][dep]["state"] != "done"]


def claim_task(root: Path, task_id: str, agent_id: str, lease_seconds: int = 900) -> dict:
    task_id, agent_id = _safe_id(task_id, "task ID"), _safe_id(agent_id, "agent ID")
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 30 <= lease_seconds <= 86400:
        raise ValueError("lease-seconds must be an integer 30..86400")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        agent = _require_agent(board, agent_id)
        task = board["tasks"][task_id]
        if task["state"] == "done":
            raise ValueError("task is already done")
        if task["state"] == "review":
            raise ValueError("task is awaiting review")
        if task["state"] == "blocked":
            raise ValueError("task is blocked; unblock it first")
        if task.get("assignedAgent") and task["assignedAgent"] != agent_id:
            raise ValueError(f"task is assigned to {task['assignedAgent']}")
        missing_caps = sorted(set(task.get("requiredCapabilities", [])) - set(agent.get("capabilities", [])))
        if missing_caps:
            raise ValueError("agent is missing capabilities: " + ", ".join(missing_caps))
        blockers = _deps_ready(board, task)
        if blockers:
            raise ValueError("dependencies not done yet: " + ", ".join(blockers))
        stamp = datetime.now(timezone.utc)
        if task["state"] == "claimed":
            expiry = _parse_time(task["leaseExpiresAt"]) if task.get("leaseExpiresAt") else stamp
            if expiry > stamp and task.get("ownerAgent") != agent_id:
                raise ValueError(f"task is claimed by {task.get('ownerAgent')} until {task.get('leaseExpiresAt')}")
        task["state"] = "claimed"
        task["ownerAgent"] = agent_id
        task["leaseExpiresAt"] = (stamp + timedelta(seconds=lease_seconds)).astimezone().isoformat(timespec="seconds")
        task["updatedAt"] = now()
        agent["lastSeenAt"] = now()
        _commit(root, board, "team.task.claimed", {"taskId": task_id, "agentId": agent_id, "leaseExpiresAt": task["leaseExpiresAt"]})
        return task


def heartbeat(root: Path, task_id: str, agent_id: str, lease_seconds: int = 900) -> dict:
    task_id, agent_id = _safe_id(task_id, "task ID"), _safe_id(agent_id, "agent ID")
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 30 <= lease_seconds <= 86400:
        raise ValueError("lease-seconds must be an integer 30..86400")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        agent = _require_agent(board, agent_id)
        task = board["tasks"][task_id]
        if task["state"] != "claimed" or task.get("ownerAgent") != agent_id:
            raise ValueError("only the active claim owner may heartbeat")
        if not task.get("leaseExpiresAt") or _parse_time(task["leaseExpiresAt"]) <= datetime.now(timezone.utc):
            raise ValueError("lease has expired; re-claim the task")
        task["leaseExpiresAt"] = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).astimezone().isoformat(timespec="seconds")
        task["updatedAt"] = now()
        agent["lastSeenAt"] = now()
        _commit(root, board, "team.task.heartbeat", {"taskId": task_id, "agentId": agent_id, "leaseExpiresAt": task["leaseExpiresAt"]})
        return task


def release_task(root: Path, task_id: str, agent_id: str, reason: str) -> dict:
    task_id, agent_id = _safe_id(task_id, "task ID"), _safe_id(agent_id, "agent ID")
    reason = _text(reason, "reason", 500)
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        task = board["tasks"][task_id]
        if task["state"] != "claimed" or task.get("ownerAgent") != agent_id:
            raise ValueError("only the claim owner may release the task")
        task.update({"state": "open", "ownerAgent": None, "leaseExpiresAt": None, "updatedAt": now(), "lastReleaseReason": reason})
        _commit(root, board, "team.task.released", {"taskId": task_id, "agentId": agent_id})
        return task


def handoff_task(root: Path, task_id: str, from_agent: str, to_agent: str, note: str) -> dict:
    task_id = _safe_id(task_id, "task ID")
    from_agent = _safe_id(from_agent, "from-agent")
    to_agent = _safe_id(to_agent, "to-agent")
    note = _text(note, "handoff note", 1000)
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        _require_agent(board, to_agent)
        task = board["tasks"][task_id]
        if task["state"] != "claimed" or task.get("ownerAgent") != from_agent:
            raise ValueError("only the active claim owner may hand off")
        missing_caps = sorted(set(task.get("requiredCapabilities", [])) - set(board["agents"][to_agent].get("capabilities", [])))
        if missing_caps:
            raise ValueError("target agent is missing capabilities: " + ", ".join(missing_caps))
        task.update({"state": "open", "ownerAgent": None, "assignedAgent": to_agent,
                     "leaseExpiresAt": None, "updatedAt": now(),
                     "lastHandoff": {"from": from_agent, "to": to_agent, "note": note, "at": now()}})
        _commit(root, board, "team.task.handed_off", {"taskId": task_id, "fromAgent": from_agent, "toAgent": to_agent})
        return task


def submission_payload(task_id: str, agent_id: str, summary: str, evidence: list[str]) -> dict:
    """Canonical payload for the submit signature. Rebuilt during verification."""
    return {"type": "pakem.team.submission.v1", "taskId": task_id, "agentId": agent_id,
            "summary": summary, "evidence": list(evidence)}


def review_payload(task_id: str, reviewer_id: str, decision: str, note: str, implementer: str) -> dict:
    return {"type": "pakem.team.review.v1", "taskId": task_id, "reviewerId": reviewer_id,
            "decision": decision, "note": note, "implementer": implementer}


def tasks_map(board: dict) -> dict:
    """`status()` returns tasks as a list; some callers need a map keyed by taskId."""
    tasks = board.get("tasks") or []
    if isinstance(tasks, dict):
        return tasks
    return {task.get("taskId"): task for task in tasks if task.get("taskId")}


def signed_actions(root: Path) -> list[dict]:
    """Collect every signed action, together with the payload it should have.

    The reconstructed payload is compared with the envelope payload, so changing
    board content (summary, evidence, decision) breaks the signature.
    """
    actions = []
    for task_id, task in tasks_map(status(root)).items():
        submission = task.get("submission") or {}
        if submission.get("signature") and submission.get("agentId"):
            actions.append({
                "kind": "submission", "taskId": task_id, "agentId": submission["agentId"],
                "expected": submission_payload(task_id, submission["agentId"],
                                               submission.get("summary", ""),
                                               submission.get("evidence") or []),
                "envelope": submission["signature"],
            })
        review = task.get("lastReview") or {}
        if review.get("signature"):
            actions.append({
                "kind": "review", "taskId": task_id, "agentId": review.get("reviewerId"),
                "expected": review_payload(task_id, review.get("reviewerId", ""),
                                           review.get("decision", ""), review.get("note", ""),
                                           (task.get("submission") or {}).get("agentId", "")),
                "envelope": review["signature"],
            })
    return actions


def submit_task(root: Path, task_id: str, agent_id: str, summary: str, evidence: list[str],
                signature: dict | None = None) -> dict:
    task_id, agent_id = _safe_id(task_id, "task ID"), _safe_id(agent_id, "agent ID")
    summary = _text(summary, "summary", 2000)
    proofs = _string_list(evidence, "evidence", 50)
    if not proofs:
        raise ValueError("at least one evidence reference is required")
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        _require_agent(board, agent_id)
        task = board["tasks"][task_id]
        if task["state"] != "claimed" or task.get("ownerAgent") != agent_id:
            raise ValueError("only the active claim owner may submit")
        if not task.get("leaseExpiresAt") or _parse_time(task["leaseExpiresAt"]) <= datetime.now(timezone.utc):
            raise ValueError("lease has expired; re-claim before submitting")
        task.update({"state": "review", "ownerAgent": None, "leaseExpiresAt": None, "updatedAt": now(),
                     "submission": {"agentId": agent_id, "summary": summary, "evidence": proofs,
                                    "submittedAt": now(),
                                    **({"signature": signature} if signature else {})}})
        _commit(root, board, "team.task.submitted", {"taskId": task_id, "agentId": agent_id, "evidenceCount": len(proofs)})
        return task


def review_task(root: Path, task_id: str, reviewer_id: str, decision: str, note: str = "",
                signature: dict | None = None) -> dict:
    task_id, reviewer_id = _safe_id(task_id, "task ID"), _safe_id(reviewer_id, "reviewer ID")
    if decision not in {"approve", "rework"}:
        raise ValueError("decision must be approve or rework")
    note = _text(note, "review note", 1000, required=False)
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        reviewer = _require_agent(board, reviewer_id)
        if reviewer["role"] not in {"reviewer", "lead", "coordinator"}:
            raise ValueError("reviewer must have role reviewer, lead, or coordinator")
        task = board["tasks"][task_id]
        if task["state"] != "review" or not task.get("submission"):
            raise ValueError("task is not awaiting review")
        implementer = task["submission"]["agentId"]
        if reviewer_id == implementer:
            raise ValueError("independent review is required: reviewer must not be the implementer")
        result = {"reviewerId": reviewer_id, "decision": decision, "note": note, "reviewedAt": now()}
        if signature:
            result["signature"] = signature
        task["lastReview"] = result
        task["updatedAt"] = now()
        if decision == "approve":
            task["state"] = "done"
        else:
            task["state"] = "open"
            task["assignedAgent"] = implementer
            task["submission"] = None
        _commit(root, board, "team.task.reviewed", {"taskId": task_id, "reviewerId": reviewer_id, "decision": decision})
        return task


def block_task(root: Path, task_id: str, actor_id: str, reason: str) -> dict:
    task_id, actor_id = _safe_id(task_id, "task ID"), _safe_id(actor_id, "actor ID")
    reason = _text(reason, "reason", 1000)
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        _require_agent(board, actor_id)
        task = board["tasks"][task_id]
        if task["state"] == "done":
            raise ValueError("a done task cannot be blocked")
        if task["state"] == "claimed" and task.get("ownerAgent") != actor_id:
            raise ValueError("the task claim belongs to another agent")
        task.update({"state": "blocked", "ownerAgent": None, "leaseExpiresAt": None,
                     "blockedReason": reason, "updatedAt": now()})
        _commit(root, board, "team.task.blocked", {"taskId": task_id, "actorId": actor_id})
        return task


def unblock_task(root: Path, task_id: str, by: str, reason: str) -> dict:
    task_id, by = _safe_id(task_id, "task ID"), _safe_id(by, "coordinator ID")
    reason = _text(reason, "reason", 500)
    with _board_lock(root):
        board = _load_board_unlocked(root, create=False)
        if board is None or task_id not in board["tasks"]:
            raise ValueError(f"task {task_id} not found")
        coordinator = _require_agent(board, by)
        if coordinator["role"] not in {"lead", "coordinator"}:
            raise ValueError("only lead/coordinator may unblock")
        task = board["tasks"][task_id]
        if task["state"] != "blocked":
            raise ValueError("task is not in state blocked")
        task.update({"state": "open", "blockedReason": None, "updatedAt": now(), "unblockedReason": reason})
        _commit(root, board, "team.task.unblocked", {"taskId": task_id, "by": by})
        return task


def _valid_coordination_event(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    actor = record.get("actor")
    return bool(record.get("protocol") == "pakem"
                and record.get("protocol_version") == "1.0"
                and record.get("event") in COORDINATION_EVENTS
                and isinstance(record.get("event_id"), str)
                and isinstance(record.get("occurred_at"), str)
                and isinstance(actor, dict)
                and isinstance(actor.get("name"), str)
                and isinstance(record.get("payload"), dict))


def read_events(root: Path, limit: int = 50) -> dict:
    if limit < 0:
        raise ValueError("limit must not be negative")
    if _storage_backend(root) == "sqlite":
        connection = _sqlite_connect(root, create=False)
        try:
            rows = connection.execute("SELECT seq, event_json FROM pakem_events ORDER BY seq").fetchall()
            valid, corrupt = [], []
            for row in rows:
                try:
                    record = json.loads(row["event_json"])
                    if not _valid_coordination_event(record):
                        raise ValueError("invalid Pakem Protocol v1 envelope")
                    valid.append(record)
                except (json.JSONDecodeError, ValueError):
                    corrupt.append(row["seq"])
            selected = valid[-limit:] if limit else valid
            return {"events": selected, "corruptLines": corrupt, "total": len(rows), "backend": "sqlite"}
        except sqlite3.Error as exc:
            raise ValueError(f"failed to read SQLite coordination ledger: {exc}") from exc
        finally:
            connection.close()
    path = events_path(root)
    if not path.is_file():
        return {"events": [], "corruptLines": [], "total": 0, "backend": "jsonl"}
    events, corrupt = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"failed to read coordination ledger: {exc}") from exc
    for number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
            if not _valid_coordination_event(record):
                raise ValueError("invalid Pakem Protocol v1 envelope")
            events.append(record)
        except (json.JSONDecodeError, ValueError):
            corrupt.append(number)
    selected = events[-limit:] if limit else events
    return {"events": selected, "corruptLines": corrupt, "total": len(events), "backend": "jsonl"}

