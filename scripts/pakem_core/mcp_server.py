"""Minimal Pakem MCP stdio server for the MCP 2026-07-28 stateless protocol.

Only JSON-RPC messages are written to stdout. Diagnostics go to stderr.
No arbitrary shell/command execution is exposed. Mutating team tools are
available only when the trusted host explicitly starts the server with
--allow-write and a fixed --agent-id.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

MCP_VERSION = "2026-07-28"
SERVER_NAME = "pakem"
SERVER_VERSION = "1.2.1"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
SERVER_INFO = "io.modelcontextprotocol/serverInfo"


def _tool(name: str, description: str, schema: dict) -> dict:
    return {"name": name, "description": description, "inputSchema": schema}


def _object(properties: dict | None = None, required: list[str] | None = None) -> dict:
    out = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        out["required"] = required
    return out


def tool_catalog(allow_write: bool, bound_agent_id: str | None, bound_role: str | None = None) -> list[dict]:
    tools = [
        _tool("pakem.context", "Read the current Pakem project, session, runtime, and team context snapshot.", _object()),
        _tool("pakem.protocol.info", "Read the stable Pakem Protocol version and negotiated capability catalogue.", _object()),
        _tool("pakem.team.status", "Read the shared multi-agent board, current tasks, agents, and lease status.", _object()),
        _tool("pakem.team.events", "Read recent append-only multi-agent coordination events.", _object({"limit": {"type": "integer", "minimum": 0, "maximum": 500}})),
        _tool("pakem.graph", "Build a best-effort static dependency graph of local project files.", _object({"include_tests": {"type": "boolean"}})),
        _tool("pakem.impact", "Analyze changed files, affected dependents, test candidates, and risk signals.", _object({
            "files": {"type": "array", "items": {"type": "string"}, "maxItems": 200},
            "base": {"type": "string"}, "staged": {"type": "boolean"}
        })),
        _tool("pakem.policy.check", "Evaluate a Pakem policy decision. This tool does not execute the requested action.", _object({
            "category": {"type": "string", "enum": ["read", "write", "command", "destructive", "deploy", "security", "policy_change", "gate_change"]},
            "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "target": {"type": "string", "maxLength": 300}
        }, ["category"])),
    ]
    if allow_write and bound_agent_id:
        tools.extend([
            _tool("pakem.team.claim", "Claim a task as the server-bound agent; the caller cannot override its identity.", _object({
                "task_id": {"type": "string"}, "lease_seconds": {"type": "integer", "minimum": 30, "maximum": 86400}
            }, ["task_id"])),
            _tool("pakem.team.heartbeat", "Renew the active task lease for the server-bound agent.", _object({
                "task_id": {"type": "string"}, "lease_seconds": {"type": "integer", "minimum": 30, "maximum": 86400}
            }, ["task_id"])),
            _tool("pakem.team.submit", "Submit a claimed task for independent review with evidence references.", _object({
                "task_id": {"type": "string"}, "summary": {"type": "string", "maxLength": 2000},
                "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 50}
            }, ["task_id", "summary", "evidence"])),
        ])
        # Review and assignment are exposed only when the bound board role permits it.
        if bound_role in {"reviewer", "lead", "coordinator"}:
            tools.append(_tool("pakem.team.review", "Approve or request rework for a submitted task as the server-bound reviewer.", _object({
                "task_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approve", "rework"]},
                "note": {"type": "string", "maxLength": 1000}
            }, ["task_id", "decision"])))
        tools.extend([
            _tool("pakem.session.start", "Start (or resume) a Pakem work session as the server-bound agent.", _object({
                "goal": {"type": "string", "minLength": 1, "maxLength": 300},
                "new": {"type": "boolean"}
            }, ["goal"])),
            _tool("pakem.session.step", "Record a finished step and the next step for the active session.", _object({
                "text": {"type": "string", "minLength": 1, "maxLength": 500},
                "next": {"type": "string", "maxLength": 500}
            }, ["text"])),
            _tool("pakem.session.finish", "Run every Pakem gate and close the session when they pass. Gate failures are returned, not raised.", _object({
                "summary": {"type": "string", "maxLength": 2000},
                "next": {"type": "string", "maxLength": 500}
            })),
        ])
        if bound_role in {"lead", "coordinator"}:
            tools.append(_tool("pakem.team.assign", "Assign a task as the server-bound lead/coordinator.", _object({
                "task_id": {"type": "string"}, "agent_id": {"type": "string"}
            }, ["task_id", "agent_id"])))
    return tools


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _result(request_id: Any, result: dict) -> dict:
    result.setdefault("resultType", "complete")
    result.setdefault("_meta", {SERVER_INFO: {"name": SERVER_NAME, "version": SERVER_VERSION}})
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _validate_modern_meta(params: dict) -> tuple[str | None, dict | None]:
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return "params._meta is required", None
    version = meta.get(META_VERSION)
    caps = meta.get(META_CLIENT_CAPS)
    if not isinstance(version, str) or not version:
        return f"_meta.{META_VERSION} must be a string", None
    if not isinstance(caps, dict):
        return f"_meta.{META_CLIENT_CAPS} must be an object", None
    client_info = meta.get(META_CLIENT_INFO)
    if client_info is not None and not isinstance(client_info, dict):
        return f"_meta.{META_CLIENT_INFO} must be an object", None
    return None, meta


def _run_context(root: Path) -> dict:
    script = Path(__file__).resolve().parents[1] / "pakem.py"
    # In installed projects the CLI is vendored beside pakem_core.
    vendored = root / ".pakem" / "pakem.py"
    cli = vendored if vendored.is_file() else script
    result = __import__("subprocess").run([sys.executable, str(cli), "context", "--json"],
                                          cwd=root, text=True, capture_output=True,
                                          timeout=25, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError((result.stderr or result.stdout or "pakem context failed").strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"context output is not valid JSON: {exc}") from exc


def _run_cli(root: Path, *args: str, timeout: int = 180) -> dict:
    """Run the Pakem CLI installed in the project; this is not a free shell."""
    import subprocess

    vendored = root / ".pakem" / "pakem.py"
    cli = vendored if vendored.is_file() else Path(__file__).resolve().parents[1] / "pakem.py"
    if not cli.is_file():
        raise RuntimeError("Pakem CLI not found in this project")
    result = subprocess.run([sys.executable, str(cli), *args], cwd=root, text=True,
                            capture_output=True, timeout=timeout, check=False)
    return {"ok": result.returncode == 0, "exit": result.returncode,
            "output": (result.stdout or "").strip(),
            "error": (result.stderr or "").strip()}


def _call_tool(name: str, args: dict, root: Path, allow_write: bool,
               bound_agent_id: str | None) -> dict:
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    from pakem_core import coordination, intelligence, protocol, runtime

    if name == "pakem.context":
        return _run_context(root)
    if name == "pakem.protocol.info":
        return {"protocol": protocol.PROTOCOL_NAME, "version": protocol.PROTOCOL_VERSION,
                "supported_versions": list(protocol.SUPPORTED_VERSIONS),
                "capabilities": protocol.CAPABILITIES}
    if name == "pakem.team.status":
        return coordination.status(root)
    if name == "pakem.team.events":
        return coordination.read_events(root, int(args.get("limit", 50)))
    if name == "pakem.graph":
        return intelligence.build_dependency_graph(root, bool(args.get("include_tests", True)))
    if name == "pakem.impact":
        files = args.get("files")
        if files is not None and (not isinstance(files, list) or any(not isinstance(x, str) for x in files)):
            raise ValueError("files must be an array of strings")
        if args.get("base") and args.get("staged"):
            raise ValueError("base and staged cannot be used together")
        changed = intelligence.changed_files_for_impact(root, files, args.get("base"), bool(args.get("staged", False)))
        graph = intelligence.build_dependency_graph(root)
        return intelligence.analyze_impact(root, changed, graph)
    if name == "pakem.policy.check":
        category = args.get("category")
        risk = args.get("risk", "medium")
        target = args.get("target", "")
        return runtime.evaluate_policy(root, category, risk, target)

    if not allow_write or not bound_agent_id:
        raise PermissionError("mutating tools are not enabled; the host must use --allow-write and --agent-id")
    task_id = args.get("task_id")
    if name == "pakem.team.claim":
        return coordination.claim_task(root, task_id, bound_agent_id, int(args.get("lease_seconds", 900)))
    if name == "pakem.team.heartbeat":
        return coordination.heartbeat(root, task_id, bound_agent_id, int(args.get("lease_seconds", 900)))
    if name == "pakem.team.submit":
        return coordination.submit_task(root, task_id, bound_agent_id, args.get("summary", ""), args.get("evidence", []))
    if name == "pakem.team.review":
        return coordination.review_task(root, task_id, bound_agent_id, args.get("decision"), args.get("note", ""))
    if name == "pakem.session.start":
        argv = ["start", str(args.get("goal", "")).strip()]
        if bound_agent_id:
            argv += ["--agent", bound_agent_id]
        if args.get("new"):
            argv.append("--new")
        return _run_cli(root, *argv)
    if name == "pakem.session.step":
        argv = ["step", str(args.get("text", "")).strip()]
        if args.get("next"):
            argv += ["--next", str(args["next"]).strip()]
        return _run_cli(root, *argv)
    if name == "pakem.session.finish":
        argv = ["finish"]
        if args.get("summary"):
            argv += ["--summary", str(args["summary"]).strip()]
        if args.get("next"):
            argv += ["--next", str(args["next"]).strip()]
        return _run_cli(root, *argv, timeout=600)
    if name == "pakem.team.assign":
        return coordination.assign_task(root, task_id, args.get("agent_id"), bound_agent_id)
    raise KeyError(f"tool not found: {name}")


def handle_message(message: dict, root: str | Path, allow_write: bool = False,
                   bound_agent_id: str | None = None) -> dict | None:
    """Process one modern MCP request. Notifications return None."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _rpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
    method = message.get("method")
    request_id = message.get("id")
    if not isinstance(method, str) or not method:
        return _rpc_error(request_id, -32600, "Invalid Request")
    is_notification = "id" not in message
    if is_notification:
        return None
    if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
        return _rpc_error(request_id, -32600, "Request id must be a string or integer")
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _rpc_error(request_id, -32602, "params must be an object")
    meta_error, meta = _validate_modern_meta(params)
    if meta_error:
        return _rpc_error(request_id, -32602, meta_error)
    peer_version = meta[META_VERSION]
    if peer_version != MCP_VERSION:
        return _rpc_error(request_id, -32022, "Unsupported protocol version",
                           {"supported": [MCP_VERSION], "requested": peer_version})
    root = Path(root).resolve()
    try:
        if method == "server/discover":
            return _result(request_id, {
                "supportedVersions": [MCP_VERSION],
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": "Pakem provides project context, static intelligence, policy decisions, and optional team coordination. No arbitrary shell execution is exposed.",
                "ttlMs": 3600000,
                "cacheScope": "public",
            })
        if method == "tools/list":
            bound_role = None
            if allow_write and bound_agent_id:
                from pakem_core.coordination import status as team_status
                bound_role = next((agent.get("role") for agent in team_status(root).get("agents", [])
                                   if agent.get("agentId") == bound_agent_id), None)
            return _result(request_id, {"tools": tool_catalog(allow_write, bound_agent_id, bound_role), "cacheScope": "private", "ttlMs": 60000})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not name:
                return _rpc_error(request_id, -32602, "tools/call requires params.name")
            bound_role = None
            if allow_write and bound_agent_id:
                from pakem_core.coordination import status as team_status
                bound_role = next((agent.get("role") for agent in team_status(root).get("agents", [])
                                   if agent.get("agentId") == bound_agent_id), None)
            known = {tool["name"] for tool in tool_catalog(allow_write, bound_agent_id, bound_role)}
            if name not in known:
                return _rpc_error(request_id, -32602, f"tool is not available: {name}")
            try:
                data = _call_tool(name, arguments, root, allow_write, bound_agent_id)
                return _result(request_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                                             "structuredContent": data, "isError": False})
            except PermissionError as exc:
                return _result(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
            except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                return _result(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return _rpc_error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:  # keep the stdio process alive on a failed request
        return _rpc_error(request_id, -32603, "Internal error", str(exc))


def serve_stdio(root: str | Path, allow_write: bool = False,
                bound_agent_id: str | None = None) -> int:
    root = Path(root).resolve()
    if allow_write and not bound_agent_id:
        print("[pakem-mcp] --allow-write requires a host-bound --agent-id.", file=sys.stderr)
        return 2
    for line in sys.stdin:
        if len(line.encode("utf-8", errors="replace")) > 8 * 1024 * 1024:
            response = _rpc_error(None, -32600, "Message too large (max 8 MiB)")
        else:
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                response = _rpc_error(None, -32700, f"Parse error: {exc.msg}")
            else:
                response = handle_message(message, root, allow_write, bound_agent_id)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0
