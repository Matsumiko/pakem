"""Artifact reconciliation: what plan/spec claims versus what actually changed.

The functions here are pure: they do not read the disk and do not touch git. The
caller (CLI) collects `changed_files`, `tasks`, and `acceptance`, then hands them
in here. That makes the logic testable without a repo and without subprocesses.
"""
from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from .intelligence import CODE_EXTS

SCHEMA_VERSION = "pakem.reconciliation/v1"


def is_code_path(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in CODE_EXTS


def matches(path: str, scope: str) -> bool:
    """Match one git path against one task scope entry.

    A scope entry may be an exact file, a directory (with or without a trailing
    slash), or a simple glob pattern. Matching is always against a relative
    POSIX-formatted path.
    """
    entry = str(scope).strip().replace("\\", "/").rstrip("/")
    if not entry:
        return False
    if path == entry:
        return True
    if path.startswith(entry + "/"):
        return True
    return fnmatch.fnmatch(path, entry)


def declared_scope(tasks: list[dict]) -> list[str]:
    seen = []
    for task in tasks:
        for entry in task.get("files", []) or []:
            entry = str(entry).strip()
            if entry and entry not in seen:
                seen.append(entry)
    return seen


def reconcile(changed_files: list[str], tasks: list[dict] | None = None,
              acceptance: list[dict] | None = None) -> dict:
    """Compare actual changes against the plan scope and the spec acceptance criteria."""
    tasks = tasks or []
    acceptance = acceptance or []
    changed = sorted({str(p).strip().replace("\\", "/") for p in changed_files if str(p).strip()})
    scope = declared_scope(tasks)

    in_scope = [p for p in changed if any(matches(p, entry) for entry in scope)]
    out_of_scope = [p for p in changed if p not in in_scope]
    code_out = [p for p in out_of_scope if is_code_path(p)]

    per_task = []
    for task in tasks:
        entries = [str(f).strip() for f in (task.get("files") or []) if str(f).strip()]
        touched = [p for p in changed if any(matches(p, entry) for entry in entries)]
        per_task.append({
            "taskId": task.get("taskId") or task.get("id"),
            "done": bool(task.get("done")),
            "declared": entries,
            "changed": touched,
            "untouched": [e for e in entries if not any(matches(p, e) for p in changed)],
        })

    unchecked = [item for item in acceptance if not item.get("checked")]
    return {
        "schema_version": SCHEMA_VERSION,
        "changed_files": changed,
        "declared_scope": scope,
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "code_out_of_scope": code_out,
        "tasks": per_task,
        "acceptance": {
            "total": len(acceptance),
            "checked": len(acceptance) - len(unchecked),
            "unchecked": [str(item.get("text", "")).strip() for item in unchecked],
        },
        "summary": {
            "changed": len(changed),
            "in_scope": len(in_scope),
            "out_of_scope": len(out_of_scope),
            "code_out_of_scope": len(code_out),
            "acceptance_unchecked": len(unchecked),
        },
        "ok": not code_out and not unchecked,
    }


def render_text(result: dict) -> str:
    summary = result["summary"]
    lines = [f"RECONCILIATION  {summary['changed']} files changed, "
             f"{summary['in_scope']} in scope, {summary['out_of_scope']} out of scope"]
    if not result["declared_scope"] and summary["changed"]:
        lines.append("  (no PLAN.md/task scope; all changes counted as out of scope)")
    if result["code_out_of_scope"]:
        lines.append("  out of scope (code):")
        lines.extend(f"    - {p}" for p in result["code_out_of_scope"])
    other = [p for p in result["out_of_scope"] if p not in result["code_out_of_scope"]]
    if other:
        lines.append("  out of scope (non-code, usually safe):")
        lines.extend(f"    - {p}" for p in other)
    acceptance = result["acceptance"]
    if acceptance["total"]:
        lines.append(f"  acceptance: {acceptance['checked']}/{acceptance['total']} checked")
        lines.extend(f"    [ ] {text}" for text in acceptance["unchecked"][:10])
    for task in result["tasks"]:
        if task["untouched"] and task["done"]:
            lines.append(f"  note: {task['taskId']} done but scope untouched: "
                         + ", ".join(task["untouched"]))
    lines.append("  VERDICT: " + ("aligned" if result["ok"] else "not aligned"))
    return "\n".join(lines)
