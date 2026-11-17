"""Pakem Autonomous Runtime primitives (stdlib-only, no agent execution).

This module stores workflow state, checkpoints, policy decisions and lifecycle
hook receipts. It deliberately does not execute commands, deploy code, or spawn
agents; those remain responsibilities of a host runtime.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RUNTIME_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
STATES = {
    "initialized", "planning", "ready", "executing", "verifying",
    "blocked", "recovering", "completed", "failed",
}
TERMINAL_STATES = {"completed", "failed"}
TRANSITIONS = {
    "initialized": {"planning", "ready", "blocked", "failed"},
    "planning": {"ready", "blocked", "failed"},
    "ready": {"planning", "executing", "blocked", "failed"},
    "executing": {"verifying", "blocked", "failed", "recovering"},
    "verifying": {"completed", "executing", "blocked", "failed", "recovering"},
    "blocked": {"planning", "ready", "executing", "recovering", "failed"},
    "recovering": {"planning", "ready", "executing", "verifying", "blocked", "failed"},
    "failed": {"recovering", "planning"},
    "completed": set(),
}
CATEGORIES = {"read", "write", "command", "destructive", "deploy", "security", "policy_change", "gate_change"}
RISKS = {"low", "medium", "high", "critical"}
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
AUTONOMY_MODES = {"manual", "assisted", "guarded_autonomous"}
HOOKS = {"session.start", "task.before", "task.after", "verification.before", "session.finish", "handover"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_json(path: Path, data: dict, private: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        if private:
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


def _read_json(path: Path, default=None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid runtime JSON in {path.name}: {exc}") from exc


def runtime_dir(root: Path) -> Path:
    return root / ".pakem" / "runtime"


def workflow_path(root: Path) -> Path:
    return runtime_dir(root) / "workflow.json"


def policy_path(root: Path) -> Path:
    return root / ".pakem" / "POLICY.json"


def approvals_path(root: Path) -> Path:
    return runtime_dir(root) / "approvals.json"


def default_policy() -> dict:
    return {
        "schemaVersion": POLICY_SCHEMA_VERSION,
        "autonomy": "assisted",
        "maxAutonomousRisk": "medium",
        "approvalRequiredFor": ["destructive", "deploy", "security", "policy_change", "gate_change"],
        "deniedCategories": [],
        "approvalTtlSeconds": 900,
        "description": "Normal project edits may proceed; sensitive or high-risk actions require host-mediated approval.",
    }


def validate_policy(policy: object) -> list[str]:
    if not isinstance(policy, dict):
        return ["policy must be a JSON object"]
    errors = []
    allowed = {"schemaVersion", "autonomy", "maxAutonomousRisk", "approvalRequiredFor", "deniedCategories", "approvalTtlSeconds", "description"}
    unknown = sorted(set(policy) - allowed)
    if unknown:
        errors.append("unknown policy fields: " + ", ".join(unknown))
    if not isinstance(policy.get("schemaVersion"), int) or isinstance(policy.get("schemaVersion"), bool) or policy.get("schemaVersion") != POLICY_SCHEMA_VERSION:
        errors.append("schemaVersion must be the integer 1")
    if policy.get("autonomy") not in AUTONOMY_MODES:
        errors.append("autonomy must be manual, assisted, or guarded_autonomous")
    if policy.get("maxAutonomousRisk") not in RISKS:
        errors.append("maxAutonomousRisk is not known")
    for key in ("approvalRequiredFor", "deniedCategories"):
        values = policy.get(key)
        if not isinstance(values, list) or any(v not in CATEGORIES for v in values) or len(values) != len(set(values)):
            errors.append(f"{key} must be an array of unique valid Pakem categories")
    ttl = policy.get("approvalTtlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 30 <= ttl <= 86400:
        errors.append("approvalTtlSeconds must be an integer between 30 and 86400")
    return errors


def ensure_policy(root: Path, template: Path | None = None) -> bool:
    dst = policy_path(root)
    if dst.exists():
        return False
    policy = default_policy()
    if template and template.is_file():
        loaded = _read_json(template)
        if not validate_policy(loaded):
            policy = loaded
    _atomic_json(dst, policy, private=False)
    return True


def load_policy(root: Path) -> dict:
    policy = _read_json(policy_path(root), default_policy())
    errors = validate_policy(policy)
    if errors:
        raise ValueError("POLICY.json is invalid: " + "; ".join(errors))
    return policy


def _git_snapshot(root: Path) -> dict:
    def git(*args):
        try:
            result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                    text=True, timeout=5, check=False)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return {"head": git("rev-parse", "HEAD"),
            "status": (git("status", "--short") or "").splitlines() if git("rev-parse", "--is-inside-work-tree") else None}


def load_workflow(root: Path) -> dict | None:
    workflow = _read_json(workflow_path(root))
    if workflow is None:
        return None
    errors = validate_workflow(workflow)
    if errors:
        raise ValueError("workflow state is invalid: " + "; ".join(errors))
    return workflow


def validate_workflow(workflow: object) -> list[str]:
    if not isinstance(workflow, dict):
        return ["workflow must be a JSON object"]
    errors = []
    if workflow.get("schemaVersion") != RUNTIME_SCHEMA_VERSION:
        errors.append("workflow schemaVersion must be 1")
    if not isinstance(workflow.get("workflowId"), str) or not workflow.get("workflowId"):
        errors.append("workflowId must be a string")
    if workflow.get("state") not in STATES:
        errors.append("workflow state is not known")
    if not isinstance(workflow.get("revision"), int) or isinstance(workflow.get("revision"), bool) or workflow.get("revision", 0) < 1:
        errors.append("workflow revision must be a positive integer")
    if not isinstance(workflow.get("checkpointIds", []), list):
        errors.append("checkpointIds must be an array")
    return errors


def init_workflow(root: Path, goal: str = "", new: bool = False) -> dict:
    current = load_workflow(root)
    path = workflow_path(root)
    if current and not new:
        raise ValueError(f"workflow already exists (state={current['state']}); use runtime status or --new")
    if current and current["state"] not in TERMINAL_STATES:
        raise ValueError("an active workflow must not be overwritten; complete it or mark it failed before --new")
    if current:
        archive = runtime_dir(root) / "archives" / f"{current['workflowId']}.json"
        if not archive.exists():
            _atomic_json(archive, current)
    workflow = {
        "schemaVersion": RUNTIME_SCHEMA_VERSION,
        "workflowId": str(uuid.uuid4()),
        "state": "planning",
        "goal": goal.strip(),
        "revision": 1,
        "createdAt": now(),
        "updatedAt": now(),
        "activeSessionId": None,
        "currentTaskId": None,
        "checkpointIds": [],
        "lastTransition": {"from": None, "to": "planning", "reason": "workflow initialized", "at": now()},
    }
    _atomic_json(path, workflow)
    return workflow


def _checkpoint(root: Path, workflow: dict, label: str) -> dict:
    cid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    snapshot = {
        "schemaVersion": 1,
        "checkpointId": cid,
        "workflowId": workflow["workflowId"],
        "label": label[:120],
        "createdAt": now(),
        "workflow": workflow,
        "repository": _git_snapshot(root),
    }
    directory = runtime_dir(root) / "checkpoints"
    _atomic_json(directory / f"{cid}.json", snapshot)
    ids = list(workflow.get("checkpointIds", []))
    ids.append(cid)
    workflow["checkpointIds"] = ids[-100:]
    return snapshot


def create_checkpoint(root: Path, label: str = "manual") -> dict:
    workflow = load_workflow(root)
    if not workflow:
        raise ValueError("no workflow yet; run pakem runtime init")
    snap = _checkpoint(root, workflow, label or "manual")
    workflow["revision"] += 1
    workflow["updatedAt"] = now()
    workflow["lastCheckpointId"] = snap["checkpointId"]
    _atomic_json(workflow_path(root), workflow)
    return snap


def transition_workflow(root: Path, target: str, reason: str = "", task_id: str | None = None) -> tuple[dict, dict | None]:
    workflow = load_workflow(root)
    if not workflow:
        raise ValueError("no workflow yet; run pakem runtime init")
    if target not in STATES:
        raise ValueError(f"unknown state: {target}")
    source = workflow["state"]
    if target not in TRANSITIONS[source]:
        raise ValueError(f"transition not allowed: {source} -> {target}")
    snap = None
    if source in {"executing", "verifying", "blocked", "recovering"}:
        snap = _checkpoint(root, workflow, f"before-{source}-to-{target}")
    workflow["state"] = target
    workflow["revision"] += 1
    workflow["updatedAt"] = now()
    workflow["lastTransition"] = {"from": source, "to": target,
                                   "reason": reason.strip()[:500], "at": now()}
    if task_id is not None:
        workflow["currentTaskId"] = task_id
    if target == "completed":
        workflow["completedAt"] = now()
    _atomic_json(workflow_path(root), workflow)
    return workflow, snap


def _safe_checkpoint_path(root: Path, checkpoint_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9T_-]{1,80}", checkpoint_id):
        raise ValueError("checkpoint ID is not valid")
    return runtime_dir(root) / "checkpoints" / f"{checkpoint_id}.json"


def recover_workflow(root: Path, checkpoint_id: str | None = None) -> tuple[dict, dict]:
    workflow = load_workflow(root)
    if not workflow:
        raise ValueError("no workflow yet; run pakem runtime init")
    ids = workflow.get("checkpointIds", [])
    selected = checkpoint_id or (ids[-1] if ids else None)
    if not selected:
        raise ValueError("no checkpoint to recover from")
    checkpoint = _read_json(_safe_checkpoint_path(root, selected))
    if not isinstance(checkpoint, dict) or checkpoint.get("workflowId") != workflow["workflowId"]:
        raise ValueError("checkpoint not found or does not belong to the active workflow")
    saved = checkpoint.get("workflow")
    errors = validate_workflow(saved)
    if errors:
        raise ValueError("checkpoint snapshot is corrupt: " + "; ".join(errors))
    before = workflow["state"]
    restored = dict(saved)
    restored["state"] = "recovering"
    restored["revision"] = workflow["revision"] + 1
    restored["updatedAt"] = now()
    restored["lastTransition"] = {"from": before, "to": "recovering",
                                   "reason": f"recovered from checkpoint {selected}", "at": now()}
    restored["recoveredFrom"] = selected
    restored["checkpointIds"] = list(dict.fromkeys(ids + [selected]))[-100:]
    current_repo = _git_snapshot(root)
    saved_repo = checkpoint.get("repository") or {}
    drift = {"head_changed": bool(saved_repo.get("head") and current_repo.get("head") and
                                   saved_repo.get("head") != current_repo.get("head")),
             "working_tree_changed": saved_repo.get("status") != current_repo.get("status")}
    _atomic_json(workflow_path(root), restored)
    return restored, {"checkpoint_id": selected, "drift": drift,
                      "saved_repository": saved_repo, "current_repository": current_repo}


def _approval_scope(category: str, risk: str, target: str, workflow_id: str | None) -> str:
    raw = json.dumps([category, risk, target.strip(), workflow_id or ""], separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_approvals(root: Path) -> list[dict]:
    data = _read_json(approvals_path(root), {"schemaVersion": 1, "approvals": []})
    if not isinstance(data, dict) or data.get("schemaVersion") != 1 or not isinstance(data.get("approvals"), list):
        raise ValueError("runtime approvals store is not valid")
    return data["approvals"]


def grant_approval(root: Path, category: str, risk: str, target: str = "", reason: str = "") -> dict:
    if category not in CATEGORIES or risk not in RISKS:
        raise ValueError("unknown category or risk")
    if not reason.strip():
        raise ValueError("approval requires --reason")
    policy = load_policy(root)
    workflow = load_workflow(root)
    workflow_id = workflow.get("workflowId") if workflow else None
    approval = {
        "approvalId": uuid.uuid4().hex,
        "category": category,
        "risk": risk,
        "targetHash": hashlib.sha256(target.strip().encode("utf-8")).hexdigest() if target.strip() else None,
        "scopeHash": _approval_scope(category, risk, target, workflow_id),
        "workflowId": workflow_id,
        "reason": reason.strip()[:500],
        "grantedAt": now(),
        "expiresAt": (datetime.now(timezone.utc) + timedelta(seconds=policy["approvalTtlSeconds"])).isoformat(timespec="seconds"),
        "consumedAt": None,
    }
    approvals = _load_approvals(root)
    approvals.append(approval)
    _atomic_json(approvals_path(root), {"schemaVersion": 1, "approvals": approvals[-500:]})
    return approval


def evaluate_policy(root: Path, category: str, risk: str, target: str = "",
                    approval_id: str | None = None) -> dict:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    if risk not in RISKS:
        raise ValueError(f"unknown risk: {risk}")
    policy = load_policy(root)
    workflow = load_workflow(root)
    workflow_id = workflow.get("workflowId") if workflow else None
    denied = category in policy["deniedCategories"]
    approval_required = category in policy["approvalRequiredFor"]
    if policy["autonomy"] == "manual" and category != "read":
        approval_required = True
    if policy["autonomy"] == "assisted" and category == "command" and risk != "low":
        approval_required = True
    if RISK_RANK[risk] > RISK_RANK[policy["maxAutonomousRisk"]]:
        approval_required = True
    if denied:
        return {"decision": "deny", "allowed": False, "requiresApproval": False,
                "reason": f"category {category} is denied by policy", "category": category, "risk": risk}

    consumed = None
    if approval_id:
        approvals = _load_approvals(root)
        for item in approvals:
            if item.get("approvalId") != approval_id:
                continue
            expected = _approval_scope(category, risk, target, workflow_id)
            try:
                expired = datetime.fromisoformat(item.get("expiresAt", "")) <= datetime.now(timezone.utc)
            except (TypeError, ValueError):
                expired = True
            valid = (not item.get("consumedAt") and not expired and
                     item.get("scopeHash") == expected and item.get("workflowId") == workflow_id)
            if valid:
                item["consumedAt"] = now()
                _atomic_json(approvals_path(root), {"schemaVersion": 1, "approvals": approvals})
                consumed = approval_id
                break
        if consumed:
            return {"decision": "allow", "allowed": True, "requiresApproval": False,
                    "reason": "explicit approval matches, is not expired, and is consumed once",
                    "category": category, "risk": risk, "approvalId": consumed}
        return {"decision": "require_approval", "allowed": False, "requiresApproval": True,
                "reason": "approval ID is not valid, expired, already used, or scope does not match",
                "category": category, "risk": risk}

    if approval_required:
        return {"decision": "require_approval", "allowed": False, "requiresApproval": True,
                "reason": "category or risk level requires explicit approval",
                "category": category, "risk": risk}
    return {"decision": "allow", "allowed": True, "requiresApproval": False,
            "reason": f"allowed by mode {policy['autonomy']} for risk {risk}",
            "category": category, "risk": risk}


def dispatch_hook(root: Path, hook: str, payload: dict | None = None,
                  approval_id: str | None = None) -> dict:
    if hook not in HOOKS:
        raise ValueError(f"unknown hook: {hook}; choose one of: {', '.join(sorted(HOOKS))}")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("hook payload must be a JSON object")
    defaults = {
        "session.start": ("read", "low"),
        "task.before": ("write", "medium"),
        "task.after": ("read", "low"),
        "verification.before": ("command", "low"),
        "session.finish": ("read", "low"),
        "handover": ("write", "medium"),
    }
    default_category, default_risk = defaults[hook]
    category = payload.get("category", default_category)
    risk = payload.get("risk", default_risk)
    target = payload.get("target", "")
    if not isinstance(target, str):
        raise ValueError("payload.target must be a string")
    result = evaluate_policy(root, category, risk, target, approval_id=approval_id)
    encoded_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    receipt = {
        "hook": hook, "occurredAt": now(), "decision": result["decision"],
        "category": category, "risk": risk,
        "targetHash": hashlib.sha256(target.encode("utf-8")).hexdigest() if target else None,
        "payloadHash": hashlib.sha256(encoded_payload.encode("utf-8")).hexdigest(),
        "reason": result["reason"],
    }
    path = runtime_dir(root) / "hooks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(line)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("runtime hook ledger write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"protocol": "pakem", "runtime_version": 1, "hook": hook, **result,
            "receipt": {k: v for k, v in receipt.items() if k != "payloadHash"}}
