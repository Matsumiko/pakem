"""Safe, explicit Git worktree helpers for isolated multi-agent task work.

This module creates/removes worktrees only. It never merges, pushes, resets, or
runs project commands. The project root and managed worktree directory are
validated before every operation.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{label} is not valid")
    return value


def _git(root: Path, *args: str, timeout: int = 30) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True,
                            timeout=timeout, check=False)
    if result.returncode:
        message = (result.stderr or result.stdout or "git command failed").strip()
        raise RuntimeError(message)
    return result.stdout.strip()


def _root(root: str | Path) -> Path:
    value = Path(root).resolve()
    if not (value / ".git").exists():
        # Linked worktrees have a .git file; bare repos are not suitable.
        raise ValueError("worktree command must run inside a Git working tree")
    return value


def _managed_dir(root: Path) -> Path:
    return root / ".pakem" / "worktrees"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def create(root: str | Path, task_id: str, agent_id: str,
           base_ref: str = "HEAD") -> dict[str, Any]:
    root = _root(root)
    task_id = _safe_id(task_id, "task ID")
    agent_id = _safe_id(agent_id, "agent ID")
    if not isinstance(base_ref, str) or not base_ref.strip() or base_ref.startswith("-"):
        raise ValueError("base_ref is not valid")
    pakem_dir = root / ".pakem"
    if pakem_dir.is_symlink():
        raise ValueError(".pakem must not be a symlink for worktree operations")
    folder = _managed_dir(root)
    if folder.is_symlink():
        raise ValueError(".pakem/worktrees must not be a symlink")
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{task_id}--{agent_id}"
    if destination.exists():
        raise ValueError(f"worktree already exists: {destination.relative_to(root).as_posix()}")
    branch = f"pakem/{task_id}/{agent_id}"
    _git(root, "check-ref-format", "--branch", branch)
    # Verify ref exists before creating a branch or directory.
    _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    _git(root, "worktree", "add", "-b", branch, str(destination), base_ref)
    return {
        "created": True,
        "task_id": task_id,
        "agent_id": agent_id,
        "branch": branch,
        "path": destination.relative_to(root).as_posix(),
        "base_ref": base_ref,
        "merge_performed": False,
    }


def list_worktrees(root: str | Path) -> dict[str, Any]:
    root = _root(root)
    raw = _git(root, "worktree", "list", "--porcelain")
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.splitlines() + [""]:
        if not line:
            if current:
                path = Path(current.get("path", ""))
                current["managed_by_pakem"] = bool(path and _is_within(path, _managed_dir(root)))
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key == "bare":
            current["bare"] = True
        elif key == "locked":
            current["locked"] = value or True
        elif key == "prunable":
            current["prunable"] = value or True
    return {"worktrees": records, "managed_count": sum(1 for x in records if x["managed_by_pakem"])}


def remove(root: str | Path, path: str, force: bool = False) -> dict[str, Any]:
    root = _root(root)
    raw_candidate = (root / path) if not Path(path).is_absolute() else Path(path)
    if raw_candidate.is_symlink():
        raise ValueError("symlink is not allowed as a worktree target")
    candidate = raw_candidate.resolve(strict=False)
    pakem_dir = root / ".pakem"
    managed = _managed_dir(root)
    if pakem_dir.is_symlink() or managed.is_symlink():
        raise ValueError(".pakem/worktrees must not be a symlink")
    if not _is_within(candidate, managed) or candidate == managed.resolve(strict=False):
        raise ValueError("Pakem may only remove worktrees inside .pakem/worktrees/")
    if not candidate.exists():
        raise ValueError("worktree not found")
    if not force:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=candidate, text=True,
                               capture_output=True, timeout=30, check=False)
        if dirty.returncode == 0 and dirty.stdout.strip():
            raise ValueError("worktree still has uncommitted changes; "
                             "commit or stash them first, or use --force to discard them")
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(candidate))
    _git(root, *args)
    return {"removed": True, "path": candidate.relative_to(root).as_posix(),
            "force": bool(force), "branch_deleted": False}


def resolve(root: str | Path, name: str) -> Path:
    """Translate a managed worktree name into a validated Path.

    Accepts `T1--solo` (folder name), `T1/solo` (task/agent), or a relative or
    absolute path. Only worktrees inside `.pakem/worktrees/` are accepted.
    """
    root = _root(root)
    managed = _managed_dir(root).resolve(strict=False)
    raw = str(name or "").strip().replace("\\", "/").rstrip("/")
    if not raw:
        raise ValueError("worktree name is empty")
    p = Path(raw)
    candidates = [p] if p.is_absolute() else [root / raw, managed / raw]
    if "/" in raw and not raw.startswith("."):
        task, agent = raw.split("/", 1)
        candidates.append(managed / f"{task}--{agent}")
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved == managed or not _is_within(resolved, managed):
            continue
        if not (resolved / ".git").exists():
            continue
        return resolved
    existing = sorted(x.name for x in managed.iterdir() if x.is_dir()) if managed.is_dir() else []
    hint = f" Available: {', '.join(existing)}." if existing else ""
    raise ValueError(f"managed worktree not found: {raw}.{hint}")


def changed_files(root: str | Path, name: str, base: str | None = None) -> list[str]:
    """Files changed in a worktree relative to its branch point from the root.

    `git diff <merge-base>` counts commits on the branch plus uncommitted changes
    at once; untracked files are added from status. Paths are always relative and
    POSIX-formatted, ready to compare against the task scope.
    """
    root = _root(root)
    worktree = resolve(root, name)
    head = _git(worktree, "rev-parse", "--verify", "HEAD")
    ref = base
    if not ref:
        try:
            ref = _git(root, "merge-base", "HEAD", head)
        except RuntimeError:
            ref = head  # unrelated history: compare against the worktree HEAD only
    raw = _git(worktree, "diff", "--name-only", "--no-renames", ref)
    paths = [line.strip() for line in raw.splitlines() if line.strip()]
    status = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    for line in status.splitlines():
        if line.startswith("?? "):
            entry = line[3:].strip()
            if entry.startswith('"') and entry.endswith('"'):
                entry = entry[1:-1]
            if entry:
                paths.append(entry.replace("\\", "/"))
    return sorted({p for p in paths if p})

def cleanup_for_task(root: str | Path, task_id: str, dry_run: bool = False) -> list[dict[str, Any]]:
    """Clean up the worktree owned by one task when it is safe.

    Only worktrees that are clean and whose commits are already part of HEAD are
    removed. Worktrees with unmerged commits or uncommitted files are left alone
    and reported: that is unfinished work, not garbage.
    """
    root = _root(root)
    task_id = _safe_id(task_id, "task ID")
    head = _git(root, "rev-parse", "HEAD").strip()
    report: list[dict[str, Any]] = []
    for record in list_worktrees(root)["worktrees"]:
        branch = record.get("branch") or ""
        if not branch.startswith(f"pakem/{task_id}/"):
            continue
        path = Path(record["path"])
        item = {"task_id": task_id, "branch": branch,
                "path": path.relative_to(root).as_posix() if _is_within(path, root) else str(path),
                "action": "keep", "reason": ""}
        if record.get("locked") or record.get("prunable"):
            item["reason"] = "worktree is locked or prunable"
        elif record.get("detached"):
            item["reason"] = "HEAD detached"
        else:
            worktree_head = record.get("head") or ""
            merged = subprocess.run(["git", "-C", str(path), "merge-base", "--is-ancestor",
                                     worktree_head, head], capture_output=True, text=True,
                                    timeout=30, check=False)
            dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain"],
                                   capture_output=True, text=True, timeout=30, check=False)
            if merged.returncode != 0:
                item["reason"] = f"commit {worktree_head[:8]} not merged into HEAD"
            elif dirty.returncode == 0 and dirty.stdout.strip():
                item["reason"] = "uncommitted changes remain"
            elif dry_run:
                item["action"] = "would-remove"
            else:
                try:
                    _git(root, "worktree", "remove", str(path))
                except RuntimeError as exc:
                    item["reason"] = f"failed to remove: {exc}"
                else:
                    deleted = subprocess.run(["git", "-C", str(root), "branch", "-D", branch],
                                             capture_output=True, text=True, timeout=30, check=False)
                    item.update({"action": "removed", "branch_deleted": deleted.returncode == 0})
        report.append(item)
    return report


def cleanup_merged(root: str | Path, dry_run: bool = False) -> list[dict[str, Any]]:
    """Clean up every pakem/* worktree that is safe to remove."""
    root = _root(root)
    seen: list[str] = []
    for record in list_worktrees(root)["worktrees"]:
        parts = (record.get("branch") or "").split("/")
        if len(parts) >= 3 and parts[0] == "pakem" and parts[1] not in seen:
            seen.append(parts[1])
    report: list[dict[str, Any]] = []
    for task_id in seen:
        report.extend(cleanup_for_task(root, task_id, dry_run=dry_run))
    return report
