#!/usr/bin/env python3
"""Pakem - work discipline for coding agents.

Commands: init, start, step, status, check, finish, adr, adapt, hook
No dependencies (stdlib Python 3.10+ only).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

VERSION = "1.2.1"
PROTOCOL_VERSION = "1.0"
PROTOCOL_EVENTS = {
    "session.started", "session.abandoned", "session.step_recorded",
    "session.resumed", "session.finish_blocked", "session.finished", "task.added",
    "task.completed", "task.dropped", "spec.approved", "decision.recorded",
    "bug.recorded", "handover.created", "integrity.repinned", "verification.completed",
    "runtime.workflow.initialized", "runtime.state.transitioned",
    "runtime.checkpoint.created", "runtime.recovered", "runtime.hook.dispatched",
    "policy.decision", "policy.approval.granted",
    "team.agent.registered", "team.task.created", "team.task.assigned",
    "team.task.claimed", "team.task.heartbeat", "team.task.released",
    "team.task.handed_off", "team.task.submitted", "team.task.reviewed",
    "team.task.blocked", "team.task.unblocked", "ledger.sealed",
}
PAKEM_DIR = ".pakem"
HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE.parent / "assets" / "templates"
PYCMD = "python" if os.name == "nt" else "python3"
NO_BUGS = "_No bugs recorded yet._"
BUG_HEADER = ("# BUG-HISTORY\n\nCheck this file BEFORE fixing a bug. Newest entry first.\n\n"
              "## Entries\n\n" + NO_BUGS + "\n")
STRENGTH = {"required": 3, "when-decision": 2, "when-needed": 2, "skip": 1}

EXISTING_MARKERS = [
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle", "composer.json", "Gemfile", "src", "app", "lib",
]
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".pakem", "target", ".next", ".wrangler", "coverage", ".cache"}
TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec"}
TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"
    r"|Tests?\.(java|kt|cs)$|_spec\.rb$)"
)
ENV_RE = re.compile(r"process\.env|os\.environ|import\.meta\.env|Deno\.env|getenv\(|ENV\[")
CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rb",
             ".php", ".rs", ".java", ".kt", ".cs", ".vue", ".svelte"}
LOCK_CANDIDATES = {
    "package.json": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"],
    "go.mod": ["go.sum"],
    "Cargo.toml": ["Cargo.lock"],
    "Gemfile": ["Gemfile.lock"],
    "composer.json": ["composer.lock"],
}
CI_PATHS = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
            "azure-pipelines.yml"]
SURFACE_VALUES = {
    "exposure": ({"private", "public"}, "private"),
    "deploy": ({"none", "staging", "production"}, "none"),
    "handover": ({"true", "false"}, "false"),
    "sensitive": ({"true", "false"}, "false"),
}
DEPLOY_RANK = {"none": 0, "staging": 1, "production": 2}

PROFILES = {
    "oneoff":   dict(tests="skip", adr="skip", research="skip", modular="skip"),
    "app":      dict(tests="required", adr="when-decision", research="when-needed", modular="required"),
    "library":  dict(tests="required", adr="when-decision", research="when-needed", modular="required"),
    "research": dict(tests="skip", adr="when-decision", research="required", modular="skip"),
}
DEFAULT_REASONS = {
    "oneoff": {
        "tests": "Throwaway script/utility; proven by real output in verify.",
        "adr": "No long-lived architecture decision.",
        "research": "No technology exploration.",
        "modular": "Small enough; one tidy file/script beats a layered structure.",
    },
    "research": {
        "tests": "Research project; no production code to test yet.",
        "modular": "No production code yet.",
        "verify": "Research project: no code to test. Verification = sourced findings in docs/research/.",
    },
}
FILES_BY_TYPE = {
    "oneoff":   ["CONTEXT.md", "PROJECT.md"],
    "research": ["CONTEXT.md", "PROJECT.md", "DECISIONS.md"],
    "app":      ["CONTEXT.md", "PROJECT.md", "MODULE-MAP.md", "DECISIONS.md", "BUG-HISTORY.md"],
    "library":  ["CONTEXT.md", "PROJECT.md", "MODULE-MAP.md", "DECISIONS.md", "BUG-HISTORY.md"],
}
ROUTING_ROWS = {
    "PROJECT.md": ("starting any task (stack, conventions, commands, definition of done)", "PROJECT.md"),
    "MODULE-MAP.md": ("adding/changing a module, moving or deleting files", "MODULE-MAP.md"),
    "DECISIONS.md": ("choosing a library, pattern, or architecture", "DECISIONS.md (and docs/adr/)"),
    "BUG-HISTORY.md": ("fixing a bug (check first: has this happened before?)", "BUG-HISTORY.md"),
}
DOD = {
    "app": "Tests pass; the app can be run from scratch following README; no secrets in code; "
           "`.pakem/` is updated (MODULE-MAP when the structure changes, DECISIONS when a decision "
           "was made, BUG-HISTORY when a bug was fixed).",
    "library": "Tests pass; the public API is documented; breaking changes are recorded; "
               "`.pakem/` is updated (MODULE-MAP, DECISIONS, BUG-HISTORY as applicable).",
    "oneoff": "Real output is produced from sample input and inspected. `verify` contains the command "
              "that proves it (e.g. run the script, then check the output file exists and is not empty).",
    "research": "The research question is answered with sources; findings are stored in docs/research/; "
                "recommendations and their reasoning are recorded.",
}

ADAPTERS = {
    "claude": ("CLAUDE.md", ""),
    "codex": ("AGENTS.md", ""),
    "gemini": ("GEMINI.md", ""),
    "copilot": (".github/copilot-instructions.md", ""),
    "cursor": (".cursor/rules/pakem.mdc",
               "---\ndescription: Pakem work protocol\nalwaysApply: true\n---\n\n"),
}
BEGIN = "<!-- pakem:begin -->"
END = "<!-- pakem:end -->"
BEGIN_PROTOCOL = "<!-- pakem:protocol:begin -->"
END_PROTOCOL = "<!-- pakem:protocol:end -->"
PROTOCOL_STEPS = [
    "Read `.pakem/CONTEXT.md` first, then `pakem context --json` for a workflow snapshot; read only the files it routes you to.",
    "Start: `pakem start \"<goal>\"`. If a session was interrupted, inspect the repo state and continue from its `nextStep`.",
    "Non-trivial work: `pakem spec \"<title>\"` → fill → `pakem spec --approve`; split tasks with `pakem plan add \"<task>\" --files ... --verify ...`; mark done with `pakem plan done T1` (runs that task's `--verify` and stores the evidence; exceptions must be explicit: `--no-verify --reason \"...\"`).",
    "While working, at every natural stopping point: `pakem step \"<what just finished>\" --next \"<next step>\"`.",
    "Finish: `pakem reconcile` first (files outside plan scope, unchecked acceptance), then `pakem finish --summary \"<summary + evidence>\"`. Do not say done before exit 0. Bug: `pakem bug \"<title>\"` then `finish --fixed-bug`. Report every [WARN].",
    "When choosing documents/structure: `pakem audit`. Do REQUIRED, defer RECOMMENDED with a reason, do not create NOT NEEDED.",
    "For machine context, use `pakem context --json` and `pakem reconcile --json`; before a refactor or cross-module change, use `pakem graph --json` and `pakem impact --files <file...> --json`.",
    "Follow Pakem Protocol v1.0 in `.pakem/protocol/v1/`; events are an append-only record, not proof of work quality.",
    "Graph/impact are static and advisory; do not conclude a file is safe or unaffected just because there is no edge. Run the actual verify and review.",
    "Use `pakem runtime hook <event> --payload-file <json> --json` before an action; continue only when decision=allow. require_approval must wait for user confirmation through a trusted host; an agent must not approve itself.",
    "Runtime workflow: `pakem runtime status --json`; explicit transitions; create a checkpoint before risk points; recovery restores workflow metadata only and does NOT revert source code.",
    "Multi-agent: use `pakem team status --json`; register agents, split tasks, assign/claim with a lease, heartbeat, handoff, submit with evidence, then require a different reviewer before a task is done. If the agent has an identity, use `team submit --sign`/`team review --sign` and check `pakem team verify`.",
    "Agent ID/role on the team board is cooperative metadata, not authentication. The runtime host must bind a trusted caller identity to --agent; do not treat a local lease as a distributed lock on a network filesystem.",
    "Pakem Protocol v1.0 is a stable contract; use `pakem protocol negotiate --peer-version 1.0` before cross-runtime integration. A capability is not permission to cause side effects.",
    "MCP integration: `pakem mcp serve` is read-only by default. Mutation mode only through a trusted host with a fixed `--agent-id` and `--allow-write`; MCP clientInfo is not authentication.",
    "For Git-based agent isolation, use `pakem worktree create <task> --agent <id> --base <ref>`. Check for scope widening with `pakem worktree scope <task>--<agent> --strict` before merging; the `worktree` gate runs the same check during `check`/`finish`. Pakem does not merge or push automatically; verification and review remain required.",
    "Gate failed: fix the root cause. Do not edit the gate or weaken the rules to pass it.",
    "Ambiguous requirement: ask the user or record the assumption through `step`. Do not guess silently.",
    "Existing repo: follow the existing pattern; do not reshape the structure unless asked.",
]
PROTOCOL_TEXT = "\n".join(f"{i}. {s}" for i, s in enumerate(PROTOCOL_STEPS, 1))
BLOCK = f"""{BEGIN}
## Pakem - work protocol

This project uses Pakem. The source of truth lives in `.pakem/` (this block is generated; do not edit it,
regenerate with `pakem adapt`).

Below, `pakem` means `python3 .pakem/pakem.py` (on Windows replace `python3` with `python` or `py -3`).

{BEGIN_PROTOCOL}
## Protocol
{PROTOCOL_TEXT}
{END_PROTOCOL}
{END}"""

ADR_TEMPLATE = """# {num}. {title}

- Status: proposed
- Date: {date}

## Context
[FILL: the problem and constraints that force this decision]

## Options considered
1. [FILL: option A - pros and cons]
2. [FILL: option B - pros and cons]

## Decision
[FILL: the chosen option and the main reason]

## Consequences
[FILL: positive and negative impact, and what must be guarded]
"""
NO_DECISIONS = "_No decisions recorded yet._"
LEGACY_NO_BUGS = "_Belum ada bug tercatat._"
LEGACY_NO_DECISIONS = "_Belum ada keputusan tercatat._"

HANDOVER_TEMPLATE = """# HANDOVER

One handover file. State facts; never put passwords, tokens, or secrets here.

- Date: [FILL: YYYY-MM-DD]
- From / to: [FILL: name and role]
- Status: [FILL: e.g. stable production / development / shut down]

## How to run
[FILL: setup, run, test, deploy — commands that actually work]

## Access
[FILL: accounts/services and who holds them, WITHOUT passwords]

## Contacts
[FILL: name, role, communication channel]

## Unfinished work
[FILL: remaining features/bugs/work with the next step]

## Risks & known issues
[FILL: known bugs, limitations, technical debt that matters]

## Key decisions
[FILL: links to docs/adr/ or a summary of decisions that must not be re-debated]
"""

SPEC_FILE = "SPEC.md"
PLAN_FILE = "PLAN.md"
SPEC_TEMPLATE = """# SPEC - {title}

Status: draft
Created: {date}

## Problem
[FILL: the problem to solve and for whom]

## Non-goals
[FILL: what is intentionally out of scope]

## Acceptance
- [ ] [FILL: a criterion that can be verified]

## Approach
[FILL: a short approach, not a task list]
"""

PLAN_RE = re.compile(r"(?m)^- \[( |x)\] (T\d+) - (.*?) \| files: (.*?) \| verify: (.*)$")


# ---------------------------------------------------------------- util

def die(msg: str, code: int = 2):
    print(f"pakem: {msg}", file=sys.stderr)
    sys.exit(code)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].strip("-") or "session"

def count(n: int, singular: str, plural_form: str | None = None) -> str:
    """`1 task`, `2 tasks` — this text is read by humans."""
    return f"{n} {singular if n == 1 else (plural_form or singular + 's')}"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def write(p: Path, text: str):
    """All writes go through the atomic path; avoid half-written documents when the process dies."""
    write_atomic(p, text)

def write_atomic(p: Path, text: str):
    """Write through a temporary file + fsync + rename, so a power loss does not leave half-written JSON."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        try:
            dirfd = os.open(p.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dirfd)
        except OSError:
            pass
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass

@contextlib.contextmanager
def pakem_lock(root: Path):
    """Cross-process lock for session/rule mutations. Windows uses msvcrt, POSIX uses fcntl."""
    d = sessions_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    lock_path = d / ".lock"
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r+", encoding="utf-8") as f:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            f.write("0")
            f.flush()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def protocol_block() -> str:
    return f"{BEGIN_PROTOCOL}\n{PROTOCOL_TEXT}\n{END_PROTOCOL}"

def sync_context_protocol(root: Path) -> bool:
    """Update only the protocol block in CONTEXT.md; project routing/content is untouched."""
    p = root / PAKEM_DIR / "CONTEXT.md"
    if not p.is_file():
        return False
    text = read(p)
    block = protocol_block()
    if BEGIN_PROTOCOL in text and END_PROTOCOL in text:
        new = re.sub(re.escape(BEGIN_PROTOCOL) + r".*?" + re.escape(END_PROTOCOL),
                     lambda _: block, text, count=1, flags=re.S)
    else:
        m = re.search(r"(?ms)^## (?:Protokol|Protocol)\n.*?(?=^## |\Z)", text)
        if not m:
            return False
        section = ("## Protocol\n\n"
                   "Below, `pakem` means `python3 .pakem/pakem.py` "
                   "(on Windows replace `python3` with `python` or `py -3`).\n\n"
                   + block + "\n\n")
        new = text[:m.start()] + section + text[m.end():]
    if new == text:
        return False
    write(p, new)
    return True

def context_protocol_state(root: Path) -> str:
    p = root / PAKEM_DIR / "CONTEXT.md"
    if not p.is_file():
        return "no CONTEXT.md"
    m = re.search(re.escape(BEGIN_PROTOCOL) + r"(.*?)" + re.escape(END_PROTOCOL),
                  read(p), re.S)
    if not m:
        return "protocol not marked (run pakem upgrade)"
    return "ok" if m.group(1).strip() == PROTOCOL_TEXT.strip() else "stale (run pakem upgrade)"


def sync_protocol_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install the Pakem-managed protocol schemas into .pakem/protocol/v1."""
    source = source_dir or (HERE.parent / "protocol" / "v1")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "protocol" / "v1"
    changed = []
    for name in ("README.md", "event.schema.json", "session.schema.json", "capabilities.schema.json"):
        src = source / name
        if not src.is_file():
            continue
        text = read(src)
        dst = target / name
        if not dst.is_file() or read(dst) != text:
            write(dst, text)
            changed.append(name)
    return changed


def sync_core_package(root: Path, source_dir: Path | None = None) -> list[str]:
    """Copy the language-neutral core modules beside the vendored CLI."""
    source = source_dir or (HERE / "pakem_core")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "pakem_core"
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(source.glob("*.py")):
        dst = target / src.name
        content = read(src)
        if not dst.is_file() or read(dst) != content:
            write(dst, content)
            copied.append(src.name)
    return copied


def sync_intelligence_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install JSON contracts for intelligence outputs."""
    source = source_dir or (HERE.parent / "intelligence" / "v1")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "intelligence" / "v1"
    changed = []
    for name in ("README.md", "dependency-graph.schema.json", "impact-analysis.schema.json", "reconciliation.schema.json"):
        src = source / name
        if not src.is_file():
            continue
        text = read(src)
        dst = target / name
        if not dst.is_file() or read(dst) != text:
            write(dst, text)
            changed.append(name)
    return changed


def sync_runtime_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install versioned runtime/policy contracts without overwriting project policy."""
    base = source_dir or (HERE.parent / "runtime" / "v1")
    policy_source = (base.parent.parent / "policy" / "v1") if source_dir else (HERE.parent / "policy" / "v1")
    changed = []
    for source, target_rel, names in (
        (base, Path("runtime") / "v1", ("README.md", "workflow.schema.json", "checkpoint.schema.json", "hook-payload.schema.json", "hook-decision.schema.json", "approval.schema.json", "task-evidence.schema.json", "work-report.schema.json")),
        (policy_source, Path("policy") / "v1", ("README.md", "policy.schema.json")),
    ):
        if not source.is_dir():
            continue
        target = root / PAKEM_DIR / target_rel
        for name in names:
            src = source / name
            if not src.is_file():
                continue
            content = read(src)
            dst = target / name
            if not dst.is_file() or read(dst) != content:
                write(dst, content)
                changed.append(f"{target_rel.as_posix()}/{name}")
    return changed


def sync_coordination_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install the versioned multi-agent coordination contract."""
    source = source_dir or (HERE.parent / "coordination" / "v1")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "coordination" / "v1"
    changed = []
    for name in ("README.md", "board.schema.json", "event.schema.json", "status.schema.json"):
        src = source / name
        if not src.is_file():
            continue
        content = read(src)
        dst = target / name
        if not dst.is_file() or read(dst) != content:
            write(dst, content)
            changed.append(name)
    return changed


def sync_identity_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install public identity and signed-envelope contracts."""
    source = source_dir or (HERE.parent / "identity" / "v1")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "identity" / "v1"
    changed = []
    for name in ("README.md", "agent-identity.schema.json", "identity-registry.schema.json", "signed-payload.schema.json"):
        src = source / name
        if not src.is_file():
            continue
        content = read(src)
        dst = target / name
        if not dst.is_file() or read(dst) != content:
            write(dst, content)
            changed.append(f"identity/v1/{name}")
    return changed


def sync_storage_schemas(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install the versioned team storage contract."""
    source = source_dir or (HERE.parent / "storage" / "v1")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "storage" / "v1"
    changed = []
    for name in ("README.md", "team-storage.schema.json"):
        src = source / name
        if not src.is_file():
            continue
        content = read(src)
        dst = target / name
        if not dst.is_file() or read(dst) != content:
            write(dst, content)
            changed.append(f"storage/v1/{name}")
    return changed


def sync_adapter_docs(root: Path, source_dir: Path | None = None) -> list[str]:
    """Install versioned adapter contracts/documentation without project overwrite."""
    source = source_dir or (HERE.parent / "adapters")
    if not source.is_dir():
        return []
    target = root / PAKEM_DIR / "adapters"
    changed = []
    for src in sorted(source.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(source)
        dst = target / rel
        content = read(src)
        if not dst.is_file() or read(dst) != content:
            write(dst, content)
            changed.append(rel.as_posix())
    return changed


def strip_comments(text: str) -> str:
    """Remove HTML comments but keep the line count."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def find_root():
    cur = Path.cwd().resolve()
    for p in [cur, *cur.parents]:
        if (p / PAKEM_DIR).is_dir():
            return p
    return None


def _main_worktree(root: Path) -> Path:
    """The real root when invoked from a linked worktree.

    `.pakem` is checked out into the worktree too, but state (sessions, board,
    locks, plan) belongs to the repo, not to one working copy. Without this, an
    agent working inside a worktree reads a stale plan/board and `worktree scope`
    cannot find its own worktree.
    """
    if not (root / ".git").is_file():  # `.git` file = linked worktree
        return root
    try:
        listed = subprocess.run(["git", "-C", str(root), "worktree", "list", "--porcelain"],
                                text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return root
    if listed.returncode:
        return root
    for line in listed.stdout.splitlines():
        if line.startswith("worktree "):
            main = Path(line[len("worktree "):].strip()).resolve(strict=False)
            return main if (main / PAKEM_DIR).is_dir() else root
    return root


def need_root() -> Path:
    r = find_root()
    if not r:
        die("no .pakem/ yet. Run: python3 <skill-location>/scripts/pakem.py init --type app")
    return _main_worktree(r)


def read_config(root: Path) -> dict:
    p = root / PAKEM_DIR / "PROJECT.md"
    cfg: dict = {}
    if not p.exists():
        return cfg
    m = re.match(r"\A---\n(.*?)\n---\n", read(p), re.S)
    if not m:
        return cfg
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        # strip wrapping quotes only when paired (do not break `python -c "..."`)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" and v.count(v[0]) == 2:
            v = v[1:-1]
        cfg[k.strip()] = v
    return cfg


def has_real_files(d: Path) -> bool:
    return d.is_dir() and any(f.is_file() and f.name not in (".gitkeep", ".keep") for f in d.rglob("*"))


def find_tests(root: Path) -> bool:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        in_test_dir = Path(dp).name in TEST_DIR_NAMES
        for f in fns:
            if f in (".gitkeep", ".keep"):
                continue
            if in_test_dir or TEST_FILE_RE.search(f):
                return True
    return False


def detect_verify(root: Path) -> str:
    pj = root / "package.json"
    if pj.exists():
        try:
            scripts = json.loads(pj.read_text(encoding="utf-8")).get("scripts", {})
        except Exception:
            scripts = {}
        cmds = []
        if "test" in scripts:
            cmds.append("npm test")
        if "lint" in scripts:
            cmds.append("npm run lint")
        if cmds:
            return " && ".join(cmds)
    mk = root / "Makefile"
    if mk.exists() and re.search(r"(?m)^test\s*:", read(mk)):
        return "make test"
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    if any((root / f).exists() for f in ("pyproject.toml", "pytest.ini", "setup.cfg", "requirements.txt")):
        return f"{PYCMD} -m pytest"
    return ""


# ---------------------------------------------------------------- git & snapshot

def _git(root: Path, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def git_state(root: Path):
    """Lightweight snapshot of repo condition; None when not a git repo / git is unavailable."""
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return None
    head = (_git(root, "rev-parse", "HEAD") or "").strip() or None
    out = _git(root, "status", "--porcelain") or ""
    dirty = sorted(line for line in out.splitlines() if line and ".pakem/" not in line[3:])
    return {"head": head, "dirty": dirty[:200]}


def git_drift(root: Path, saved: dict, cur: dict):
    msgs = []
    if saved.get("head") != cur.get("head"):
        n = None
        if saved.get("head") and cur.get("head"):
            out = _git(root, "rev-list", "--count", f"{saved['head']}..{cur['head']}")
            n = out.strip() if out else None
        msgs.append(f"HEAD changed ({count(int(n), 'new commit')})" if n else "HEAD changed")
    a, b = set(saved.get("dirty", [])), set(cur.get("dirty", []))
    added, removed = sorted(b - a), sorted(a - b)
    if added:
        msgs.append("changed since the last record: " + "; ".join(x.strip() for x in added[:5])
                    + (f" (+{len(added) - 5} more)" if len(added) > 5 else ""))
    if removed:
        msgs.append("previously changed, now clean (committed/reverted): "
                    + "; ".join(x.strip() for x in removed[:5])
                    + (f" (+{len(removed) - 5} more)" if len(removed) > 5 else ""))
    return msgs


def config_snapshot(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items()
            if k.startswith("rule.") or k in ("verify", "sensitive", "exposure", "deploy", "handover")}


def pakem_hash(root: Path):
    p = root / PAKEM_DIR / "pakem.py"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def pakem_manifest(root: Path) -> dict:
    """Hash of the CLI + every Core module used by the gates.

    Only `pakem.py` used to be pinned, even though the gates also live in `pakem_core/*`.
    Editing a single Core module used to leave no trace at all.
    """
    base = root / PAKEM_DIR
    files: dict[str, str] = {}
    cli = base / "pakem.py"
    if cli.is_file():
        files["pakem.py"] = hashlib.sha256(cli.read_bytes()).hexdigest()[:16]
    core = base / "pakem_core"
    if core.is_dir():
        for path in sorted(core.glob("*.py")):
            files[f"pakem_core/{path.name}"] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return files


def integrity_drift(root: Path, pinned: dict | None) -> list[dict]:
    if not pinned:
        return []
    current = pakem_manifest(root)
    out = []
    for name, old in sorted(pinned.items()):
        new = current.get(name)
        if new is None:
            out.append({"file": name, "state": "missing", "pinned": old, "actual": None})
        elif new != old:
            out.append({"file": name, "state": "changed", "pinned": old, "actual": new})
    for name in sorted(set(current) - set(pinned)):
        out.append({"file": name, "state": "added", "pinned": None, "actual": current[name]})
    return out


def tamper_findings(root: Path, cfg: dict, sess: dict):
    """Changes to rules/verify/CLI since the session started. Does not block; only reports."""
    out = []
    snap = sess.get("configSnapshot")
    if snap:
        for k, old in snap.items():
            new = cfg.get(k)
            if k.startswith("rule."):
                if new is None:
                    out.append(f"{k} deleted (previously: {old})")
                elif STRENGTH.get(new, 0) < STRENGTH.get(old, 0):
                    out.append(f"{k} relaxed: {old} -> {new}")
            elif k == "sensitive":
                if old.lower() == "true" and (new or "").lower() != "true":
                    out.append(f"sensitive downgraded: true -> {new or '(empty)'}")
            elif k == "exposure":
                if old.lower() == "public" and (new or "").strip().lower() != "public":
                    out.append(f"exposure downgraded: public -> {new or '(empty)'}")
            elif k == "deploy":
                old_rank = DEPLOY_RANK.get(old.lower(), 0)
                new_rank = DEPLOY_RANK.get((new or "none").strip().lower(), 0)
                if new_rank < old_rank:
                    out.append(f"deploy downgraded: {old} -> {new or 'none'}")
            elif k == "handover":
                if old.lower() == "true" and (new or "").strip().lower() != "true":
                    out.append(f"handover downgraded: true -> {new or '(empty)'}")
            elif k == "verify" and new != old:
                out.append(f"verify changed: '{old}' -> '{new or ''}'")
    drift = integrity_drift(root, sess.get("pakemIntegrity"))
    if drift:
        for item in drift:
            label = {"changed": "modified", "missing": "deleted",
                     "added": "added"}[item["state"]]
            out.append(f".pakem/{item['file']} {label} during this session")
    else:
        h = sess.get("pakemHash")
        if h and pakem_hash(root) != h:
            out.append(".pakem/pakem.py modified during this session")
    return out


# ---------------------------------------------------------------- session

def sessions_dir(root: Path) -> Path:
    return root / PAKEM_DIR / "sessions"


def scan_sessions(root: Path):
    """Return (valid sessions, broken files). Broken files must not vanish silently."""
    out, bad = [], []
    d = sessions_dir(root)
    if not d.is_dir():
        return out, bad
    for p in sorted(d.glob("*.json")):
        try:
            out.append((p, json.loads(read(p))))
        except Exception:
            bad.append(p)
    return out, bad

def load_sessions(root: Path):
    return scan_sessions(root)[0]

def warn_corrupt_sessions(root: Path, quiet: bool = False):
    _, bad = scan_sessions(root)
    for p in bad:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        if not quiet:
            print(f"[WARN] corrupt session ignored: {rel} (invalid contents; inspect or delete)", flush=True)
    return bad


def active_session(root: Path):
    act = [(p, d) for p, d in load_sessions(root) if d.get("status") == "active"]
    return act[-1] if act else None


def save_session(p: Path, data: dict):
    write_atomic(p, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def events_dir(root: Path) -> Path:
    return root / PAKEM_DIR / "events"


def _event_body(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "integrity"}


def _event_hash(record: dict, prev: str | None) -> str:
    """Hash of the event content plus the previous event hash — that is what binds the chain."""
    body = _event_body(record)
    body["prev"] = prev
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _ledger_prev_hash(path: Path) -> str | None:
    """Hash of the last event; None when the ledger is empty or the last event is not intact."""
    if not path.is_file():
        return None
    try:
        lines = [line for line in read(path).splitlines() if line.strip()]
        last = json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None
    integrity = last.get("integrity") if isinstance(last, dict) else None
    if isinstance(integrity, dict) and isinstance(integrity.get("hash"), str):
        return integrity["hash"]
    return None


def verify_ledger_file(path: Path) -> dict:
    """Check the hash chain of one ledger file.

    Old events without `integrity` are accepted as pre-chain history; the new chain
    starts after them. All new events must have a matching `prev` and `hash`.
    """
    info = {"file": path.name, "events": 0, "legacy": 0, "head": None,
            "problems": [], "seals": []}
    previous: str | None = None
    if not path.is_file():
        info["problems"].append({"line": 0, "reason": "ledger missing"})
        return info
    for line_no, line in enumerate(read(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            info["problems"].append({"line": line_no, "reason": "invalid JSON"})
            previous = None
            continue
        integrity = record.get("integrity") if isinstance(record, dict) else None
        if not isinstance(integrity, dict):
            info["legacy"] += 1
            previous = None
            continue
        prev = integrity.get("prev")
        stored = integrity.get("hash")
        if prev != previous:
            info["problems"].append({
                "line": line_no, "event_id": record.get("event_id"),
                "reason": "prev mismatch: events missing, inserted, or reordered"})
        computed = _event_hash(record, prev if isinstance(prev, str) else None)
        if not isinstance(stored, str) or computed != stored:
            info["problems"].append({
                "line": line_no, "event_id": record.get("event_id"),
                "reason": "hash mismatch: event contents changed"})
        previous = stored if isinstance(stored, str) else computed
        info["events"] += 1
        info["head"] = previous
        if record.get("event") == "ledger.sealed":
            info["seals"].append({"line": line_no, "payload": record.get("payload") or {},
                                  "chain_before": prev if isinstance(prev, str) else None})
    return info


def _verify_seals(root: Path, info: dict) -> tuple[list[dict], list[str]]:
    """Verify signature envelopes on `ledger.sealed` events."""
    problems: list[dict] = []
    notes: list[str] = []
    if not info["seals"]:
        return problems, notes
    try:
        from pakem_core import identity as identity_core
    except ImportError as exc:
        return problems, [f"identity module unavailable: {exc}"]
    for seal in info["seals"]:
        payload = seal["payload"]
        envelope = payload.get("seal")
        if not isinstance(envelope, dict):
            problems.append({"line": seal["line"], "reason": "seal without signature envelope"})
            continue
        try:
            identity_core.verify(root, envelope)
        except ImportError as exc:
            notes.append(f"seal at line {seal['line']} not verified: {exc}")
            continue
        except Exception as exc:
            problems.append({"line": seal["line"], "reason": f"invalid seal signature: {exc}"})
            continue
        sealed_head = (envelope.get("payload") or {}).get("chain_head")
        if sealed_head != payload.get("chain_head"):
            problems.append({"line": seal["line"],
                             "reason": "chain_head in signature does not match payload"})
            continue
        # The signature binds the chain hash at seal time. If the whole chain is
        # rewritten (hashes recomputed by an attacker), this is where it shows: the
        # chain before the seal no longer matches what was signed.
        if sealed_head != seal.get("chain_before"):
            problems.append({"line": seal["line"],
                             "reason": "chain before seal does not match the signed chain (ledger rewritten)"})
    return problems, notes


HANDOVER_STAMP_RE = re.compile(
    r"<!--\s*pakem:handover\s+head=(?P<head>[0-9a-f]{7,40})\s+at=(?P<at>[^\s]+)"
    r"(?:\s+session=(?P<session>[^\s]+))?\s*-->")
HANDOVER_CANDIDATES = ("HANDOVER.md", "docs/HANDOVER.md")


def handover_path(root: Path):
    rel = first_existing(root, *HANDOVER_CANDIDATES)
    return (root / rel) if rel else None


def handover_state(root: Path) -> dict:
    """Handover status: present or not, its HEAD stamp, and how many commits since the stamp."""
    path = handover_path(root)
    if path is None:
        return {"present": False, "path": None, "stamp": None, "head": None,
                "stale": False, "commits_since": None}
    text = read(path)
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    match = HANDOVER_STAMP_RE.search(text)
    stamp, commits_since, stale = None, None, True
    if match:
        stamped = match.group("head")
        stamp = {"head": stamped, "at": match.group("at"), "session": match.group("session")}
        count = (_git(root, "rev-list", "--count", f"{stamped}..HEAD") or "").strip()
        commits_since = int(count) if count.isdigit() else None
        stale = not head.startswith(stamped) or bool(commits_since)
    return {"present": True, "path": path.relative_to(root).as_posix(), "stamp": stamp,
            "head": head or None, "stale": stale, "commits_since": commits_since}


def write_handover_stamp(root: Path, path: Path, session_id: str = "") -> dict:
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    if not head:
        raise ValueError("cannot read HEAD; handover stamp requires a Git commit")
    stamp = f"<!-- pakem:handover head={head} at={now()} session={session_id or '-'} -->"
    text = read(path)
    if HANDOVER_STAMP_RE.search(text):
        text = HANDOVER_STAMP_RE.sub(stamp, text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + stamp + "\n"
    write(path, text)
    return {"path": path.relative_to(root).as_posix(), "head": head, "at": now()}


def gate_handover(root: Path, finishing: bool = False):
    """A filled-in but stale HANDOVER.md still misleads the receiver.

    During `check` this is a warning, not a failure: handover only becomes relevant
    when work is about to be handed over, and a repo that commits every day would
    keep the gate red until the agent learns to ignore it. During `finish` it binds.
    """
    flag = (read_config(root).get("handover") or "false").strip().lower() == "true"
    state = handover_state(root)
    if not state["present"]:
        if flag:
            return "fail", "handover=true but HANDOVER.md is missing (run `pakem handover`)"
        return "skip", "no HANDOVER.md"
    if not state["head"]:
        return "skip", "repo has no commits; handover stamp cannot be compared"
    if state["stamp"] is None:
            return "fail", (f"{state['path']}: no HEAD stamp — cannot tell which commit "
                        f"the contents match (run `pakem handover --stamp`)")
    if state["stale"]:
        extra = (f", {count(state['commits_since'], 'commit')} since the stamp"
                 if state["commits_since"] else "")
        message = (f"{state['path']}: stale — stamp {state['stamp']['head'][:8]}, "
                   f"HEAD {(state['head'] or '?')[:8]}{extra}. Update the contents, then "
                   f"`pakem handover --stamp`")
        return ("fail" if finishing else "warn"), message
    return "pass", f"{state['path']}: stamp {state['head'][:8]}"


def ledger_targets(root: Path, session_filter: str | None = None) -> list[Path]:
    d = events_dir(root)
    if session_filter:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", session_filter):
            die("session ID contains invalid characters")
        return [d / f"{session_filter}.jsonl"]
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jsonl"))


def gate_ledger(root: Path):
    """The ledger event hash chain must be intact: no line missing, inserted, or altered."""
    act = active_session(root)
    session_id = act[1].get("id") if act else None
    files = ledger_targets(root, session_id) if session_id else ledger_targets(root)
    if not files:
        return "skip", "no event ledger yet"
    total, seals, head, problems, notes = 0, 0, None, [], []
    for path in files:
        if not path.is_file():
            continue
        info = verify_ledger_file(path)
        seal_problems, seal_notes = _verify_seals(root, info)
        info["problems"] += seal_problems
        notes += seal_notes
        total += info["events"]
        seals += len(info["seals"])
        head = info["head"] or head
        problems += [f"{info['file']}:{p['line']} {p['reason']}" for p in info["problems"]]
    if problems:
        return "fail", ("inconsistent ledger: " + "; ".join(problems[:3])
                        + ". Do not edit the ledger; restore from an intact copy")
    if not total and not seals:
        return "skip", "no integrity-protected events yet"
    message = f"{total} event, {seals} seal, head={(head or '-')[:16]}"
    if notes:
        message += " | " + "; ".join(notes[:2])
    return "pass", message


def append_event(root: Path, event: str, session: dict | None = None,
                 payload: dict | None = None, actor_type: str = "agent") -> bool:
    """Append one protocol event. Call while holding pakem_lock for serialized writes."""
    if event not in PROTOCOL_EVENTS:
        raise ValueError(f"unknown Pakem event: {event}")
    session_id = (session or {}).get("id")
    safe_session_id = session_id if isinstance(session_id, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,180}", session_id) else None
    filename = f"{safe_session_id}.jsonl" if safe_session_id else "project.jsonl"
    path = events_dir(root) / filename
    actor_name = (session or {}).get("agent") or ("pakem" if actor_type == "system" else "unknown")
    record = {
        "protocol": "pakem",
        "protocol_version": PROTOCOL_VERSION,
        "event_id": str(uuid.uuid4()),
        "event": event,
        "occurred_at": now(),
        "session_id": session_id,
        "actor": {"type": actor_type, "name": str(actor_name)},
        "payload": payload or {},
    }
    prev = _ledger_prev_hash(path)
    record["integrity"] = {"prev": prev, "hash": _event_hash(record, prev)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
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
        return True
    except OSError as exc:
        print(f"[WARN] cannot write event ledger: {exc}", flush=True)
        return False


def validate_event_record(record: object) -> list[str]:
    """Validate the v1 event envelope without third-party JSON Schema dependencies."""
    if not isinstance(record, dict):
        return ["event must be a JSON object"]
    errors = []
    required = ("protocol", "protocol_version", "event_id", "event", "occurred_at",
                "session_id", "actor", "payload")
    for key in required:
        if key not in record:
            errors.append(f"missing required field: {key}")
    if errors:
        return errors
    if record.get("protocol") != "pakem":
        errors.append("protocol must be 'pakem'")
    if record.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be '{PROTOCOL_VERSION}'")
    if not isinstance(record.get("event_id"), str) or not record["event_id"].strip():
        errors.append("event_id must be a non-empty string")
    if record.get("event") not in PROTOCOL_EVENTS:
        errors.append("event not supported by Pakem Protocol v1.0")
    if record.get("session_id") is not None and not isinstance(record.get("session_id"), str):
        errors.append("session_id must be a string or null")
    try:
        stamp = record.get("occurred_at")
        if not isinstance(stamp, str) or not stamp:
            raise ValueError
        parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed_stamp.tzinfo is None or parsed_stamp.utcoffset() is None:
            raise ValueError("timezone must be explicit")
    except (TypeError, ValueError):
        errors.append("occurred_at must be an ISO 8601 timestamp")
    actor = record.get("actor")
    if not isinstance(actor, dict):
        errors.append("actor must be an object")
    else:
        if actor.get("type") not in ("agent", "user", "system"):
            errors.append("actor.type must be agent, user, or system")
        if not isinstance(actor.get("name"), str) or not actor.get("name", "").strip():
            errors.append("actor.name must be a non-empty string")
        if set(actor) - {"type", "name"}:
            errors.append("actor may only contain type and name")
    if not isinstance(record.get("payload"), dict):
        errors.append("payload must be an object")
    integrity = record.get("integrity")
    if integrity is not None:
        if not isinstance(integrity, dict):
            errors.append("integrity must be an object")
        else:
            if set(integrity) - {"prev", "hash"}:
                errors.append("integrity may only contain prev and hash")
            if integrity.get("prev") is not None and not isinstance(integrity.get("prev"), str):
                errors.append("integrity.prev must be a string or null")
            if not isinstance(integrity.get("hash"), str) or not re.fullmatch(r"[0-9a-f]{64}",
                                                                             integrity.get("hash") or ""):
                errors.append("integrity.hash must be 64 hex characters (sha256)")
    extras = set(record) - set(required) - {"integrity"}
    if extras:
        errors.append("unknown envelope field: " + ", ".join(sorted(extras)))
    return errors


def validate_session_record(record: object) -> list[str]:
    """Validate the portable baseline while allowing legacy and forward-compatible fields."""
    if not isinstance(record, dict):
        return ["session must be a JSON object"]
    errors = []
    required = ("id", "goal", "status", "startedAt", "steps")
    for key in required:
        if key not in record:
            errors.append(f"missing required field: {key}")
    if errors:
        return errors
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        errors.append("id must be a non-empty string")
    if not isinstance(record.get("goal"), str) or not record["goal"].strip():
        errors.append("goal must be a non-empty string")
    if record.get("status") not in ("active", "finished", "abandoned"):
        errors.append("status must be active, finished, or abandoned")
    try:
        stamp = record.get("startedAt")
        parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if isinstance(stamp, str) else None
        if parsed_stamp is None or parsed_stamp.tzinfo is None or parsed_stamp.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("startedAt must be an ISO 8601 timestamp with timezone")
    if not isinstance(record.get("steps"), list):
        errors.append("steps must be an array")
    version = record.get("schemaVersion")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 1):
        errors.append("schemaVersion must be an integer >= 1 when set")
    if "finishedAt" in record:
        try:
            stamp = record["finishedAt"]
            parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if isinstance(stamp, str) else None
            if parsed_stamp is None or parsed_stamp.tzinfo is None or parsed_stamp.utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("finishedAt must be an ISO 8601 timestamp with timezone")
    return errors


def read_event_ledger(root: Path, session_filter: str | None = None):
    records, corrupt = [], []
    d = events_dir(root)
    if not d.is_dir():
        return records, corrupt
    if session_filter and not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", session_filter):
        return records, [{"file": "-", "line": 0, "reason": "session ID contains invalid characters"}]
    files = [d / f"{session_filter}.jsonl"] if session_filter else sorted(d.glob("*.jsonl"))
    for path in files:
        if not path.is_file():
            continue
        for line_no, line in enumerate(read(path).splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                corrupt.append({"file": path.name, "line": line_no, "reason": "invalid JSON"})
                continue
            problems = validate_event_record(item)
            if problems:
                corrupt.append({"file": path.name, "line": line_no, "reason": "; ".join(problems)})
                continue
            records.append(item)
    def chronological_key(item):
        stamp = datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
        return stamp.timestamp()
    records.sort(key=chronological_key)
    return records, corrupt


def print_session(d: dict):
    print(f"  id          : {d.get('id')}")
    print(f"  goal        : {d.get('goal')}")
    print(f"  started     : {d.get('startedAt')}")
    print(f"  lastPosition: {d.get('lastPosition') or '-'}")
    print(f"  nextStep    : {d.get('nextStep') or '-'}")
    ev = d.get("verifyEvidence") or {}
    if ev:
        print(f"  verify      : {ev.get('status')} exit={ev.get('exit')} hash={ev.get('outputHash') or '-'}")
    steps = d.get("steps", [])[-3:]
    if steps:
        print("  last steps:")
        for s in steps:
            print(f"    - {s['at']}: {s['text']}")


# ---------------------------------------------------------------- gate

def gate_session(root: Path, summary):
    act = active_session(root)
    if not act:
        return "fail", 'no active session. Run: pakem start "goal"'
    if not summary or len(summary.strip()) < 10:
        return "fail", "--summary required (min. 10 chars): what finished and how it was proven"
    return "pass", f"session {act[1].get('id')}"


def gate_rules(root: Path, cfg: dict):
    problems = []
    for name in ("tests", "adr", "research", "modular"):
        v = cfg.get(f"rule.{name}", "").strip()
        if not v:
            continue
        if v == "skip":
            if not cfg.get(f"reason.{name}", "").strip():
                problems.append(f"rule.{name}=skip without reason.{name} (write the reason in PROJECT.md)")
        elif v == "required":
            if name == "tests" and not find_tests(root):
                problems.append("rule.tests=required but no test files exist (besides .gitkeep)")
            elif name == "adr":
                d = root / "docs" / "adr"
                if not any(f.name != "TEMPLATE.md" for f in d.glob("*.md")):
                    problems.append("rule.adr=required but docs/adr/ has no ADR")
            elif name == "research" and not has_real_files(root / "docs" / "research"):
                problems.append("rule.research=required but docs/research/ is still empty")
        elif v not in ("when-decision", "when-needed"):
            problems.append(f"rule.{name} has unknown value: '{v}' "
                            "(use required | skip | when-decision | when-needed)")
    if problems:
        return "fail", "; ".join(problems)
    return "pass", "rules satisfied"


PLACEHOLDER_RES = [re.compile(r"\[(?:ISI|FILL)\b"), re.compile(r"\{\{[^}]*\}\}"), re.compile(r"\bTODO\b")]

def has_placeholder(text: str) -> bool:
    """True for `[FILL`, `[ISI` (legacy), `{{...}}`, or `TODO`."""
    return any(r.search(text or "") for r in PLACEHOLDER_RES)


def gate_placeholder(root: Path):
    files = sorted((root / PAKEM_DIR).glob("*.md"))
    files += sorted(f for f in (root / "docs" / "adr").glob("*.md") if f.name != "TEMPLATE.md")
    for rel in ("HANDOVER.md", "docs/HANDOVER.md"):
        p = root / rel
        if p.is_file():
            files.append(p)
    hits = []
    for f in files:
        for i, line in enumerate(strip_comments(read(f)).splitlines(), 1):
            if any(r.search(line) for r in PLACEHOLDER_RES):
                hits.append(f"{f.relative_to(root).as_posix()}:{i}")
    if hits:
        shown = ", ".join(hits[:10]) + (f" (+{len(hits) - 10} more)" if len(hits) > 10 else "")
        return "fail", f"{len(hits)} placeholders remaining: {shown}"
    return "pass", "no placeholders"


def spec_path(root: Path) -> Path:
    return root / PAKEM_DIR / SPEC_FILE

def plan_path(root: Path) -> Path:
    return root / PAKEM_DIR / PLAN_FILE

def spec_status(root: Path) -> str:
    p = spec_path(root)
    if not p.is_file():
        return "missing"
    m = re.search(r"(?mi)^status:\s*(draft|approved)\s*$", read(p))
    return m.group(1).lower() if m else "draft"

def plan_tasks(root: Path):
    p = plan_path(root)
    if not p.is_file():
        return []
    tasks = []
    for mark, tid, text, files, verify in PLAN_RE.findall(read(p)):
        text = text.strip()
        tasks.append({"done": mark == "x", "id": tid, "text": text,
                      "files": files.strip(), "verify": verify.strip(),
                      "dropped": bool(re.search(r"\[dropped:", text))})
    return tasks

def malformed_plan_lines(root: Path):
    p = plan_path(root)
    if not p.is_file():
        return []
    return [line for line in read(p).splitlines()
            if line.startswith("- [") and not PLAN_RE.match(line)]

def clean_plan_field(value: str, allow_pipe: bool = False) -> str:
    """One task per line, so newlines are always discarded.

    `|` is the column separator in PLAN.md: text/files fields discard it. The verify
    field sits at the end of the line, so shell pipes are safely preserved.
    """
    pattern = r"[\r\n]+" if allow_pipe else r"[\r\n|]+"
    return re.sub(pattern, " ", value or "").strip()

def write_plan(root: Path, tasks):
    done = sum(1 for t in tasks if t["done"])
    lines = [
        "# PLAN",
        "",
        "Small tasks (2-5 minutes). One task per line.",
        "",
        f"Status: {done}/{len(tasks)} done.",
        "",
        "## Tasks",
    ]
    for t in tasks:
        mark = "x" if t["done"] else " "
        lines.append(f"- [{mark}] {t['id']} - {t['text']} | files: {t['files']} | verify: {t['verify']}")
    write(plan_path(root), "\n".join(lines) + "\n")

def sync_plan_next(root: Path, tasks):
    """PLAN is intent; nextStep is the actual position. After the plan changes, align them."""
    act = active_session(root)
    if not act:
        return
    pending = next((t for t in tasks if not t["done"]), None)
    next_step = f"{pending['id']} - {pending['text']}" if pending else "done - run pakem finish"
    if act[1].get("nextStep") == next_step:
        return
    act[1]["nextStep"] = next_step
    act[1]["git"] = git_state(root)
    save_session(act[0], act[1])

ACCEPTANCE_RE = re.compile(r"(?m)^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")


def spec_acceptance(root: Path) -> list[dict]:
    """Read the checkboxes in the Acceptance section of SPEC.md. Empty when that section is absent."""
    p = spec_path(root)
    if not p.is_file():
        return []
    text = read(p)
    m = re.search(r"(?ms)^##\s*Acceptance\s*$(.*?)(?=^##\s|\Z)", text)
    if not m:
        return []
    return [{"text": body.strip(), "checked": mark.lower() == "x"}
            for mark, body in ACCEPTANCE_RE.findall(m.group(1))]


def gate_spec(root: Path):
    p = spec_path(root)
    if not p.is_file():
        return "skip", "no SPEC.md"
    status = spec_status(root)
    if status != "approved":
        return "fail", "SPEC.md exists but is not approved. Fill the placeholders, then: pakem spec --approve"
    return "pass", "SPEC.md approved"


def gate_acceptance(root: Path):
    """Only during finish: approval proves the plan, checkboxes prove the result."""
    if not spec_path(root).is_file():
        return "skip", "no SPEC.md"
    acceptance = spec_acceptance(root)
    if not acceptance:
        return "skip", "SPEC.md has no Acceptance section"
    unchecked = [item["text"] for item in acceptance if not item["checked"]]
    if unchecked:
        first = unchecked[0]
        more = f" (+{len(unchecked) - 1} more)" if len(unchecked) > 1 else ""
        return "fail", (f"{len(unchecked)}/{len(acceptance)} acceptance criteria unchecked: "
                        f"{first[:60]}{more}. Check it in SPEC.md only when actually proven")
    return "pass", f"acceptance {len(acceptance)}/{len(acceptance)} checked"


def plan_scope_tasks(root: Path) -> list[dict]:
    """Shape plan tasks for reconciliation: files are split on commas."""
    return [{"taskId": task["id"], "done": task["done"],
             "files": [f.strip() for f in task["files"].split(",") if f.strip()]}
            for task in plan_tasks(root)]


def board_scope_tasks(root: Path) -> list[dict]:
    """Team tasks on the board also declare files; they are a scope source too."""
    path = root / ".pakem" / "team" / "board.json"
    if not path.is_file():
        return []
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    tasks = board.get("tasks") or {}
    items = tasks.values() if isinstance(tasks, dict) else tasks
    out = []
    for task in items:
        if not isinstance(task, dict):
            continue
        task_id = task.get("taskId") or task.get("id")
        files = task.get("files") or []
        if isinstance(files, str):
            files = files.split(",")
        files = [str(f).strip() for f in files if str(f).strip()]
        if task_id and files:
            out.append({"taskId": str(task_id), "done": task.get("state") in ("done", "closed"),
                        "files": files})
    return out


def scope_tasks(root: Path) -> list[dict]:
    """Merge scope from PLAN.md and the board per taskId, without duplicate files."""
    merged: dict[str, dict] = {}
    for task in plan_scope_tasks(root) + board_scope_tasks(root):
        task_id = str(task["taskId"])
        if task_id not in merged:
            merged[task_id] = {"taskId": task_id, "done": bool(task["done"]),
                               "files": list(task["files"])}
            continue
        entry = merged[task_id]
        entry["files"] += [f for f in task["files"] if f not in entry["files"]]
        entry["done"] = entry["done"] and bool(task["done"])
    return list(merged.values())


def _reconcile_import():
    try:
        from pakem_core import reconcile as core
        from pakem_core import intelligence
        return core, intelligence
    except ImportError as exc:
        die(f"Pakem Reconcile module unavailable: {exc}. Run the latest CLI from the skill install: "
            f"`python3 <skill-location>/scripts/pakem.py upgrade` from the project root.")


def build_reconciliation(root: Path, base: str | None = None, staged: bool = False) -> dict:
    core, intelligence = _reconcile_import()
    try:
        changed = intelligence.changed_files_for_impact(root, base=base, staged=staged)
    except intelligence.NoChangesDetected:
        changed = []  # a clean repo is a valid result, not an error
    return core.reconcile(changed, scope_tasks(root), spec_acceptance(root))


def session_base(root: Path):
    """HEAD when the active session started.

    The `scope` gate must see work that is already committed. `git diff HEAD` only
    sees the working tree, so an agent that commits and then runs `finish` passed
    the gate without ever being compared against its task scope.
    """
    act = active_session(root)
    if not act:
        return None
    return (act[1].get("git") or {}).get("head") or None

def gate_scope(root: Path):
    """Code changes outside the task scope = a sign of work drifting without a trace."""
    if not plan_path(root).is_file() and not board_scope_tasks(root):
        return "skip", "no task scope (PLAN.md or board)"
    try:
        result = build_reconciliation(root, base=session_base(root))
    except SystemExit:
        raise
    except Exception as exc:  # no git repo, etc.
        return "skip", f"cannot read changes: {exc}"
    code_out = result["code_out_of_scope"]
    other_out = [p for p in result["out_of_scope"] if p not in code_out]
    if code_out:
        shown = ", ".join(code_out[:4]) + (" ..." if len(code_out) > 4 else "")
        return "fail", (f"{len(code_out)} code files changed outside task scope: {shown}. "
                        f"Add scope (pakem plan add ... --files ... / team add ... --files ...) "
                        f"or revert the changes")
    if other_out:
        return "pass", f"{len(other_out)} non-code files outside scope (docs/config): " + ", ".join(other_out[:4])
    if result["summary"]["changed"]:
        return "pass", f"{result['summary']['in_scope']} files changed, all within task scope"
    return "pass", "no pending changes"

def worktree_scope(root: Path, name: str) -> tuple[dict, dict]:
    """Reconcile one worktree against the task scope recorded in its name."""
    from pakem_core import git_worktree
    path = git_worktree.resolve(root, name)
    changed = git_worktree.changed_files(root, path)
    task_id = path.name.split("--", 1)[0]
    tasks = [task for task in scope_tasks(root) if str(task["taskId"]) == task_id]
    core, _ = _reconcile_import()
    result = core.reconcile(changed, tasks, [])
    meta = {"name": path.name, "task": task_id, "path": path.relative_to(root).as_posix(),
            "scoped": bool(tasks)}
    return result, meta


def gate_worktree(root: Path):
    """Changes in a managed worktree must stay inside its task scope.

    Without this gate, an agent could drift inside an isolated worktree unseen by
    `scope`, and the changes would land when the branch is merged.
    """
    if not (root / ".pakem" / "worktrees").is_dir():
        return "skip", "no Pakem worktrees"
    try:
        from pakem_core import git_worktree
        entries = git_worktree.list_worktrees(root)["worktrees"]
    except Exception as exc:
        return "skip", f"cannot read worktree list: {exc}"
    managed = [e for e in entries if e.get("managed_by_pakem") and Path(e["path"]).exists()]
    if not managed:
        return "skip", "no active Pakem worktrees"
    problems, unreadable, files = [], [], 0
    for entry in managed:
        name = Path(entry["path"]).name
        try:
            result, meta = worktree_scope(root, name)
        except SystemExit:
            raise
        except Exception as exc:
            unreadable.append(f"{name} ({exc})")
            continue
        files += len(result["changed_files"])
        if not meta["scoped"] and result["changed_files"]:
            problems.append(f"{meta['name']}: task {meta['task']} has no file scope "
                            f"(pakem plan add ... --files ... or team add ... --files ...)")
        elif result["code_out_of_scope"]:
            shown = ", ".join(result["code_out_of_scope"][:4])
            problems.append(f"{meta['name']}: {shown}")
    if problems:
        return "fail", ("code outside worktree scope: " + "; ".join(problems[:3])
                        + ". Add task scope or revert the changes")
    note = f" (unreadable: {', '.join(unreadable[:2])})" if unreadable else ""
    return "pass", f"{len(managed)} worktrees, {files} files changed, all within scope{note}"


def gate_plan(root: Path):
    p = plan_path(root)
    if not p.is_file():
        return "skip", "no PLAN.md"
    bad = malformed_plan_lines(root)
    if bad:
        return "fail", f"{len(bad)} unrecognized task lines in PLAN.md (use the pakem plan add format)"
    tasks = plan_tasks(root)
    if not tasks:
        return "fail", "PLAN.md has no tasks yet (pakem plan add ...)"
    pending = [t["id"] for t in tasks if not t["done"]]
    if pending:
        return "fail", f"{count(len(pending), 'task')} not done: {', '.join(pending)}"
    return "pass", f"{len(tasks)} tasks done"

def print_workflow(root: Path):
    if spec_path(root).is_file():
        print(f"  spec        : {spec_status(root)}")
    tasks = plan_tasks(root)
    if tasks:
        done = sum(1 for t in tasks if t["done"])
        pending = next((t for t in tasks if not t["done"]), None)
        tail = f"; next {pending['id']} - {pending['text']}" if pending else "; all done"
        print(f"  plan        : {done}/{len(tasks)} done{tail}")


PATH_TOKEN = re.compile(r"`([^`\s]+)`")
EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,4}$")


def gate_drift(root: Path):
    bad = []
    for fname in ("MODULE-MAP.md", "DECISIONS.md"):
        p = root / PAKEM_DIR / fname
        if not p.exists():
            continue
        raw = read(p)
        raw_lines = raw.splitlines()
        for i, line in enumerate(strip_comments(raw).splitlines(), 1):
            if i <= len(raw_lines) and "pakem:ignore" in raw_lines[i - 1]:
                continue
            for m in PATH_TOKEN.finditer(line):
                tok = m.group(1).rstrip(".,;:")
                tok = re.sub(r":\d+(-\d+)?$", "", tok)
                if tok.startswith(("http://", "https://", "-", "$", "~", "@", "#", "/")):
                    continue
                if any(c in tok for c in "*<>{}|=()[]\\"):
                    continue
                if tok.startswith(".env"):
                    continue
                if "/" not in tok and not EXT_RE.search(tok):
                    continue
                if not (root / tok).exists():
                    bad.append(f"{fname}:{i} -> {tok}")
    if bad:
        shown = "; ".join(bad[:10]) + (f" (+{len(bad) - 10} more)" if len(bad) > 10 else "")
        return "fail", f"paths in docs do not exist in the repo (drift): {shown}"
    return "pass", "paths in MODULE-MAP/DECISIONS are still valid"


def gate_verify(root: Path, cfg: dict, skip: bool, evidence: dict | None = None):
    cmd = cfg.get("verify", "").strip()
    if skip:
        if evidence is not None:
            evidence["verify"] = {"cmd": cmd, "status": "skip", "exit": None, "at": now(),
                                  "reason": "--skip-verify"}
        return "skip", "verify skipped (--skip-verify)"
    if not cmd or has_placeholder(cmd):
        reason = cfg.get("reason.verify", "").strip()
        if reason:
            if evidence is not None:
                evidence["verify"] = {"cmd": cmd, "status": "skip", "exit": None,
                                      "at": now(), "reason": reason}
            return "skip", f"verify skipped: {reason}"
        if evidence is not None:
            evidence["verify"] = {"cmd": cmd, "status": "fail", "exit": None,
                                  "at": now(), "reason": "verify empty"}
        return "fail", "`verify` in PROJECT.md is empty. Fill in the test/lint/build command, or write reason.verify."
    try:
        timeout = int(cfg.get("verify.timeout", "900") or 900)
    except ValueError:
        timeout = 900
    print(f"       $ {cmd}", flush=True)
    started = time.monotonic()
    try:
        r = subprocess.run(cmd, shell=True, cwd=root, timeout=timeout, capture_output=True, text=True)
        output = (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
        status = "pass" if rc == 0 else "fail"
        msg = "verify exit 0" if rc == 0 else f"verify exit {rc}"
    except subprocess.TimeoutExpired as e:
        raw = (e.stdout or "") + (e.stderr or "")
        output = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        rc = None
        status = "fail"
        msg = f"verify exceeded the {timeout}s limit"
    if output:
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
    if evidence is not None:
        evidence["verify"] = {
            "cmd": cmd,
            "status": status,
            "exit": rc,
            "at": now(),
            "durationMs": int((time.monotonic() - started) * 1000),
            "outputHash": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()[:16],
            "pakemHash": pakem_hash(root),
        }
    return status, msg


def gate_bug(root: Path):
    act = active_session(root)
    if act and act[1].get("bugs"):
        return "pass", "bug entries for this session: " + ", ".join(act[1]["bugs"])
    return "fail", '--fixed-bug used but no entry exists. Run: pakem bug "title"'


def run_gates(root: Path, cfg: dict, *, skip_verify=False, summary=None, finishing=False,
              fixed_bug=False, evidence: dict | None = None):
    """Run all gates, print the results. Return (failed gate names, warnings)."""
    plan = []
    if finishing:
        plan.append(("session", lambda: gate_session(root, summary)))
        if fixed_bug:
            plan.append(("bug", lambda: gate_bug(root)))
    plan += [
        ("rules", lambda: gate_rules(root, cfg)),
        ("placeholder", lambda: gate_placeholder(root)),
        ("spec", lambda: gate_spec(root)),
        ("plan", lambda: gate_plan(root)),
        ("task-verify", lambda: gate_task_verify(root)),
        ("scope", lambda: gate_scope(root)),
        ("worktree", lambda: gate_worktree(root)),
        ("drift", lambda: gate_drift(root)),
        ("handover", lambda: gate_handover(root, finishing)),
        ("ledger", lambda: gate_ledger(root)),
    ]
    if finishing:
        plan.append(("acceptance", lambda: gate_acceptance(root)))
    plan.append(("verify", lambda: gate_verify(root, cfg, skip_verify, evidence)))
    failed, warnings = [], []
    for name, fn in plan:
        status, msg = fn()
        if status not in ("pass", "fail", "skip", "warn"):
            status = "fail"
        print(f"[{ {'pass': 'PASS', 'fail': 'FAIL', 'skip': 'SKIP', 'warn': 'WARN'}[status] }] "
              f"{name}: {msg}", flush=True)
        if status == "fail":
            failed.append(name)
        elif status == "warn":
            warnings.append(f"{name}: {msg}")
    act = active_session(root)
    if act:
        for w in tamper_findings(root, cfg, act[1]):
            warnings.append(f"rules-changed: {w}")
            print(f"[WARN] rules-changed: {w}", flush=True)
    return failed, warnings


# ---------------------------------------------------------------- adapter

def parse_adapters(s: str):
    s = (s or "").strip()
    if s in ("", "none"):
        return []
    names = [x.strip() for x in s.split(",") if x.strip()]
    for n in names:
        if n not in ADAPTERS:
            die(f"unknown adapter: {n}. Choices: {', '.join(ADAPTERS)}")
    return names


def write_adapter(root: Path, name: str) -> str:
    rel, header = ADAPTERS[name]
    p = root / rel
    if p.exists():
        t = read(p)
        if BEGIN in t and END in t:
            new = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), lambda m: BLOCK, t, flags=re.S)
            state = "updated"
        else:
            new = t.rstrip("\n") + "\n\n" + BLOCK + "\n"
            state = "block added"
    else:
        new = header + BLOCK + "\n"
        state = "created"
    write(p, new)
    return f"{rel} ({state})"


# ---------------------------------------------------------------- commands

def cmd_init(a):
    root = Path.cwd()
    pk = root / PAKEM_DIR
    if pk.exists() and not a.force:
        die(".pakem/ already exists. Use --force to overwrite template files (old contents are lost).")
    if not TEMPLATE_DIR.is_dir():
        die(f"assets/templates folder not found at {TEMPLATE_DIR}. Run init from the Pakem skill location.")
    existing = (not a.fresh) and (a.existing or any((root / m).exists() for m in EXISTING_MARKERS))
    prof = dict(PROFILES[a.type])
    reasons = dict(DEFAULT_REASONS.get(a.type, {}))
    if existing and prof["tests"] == "required" and not find_tests(root):
        prof["tests"] = "skip"
        reasons["tests"] = ("Existing repo has no tests; follow the existing pattern. "
                            "Switch to required if you want to start adding tests.")
    verify = a.verify if a.verify is not None else detect_verify(root)

    files = FILES_BY_TYPE[a.type]
    routing = "\n".join(
        f"| {when} | {what} |" for f, (when, what) in ROUTING_ROWS.items() if f in files
    )
    subs = {
        "TYPE": a.type, "NAME": root.name, "VERIFY": verify,
        "R_TESTS": prof["tests"], "REASON_TESTS": reasons.get("tests", ""),
        "R_ADR": prof["adr"], "REASON_ADR": reasons.get("adr", ""),
        "R_RESEARCH": prof["research"], "REASON_RESEARCH": reasons.get("research", ""),
        "R_MODULAR": prof["modular"], "REASON_MODULAR": reasons.get("modular", ""),
        "REASON_VERIFY": reasons.get("verify", ""),
        "DOD": DOD[a.type], "ROUTING": routing, "DATE": datetime.now().strftime("%Y-%m-%d"),
        "PROTOCOL": PROTOCOL_TEXT,
        "EXISTING_NOTE": ("This repo existed before Pakem. FOLLOW the existing pattern; "
                          "do not reshape the structure unless the user asks.") if existing else
                         "New project: the structure follows the `rule.*` section above.",
    }
    (pk / "sessions").mkdir(parents=True, exist_ok=True)
    for fname in files:
        text = read(TEMPLATE_DIR / fname)
        for k, v in subs.items():
            text = text.replace("{{" + k + "}}", v)
        write(pk / fname, text)

    created = []
    if not existing:
        if prof["tests"] == "required":
            write(root / "tests" / ".gitkeep", "")
            created.append("tests/")
        if prof["adr"] != "skip":
            write(root / "docs" / "adr" / "TEMPLATE.md",
                  ADR_TEMPLATE.format(num="NNNN", title="[decision title]", date="YYYY-MM-DD"))
            created.append("docs/adr/")
        if prof["research"] == "required":
            write(root / "docs" / "research" / ".gitkeep", "")
            created.append("docs/research/")

    # sessions are local by default
    gi = root / ".gitignore"
    lines = [".pakem/sessions/", ".pakem/events/", ".pakem/runtime/", ".pakem/team/", ".pakem/worktrees/"]
    cur = read(gi) if gi.exists() else ""
    missing_lines = [line for line in lines if line not in cur.splitlines()]
    if missing_lines:
        write(gi, (cur.rstrip("\n") + "\n" if cur else "") + "".join(line + "\n" for line in missing_lines))

    # copy the CLI into the project so it is self-contained (used by hooks and adapters)
    dst = pk / "pakem.py"
    if Path(__file__).resolve() != dst.resolve():
        write(dst, Path(__file__).read_text(encoding="utf-8"))
    core_files = sync_core_package(root)
    intelligence_files = sync_intelligence_schemas(root)
    protocol_files = sync_protocol_schemas(root)
    runtime_schema_files = sync_runtime_schemas(root)
    coordination_schema_files = sync_coordination_schemas(root)
    identity_schema_files = sync_identity_schemas(root)
    storage_schema_files = sync_storage_schemas(root)
    adapter_doc_files = sync_adapter_docs(root)
    try:
        from pakem_core.runtime import ensure_policy
        policy_created = ensure_policy(root, TEMPLATE_DIR / "POLICY.json")
    except ImportError as exc:
        die(f"Pakem Runtime module unavailable: {exc}")

    adapters = []
    for n in parse_adapters(a.adapter):
        adapters.append(write_adapter(root, n))

    print(f"Pakem installed in {root} (type: {a.type}, {'existing repo' if existing else 'new project'})")
    print(f"  .pakem/: {', '.join(files)}")
    if created:
        print(f"  new folders: {', '.join(created)}")
    for x in adapters:
        print(f"  adapter: {x}")
    if core_files:
        print(f"  core modules: {', '.join(core_files)}")
    if intelligence_files:
        print(f"  intelligence schemas: {', '.join(intelligence_files)}")
    if runtime_schema_files:
        print(f"  runtime/policy schemas: {', '.join(runtime_schema_files)}")
    if coordination_schema_files:
        print(f"  coordination schemas: {', '.join(coordination_schema_files)}")
    if identity_schema_files:
        print(f"  identity schemas: {', '.join(identity_schema_files)}")
    if storage_schema_files:
        print(f"  storage schemas: {', '.join(storage_schema_files)}")
    if adapter_doc_files:
        print(f"  adapter contracts: {', '.join(adapter_doc_files)}")
    if policy_created:
        print("  policy: .pakem/POLICY.json created (assisted mode)")
    print(f"  verify detected: {verify or '(empty - fill in PROJECT.md)'}")
    if a.hook:
        cmd_hook(argparse.Namespace(action="install", skip_verify=False))
    rows, _, _ = audit_rows(root, read_config(root))
    wajib_gap = sum(1 for r in rows if r["tier"] == "required" and r["ok"] is False)
    advised_gap = sum(1 for r in rows if r["tier"] == "recommended" and r["ok"] is False)
    n_tidak = sum(1 for r in rows if r["tier"] == "not-needed")
    print(f"\nArtifact plan: {wajib_gap} REQUIRED missing, {advised_gap} recommended, {n_tidak} not needed.")
    print("  Details: python3 .pakem/pakem.py audit. Do not create empty files; defer what is not needed yet.")
    print("\nNext steps:")
    print("  1. Fill every [FILL: ...] in .pakem/*.md (pakem check rejects while any remain).")
    print("  2. Make sure `verify` in .pakem/PROJECT.md has the right test/lint/build command.")
    print("  3. See which artifacts are worthwhile: python3 .pakem/pakem.py audit")
    print('  4. python3 .pakem/pakem.py start "<goal>"')
    return 0


def cmd_start(a):
    root = need_root()
    warn_corrupt_sessions(root)
    cfg = read_config(root)
    with pakem_lock(root):
        return _start_locked(a, root, cfg)

def _start_locked(a, root, cfg):
    act = active_session(root)
    if act and not a.new:
        append_event(root, "session.resumed", act[1],
                     {"requested_goal": a.goal, "next_step": act[1].get("nextStep") or None})
        print("An active session is not finished. CONTINUE this session; do not start from scratch:")
        print_session(act[1])
        print_workflow(root)
        saved, cur = act[1].get("git"), git_state(root)
        if saved is not None and cur is not None:
            msgs = git_drift(root, saved, cur)
            if msgs:
                print("\nCHECK: repo state changed since the last record:")
                for m in msgs:
                    print(f"  - {m}")
                print("  (may be unrecorded work; verify first before continuing from nextStep)")
            else:
                print("\nRepo state is unchanged since the last record.")
        print("\n(Want to ignore the old session and start fresh? pakem start --new \"goal\")")
        return 0
    if act and a.new:
        act[1]["status"] = "abandoned"
        act[1]["abandonedAt"] = now()
        save_session(act[0], act[1])
        append_event(root, "session.abandoned", act[1], {"reason": "replaced_by_new_session"})
    sid = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f") + "-" + slug(a.goal)
    data = {
        "id": sid, "goal": a.goal, "prompt": a.prompt or a.goal, "agent": a.agent or "",
        "status": "active", "startedAt": now(), "steps": [],
        "lastPosition": "", "nextStep": "", "summary": "", "gateFailures": [],
        "bugs": [], "warnings": [],
        "configSnapshot": config_snapshot(cfg), "pakemHash": pakem_hash(root),
        "pakemIntegrity": pakem_manifest(root), "git": git_state(root),
    }
    data["schemaVersion"] = 1
    save_session(sessions_dir(root) / f"{sid}.json", data)
    append_event(root, "session.started", data, {"goal": a.goal, "agent": data.get("agent") or None})
    print(f"Session created: {sid}")
    print_workflow(root)
    print("Read .pakem/CONTEXT.md first, then the files it routes you to.")
    return 0


def cmd_step(a):
    root = need_root()
    with pakem_lock(root):
        return _step_locked(a, root)

def _step_locked(a, root):
    act = active_session(root)
    if not act:
        die('no active session. Run: pakem start "goal"')
    p, d = act
    d["steps"].append({"at": now(), "text": a.text})
    d["lastPosition"] = a.text
    if a.next is not None:
        d["nextStep"] = a.next
    d["git"] = git_state(root)
    save_session(p, d)
    append_event(root, "session.step_recorded", d,
                 {"text": a.text, "next_step": d.get("nextStep") or None})
    print(f"Recorded. nextStep: {d.get('nextStep') or '-'}")
    return 0


def _stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _span_ms(start, end):
    first, last = _stamp(start), _stamp(end)
    if first is None or last is None:
        return None
    return max(int((last - first).total_seconds() * 1000), 0)


def _human_duration(ms):
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{int(ms)}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}j {int((seconds % 3600) // 60)}m"


def build_report(root: Path, session_id: str = "", limit: int = 0) -> dict:
    """Summarize work from existing sources: sessions, plan, verify evidence, ledger.

    The reported time is the session wall clock (startedAt until finishedAt/now),
    not the agent's compute time — Pakem does not measure that and will not guess it.
    """
    sessions, _bad = scan_sessions(root)
    ledger = {"files": 0, "events": 0, "seals": 0, "head": None, "ok": True, "problems": []}
    per_session_events = {}
    directory = events_dir(root)
    if directory.is_dir():
        for path in sorted(directory.glob("*.jsonl")):
            info = verify_ledger_file(path)
            seal_problems, _notes = _verify_seals(root, info)
            info["problems"] += seal_problems
            ledger["files"] += 1
            ledger["events"] += info["events"]
            ledger["seals"] += len(info["seals"])
            ledger["head"] = info["head"] or ledger["head"]
            per_session_events[path.stem] = info["events"]
            ledger["problems"] += [{"file": info["file"], **problem} for problem in info["problems"]]
    ledger["ok"] = not ledger["problems"]

    rows = []
    for path, data in sessions:
        sid = str(data.get("id") or path.stem)
        finished = data.get("finishedAt")
        rows.append({
            "id": sid,
            "goal": str(data.get("goal") or ""),
            "agent": str(data.get("agent") or ""),
            "status": str(data.get("status") or "?"),
            "started_at": data.get("startedAt"),
            "finished_at": finished,
            "duration_ms": _span_ms(data.get("startedAt"), finished or now()),
            "steps": len(data.get("steps") or []),
            "events": per_session_events.get(sid, 0),
            "gate_failures": len(data.get("gateFailures") or []),
            "warnings": len(data.get("warnings") or []),
            "fabricated_verify": bool((data.get("verifyEvidence") or {}).get("fabricated")),
        })
    rows.sort(key=lambda row: str(row["started_at"] or ""), reverse=True)
    if session_id:
        rows = [row for row in rows if row["id"] == session_id]
    if limit > 0:
        rows = rows[:limit]

    evidence = load_task_evidence(root).get("tasks", {})
    tasks = []
    for task in plan_tasks(root):
        entry = evidence.get(task["id"]) or {}
        state = "dropped" if task["dropped"] else ("done" if task["done"] else "open")
        tasks.append({
            "task_id": task["id"],
            "state": state,
            "text": task["text"],
            "scope": [part for part in re.split(r"[,\s]+", task["files"]) if part],
            "verify_status": entry.get("status"),
            "verify_duration_ms": entry.get("durationMs"),
            "verified_at": entry.get("at"),
            "waived_reason": entry.get("reason") if entry.get("status") == "waived" else None,
            "evidence_files": sorted((entry.get("files") or {}).keys()),
        })

    totals = {
        "sessions": len(rows),
        "duration_ms": sum(row["duration_ms"] or 0 for row in rows),
        "events": sum(row["events"] for row in rows),
        "tasks": len(tasks),
        "tasks_done": sum(1 for task in tasks if task["state"] == "done"),
        "tasks_open": sum(1 for task in tasks if task["state"] == "open"),
        "tasks_dropped": sum(1 for task in tasks if task["state"] == "dropped"),
        "verified": sum(1 for task in tasks if task["verify_status"] == "pass"),
        "verify_failed": sum(1 for task in tasks if task["verify_status"] == "fail"),
        "waived": sum(1 for task in tasks if task["verify_status"] == "waived"),
        "unproven_done": sum(1 for task in tasks if task["state"] == "done"
                              and task["verify_status"] not in ("pass", "waived")),
    }
    return {"schema_version": WORK_REPORT_VERSION, "generated_at": now(),
            "scope": {"session": session_id or None, "limit": limit or None},
            "sessions": rows, "tasks": tasks, "ledger": ledger, "totals": totals}


def render_report(data: dict) -> None:
    totals = data["totals"]
    ledger = data["ledger"]
    print(f"WORK REPORT  {totals['sessions']} sessions, {totals['tasks']} tasks")
    spans = [stamp for stamp in (_stamp(row["started_at"]) for row in data["sessions"]) if stamp]
    if spans:
        oldest, newest = min(spans), max(spans)
        print(f"range          : {oldest.strftime('%Y-%m-%d %H:%M')} .. "
              f"{newest.strftime('%Y-%m-%d %H:%M')}  (total {_human_duration(totals['duration_ms'])})")
    print("time           : session wall clock, not agent compute time")
    print()
    print("SESSIONS")
    if not data["sessions"]:
        print("  (no sessions yet)")
    for row in data["sessions"]:
        status = "active" if row["status"] == "active" else row["status"]
        goal = (row["goal"] or row["id"])[:38]
        print(f"  {goal:<38} {_human_duration(row['duration_ms']):>8}  "
              f"{row['steps']:>2} step  {row['events']:>3} event  {status}")
        if row["gate_failures"] or row["warnings"]:
            print(f"  {'':<38} gate failures {row['gate_failures']}, warnings {row['warnings']}")
    print()
    print("TASKS (PLAN.md)" + ("  — whole project; the session filter applies only to the SESSIONS list"
                              if data["scope"]["session"] else ""))
    if not data["tasks"]:
        print("  (no tasks yet)")
    for task in data["tasks"]:
        mark = "x" if task["state"] == "done" else ("-" if task["state"] == "dropped" else " ")
        detail = []
        if task["verify_status"] == "pass":
            detail.append(f"verify pass {_human_duration(task['verify_duration_ms'])}")
        elif task["verify_status"] == "fail":
            detail.append("verify FAILED")
        elif task["verify_status"] == "waived":
            detail.append(f"waived: {task['waived_reason'] or 'without reason'}")
        elif task["state"] == "done":
            detail.append("without verify evidence")
        if task["scope"]:
            detail.append(", ".join(task["scope"][:3]) + (" ..." if len(task["scope"]) > 3 else ""))
        print(f"  [{mark}] {task['task_id']:<6} {task['text'][:44]:<44} {'  '.join(detail)}")
    print()
    head = (ledger["head"] or "-")[:16]
    verdict = "OK" if ledger["ok"] else "BROKEN"
    print(f"LEDGER  {ledger['files']} file, {ledger['events']} event, {ledger['seals']} seal, "
          f"head={head}  {verdict}")
    for problem in ledger["problems"][:3]:
        print(f"  {problem['file']}:{problem['line']}  {problem['reason']}")
    print()
    print(f"EVIDENCE  {count(totals['verified'], 'task')} proven, {totals['verify_failed']} failed, "
          f"{totals['waived']} waived, {totals['unproven_done']} done without evidence")
    if totals["unproven_done"]:
        print("        tasks done without evidence are rejected by the task-verify gate; run `pakem plan done <id>`")
    if not ledger["ok"]:
        print("        broken ledger: inspect with `pakem events --verify`")


def cmd_report(a) -> int:
    root = need_root()
    warn_corrupt_sessions(root)
    if a.limit < 0:
        die("--limit must not be negative")
    data = build_report(root, session_id=(a.session or ""), limit=a.limit)
    if a.session and not data["sessions"]:
        die(f"session not found: {a.session}")
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data["ledger"]["ok"] else 1
    render_report(data)
    return 0 if data["ledger"]["ok"] else 1


def cmd_status(a):
    root = need_root()
    warn_corrupt_sessions(root)
    cfg = read_config(root)
    print(f"Project: {root.name}  (type: {cfg.get('type', '?')})")
    print(f"verify : {cfg.get('verify') or '(empty)'}")
    rules = [f"{n}={cfg.get('rule.' + n)}" for n in ("tests", "adr", "research", "modular") if cfg.get("rule." + n)]
    print(f"rules  : {', '.join(rules) or '-'}")
    print_workflow(root)
    act = active_session(root)
    if act:
        print("Active session:")
        print_session(act[1])
    else:
        print("Active session: none")
        done = [d for _, d in load_sessions(root) if d.get("status") == "finished"]
        if done:
            print(f"Last session finished: {done[-1]['id']} - {done[-1].get('summary', '')[:80]}")
    return 0


def cmd_integrity(a):
    """Show whether the CLI/Core running the gates is still the same as the one pinned at start."""
    root = need_root()
    act = active_session(root)
    if a.session:
        path = sessions_dir(root) / f"{a.session}.json"
        if not path.is_file():
            die(f"session not found: {a.session}")
        try:
            sess = json.loads(read(path))
        except ValueError:
            die(f"corrupt session: {a.session}")
    elif act:
        sess = act[1]
    else:
        die("no active session; use --session ID or run `pakem start` first")
    pinned = sess.get("pakemIntegrity") or {}
    if not pinned and sess.get("pakemHash"):
        pinned = {"pakem.py": sess["pakemHash"]}
    if a.re_pin:
        if not a.reason:
            die("--re-pin requires --reason so the change reason is recorded")
        drift = integrity_drift(root, pinned)
        sess["pakemIntegrity"] = pakem_manifest(root)
        sess["pakemHash"] = pakem_hash(root)
        target = act[0] if (act and act[1] is sess) else sessions_dir(root) / f"{sess['id']}.json"
        save_session(target, sess)
        append_event(root, "integrity.repinned", sess,
                     {"files": [item["file"] for item in drift], "reason": clean_plan_field(a.reason)})
        print(f"Integrity re-pinned: {len(pinned)} files; {len(drift)} changes recorded "
              f"({', '.join(item['file'] for item in drift) or '-'})")
        return 0
    drift = integrity_drift(root, pinned)
    payload = {"session": sess.get("id"), "pinned_count": len(pinned), "drift": drift,
               "ok": not drift}
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not drift else 1
    print(f"INTEGRITY {sess.get('id')}  {len(pinned)} files pinned")
    if not pinned:
        print("  (legacy session without manifest; nothing to compare)")
        return 0
    if not drift:
        print("  [OK  ] CLI and Core match the session start")
        return 0
    print(f"  [FAIL] {len(drift)} files changed since the session started:")
    for item in drift:
        label = {"changed": "changed", "missing": "missing", "added": "new"}[item["state"]]
        print(f"    .pakem/{item['file']:<36} {label:<8} {item['pinned'] or '-':<17} -> "
              f"{item['actual'] or '-'}")
    print("  Gates run by a modified CLI prove nothing. If this change is "
          "intentional, record it: pakem integrity --re-pin --reason \"...\"")
    return 1


def cmd_check(a):
    root = need_root()
    warn_corrupt_sessions(root)
    cfg = read_config(root)
    failed, warnings = run_gates(root, cfg, skip_verify=a.skip_verify)
    if warnings:
        print(f"\nWARNING: {len(warnings)} gate/rule warnings during this session. Report them to the user.")
    if failed:
        print(f"\nRESULT: FAILED ({len(failed)} gates: {', '.join(failed)})")
        return 1
    print("\nRESULT: PASSED")
    return 0


def cmd_finish(a):
    root = need_root()
    warn_corrupt_sessions(root)
    cfg = read_config(root)
    with pakem_lock(root):
        return _finish_locked(a, root, cfg)

def _finish_locked(a, root, cfg):
    evidence: dict = {}
    failed, warnings = run_gates(root, cfg, summary=a.summary, finishing=True,
                                 fixed_bug=a.fixed_bug, evidence=evidence)

    rows, _, _ = audit_rows(root, cfg)
    wajib = [r for r in rows if r["tier"] == "required" and r["ok"] is False]
    for r in wajib:
        print(f"[WARN] required: {r['label']} — {r['detail']}", flush=True)
    risk = risk_warnings(root, cfg)
    for r in risk:
        print(f"[WARN] risk: {r}", flush=True)

    act = active_session(root)
    if warnings:
        print(f"\nWARNING: {len(warnings)} gate/rule warnings during this session. Report them to the user.")
    if wajib:
        print(f"WARNING: {len(wajib)} REQUIRED audit gaps unresolved (advisory; "
              "use --strict to fail).")
    if risk:
        print(f"WARNING: {len(risk)} risks unresolved (advisory, non-blocking). "
              "Report them to the user; defer with a reason if truly not needed yet.")

    ev = evidence.get("verify") or {}
    if ev:
        print(f"[EVIDENCE] verify: {ev.get('status')} exit={ev.get('exit')} "
              f"hash={ev.get('outputHash') or '-'}", flush=True)
        append_event(root, "verification.completed", act[1] if act else None,
                     {"status": ev.get("status"), "exit": ev.get("exit"),
                      "duration_ms": ev.get("durationMs"), "output_hash": ev.get("outputHash")})
    if a.strict:
        strict = []
        if warnings:
            strict.append(f"{len(warnings)} rules/verify/CLI changes")
        if ev.get("status") != "pass":
            strict.append("verify is not pass")
        if wajib:
            strict.append(f"{len(wajib)} REQUIRED audit gaps")
        for s in strict:
            print(f"[FAIL] strict: {s}", flush=True)
        if strict:
            failed.append("strict")

    if failed:
        if act:
            act[1].setdefault("gateFailures", []).append({"at": now(), "failed": failed})
            act[1]["verifyEvidence"] = ev
            act[1]["auditGaps"] = [r["label"] for r in wajib]
            save_session(act[0], act[1])
        append_event(root, "session.finish_blocked", act[1] if act else None,
                     {"failed_gates": failed, "summary": a.summary.strip()})
        print(f"\nRESULT: FAILED ({len(failed)} gates: {', '.join(failed)}). Work is NOT finished.")
        return 1
    p, d = act
    d.update(status="finished", finishedAt=now(), summary=a.summary.strip(),
             nextStep=a.next if a.next is not None else "done", warnings=warnings,
             riskWarnings=risk, verifyEvidence=ev, auditGaps=[r["label"] for r in wajib])
    save_session(p, d)
    append_event(root, "session.finished", d,
                 {"summary": d.get("summary", ""), "verification": ev.get("status"),
                  "failed_gates": []})
    print("\nRESULT: PASSED. Session closed.")
    return 0


def cmd_bug(a):
    root = need_root()
    with pakem_lock(root):
        return _bug_locked(a, root)

def _bug_locked(a, root):
    p = root / PAKEM_DIR / "BUG-HISTORY.md"
    if not p.exists():
        write(p, BUG_HEADER)
    text = read(p)
    nums = [int(m.group(1)) for m in re.finditer(r"(?m)^## BUG-(\d+)", strip_comments(text))]
    bid = f"BUG-{(max(nums) + 1 if nums else 1):03d}"

    def fld(v, hint):
        return v if v else f"[FILL: {hint}]"

    entry = (
        f"## {bid} - {a.title} ({datetime.now().strftime('%Y-%m-%d')})\n"
        f"- Symptom: {fld(a.symptom, 'what looks wrong')}\n"
        f"- Root cause: {fld(a.cause, 'the actual cause, not the symptom')}\n"
        f"- Fix: {fld(a.fix, 'what changed')}\n"
        f"- Prevention / test: {fld(a.prevent, 'the test or rule that prevents recurrence')}\n"
    )
    inserted = False
    for marker in (NO_BUGS, LEGACY_NO_BUGS):
        if marker in text:
            text = text.replace(marker, entry.rstrip("\n"), 1)
            inserted = True
            break
    if not inserted:
        for heading in ("## Entries\n", "## Entri\n"):
            if heading in text:
                head, sep, tail = text.partition(heading)
                text = head + sep + "\n" + entry + "\n" + tail.lstrip("\n")
                inserted = True
                break
    if not inserted:
        text = text.rstrip("\n") + "\n\n" + entry
    write(p, text)
    act = active_session(root)
    if act:
        act[1].setdefault("bugs", []).append(bid)
        save_session(act[0], act[1])
    append_event(root, "bug.recorded", act[1] if act else None,
                 {"bug_id": bid, "title": a.title})
    left = any(r.search(entry) for r in PLACEHOLDER_RES)
    print(f"{bid} recorded in .pakem/BUG-HISTORY.md." + (" Complete the [FILL: ...] fields before finish." if left else ""))
    if not act:
        print("Note: no active session; the entry is not linked to any session.")
    return 0


def cmd_adr(a):
    root = need_root()
    with pakem_lock(root):
        return _adr_locked(a, root)

def _adr_locked(a, root):
    d = root / "docs" / "adr"
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for f in d.glob("*.md") if (m := re.match(r"(\d{4})-", f.name))]
    num = f"{(max(nums) + 1 if nums else 1):04d}"
    fname = f"{num}-{slug(a.title, 50)}.md"
    write(d / fname, ADR_TEMPLATE.format(num=num, title=a.title, date=datetime.now().strftime("%Y-%m-%d")))
    dec = root / PAKEM_DIR / "DECISIONS.md"
    entry = f"- `docs/adr/{fname}` - {a.title}"
    if dec.exists():
        t = read(dec)
        if NO_DECISIONS in t:
            t = t.replace(NO_DECISIONS, entry, 1)
        elif LEGACY_NO_DECISIONS in t:
            t = t.replace(LEGACY_NO_DECISIONS, entry, 1)
        else:
            t = t.rstrip("\n") + "\n" + entry + "\n"
        write(dec, t)
    act = active_session(root)
    append_event(root, "decision.recorded", act[1] if act else None,
                 {"adr_file": f"docs/adr/{fname}", "title": a.title})
    print(f"ADR created: docs/adr/{fname}. Fill every [FILL: ...] before finish.")
    return 0


def cmd_handover(a):
    root = need_root()
    act = active_session(root)
    if a.check:
        state = handover_state(root)
        if not state["present"]:
            print("[SKIP] handover: no HANDOVER.md")
            return 0
            print(f"file  : {state['path']}")
        if not state["head"]:
            print("[SKIP] repo has no commits; handover stamp cannot be compared")
            return 0
        if state["stamp"] is None:
            print("[FAIL] no HEAD stamp: run `pakem handover --stamp` after the final contents")
            return 1
        print(f"stamp : {state['stamp']['head'][:8]} ({state['stamp']['at']})")
        print(f"head  : {(state['head'] or '?')[:8]}")
        if state["stale"]:
            print(f"[FAIL] stale: {count(state['commits_since'], 'commit') if state['commits_since'] is not None else '?'} since the stamp; "
                  f"update the contents, then `pakem handover --stamp`")
            return 1
        print("[OK  ] stamp matches HEAD")
        return 0
    with pakem_lock(root):
        existing = handover_path(root)
        if a.stamp:
            if existing is None:
                die("HANDOVER.md does not exist. Create it first: pakem handover")
            try:
                stamped = write_handover_stamp(root, existing, (act[1].get("id") if act else ""))
            except ValueError as exc:
                die(f"{exc}. Commit first, then rerun `pakem handover --stamp`.")
            append_event(root, "handover.created", act[1] if act else None,
                         {"path": stamped["path"], "stamp": True, "head": stamped["head"]})
        else:
            if existing is not None and not a.force:
                die("HANDOVER.md already exists. Use --stamp to update the stamp, "
                    "--force to overwrite it (old contents are lost).")
            p = root / "HANDOVER.md"
            write(p, HANDOVER_TEMPLATE)
            try:
                stamped = write_handover_stamp(root, p, (act[1].get("id") if act else ""))
            except ValueError as exc:
                stamped = {"path": "HANDOVER.md", "head": None}
                print(f"[WARN] {exc}; document created without a stamp. Run `pakem handover --stamp` "
                      f"after the first commit.")
            append_event(root, "handover.created", act[1] if act else None,
                         {"path": "HANDOVER.md", "head": stamped["head"]})
    if a.stamp:
        print(f"Stamp updated: {stamped['path']} @ {stamped['head'][:8]}")
    elif stamped.get("head"):
        print("HANDOVER.md created and stamped with the current HEAD.")
        print("Fill every [FILL: ...], then `pakem handover --stamp` so the stamp matches the latest commit.")
    else:
        print("HANDOVER.md created without a stamp (repo has no commits).")
    cfg = read_config(root)
    if (cfg.get("handover") or "false").strip().lower() != "true":
        print("Note: the `handover` flag in PROJECT.md is still false; set it true if this project is actually handed over.")
    return 0


def cmd_spec(a):
    root = need_root()
    with pakem_lock(root):
        p = spec_path(root)
        if a.approve:
            if not p.is_file():
                die('SPEC.md does not exist. Create it first: pakem spec "title"')
            text = read(p)
            if any(r.search(text) for r in PLACEHOLDER_RES):
                die("SPEC.md still has placeholders. Fill them first, then --approve.")
            if spec_status(root) == "approved":
                print("SPEC.md is already approved.")
                return 0
            if not re.search(r"(?mi)^status:", text):
                die("SPEC.md has no Status: line")
            text = re.sub(r"(?mi)^status:.*$", "Status: approved", text, count=1)
            text = text.rstrip("\n") + f"\nApproved: {datetime.now().strftime('%Y-%m-%d')}\n"
            write(p, text)
            act = active_session(root)
            title_match = re.search(r"(?m)^#\s+(.+)$", text)
            append_event(root, "spec.approved", act[1] if act else None,
                         {"path": ".pakem/SPEC.md", "title": title_match.group(1).strip() if title_match else None})
            print("SPEC.md approved.")
            return 0
        if not a.title:
            die('spec title required: pakem spec "title"')
        if p.exists() and not a.force:
            die("SPEC.md already exists. Use --force to overwrite it (old contents are lost).")
        text = (SPEC_TEMPLATE.replace("{title}", a.title)
                .replace("{date}", datetime.now().strftime("%Y-%m-%d")))
        write(p, text)
        print("SPEC.md created. Fill the placeholders, then: pakem spec --approve")
        return 0


# ---------------------------------------------------------------- per-task evidence

TASK_EVIDENCE_VERSION = "pakem.task-evidence/v1"
WORK_REPORT_VERSION = "pakem.work-report/v1"


def task_files(task: dict) -> list[str]:
    return [f.strip() for f in (task.get("files") or "").split(",") if f.strip()]


def task_evidence_path(root: Path) -> Path:
    return root / PAKEM_DIR / "verify" / "tasks.json"


def load_task_evidence(root: Path) -> dict:
    path = task_evidence_path(root)
    empty = {"schema_version": TASK_EVIDENCE_VERSION, "tasks": {}}
    if not path.is_file():
        return empty
    try:
        data = json.loads(read(path))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
        return empty
    data.setdefault("schema_version", TASK_EVIDENCE_VERSION)
    return data


def save_task_evidence(root: Path, data: dict):
    write(task_evidence_path(root), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def scope_digest(root: Path, entries: list[str]) -> dict[str, str]:
    """Fingerprint of file content that falls inside the task scope.

    Used to detect stale evidence: if a file changes after verify runs, that verify
    result no longer proves anything about the current content.
    """
    if not entries:
        return {}
    try:
        core, _ = _reconcile_import()
    except SystemExit:
        return {}
    from pakem_core.intelligence import SKIP_DIRS
    found: dict[str, str] = {}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if not any(core.matches(rel, entry) for entry in entries):
                continue
            try:
                if path.is_symlink() or path.stat().st_size > 2_000_000:
                    continue
                found[rel] = _file_digest(path)
            except OSError:
                continue
            if len(found) >= 2000:
                return found
    return found


def run_task_verify(root: Path, task: dict, cfg: dict) -> dict:
    """Run the verify command owned by one task and return its evidence."""
    cmd = (task.get("verify") or "").strip()
    try:
        timeout = int(cfg.get("verify.timeout", "900") or 900)
    except ValueError:
        timeout = 900
    print(f"       $ {cmd}", flush=True)
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, shell=True, cwd=root, timeout=timeout,
                              capture_output=True, text=True)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or "") + (exc.stderr or "")
        output = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
        code = None
    if output:
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
    status = "pass" if code == 0 else "fail"
    return {
        "command": cmd,
        "status": status,
        "exit": code,
        "at": now(),
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputHash": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()[:16],
        "files": scope_digest(root, task_files(task)),
    }


def gate_task_verify(root: Path):
    """A `[x]` task must have verify evidence that is still valid."""
    tasks = [task for task in plan_tasks(root) if task.get("done")]
    if not tasks:
        return "skip", "no completed tasks yet"
    evidence = load_task_evidence(root)["tasks"]
    proven, without_command, waived, dropped, problems = 0, [], [], [], []
    for task in tasks:
        tid = task["id"]
        if task.get("dropped"):
            dropped.append(tid)
            continue
        entry = evidence.get(tid)
        if not task_files(task) and not (task.get("verify") or "").strip():
            without_command.append(tid)
            continue
        if entry is None:
            if (task.get("verify") or "").strip():
                problems.append(f"{tid}: no verify evidence yet")
            else:
                without_command.append(tid)
            continue
        if entry.get("status") == "waived":
            waived.append(f"{tid}: {entry.get('reason') or 'without reason'}")
            continue
        if entry.get("status") != "pass":
            problems.append(f"{tid}: verify {entry.get('status')} (exit {entry.get('exit')})")
            continue
        recorded = entry.get("files") or {}
        current = scope_digest(root, task_files(task))
        changed = sorted(set(recorded) | set(current))
        if any(recorded.get(rel) != current.get(rel) for rel in changed):
            diff = [rel for rel in changed if recorded.get(rel) != current.get(rel)]
            problems.append(f"{tid}: stale evidence, files changed after verify ({', '.join(diff[:3])})")
            continue
        proven += 1
    if problems:
        return "fail", ("; ".join(problems[:3])
                        + ". Run `pakem plan done <id>` to refresh the evidence, "
                          "or record an explicit waiver: --no-verify --reason \"...\"")
    notes = []
    if without_command:
        notes.append(f"{len(without_command)} without a verify command: {', '.join(without_command[:3])}")
    if waived:
        notes.append("waived: " + "; ".join(waived[:3]))
    if dropped:
        notes.append(f"{len(dropped)} dropped (not claimed done)")
    message = f"{count(proven, 'task')} proven"
    if notes:
        message += " | " + " | ".join(notes)
    return "pass", message


def record_task_verify(root: Path, task: dict) -> dict:
    """Run the task verify, store its evidence, and print a short summary."""
    result = run_task_verify(root, task, read_config(root))
    evidence = load_task_evidence(root)
    evidence["tasks"][task["id"]] = result
    save_task_evidence(root, evidence)
    print(f"[EVIDENCE] {task['id']}: {result['status']} exit={result['exit']} "
          f"hash={result['outputHash']} files={len(result['files'])}")
    return result


def _plan_target(a) -> str:
    tid = (a.target or "").upper()
    if not re.fullmatch(r"T\d+", tid):
        die("task id required, e.g. pakem plan done T1")
    return tid


def cmd_plan(a):
    root = need_root()
    verified = None
    if a.action == "done":
        tid = _plan_target(a)
        task = next((item for item in plan_tasks(root) if item["id"].upper() == tid), None)
        if task is None:
            die(f"task {tid} not found")
        if (task.get("verify") or "").strip() and not getattr(a, "no_verify", False):
            # Verify runs OUTSIDE the lock: the verify command may invoke pakem again
            # (e.g. `pakem check`), and flock is not reentrant — holding the lock while
            # waiting for a child that needs the same lock means hanging until timeout.
            verified = record_task_verify(root, task)
            if verified["status"] != "pass":
                die(f"{tid} verify failed; task stays open. Fix it first, or record an "
                    f'explicit waiver: pakem plan done {tid} --no-verify --reason "..."')
    with pakem_lock(root):
        return _cmd_plan_locked(root, a, verified)


def _cmd_plan_locked(root: Path, a, verified: dict | None):
    bad = malformed_plan_lines(root)
    if bad:
        die("PLAN.md has unrecognized task lines. Fix them first; do not let tasks disappear.")
    tasks = plan_tasks(root)
    if a.action == "list":
        if not tasks:
            print("No PLAN.md yet. Add a task: pakem plan add \"...\" --files ... --verify ...")
            return 0
        done = sum(1 for t in tasks if t["done"])
        print(f"PLAN {done}/{len(tasks)} done")
        for t in tasks:
            mark = "x" if t["done"] else " "
            print(f"  [{mark}] {t['id']} - {t['text']}")
            print(f"        files: {t['files']} | verify: {t['verify']}")
        return 0
    if a.action == "add":
        if not a.target:
            die('task required: pakem plan add "..." --files ... --verify ...')
        if not a.files or not a.verify:
            die("--files and --verify are required for a new task.")
        num = max((int(t["id"][1:]) for t in tasks), default=0) + 1
        tasks.append({"done": False, "id": f"T{num}", "text": clean_plan_field(a.target),
                      "files": clean_plan_field(a.files),
                      "verify": clean_plan_field(a.verify, allow_pipe=True)})
        write_plan(root, tasks)
        sync_plan_next(root, tasks)
        act = active_session(root)
        append_event(root, "task.added", act[1] if act else None,
                     {"task_id": f"T{num}", "text": tasks[-1]["text"],
                      "files": tasks[-1]["files"], "verify": tasks[-1]["verify"]})
        if spec_status(root) == "draft":
            print("Note: SPEC.md is still draft; finish rejects until it is approved.")
        print(f"T{num} added. Do it, then: pakem plan done T{num}")
        return 0
    tid = _plan_target(a)
    task = next((t for t in tasks if t["id"].upper() == tid), None)
    if not task:
        die(f"task {tid} not found")
    if task["done"]:
        print(f"{tid} done; verify evidence refreshed." if verified is not None
              else f"{tid} is already done.")
        return 0
    if a.action == "drop" and not a.reason:
        die("--reason required for plan drop.")
    if a.action == "done":
        if getattr(a, "no_verify", False):
            if not a.reason:
                die("--no-verify requires --reason so the reason is recorded in the evidence.")
            evidence = load_task_evidence(root)
            evidence["tasks"][tid] = {
                "command": (task.get("verify") or "").strip(), "status": "waived", "exit": None,
                "at": now(), "reason": clean_plan_field(a.reason),
                "files": scope_digest(root, task_files(task))}
            save_task_evidence(root, evidence)
            print(f"[WAIVER] {tid}: {clean_plan_field(a.reason)}")
        elif verified is None:
            print(f"note: {tid} has no verify command; no evidence was run.")
    task["done"] = True
    if a.action == "drop":
        task["text"] += f" [dropped: {clean_plan_field(a.reason)}]"
    write_plan(root, tasks)
    sync_plan_next(root, tasks)
    act = active_session(root)
    append_event(root, "task.dropped" if a.action == "drop" else "task.completed",
                 act[1] if act else None,
                 {"task_id": tid, "text": task["text"],
                  "reason": clean_plan_field(a.reason) if a.action == "drop" else None})
    print(f"{tid} {'dropped' if a.action == 'drop' else 'done'}.")
    if a.action == "done":
        _report_worktree_cleanup(root, tid)
    return 0


def _report_worktree_cleanup(root: Path, task_id: str) -> None:
    """After a task finishes, a worktree that is merged & clean does not need to be kept."""
    try:
        from pakem_core import git_worktree
        results = git_worktree.cleanup_for_task(root, task_id)
    except Exception as exc:  # missing module, broken git, repo is not git
        print(f"[WARN] worktree {task_id}: cleanup skipped ({exc})")
        return
    for item in results:
        if item["action"] == "removed":
            print(f"[WT ] {item['branch']} deleted (merged, clean)")
        else:
            print(f"[WARN] worktree {item['branch']} left as is: {item['reason']}")


def cmd_adapt(a):
    root = need_root()
    names = parse_adapters(a.adapter)
    if not names:
        die("no adapter selected")
    for n in names:
        print(f"adapter: {write_adapter(root, n)}")
    return 0


# ---------------------------------------------------------------- team / multi-agent coordination

def _coordination_import():
    try:
        from pakem_core import coordination as core
        return core
    except ImportError as exc:
        die(f"Pakem Coordination module unavailable: {exc}. Run the latest CLI from the skill install: `python3 <skill-location>/scripts/pakem.py upgrade` from the project root.")


def _identity_registry(root: Path) -> dict:
    path = root / PAKEM_DIR / "identity" / "registry.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(read(path))
    except json.JSONDecodeError:
        return {}


def _agent_fingerprint(root: Path, agent_id: str) -> str | None:
    agent = (_identity_registry(root).get("agents") or {}).get(agent_id)
    if not agent or agent.get("revokedAt"):
        return None
    return agent.get("fingerprint")


def _sign_team_action(root: Path, agent_id: str, payload: dict) -> dict:
    """Sign a team action payload; fail with a clear message when a dependency is missing."""
    try:
        from pakem_core import identity as identity_core
    except ImportError as exc:
        die(f"identity module unavailable: {exc}")
    if not _agent_fingerprint(root, agent_id):
        die(f"agent {agent_id} has no active identity. Run: pakem identity create {agent_id}")
    try:
        return identity_core.sign(root, agent_id, payload)
    except RuntimeError as exc:
        die(str(exc))
    except ValueError as exc:
        die(f"failed to sign action: {exc}")


def _verify_team_signatures(root: Path, core) -> dict:
    """Verify every signed team action: signature, revocation, and content."""
    try:
        from pakem_core import identity as identity_core
    except ImportError as exc:
        die(f"identity module unavailable: {exc}")
    tasks = core.tasks_map(core.status(root))
    unsigned_submissions = sum(1 for task in tasks.values()
                               if (task.get("submission") or {}) and not (task.get("submission") or {}).get("signature"))
    unsigned_reviews = sum(1 for task in tasks.values()
                           if (task.get("lastReview") or {}) and not (task.get("lastReview") or {}).get("signature"))
    invalid, valid = [], 0
    for action in core.signed_actions(root):
        try:
            verified = identity_core.verify(root, action["envelope"])
        except ValueError as exc:
            invalid.append({"taskId": action["taskId"], "kind": action["kind"],
                            "agentId": action["agentId"], "reason": str(exc)})
            continue
        if verified.get("payload") != action["expected"]:
            invalid.append({"taskId": action["taskId"], "kind": action["kind"],
                            "agentId": action["agentId"],
                            "reason": "payload on the board differs from the signed payload"})
            continue
        valid += 1
    return {"checked": valid + len(invalid), "valid": valid, "invalid": invalid,
            "unsignedSubmissions": unsigned_submissions, "unsignedReviews": unsigned_reviews,
            "ok": not invalid}


def cmd_team(a):
    root = need_root()
    core = _coordination_import()
    try:
        if a.action == "init":
            result = core.initialize(root)
            label = "Team board initialized"
        elif a.action == "status":
            result = core.status(root)
            label = "Team status"
        elif a.action == "register":
            caps = [part.strip() for value in (a.capability or []) for part in value.split(",") if part.strip()]
            fingerprint = a.fingerprint or _agent_fingerprint(root, a.agent_id)
            result = core.register_agent(root, a.agent_id, a.role, a.name or "", caps, fingerprint)
            label = f"Agent registered: {a.agent_id}"
        elif a.action == "add":
            files = [item for group in (a.files or []) for item in group]
            caps = [part.strip() for value in (a.capability or []) for part in value.split(",") if part.strip()]
            result = core.add_task(root, a.task_id, a.title, a.description or "", a.depends_on or [],
                                   files, a.risk, caps)
            label = f"Task created: {a.task_id}"
        elif a.action == "assign":
            result = core.assign_task(root, a.task_id, a.agent, a.by)
            label = f"Task assigned: {a.task_id} -> {a.agent}"
        elif a.action == "claim":
            result = core.claim_task(root, a.task_id, a.agent, a.lease_seconds)
            label = f"Task claimed: {a.task_id}"
        elif a.action == "heartbeat":
            result = core.heartbeat(root, a.task_id, a.agent, a.lease_seconds)
            label = f"Lease renewed: {a.task_id}"
        elif a.action == "release":
            result = core.release_task(root, a.task_id, a.agent, a.reason)
            label = f"Task released: {a.task_id}"
        elif a.action == "handoff":
            result = core.handoff_task(root, a.task_id, a.from_agent, a.to_agent, a.note)
            label = f"Task handed off: {a.task_id} -> {a.to_agent}"
        elif a.action == "submit":
            envelope = None
            if getattr(a, "sign", False):
                payload = core.submission_payload(a.task_id, a.agent, a.summary, a.evidence)
                envelope = _sign_team_action(root, a.agent, payload)
            result = core.submit_task(root, a.task_id, a.agent, a.summary, a.evidence, envelope)
            label = f"Task submitted for review: {a.task_id}"
            if envelope:
                label += " (signed with Ed25519)"
        elif a.action == "review":
            envelope = None
            if getattr(a, "sign", False):
                task = core.tasks_map(core.status(root)).get(a.task_id) or {}
                implementer = (task.get("submission") or {}).get("agentId", "")
                payload = core.review_payload(a.task_id, a.reviewer, a.decision, a.note or "", implementer)
                envelope = _sign_team_action(root, a.reviewer, payload)
            result = core.review_task(root, a.task_id, a.reviewer, a.decision, a.note or "", envelope)
            label = f"Task review {a.decision}: {a.task_id}"
            if envelope:
                label += " (signed with Ed25519)"
        elif a.action == "block":
            result = core.block_task(root, a.task_id, a.agent, a.reason)
            label = f"Task blocked: {a.task_id}"
        elif a.action == "unblock":
            result = core.unblock_task(root, a.task_id, a.by, a.reason)
            label = f"Task unblocked: {a.task_id}"
        elif a.action == "verify":
            result = _verify_team_signatures(root, core)
            label = "Team signature verification"
        elif a.action == "events":
            result = core.read_events(root, a.limit)
            label = "Coordination events"
        elif a.action == "storage-info":
            result = core.storage_info(root)
            label = "Team storage backend"
        elif a.action == "storage-migrate":
            result = core.migrate_storage(root, a.to_backend)
            label = "Team storage migrated"
        elif a.action == "storage-backup":
            result = core.backup_sqlite(root, a.output, a.force)
            label = "Team storage backup created"
        else:
            die("unknown team action")
    except (ValueError, RuntimeError, OSError) as exc:
        die(str(exc))

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(label)
        if isinstance(result, dict) and "state" in result:
            print(f"  state: {result.get('state')}")
            if result.get("ownerAgent"):
                print(f"  owner: {result['ownerAgent']} (lease: {result.get('leaseExpiresAt')})")
        elif isinstance(result, dict) and "summary" in result:
            print("  tasks: " + ", ".join(f"{k}={v}" for k, v in result["summary"].items()))
            print(f"  agents: {len(result.get('agents', []))}")
        elif isinstance(result, dict) and "corruptLines" in result:
            print(f"  events: {result.get('total', 0)} | corrupt lines: {len(result.get('corruptLines', []))}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if a.action == "verify" and isinstance(result, dict):
            print(f"  signature: {result['valid']} valid, {len(result['invalid'])} invalid, "
                  f"{result['unsignedSubmissions']} submissions + {result['unsignedReviews']} reviews without signatures")
            for item in result["invalid"]:
                print(f"  [FAIL] {item['kind']} {item['taskId']} by {item['agentId']}: {item['reason']}")
    return 1 if (a.action == "verify" and not result.get("ok", True)) else 0


# ---------------------------------------------------------------- audit

def surface_config(cfg: dict):
    out, warns = {}, []
    for key, (allowed, default) in SURFACE_VALUES.items():
        raw = (cfg.get(key) or default).strip().lower()
        if raw not in allowed:
            warns.append(f"{key}='{raw}' unknown (use {', '.join(sorted(allowed))}); treating as '{default}'")
            raw = default
        out[key] = raw
    out["sensitive"] = out["sensitive"] == "true"
    out["handover"] = out["handover"] == "true"
    return out, warns

def first_existing(root: Path, *cands: str):
    for c in cands:
        if (root / c).exists():
            return c
    return None

def reads_env(root: Path) -> bool:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            if Path(f).suffix not in CODE_EXTS:
                continue
            p = Path(dp) / f
            try:
                if p.stat().st_size > 512_000:
                    continue
                if ENV_RE.search(read(p)):
                    return True
            except (OSError, UnicodeDecodeError):
                continue
    return False

def has_ci(root: Path) -> bool:
    for c in CI_PATHS:
        p = root / c
        if p.is_dir() and any(p.glob("*.y*ml")):
            return True
        if p.is_file():
            return True
    return False

def manifest_has_dependencies(root: Path, manifest: str) -> bool:
    if manifest != "package.json":
        return True
    try:
        pkg = json.loads(read(root / manifest))
    except Exception:
        return True
    return bool(pkg.get("dependencies") or pkg.get("devDependencies")
                or pkg.get("peerDependencies") or pkg.get("optionalDependencies"))

def missing_lockfile(root: Path):
    for manifest, locks in LOCK_CANDIDATES.items():
        if ((root / manifest).exists() and manifest_has_dependencies(root, manifest)
                and not any((root / l).exists() for l in locks)):
            return manifest, locks
    return None

def audit_rows(root: Path, cfg: dict):
    """Sort artifacts: required (continuity/verification), recommended (risk), not-needed."""
    surface, warns = surface_config(cfg)
    rows = []

    def add(tier: str, ok, label: str, detail: str = ""):
        rows.append({"tier": tier, "ok": ok, "label": label, "detail": detail})

    # --- required: without this the next session guesses or "done" is unproven
    # README proves how to run the project. For one-off scripts the proof is already
    # in `verify`, so README is demoted to recommended: do not demand file completeness.
    if cfg.get("type") == "oneoff":
        add("recommended", (root / "README.md").is_file(), "README.md", "setup, run, test")
    else:
        add("required", (root / "README.md").is_file(), "README.md", "setup, run, test")
    add("required", (root / ".gitignore").is_file(), ".gitignore", "local artifacts stay out of git")
    add("required", (root / PAKEM_DIR / "CONTEXT.md").is_file() and (root / PAKEM_DIR / "PROJECT.md").is_file(),
        ".pakem/CONTEXT.md + PROJECT.md", "context routing + configuration")
    verify = (cfg.get("verify") or "").strip()
    add("required", bool(verify) and not has_placeholder(verify), "verify", verify or "fill in the test/lint/build command")

    if cfg.get("rule.tests") == "required" or cfg.get("type") in ("app", "library"):
        add("required", find_tests(root), "tests/", "logic needs tests run by verify")

    if reads_env(root):
        add("required", (root / ".env.example").is_file(), ".env.example", "code reads the environment")

    missing = missing_lockfile(root)
    if missing:
        manifest, locks = missing
        add("required", False, f"lockfile for {manifest}", "one of: " + ", ".join(locks))

    gi = read(root / ".gitignore") if (root / ".gitignore").is_file() else ""
    add("recommended", ".pakem/sessions/" in gi.splitlines(), "ignore .pakem/sessions/",
        "sessions are local; do not commit")

    # --- recommended: according to risk, may be deferred with a reason
    add("recommended", (root / ".gitattributes").is_file(), ".gitattributes", "line endings, binary files, diff")
    add("recommended", bool(first_existing(root, "Makefile", "justfile")), "Makefile / justfile",
        "shortcut for the same command as verify")

    if surface["deploy"] != "none":
        add("recommended", has_ci(root), "CI (.github/workflows or equivalent)", f"deploy={surface['deploy']}")
        add("recommended", bool(first_existing(root, "DEPLOYMENT.md", "docs/DEPLOYMENT.md")),
            "DEPLOYMENT.md", "deploy and rollback steps")
        add("recommended", bool(first_existing(root, "RUNBOOK.md", "docs/RUNBOOK.md")),
            "RUNBOOK.md", "what to do when the system is down")

    if surface["sensitive"]:
        add("recommended", (root / "SECURITY.md").is_file(), "SECURITY.md", "how to report a vulnerability")
        add("recommended", bool(first_existing(root, "docs/THREAT_MODEL.md", "docs/SECURITY_CHECKLIST.md")),
            "threat model / security checklist", "sensitive: true")
        add("recommended", bool(first_existing(root, ".gitleaks.toml", ".secrets.baseline", ".snyk", "trivy.yaml")),
            "secret/dependency scan", "sensitive: true")

    if surface["exposure"] == "public":
        add("recommended", bool(first_existing(root, "LICENSE", "LICENSE.md", "COPYING")), "LICENSE", "public repo")
        add("recommended", (root / "CONTRIBUTING.md").is_file(), "CONTRIBUTING.md", "public repo")
        add("recommended", (root / "CODE_OF_CONDUCT.md").is_file(), "CODE_OF_CONDUCT.md", "public repo")
        add("recommended", bool(first_existing(root, ".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE")),
            "PR/issue template", "public repo")

    if surface["handover"]:
        handover_doc = first_existing(root, "HANDOVER.md", "docs/HANDOVER.md")
        add("recommended", bool(handover_doc), "HANDOVER.md",
            "status, access, contacts, remaining work, risks (one file)")

    if cfg.get("type") == "library":
        add("recommended", (root / "examples").is_dir(), "examples/", "library usage examples")

    if cfg.get("rule.adr") not in ("", "skip"):
        add("recommended", (root / "docs" / "adr").is_dir(), "docs/adr/", "rationale for costly-to-reverse decisions")

    # --- unnecessary: do not create them just for completeness
    if surface["exposure"] == "private":
        add("not-needed", None, "LICENSE", "private repo; change exposure: public if it will be released")
        add("not-needed", None, "FUNDING.yml, GOVERNANCE.md, MAINTAINERS.md", "private repo / small team")
    else:
        add("not-needed", None, "GOVERNANCE.md, MAINTAINERS.md", "only when the community is already large")
    add("not-needed", None, "docs/decisions/", "canonical: docs/adr/ — do not keep both")
    add("not-needed", None, "k8s/, helm/, terraform/, ansible/", "only with infrastructure as code")
    add("not-needed", None, "docs/postmortems/ or INCIDENTS.md", "only after an incident")
    if cfg.get("type") != "research":
        add("not-needed", None, "CITATION.cff", "only for research/academic projects")

    return rows, surface, warns

def risk_warnings(root: Path, cfg: dict):
    """Gaps that are risky according to their flag, for [WARN] during finish. Does not block."""
    surface, _ = surface_config(cfg)
    out = []

    def miss(label: str, *cands: str):
        if not first_existing(root, *cands):
            out.append(label)

    if surface["deploy"] != "none":
        if not has_ci(root):
            out.append(f"deploy={surface['deploy']} but no CI yet")
        miss(f"deploy={surface['deploy']} but no DEPLOYMENT.md yet", "DEPLOYMENT.md", "docs/DEPLOYMENT.md")
        miss(f"deploy={surface['deploy']} but no RUNBOOK.md yet", "RUNBOOK.md", "docs/RUNBOOK.md")

    if surface["sensitive"]:
        miss("sensitive=true but no threat model/security checklist yet",
             "docs/THREAT_MODEL.md", "docs/SECURITY_CHECKLIST.md")
        miss("sensitive=true but no secret/dependency scan yet",
             ".gitleaks.toml", ".secrets.baseline", ".snyk", "trivy.yaml")

    if surface["exposure"] == "public":
        miss("exposure=public but no LICENSE yet", "LICENSE", "LICENSE.md", "COPYING")
        miss("exposure=public but no PR/issue template yet",
             ".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE")

    if (surface["sensitive"] or surface["exposure"] == "public") and not (root / "SECURITY.md").is_file():
        out.append("SECURITY.md missing (sensitive/public flag active)")

    if surface["handover"]:
        miss("handover=true but no HANDOVER.md yet", "HANDOVER.md", "docs/HANDOVER.md")

    return list(dict.fromkeys(out))


def print_audit(root: Path, cfg: dict, rows, surface, warns):
    print(f"AUDIT  {root.name}")
    print(f"configuration: type={cfg.get('type', '?')} exposure={surface['exposure']} "
          f"deploy={surface['deploy']} handover={'true' if surface['handover'] else 'false'} "
          f"sensitive={'true' if surface['sensitive'] else 'false'}")
    for w in warns:
        print(f"[WARN] {w}")

    headings = [
        ("required", "REQUIRED - continuity & verification"),
        ("recommended", "RECOMMENDED - risk-based; may be deferred with a reason"),
        ("not-needed", "NOT NEEDED - do not create just for completeness"),
    ]
    for tier, title in headings:
        print(f"\n{title}")
        for r in rows:
            if r["tier"] != tier:
                continue
            mark = "[ok]" if r["ok"] is True else ("[gap]" if r["ok"] is False else "[-]")
            detail = f" — {r['detail']}" if r["detail"] else ""
            print(f"  {mark:<5} {r['label']}{detail}")

    gaps = [r for r in rows if r["tier"] == "required" and r["ok"] is False]
    advised = [r for r in rows if r["tier"] == "recommended" and r["ok"] is False]
    print(f"\nSummary: {len(gaps)} required missing, {len(advised)} recommended, "
          f"{sum(1 for r in rows if r['tier'] == 'not-needed')} not needed.")
    if gaps:
        print("Fix REQUIRED items first; choose the rest by risk, not completeness.")

def cmd_audit(a):
    root = need_root()
    bad = warn_corrupt_sessions(root, quiet=a.json)
    cfg = read_config(root)
    rows, surface, warns = audit_rows(root, cfg)
    act = active_session(root)
    tamper = tamper_findings(root, cfg, act[1]) if act else []
    gaps = [r for r in rows if r["tier"] == "required" and r["ok"] is False]
    if a.json:
        print(json.dumps({
            "project": root.name,
            "type": cfg.get("type", ""),
            "surface": surface,
            "warnings": warns,
            "tamper": tamper,
            "corrupt_sessions": [p.name for p in bad],
            "rows": rows,
            "summary": {
                "wajib_gap": len(gaps),
                "disarankan_gap": sum(1 for r in rows if r["tier"] == "recommended" and r["ok"] is False),
                "tidak_perlu": sum(1 for r in rows if r["tier"] == "not-needed"),
            },
        }, ensure_ascii=False, indent=2))
    else:
        for w in tamper:
            print(f"[WARN] rules-changed: {w}")
        print_audit(root, cfg, rows, surface, warns)
    return 1 if (a.strict and gaps) else 0


def hook_dir(root: Path):
    """The hooks folder git actually reads: honoring core.hooksPath and worktrees."""
    for flags in (["--path-format=absolute"], []):
        out = _git(root, "rev-parse", *flags, "--git-path", "hooks")
        if out and out.strip():
            p = Path(out.strip())
            return p if p.is_absolute() else (root / p)
    legacy = root / ".git"
    return legacy / "hooks" if legacy.is_dir() else None

def cmd_hook(a):
    root = need_root()
    hooks = hook_dir(root)
    if hooks is None:
        die("not a git repo (.git/ missing and git cannot resolve the hooks folder)")
    hp = hooks / "pre-commit"
    marker = "# pakem-hook"
    extra = " --skip-verify" if getattr(a, "skip_verify", False) else ""
    script = (
        "#!/bin/sh\n" + marker + " - created by `pakem hook install`\n"
        'cd "$(git rev-parse --show-toplevel)" || exit 1\n'
        'PY=""\n'
        'for c in python3 python "py -3"; do\n'
        '  if $c -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi\n'
        "done\n"
        'if [ -z "$PY" ]; then echo "pakem: python not found" >&2; exit 1; fi\n'
        f"$PY .pakem/pakem.py check{extra} || "
        '{ echo "pakem: gate failed, commit aborted" >&2; exit 1; }\n'
    )
    if hp.exists() and marker not in read(hp):
        die(f"{hp} already exists and was not created by Pakem. Add this line to the hook manually:\n"
            f'  python3 .pakem/pakem.py check{extra} || exit 1')
    hp.parent.mkdir(parents=True, exist_ok=True)
    write(hp, script)
    hp.chmod(hp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        shown = hp.relative_to(root).as_posix()
    except ValueError:
        shown = hp.as_posix()
    print(f"Hook installed: {shown}")
    hooks_path = (_git(root, "config", "--get", "core.hooksPath") or "").strip()
    if hooks_path:
        print(f"  following core.hooksPath: {hooks_path}")
    return 0


# ---------------------------------------------------------------- doctor

def adapter_finding(root: Path, name: str):
    rel, _ = ADAPTERS[name]
    p = root / rel
    if not p.is_file():
        return None
    t = read(p)
    if BEGIN not in t or END not in t:
        return "warn", f"adapter {rel}: exists, but without the pakem block"
    block = t[t.index(BEGIN):t.index(END) + len(END)]
    if block != BLOCK:
        return "warn", f"adapter {rel}: stale block (run pakem adapt)"
    return "ok", f"adapter {rel}"

def probe_verify(root: Path, cfg: dict):
    cmd = (cfg.get("verify") or "").strip()
    if not cmd or has_placeholder(cmd):
        return "fail", "verify empty in PROJECT.md"
    try:
        timeout = int(cfg.get("verify.timeout", "900") or 900)
    except ValueError:
        timeout = 900
    try:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "fail", f"verify exceeded the {timeout}s limit"
    if r.returncode == 0:
        return "ok", "verify exit 0"
    return "fail", f"verify exit {r.returncode}"

def doctor_issues(root: Path, cfg: dict, run_verify: bool = False):
    issues = []

    def add(level: str, msg: str):
        issues.append((level, msg))

    if not (root / PAKEM_DIR / "PROJECT.md").is_file():
        add("fail", ".pakem/PROJECT.md missing")
    elif not cfg:
        add("fail", ".pakem/PROJECT.md has no valid config frontmatter")
    else:
        add("ok", f"config: type={cfg.get('type', '?')} verify={'present' if cfg.get('verify') else 'empty'}")
        verify = (cfg.get("verify") or "").strip()
        if not verify or has_placeholder(verify):
            add("fail", "verify empty in PROJECT.md (fill in the test/lint/build command)")
        surface, surface_warns = surface_config(cfg)
        add("ok", f"flag: exposure={surface['exposure']} deploy={surface['deploy']} "
                  f"handover={'true' if surface['handover'] else 'false'} "
                  f"sensitive={'true' if surface['sensitive'] else 'false'}")
        for w in surface_warns:
            add("warn", w)
        for key in ("exposure", "deploy", "handover", "sensitive"):
            if key not in cfg:
                add("warn", f"flag {key} not set in PROJECT.md (using default)")

    status, msg = gate_placeholder(root)
    add("ok" if status == "pass" else "fail", f"placeholder: {msg}")

    test_dirs = [d for d in sorted(TEST_DIR_NAMES) if (root / d).is_dir()]
    if len(test_dirs) > 1:
        add("warn", f"multiple test folders: {', '.join(test_dirs)}; pick one")

    if spec_path(root).is_file() and spec_status(root) != "approved":
        add("warn", "SPEC.md exists but is not approved (pakem spec --approve)")
    tasks = plan_tasks(root)
    pending = [t["id"] for t in tasks if not t["done"]]
    if pending:
        add("warn", f"PLAN: {count(len(pending), 'task')} not done: {', '.join(pending)}")

    if (root / PAKEM_DIR / "pakem.py").is_file():
        add("ok", ".pakem/pakem.py exists")
    else:
        add("warn", ".pakem/pakem.py missing (hook/adapter cannot call the CLI)")
    skill_cli = HERE.parent / "scripts" / "pakem.py"
    vendored = root / PAKEM_DIR / "pakem.py"
    if skill_cli.is_file() and vendored.is_file() and skill_cli.resolve() != vendored.resolve():
        vendored_ver = _parse_version(read(vendored))
        skill_ver = _parse_version(read(skill_cli))
        if vendored_ver != skill_ver:
            add("warn", f"project CLI {vendored_ver} differs from the skill install {skill_ver} "
                        f"(run `python3 {skill_cli} upgrade` from the project root)")
        else:
            differing = []
            for src in sorted((HERE.parent / "scripts" / "pakem_core").glob("*.py")):
                dst = root / PAKEM_DIR / "pakem_core" / src.name
                if dst.is_file() and (hashlib.sha256(dst.read_bytes()).hexdigest()
                                      != hashlib.sha256(src.read_bytes()).hexdigest()):
                    differing.append(f"pakem_core/{src.name}")
            if differing:
                add("warn", "project Core differs from the skill install: "
                            + ", ".join(differing[:4]) + (" ..." if len(differing) > 4 else "")
                            + " (upgrade, or `pakem integrity --re-pin --reason ...` if intentional)")
            else:
                add("ok", f"CLI + Core in sync with the skill install {skill_ver}")
    elif vendored.is_file():
        add("info", "running from the project CLI: comparison with the skill install skipped")

    if (root / PAKEM_DIR / "pakem_core" / "intelligence.py").is_file():
        add("ok", "Pakem Core Intelligence installed")
    else:
        add("warn", "Pakem Core Intelligence not installed (run scripts/pakem.py upgrade from the latest skill install)")

    is_git = (_git(root, "rev-parse", "--is-inside-work-tree") or "").strip() == "true"
    if not is_git:
        add("warn", "not a git repo: drift checks on resume and hooks are inactive")
    else:
        add("ok", "git repo")
        hooks_path = (_git(root, "config", "--get", "core.hooksPath") or "").strip()
        if hooks_path:
            add("info", f"core.hooksPath: {hooks_path}")
        hooks = hook_dir(root)
        hp = hooks / "pre-commit" if hooks else None
        if not hp or not hp.is_file():
            add("warn", f"pre-commit hook not installed ({hp or 'hooks folder not found'})")
        elif "# pakem-hook" not in read(hp):
            add("warn", f"{hp} exists, but is not a Pakem hook")
        elif ".pakem/pakem.py check" not in read(hp):
            add("warn", "Pakem hook exists, but does not run check")
        else:
            add("ok", "Pakem pre-commit hook installed")

    adapters = [x for x in (adapter_finding(root, n) for n in ADAPTERS) if x]
    if not adapters:
        add("warn", "no agent adapter (pakem adapt --adapter claude,codex,cursor)")
    for level, msg in adapters:
        add(level, msg)
    ctx_state = context_protocol_state(root)
    if ctx_state != "ok":
        add("warn", f"CONTEXT.md: {ctx_state}")
    schema_dir = root / PAKEM_DIR / "protocol" / "v1"
    missing_schemas = [name for name in ("event.schema.json", "session.schema.json", "capabilities.schema.json")
                       if not (schema_dir / name).is_file()]
    if missing_schemas:
        add("warn", "Pakem Protocol schemas incomplete (run pakem upgrade): " +
            ", ".join(missing_schemas))
    else:
        add("ok", "Pakem Protocol v1.0 stable schemas installed")
    for module_name, label in (("protocol.py", "Protocol negotiation"),
                               ("mcp_server.py", "MCP stdio adapter"),
                               ("git_worktree.py", "Git worktree adapter")):
        module_path = root / PAKEM_DIR / "pakem_core" / module_name
        add("ok" if module_path.is_file() else "warn",
            f"Pakem {label} " + ("installed" if module_path.is_file() else "not installed (run pakem upgrade)"))
    mcp_docs = root / PAKEM_DIR / "adapters" / "mcp" / "v1" / "README.md"
    worktree_docs = root / PAKEM_DIR / "adapters" / "git-worktree" / "v1" / "README.md"
    if not (mcp_docs.is_file() and worktree_docs.is_file()):
        add("warn", "MCP/Git worktree adapter docs not installed (run pakem upgrade)")
    intelligence_dir = root / PAKEM_DIR / "intelligence" / "v1"
    missing_intelligence = [name for name in ("dependency-graph.schema.json", "impact-analysis.schema.json",
                                              "reconciliation.schema.json")
                            if not (intelligence_dir / name).is_file()]
    if missing_intelligence:
        add("warn", "Pakem Intelligence schemas incomplete (run scripts/pakem.py upgrade from the latest skill install): " +
            ", ".join(missing_intelligence))
    else:
        add("ok", "Pakem Intelligence v1 schemas installed")
    runtime_module = root / PAKEM_DIR / "pakem_core" / "runtime.py"
    if runtime_module.is_file():
        add("ok", "Pakem Autonomous Runtime installed")
    else:
        add("warn", "Pakem Runtime not installed (run scripts/pakem.py upgrade from the latest skill install)")
    runtime_schema_dir = root / PAKEM_DIR / "runtime" / "v1"
    missing_runtime_schemas = [name for name in ("workflow.schema.json", "checkpoint.schema.json",
                                                  "hook-payload.schema.json", "hook-decision.schema.json",
                                                  "approval.schema.json", "task-evidence.schema.json", "work-report.schema.json")
                                if not (runtime_schema_dir / name).is_file()]
    if missing_runtime_schemas:
        add("warn", "Pakem Runtime schemas incomplete (run pakem upgrade): " + ", ".join(missing_runtime_schemas))
    policy_schema = root / PAKEM_DIR / "policy" / "v1" / "policy.schema.json"
    if not policy_schema.is_file():
        add("warn", "Pakem Policy schema not installed (run pakem upgrade)")
    coordination_module = root / PAKEM_DIR / "pakem_core" / "coordination.py"
    if coordination_module.is_file():
        add("ok", "Pakem Multi-Agent Coordination module installed")
    else:
        add("warn", "Pakem Coordination module not installed (run scripts/pakem.py upgrade from the latest skill install)")
    coordination_schema_dir = root / PAKEM_DIR / "coordination" / "v1"
    missing_coordination = [name for name in ("board.schema.json", "event.schema.json", "status.schema.json") if not (coordination_schema_dir / name).is_file()]
    if missing_coordination:
        add("warn", "Pakem Coordination schemas incomplete (run pakem upgrade): " + ", ".join(missing_coordination))
    else:
        add("ok", "Pakem Coordination v1 schemas installed")
    identity_schema_dir = root / PAKEM_DIR / "identity" / "v1"
    if all((identity_schema_dir / name).is_file() for name in ("README.md", "agent-identity.schema.json", "identity-registry.schema.json", "signed-payload.schema.json")):
        add("ok", "Pakem Ed25519 identity schemas installed")
    else:
        add("warn", "Pakem identity schemas incomplete (run pakem upgrade)")
    storage_schema_dir = root / PAKEM_DIR / "storage" / "v1"
    if all((storage_schema_dir / name).is_file() for name in ("README.md", "team-storage.schema.json")):
        add("ok", "Pakem team storage schemas installed")
    else:
        add("warn", "Pakem storage schemas incomplete (run pakem upgrade)")
    identity_module = root / PAKEM_DIR / "pakem_core" / "identity.py"
    add("ok" if identity_module.is_file() else "warn", "Pakem Ed25519 identity module " + ("installed" if identity_module.is_file() else "not installed (run pakem upgrade)"))
    team_dir_path = root / PAKEM_DIR / "team"
    team_board = team_dir_path / "board.json"
    team_storage_config = team_dir_path / "storage.json"
    if team_board.is_file() or team_storage_config.is_file() or (team_dir_path / "team.sqlite3").is_file():
        try:
            from pakem_core.coordination import status as team_status, read_events as read_team_events, storage_info
            team_data = team_status(root)
            if not team_data.get("initialized"):
                add("warn", "team storage exists but the board is not initialized")
            else:
                add("ok", f"team board: {len(team_data.get('agents', []))} agents, {len(team_data.get('tasks', []))} tasks")
            backend = storage_info(root)
            add("ok", f"team storage backend: {backend['backend']}" + (" (atomic state+event transactions)" if backend.get("transactional_state_and_events") else ""))
            team_event_data = read_team_events(root, limit=1)
            if team_event_data.get("corruptLines"):
                add("warn", f"team event ledger: {len(team_event_data['corruptLines'])} corrupt lines")
            else:
                add("ok", f"team event ledger: {team_event_data.get('total', 0)} event")
        except (ValueError, json.JSONDecodeError, ImportError, OSError) as exc:
            add("fail", f"cannot validate team board/ledger: {exc}")
    policy_file = root / PAKEM_DIR / "POLICY.json"
    if not policy_file.is_file():
        add("warn", "POLICY.json missing (run pakem upgrade)")
    else:
        try:
            from pakem_core.runtime import validate_policy
            policy_data = json.loads(read(policy_file))
            policy_errors = validate_policy(policy_data)
            add("fail" if policy_errors else "ok", "policy: " + ("; ".join(policy_errors) if policy_errors else f"autonomy={policy_data.get('autonomy')}"))
        except (ValueError, json.JSONDecodeError, ImportError) as exc:
            add("fail", f"cannot validate policy: {exc}")
    _, corrupt_events = read_event_ledger(root)
    if corrupt_events:
        add("warn", f"event ledger: {len(corrupt_events)} invalid lines")

    good, bad = scan_sessions(root)
    for p in bad:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        add("warn", f"corrupt session ignored: {rel}")
    act = active_session(root)
    if act:
        add("info", f"active session: {act[1].get('id')}")
    else:
        add("info", "no active session")

    gi = read(root / ".gitignore") if (root / ".gitignore").is_file() else ""
    if ".pakem/sessions/" not in gi.splitlines():
        add("warn", ".gitignore does not ignore .pakem/sessions/")

    rows, _, _ = audit_rows(root, cfg)
    gaps = [r for r in rows if r["tier"] == "required" and r["ok"] is False]
    if gaps:
        add("warn", f"audit: {len(gaps)} REQUIRED missing (pakem audit)")
    else:
        add("ok", "audit: no REQUIRED items missing")

    if run_verify:
        add(*probe_verify(root, cfg))

    return issues

def cmd_doctor(a):
    root = need_root()
    cfg = read_config(root)
    issues = doctor_issues(root, cfg, run_verify=a.verify)
    fails = sum(1 for lv, _ in issues if lv == "fail")
    warns = sum(1 for lv, _ in issues if lv == "warn")
    if a.json:
        print(json.dumps({
            "project": root.name,
            "issues": [{"level": lv, "message": msg} for lv, msg in issues],
            "summary": {"fail": fails, "warn": warns,
                        "ok": sum(1 for lv, _ in issues if lv == "ok")},
        }, ensure_ascii=False, indent=2))
    else:
        print(f"DOCTOR  {root.name}")
        for level, msg in issues:
            print(f"  [{level.upper():<4}] {msg}")
        print(f"\nSummary: {fails} fail, {warns} warn. "
              + ("Fix FAILs first." if fails else "No FAILs."))
    return 1 if fails else 0


# ---------------------------------------------------------------- prune

def cmd_prune(a):
    root = need_root()
    with pakem_lock(root):
        return _prune_locked(a, root)

def _prune_locked(a, root):
    good, bad = scan_sessions(root)
    active = [d.get("id") for _, d in good if d.get("status") == "active"]
    history = [(p, d) for p, d in good if d.get("status") in ("finished", "abandoned")]
    keep = max(0, a.keep)
    beyond = history[:-keep] if keep else history
    cutoff = datetime.now().timestamp() - max(0, a.days) * 86400
    candidates = [(p, d) for p, d in beyond
                  if a.days <= 0 or p.stat().st_mtime < cutoff]

    if not a.json:
        if not candidates:
            print(f"No sessions need pruning (active: {len(active)}, "
                  f"history kept: {min(keep, len(history))}).")
        else:
            print(f"Prune candidates ({len(candidates)}):")
            for p, d in candidates:
                print(f"  {p.relative_to(root).as_posix()}  {d.get('status')}  {d.get('goal') or ''}")
        for p in bad:
            print(f"[WARN] corrupt session left untouched: {p.relative_to(root).as_posix()}")
        if candidates and not a.yes:
            print("Dry-run. Add --yes to delete the files above.")
            return 0

    deleted = 0
    if candidates and a.yes:
        for p, _ in candidates:
            try:
                p.unlink()
                deleted += 1
            except OSError as e:
                if not a.json:
                    print(f"[WARN] failed to delete {p.name}: {e}")

    if a.json:
        print(json.dumps({
            "project": root.name,
            "active": active,
            "corrupt": [p.name for p in bad],
            "candidates": [{"file": p.name, "goal": d.get("goal"), "status": d.get("status")}
                           for p, d in candidates],
            "deleted": deleted,
            "keep": min(keep, len(history)),
        }, ensure_ascii=False, indent=2))
    elif candidates:
        print(f"Deleted {deleted} sessions. Active sessions and the newest {min(keep, len(history))} history entries kept.")
    return 0


# ---------------------------------------------------------------- ci

def _read_first(path: Path, default: str) -> str:
    if not path.is_file():
        return default
    for line in read(path).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return default

def ci_steps(root: Path):
    steps = ["      - uses: actions/checkout@v4"]
    if (root / "package.json").is_file():
        node = _read_first(root / ".nvmrc", "20")
        if (root / "pnpm-lock.yaml").is_file():
            steps += [
                "      - uses: pnpm/action-setup@v4",
                "        with:",
                "          version: 9",
                "      - uses: actions/setup-node@v4",
                "        with:",
                f'          node-version: "{node}"',
                "          cache: pnpm",
                "      - run: pnpm install --frozen-lockfile",
            ]
        elif (root / "yarn.lock").is_file():
            steps += [
                "      - run: corepack enable",
                "      - uses: actions/setup-node@v4",
                "        with:",
                f'          node-version: "{node}"',
                "          cache: yarn",
                "      - run: yarn install --immutable",
            ]
        elif (root / "package-lock.json").is_file():
            steps += [
                "      - uses: actions/setup-node@v4",
                "        with:",
                f'          node-version: "{node}"',
                "          cache: npm",
                "      - run: npm ci",
            ]
        else:
            steps += [
                "      - uses: actions/setup-node@v4",
                "        with:",
                f'          node-version: "{node}"',
                "      - run: npm install",
            ]
    elif (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        py = _read_first(root / ".python-version", "3.12")
        steps += [
            "      - uses: actions/setup-python@v5",
            "        with:",
            f'          python-version: "{py}"',
        ]
        if (root / "requirements.txt").is_file():
            steps.append("      - run: python -m pip install -r requirements.txt")
        if (root / "requirements-dev.txt").is_file():
            steps.append("      - run: python -m pip install -r requirements-dev.txt")
        elif (root / "pyproject.toml").is_file():
            steps.append("      # adjust the dev extra if tests need extra dependencies")
            steps.append("      - run: python -m pip install -e .")
    elif (root / "go.mod").is_file():
        steps += [
            "      - uses: actions/setup-go@v5",
            "        with:",
            "          go-version-file: go.mod",
            "          cache: true",
            "      - run: go mod download",
        ]
    elif (root / "Cargo.toml").is_file():
        steps += [
            "      - uses: dtolnay/rust-toolchain@stable",
            "      - run: cargo fetch",
        ]
    else:
        steps.append("      # TODO: add stack setup steps before check")
    steps += [
        "      - name: Pakem gates + verify",
        "        run: python3 .pakem/pakem.py check",
        "      - name: Pakem install healthy",
        "        run: python3 .pakem/pakem.py doctor",
        "      - name: Pakem required audit",
        "        run: python3 .pakem/pakem.py audit --strict",
        "      - name: Pakem ledger intact",
        "        run: python3 .pakem/pakem.py events --verify",
    ]
    return steps

def cmd_ci(a):
    root = need_root()
    p = root / ".github" / "workflows" / "ci.yml"
    if p.exists() and not a.force:
        die(".github/workflows/ci.yml already exists. Use --force to overwrite it.")
    body = "\n".join([
        "name: CI",
        "",
        "on:",
        "  push:",
        "  pull_request:",
        "",
        "permissions:",
        "  contents: read",
        "",
        "jobs:",
        "  pakem:",
        "    runs-on: ubuntu-latest",
        "    timeout-minutes: 20",
        "    steps:",
        *ci_steps(root),
        "",
    ])
    write(p, body)
    print(f"CI created: {p.relative_to(root).as_posix()} "
          f"(`check` + verify, `doctor`, `audit --strict`, `events --verify`).")
    return 0


def _parse_version(text: str) -> str:
    m = re.search(r'(?m)^VERSION = "([^"]+)"', text)
    return m.group(1) if m else "?"

def _add_missing_flags(text: str) -> str:
    for key, value in (("exposure", "private"), ("deploy", "none"), ("handover", "false")):
        if re.search(rf"(?m)^{re.escape(key)}:", text):
            continue
        line = f"{key}: {value}"
        if re.search(r"(?m)^sensitive:.*$", text):
            text = re.sub(r"(?m)^(sensitive:.*)$", lambda m: m.group(1) + "\n" + line, text, count=1)
        elif re.search(r"(?m)^verify:.*$", text):
            text = re.sub(r"(?m)^(verify:.*)$", lambda m: line + "\n" + m.group(1), text, count=1)
        else:
            text = text.replace("---\n", "---\n" + line + "\n", 1)
    return text

def cmd_upgrade(a):
    root = need_root()
    raw = Path(a.from_path).expanduser() if a.from_path else Path(__file__)
    src = raw.resolve()
    if src.is_dir():
        src = src / "scripts" / "pakem.py"
    if not src.is_file():
        die(f"upgrade source not found: {src}")

    current = root / PAKEM_DIR / "pakem.py"
    old_text = read(current) if current.is_file() else ""
    new_text = read(src)
    old_ver, new_ver = _parse_version(old_text), _parse_version(new_text)

    project = root / PAKEM_DIR / "PROJECT.md"
    project_text = read(project) if project.is_file() else ""
    new_project = _add_missing_flags(project_text)
    added_flags = [k for k in ("exposure", "deploy", "handover")
                   if not re.search(rf"(?m)^{k}:", project_text) and re.search(rf"(?m)^{k}:", new_project)]

    gi = root / ".gitignore"
    gi_text = read(gi) if gi.is_file() else ""
    ignore_lines = [".pakem/sessions/", ".pakem/events/", ".pakem/runtime/", ".pakem/team/", ".pakem/worktrees/"]
    missing_ignore = [line for line in ignore_lines if line not in gi_text.splitlines()]
    schema_source = src.parent.parent / "protocol" / "v1"
    if not schema_source.is_dir():
        schema_source = HERE.parent / "protocol" / "v1"
    schema_names = [name for name in ("README.md", "event.schema.json", "session.schema.json", "capabilities.schema.json")
                    if (schema_source / name).is_file()]
    core_source = src.parent / "pakem_core"
    if not core_source.is_dir():
        core_source = HERE / "pakem_core"
    core_names = [p.name for p in core_source.glob("*.py")] if core_source.is_dir() else []
    intelligence_source = src.parent.parent / "intelligence" / "v1"
    if not intelligence_source.is_dir():
        intelligence_source = HERE.parent / "intelligence" / "v1"
    intelligence_names = [p.name for p in intelligence_source.iterdir() if p.is_file()] if intelligence_source.is_dir() else []
    runtime_schema_source = src.parent.parent / "runtime" / "v1"
    if not runtime_schema_source.is_dir():
        runtime_schema_source = HERE.parent / "runtime" / "v1"
    policy_schema_source = src.parent.parent / "policy" / "v1"
    if not policy_schema_source.is_dir():
        policy_schema_source = HERE.parent / "policy" / "v1"
    coordination_schema_source = src.parent.parent / "coordination" / "v1"
    if not coordination_schema_source.is_dir():
        coordination_schema_source = HERE.parent / "coordination" / "v1"
    coordination_schema_names = ([f"coordination/v1/{p.name}" for p in coordination_schema_source.iterdir() if p.is_file()] if coordination_schema_source.is_dir() else [])
    identity_schema_source = src.parent.parent / "identity" / "v1"
    if not identity_schema_source.is_dir():
        identity_schema_source = HERE.parent / "identity" / "v1"
    identity_schema_names = ([f"identity/v1/{p.name}" for p in identity_schema_source.iterdir() if p.is_file()] if identity_schema_source.is_dir() else [])
    storage_schema_source = src.parent.parent / "storage" / "v1"
    if not storage_schema_source.is_dir():
        storage_schema_source = HERE.parent / "storage" / "v1"
    storage_schema_names = ([f"storage/v1/{p.name}" for p in storage_schema_source.iterdir() if p.is_file()] if storage_schema_source.is_dir() else [])
    adapter_doc_source = src.parent.parent / "adapters"
    if not adapter_doc_source.is_dir():
        adapter_doc_source = HERE.parent / "adapters"
    adapter_doc_names = [p.relative_to(adapter_doc_source).as_posix() for p in adapter_doc_source.rglob("*") if p.is_file()] if adapter_doc_source.is_dir() else []
    runtime_schema_names = ([f"runtime/v1/{p.name}" for p in runtime_schema_source.iterdir() if p.is_file()] if runtime_schema_source.is_dir() else []) + ([f"policy/v1/{p.name}" for p in policy_schema_source.iterdir() if p.is_file()] if policy_schema_source.is_dir() else [])

    adapters = [n for n in ADAPTERS if (root / ADAPTERS[n][0]).is_file()]
    context_state = context_protocol_state(root)

    if a.dry_run:
        print(f"DRY-RUN upgrade {root.name}: pakem {old_ver} -> {new_ver}")
        print(f"  CLI     : {src} -> {current.relative_to(root).as_posix()}")
        if added_flags:
            print(f"  flag    : {', '.join(added_flags)}")
        if missing_ignore:
            print(f"  ignore  : add {', '.join(missing_ignore)} to .gitignore")
        if schema_names:
            print(f"  protocol: sync schemas {', '.join(schema_names)}")
        if core_names:
            print(f"  core    : sync modules {', '.join(core_names)}")
        if intelligence_names:
            print(f"  intelligence: sync schemas {', '.join(intelligence_names)}")
        if runtime_schema_names:
            print(f"  runtime/policy: sync schemas {', '.join(runtime_schema_names)}")
        if coordination_schema_names:
            print(f"  coordination: sync schemas {', '.join(coordination_schema_names)}")
        if adapter_doc_names:
            print(f"  adapter contracts: sync {', '.join(adapter_doc_names)}")
        if not (root / PAKEM_DIR / "POLICY.json").is_file():
            print("  policy  : create default .pakem/POLICY.json (assisted mode)")
        if context_state != "ok":
            print(f"  context : protocol {context_state}")
        if adapters:
            print(f"  adapter : {', '.join(adapters)}")
        return 0

    write(current, new_text)
    try:
        current.chmod(current.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    if new_project != project_text:
        write(project, new_project)
    if missing_ignore:
        write(gi, (gi_text.rstrip("\n") + "\n" if gi_text else "") +
              "".join(line + "\n" for line in missing_ignore))
    protocol_updated = sync_protocol_schemas(root, schema_source)
    core_updated = sync_core_package(root, core_source)
    intelligence_updated = sync_intelligence_schemas(root, intelligence_source)
    runtime_schema_updated = sync_runtime_schemas(root, runtime_schema_source)
    coordination_schema_updated = sync_coordination_schemas(root, coordination_schema_source)
    identity_schema_updated = sync_identity_schemas(root, identity_schema_source)
    storage_schema_updated = sync_storage_schemas(root, storage_schema_source)
    adapter_docs_updated = sync_adapter_docs(root, adapter_doc_source)
    try:
        from pakem_core.runtime import ensure_policy
        policy_created = ensure_policy(root, HERE.parent / "assets" / "templates" / "POLICY.json")
    except ImportError:
        policy_created = False
    context_updated = sync_context_protocol(root)

    if adapters:
        # Generate in-process; spawning the just-replaced CLI adds an unnecessary
        # child process and can leave nested stdout/stderr pipes open in some hosts.
        for name in adapters:
            try:
                print(f"adapter: {write_adapter(root, name)}")
            except OSError as exc:
                print(f"[WARN] adapter {name} failed after upgrade: {exc}")

    print(f"Upgrade complete: pakem {old_ver} -> {new_ver}")
    print(f"  CLI     : {current.relative_to(root).as_posix()}")
    if added_flags:
        print(f"  flag    : {', '.join(added_flags)} (default; change to match reality)")
    if missing_ignore:
        print(f"  ignore  : {', '.join(missing_ignore)} added")
    if protocol_updated:
        print(f"  protocol: {', '.join(protocol_updated)} synced")
    if core_updated:
        print(f"  core    : {', '.join(core_updated)} synced")
    if intelligence_updated:
        print(f"  intelligence: {', '.join(intelligence_updated)} synced")
    if runtime_schema_updated:
        print(f"  runtime/policy: {', '.join(runtime_schema_updated)} synced")
    if coordination_schema_updated:
        print(f"  coordination: {', '.join(coordination_schema_updated)} synced")
    if identity_schema_updated:
        print(f"  identity: {', '.join(identity_schema_updated)} synced")
    if storage_schema_updated:
        print(f"  storage: {', '.join(storage_schema_updated)} synced")
    if adapter_docs_updated:
        print(f"  adapter contracts: {', '.join(adapter_docs_updated)} synced")
    if policy_created:
        print("  policy: .pakem/POLICY.json created (assisted mode)")
    if context_updated:
        print("  context : protocol block synced")
    if adapters:
        print(f"  adapter : {', '.join(adapters)}")
    print("  Project content documents untouched; CLI, Core, schemas, adapter contracts, default policy (only if missing), ignore entries, and adapter blocks synced.")
    return 0



def cmd_context(a):
    """Render a compact machine-readable snapshot for agent adapters and tools."""
    root = need_root()
    cfg = read_config(root)
    act = active_session(root)
    tasks = plan_tasks(root)
    pending = [task for task in tasks if not task["done"]]
    completed = len(tasks) - len(pending)
    spec = spec_status(root)
    blockers = []
    gate_checks = (
        ("rules", lambda: gate_rules(root, cfg)),
        ("placeholder", lambda: gate_placeholder(root)),
        ("spec", lambda: gate_spec(root)),
        ("plan", lambda: gate_plan(root)),
        ("drift", lambda: gate_drift(root)),
        ("handover", lambda: gate_handover(root)),
    )
    gates = {}
    for name, check in gate_checks:
        status, detail = check()
        gates[name] = {"status": status, "detail": detail}
        if status == "fail":
            blockers.append(name + "_gate_failed")
    if not cfg.get("verify", "").strip():
        blockers.append("verify_command_missing")
    if act:
        recommended = "resume_active_session"
    elif spec == "draft":
        recommended = "complete_and_approve_spec"
    elif blockers:
        recommended = "resolve_project_gates"
    else:
        recommended = "start_session"
    surface, surface_warnings = surface_config(cfg)
    risk = risk_warnings(root, cfg)
    repository = git_state(root)
    runtime_snapshot = {"enabled": False, "workflow": None, "autonomy": None}
    try:
        from pakem_core.runtime import load_policy, load_workflow
        runtime_workflow = load_workflow(root)
        runtime_policy = load_policy(root)
        runtime_snapshot = {"enabled": True, "workflow": runtime_workflow,
                            "autonomy": runtime_policy["autonomy"],
                            "max_autonomous_risk": runtime_policy["maxAutonomousRisk"]}
        if runtime_workflow and runtime_workflow.get("state") == "blocked":
            blockers.append("runtime_workflow_blocked")
            recommended = "resolve_runtime_blocker"
        elif runtime_workflow and runtime_workflow.get("state") == "recovering":
            blockers.append("runtime_recovery_review_required")
            recommended = "inspect_repository_then_resume_runtime"
    except (ImportError, ValueError):
        runtime_snapshot["error"] = "runtime module or policy unavailable; run pakem upgrade"
    team_snapshot = {"enabled": False, "summary": {"open": 0, "claimed": 0, "review": 0, "done": 0, "blocked": 0}}
    team_board_path = root / PAKEM_DIR / "team" / "board.json"
    if team_board_path.is_file():
        try:
            from pakem_core.coordination import status as team_status
            team_data = team_status(root)
            team_snapshot = {"enabled": bool(team_data.get("initialized")),
                             "board_id": team_data.get("boardId"),
                             "revision": team_data.get("revision"),
                             "summary": team_data.get("summary", team_snapshot["summary"]),
                             "review_tasks": [t["taskId"] for t in team_data.get("tasks", []) if t.get("state") == "review"]}
            if team_snapshot["review_tasks"] and recommended == "start_session":
                recommended = "review_team_tasks"
        except (ImportError, ValueError):
            team_snapshot["error"] = "cannot read team board; run pakem doctor"
    result = {
        "protocol": "pakem",
        "protocol_version": PROTOCOL_VERSION,
        "project": {"name": root.name, "root": str(root), "type": cfg.get("type", "unknown"),
                    "verify_configured": bool(cfg.get("verify", "").strip())},
        "runtime": runtime_snapshot,
        "team": team_snapshot,
        "session": ({"active": True, "id": act[1].get("id"), "goal": act[1].get("goal"),
                     "next_step": act[1].get("nextStep") or None,
                     "last_position": act[1].get("lastPosition") or None,
                     "agent": act[1].get("agent") or None} if act else {"active": False}),
        "spec": {"status": spec},
        "plan": {"total": len(tasks), "completed": completed, "pending": len(pending),
                 "next_task": ({"id": pending[0]["id"], "text": pending[0]["text"],
                                "files": pending[0]["files"], "verify": pending[0]["verify"]}
                               if pending else None)},
        "gates": gates,
        "verify_configured": bool(cfg.get("verify", "").strip()),
        "repository": repository,
        "risk": {"surface": surface, "warnings": surface_warnings, "advisories": risk},
        "blockers": blockers,
        "recommended_next": recommended,
        "read_first": [".pakem/CONTEXT.md", ".pakem/PROJECT.md", ".pakem/POLICY.json"] + ([".pakem/coordination/v1/README.md", ".pakem/team/board.json"] if team_snapshot.get("enabled") else []),
        "interfaces": ["cli", "json", "lifecycle_events", "agent_adapters", "runtime_hooks", "policy_decisions", "checkpoint_recovery", "multi_agent_coordination", "protocol_capability_negotiation", "mcp_stdio", "git_worktree_isolation"],
    }
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Pakem context — {root.name}")
        print(f"Protocol: {PROTOCOL_VERSION} | session: {'active' if act else 'none'}")
        print(f"Spec: {spec} | plan: {completed}/{len(tasks)} | next: {recommended}")
        if team_snapshot.get("enabled"):
            print("Team: " + ", ".join(f"{k}={v}" for k, v in team_snapshot.get("summary", {}).items()))
        if blockers:
            print("Blockers: " + ", ".join(blockers))
        print("Read first: " + ", ".join(result["read_first"]))
    return 0


def _cmd_events_verify(root: Path, a) -> int:
    targets = ledger_targets(root, a.session)
    if a.expect_head and not a.session and len([p for p in targets if p.is_file()]) > 1:
        die("--expect-head requires --session: more than one ledger in this project")
    reports, problems, notes = [], [], []
    for path in targets:
        if not path.is_file():
            continue
        info = verify_ledger_file(path)
        seal_problems, seal_notes = _verify_seals(root, info)
        info["problems"] += seal_problems
        notes += seal_notes
        reports.append(info)
        problems += [{"file": info["file"], **item} for item in info["problems"]]
    head = reports[-1]["head"] if reports else None
    if a.expect_head and (head or "") != a.expect_head.strip().lower():
        problems.append({"file": "-", "line": 0,
                         "reason": "ledger head does not match --expect-head (ledger rewritten?)"})
    total = sum(item["events"] for item in reports)
    seals = sum(len(item["seals"]) for item in reports)
    legacy = sum(item["legacy"] for item in reports)
    if a.json:
        print(json.dumps({"ok": not problems, "head": head, "event_count": total,
                          "seal_count": seals, "legacy_events": legacy,
                          "files": reports, "problems": problems, "notes": notes},
                         ensure_ascii=False, indent=2))
    else:
        for note in notes:
            print(f"[WARN] {note}")
        if problems:
            print(f"LEDGER BROKEN  {len(problems)} problems")
            for item in problems[:10]:
                print(f"  {item['file']}:{item['line']}  {item['reason']}")
        else:
            print(f"LEDGER OK  {len(reports)} file, {total} event, {seals} seal, "
                  f"head={(head or '-')[:16]}")
            if legacy:
                print(f"  {legacy} legacy events without integrity (pre-chain history)")
    return 0 if not problems else 1


def _cmd_events_sign(root: Path, a) -> int:
    act = active_session(root)
    session_id = a.session or (act[1].get("id") if act else None)
    if session_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", session_id):
        die("session ID contains invalid characters")
    path = events_dir(root) / (f"{session_id}.jsonl" if session_id else "project.jsonl")
    info = verify_ledger_file(path)
    seal_problems, _ = _verify_seals(root, info)
    info["problems"] += seal_problems
    if info["problems"]:
        die("ledger cannot be sealed yet: "
            + "; ".join(f"line {item['line']}: {item['reason']}" for item in info["problems"][:3]))
    agent = (a.identity or "").strip() or ((act[1].get("agent") if act else "") or "")
    if not agent:
        die("--identity required when the session has no agent; identities: pakem identity create <id>")
    try:
        from pakem_core import identity as identity_core
    except ImportError as exc:
        die(f"identity module unavailable: {exc}")
    payload = {"ledger": path.name, "chain_head": info["head"], "event_count": info["events"],
               "sealed_at": now()}
    key_source = getattr(a, "key", None) or os.environ.get("PAKEM_SEAL_KEY") or ""
    if key_source:
        key_path = Path(key_source).expanduser()
        try:
            inside = root.resolve() in key_path.resolve().parents
        except OSError:
            inside = False
        if inside:
            print(f"[WARN] private key is inside the repo ({key_path}); the seal only proves "
                  f"file integrity, not who holds the key outside the repo.", flush=True)
    try:
        envelope = identity_core.sign(root, agent, payload, key_path=key_source or None)
    except ValueError as exc:
        die(str(exc))
    with pakem_lock(root):
        append_event(root, "ledger.sealed", {"id": session_id, "agent": agent} if session_id else None,
                     payload={**payload, "seal": envelope}, actor_type="agent")
    print(f"[SEAL] {path.name} head={(info['head'] or '-')[:16]} event={info['events']} agent={agent}")
    return 0


def cmd_events(a):
    root = need_root()
    if getattr(a, "verify", False):
        return _cmd_events_verify(root, a)
    if getattr(a, "sign", False):
        return _cmd_events_sign(root, a)
    if a.limit < 0:
        die("--limit must not be negative")
    records, corrupt = read_event_ledger(root, a.session)
    records = records[-a.limit:] if a.limit else records
    if a.json:
        print(json.dumps({"protocol": "pakem", "protocol_version": PROTOCOL_VERSION,
                          "count": len(records), "events": records, "corrupt": corrupt},
                         ensure_ascii=False, indent=2))
    else:
        if not records:
            print("No Pakem events recorded yet.")
        for item in records:
            payload = item.get("payload") or {}
            detail = payload.get("text") or payload.get("task_id") or payload.get("status") or payload.get("goal") or ""
            print(f"{item['occurred_at']}  {item['event']:<26} {detail}".rstrip())
        for item in corrupt:
            print(f"[WARN] {item['file']}:{item['line']}: {item['reason']}")
    return 1 if corrupt and a.strict else 0


def cmd_graph(a):
    """Build a static local dependency graph for the current project."""
    root = need_root()
    try:
        from pakem_core.intelligence import build_dependency_graph, render_graph_text
    except ImportError as exc:
        die(f"Pakem Core module unavailable: {exc}. Run the latest CLI from the skill install: `python3 <skill-location>/scripts/pakem.py upgrade` from the project root.")
    graph = build_dependency_graph(root, include_tests=not a.exclude_tests)
    payload = json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
    if a.output:
        out = Path(a.output).expanduser()
        if not out.is_absolute():
            out = root / out
        write(out, payload)
        print(f"Dependency graph written: {out}", file=sys.stderr if a.json else sys.stdout)
    if a.json:
        print(payload, end="")
    else:
        print(render_graph_text(graph))
    return 0


def cmd_impact(a):
    """Analyze reverse dependencies and likely verification impact."""
    root = need_root()
    try:
        from pakem_core.intelligence import (
            analyze_impact, build_dependency_graph, changed_files_for_impact,
            render_impact_text,
        )
        files = changed_files_for_impact(root, files=a.files, base=a.base, staged=a.staged)
        graph = build_dependency_graph(root)
        result = analyze_impact(root, files, graph=graph)
    except (ImportError, ValueError) as exc:
        die(str(exc))
    strict_blocked = bool(a.strict and result["risk"]["level"] == "high")
    result["strict_blocked"] = strict_blocked
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_impact_text(result))
        if strict_blocked:
            print("\n[BLOCK] HIGH risk: extra review required before the work can be declared done.")
    return 1 if strict_blocked else 0


def cmd_reconcile(a):
    """Compare actual changes against plan scope and spec acceptance criteria."""
    root = need_root()
    if not (root / ".git").exists():
        die("reconcile requires Git history; run `git init` and commit first")
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode != 0:
        die("repo has no commits; make the first commit so changes can be compared")
    try:
        result = build_reconciliation(root, base=a.base, staged=a.staged)
        from pakem_core.reconcile import render_text
    except ImportError as exc:
        die(str(exc))
    except ValueError as exc:
        die(f"cannot compare changes: {exc}")
    except Exception as exc:
        die(f"cannot read Git changes: {exc}")
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    if a.strict and not result["ok"]:
        return 1
    return 0


def cmd_protocol(a):
    if a.action == "negotiate":
        try:
            from pakem_core.protocol import negotiate
            result = negotiate(a.peer_version, a.capability or [])
        except (ImportError, ValueError) as exc:
            die(f"protocol negotiation failed: {exc}")
        if a.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            state = "COMPATIBLE" if result["compatible"] else "INCOMPATIBLE"
            print(f"{state}: Pakem {result['local_version']} <-> peer {result['peer_version']}")
            print("  common capabilities: " + (", ".join(result["common_capabilities"]) or "(none)"))
            if result["unsupported_peer_capabilities"]:
                print("  unsupported peer capabilities: " + ", ".join(result["unsupported_peer_capabilities"]))
        return 0 if result["compatible"] else 2
    if a.action == "info":
        try:
            from pakem_core.protocol import CAPABILITIES
            capabilities = CAPABILITIES
        except ImportError:
            capabilities = {}
        info = {"protocol": "pakem", "version": PROTOCOL_VERSION,
                "event_schema": ".pakem/protocol/v1/event.schema.json",
                "session_schema": ".pakem/protocol/v1/session.schema.json",
                "capabilities_schema": ".pakem/protocol/v1/capabilities.schema.json",
                "capabilities": capabilities,
                "events": sorted(PROTOCOL_EVENTS)}
        if a.json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"Pakem Protocol {PROTOCOL_VERSION}")
            print("Schema event : " + info["event_schema"])
            print("Schema session: " + info["session_schema"])
            print("Schema capabilities: " + info["capabilities_schema"])
            print("Capabilities: " + ", ".join(sorted(info["capabilities"])))
            print("Events: " + ", ".join(info["events"]))
        return 0
    path = Path(a.file).expanduser()
    kind = "event" if a.action == "validate-event" else "session"
    try:
        record = json.loads(read(path))
    except (OSError, json.JSONDecodeError) as exc:
        errors = [f"cannot read JSON: {exc}"]
    else:
        errors = validate_event_record(record) if kind == "event" else validate_session_record(record)
    if a.json:
        print(json.dumps({"kind": kind, "valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print(f"{kind.title()} invalid:")
        for error in errors:
            print("  - " + error)
    else:
        print(f"{kind.title()} valid — Pakem Protocol " + PROTOCOL_VERSION)
    return 1 if errors else 0




def cmd_identity(a):
    root = need_root()
    try:
        from pakem_core import identity as core
        if a.action == "create":
            result = core.create(root, a.agent_id, key_out=getattr(a, "key_out", None))
        elif a.action == "list":
            result = core.list_identities(root)
        elif a.action == "revoke":
            result = core.revoke(root, a.agent_id, a.reason or "")
        elif a.action == "rotate":
            result = core.rotate(root, a.agent_id, a.reason or "")
        elif a.action == "import":
            public = a.public_key
            candidate = Path(public).expanduser()
            if candidate.is_file():
                public = read(candidate).strip()
            result = core.import_public(root, a.agent_id, public, replace=a.replace)
        elif a.action == "sign":
            source = Path(a.file).expanduser()
            if source.stat().st_size > 1024 * 1024:
                raise ValueError("payload JSON must be at most 1 MiB")
            payload = json.loads(read(source))
            result = core.sign(root, a.agent_id, payload, key_path=getattr(a, "key", None))
        elif a.action == "issue":
            actions = [part.strip() for group in (a.action_scope or []) for part in group.split(",") if part.strip()]
            result = core.issue_token(root, a.agent_id, a.audience, actions, a.ttl_seconds)
        elif a.action == "verify":
            path = Path(a.file).expanduser()
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("signed envelope must be at most 2 MiB")
            envelope = json.loads(read(path))
            result = core.verify(root, envelope, a.audience, a.action_scope)
        else:
            die("unknown identity action")
    except (ImportError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        die(str(exc))
    if a.action == "sign" and a.output:
        write(Path(a.output).expanduser(), json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(f"Signed envelope written to {a.output}")
    elif a.json or a.action in {"create", "issue", "verify", "list", "revoke"}:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_mcp(a):
    if a.action != "serve":
        die("unknown MCP action")
    try:
        from pakem_core.mcp_server import serve_stdio
    except ImportError as exc:
        die(f"MCP adapter unavailable: {exc}. Run pakem upgrade.")
    if a.agent_id:
        try:
            from pakem_core.coordination import status as team_status
            board = team_status(Path.cwd())
            if not any(x.get("agentId") == a.agent_id and x.get("status") == "active" for x in board.get("agents", [])):
                die(f"agent {a.agent_id} is not registered as active on the team board")
        except (ValueError, RuntimeError, OSError) as exc:
            die(f"failed to check agent binding: {exc}")
    return serve_stdio(Path.cwd(), allow_write=a.allow_write, bound_agent_id=a.agent_id)


def cmd_worktree(a):
    try:
        from pakem_core import git_worktree
        root = need_root()
        if a.action == "create":
            result = git_worktree.create(root, a.task_id, a.agent, a.base)
        elif a.action == "list":
            result = git_worktree.list_worktrees(root)
        elif a.action == "remove":
            result = git_worktree.remove(root, a.path, a.force)
        elif a.action == "cleanup":
            if a.task_id:
                report = git_worktree.cleanup_for_task(root, a.task_id, dry_run=a.dry_run)
            else:
                report = git_worktree.cleanup_merged(root, dry_run=a.dry_run)
            if a.json:
                print(json.dumps({"dry_run": a.dry_run, "worktrees": report},
                                 ensure_ascii=False, indent=2))
            else:
                if not report:
                    print("No pakem/* worktrees.")
                for item in report:
                    if item["action"] == "removed":
                        print(f"[WT ] {item['branch']} deleted (merged, clean)")
                    elif item["action"] == "would-remove":
                        print(f"[DRY] {item['branch']} will be deleted (merged, clean)")
                    else:
                        print(f"[WARN] {item['branch']} left as is: {item['reason']}")
            return 0
        elif a.action == "scope":
            result, meta = worktree_scope(root, a.name)
            core, _ = _reconcile_import()
            if a.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"WORKTREE {meta['name']}  task {meta['task']}  ({meta['path']})")
                if not meta["scoped"] and result["changed_files"]:
                    print(f"  (task {meta['task']} has no file scope; all changes count as outside scope)")
                print(core.render_text(result))
            return 1 if (a.strict and not result["ok"]) else 0
        else:
            die("unknown worktree action")
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        die(str(exc))
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_team_storage(a, action):
    # Reuse the established team command error and output contract.
    a.action = action
    return cmd_team(a)


def _runtime_import():
    try:
        from pakem_core import runtime as runtime_core
        return runtime_core
    except ImportError as exc:
        die(f"Pakem Runtime module unavailable: {exc}. Run the latest CLI from the skill install: `python3 <skill-location>/scripts/pakem.py upgrade` from the project root.")


def _runtime_event(root: Path, event: str, workflow: dict | None = None, payload: dict | None = None):
    try:
        append_event(root, event, session=active_session(root)[1] if active_session(root) else None,
                     payload=payload or {}, actor_type="system")
    except (ValueError, OSError) as exc:
        print(f"[WARN] runtime event not recorded: {exc}", file=sys.stderr)


def cmd_runtime(a):
    root = need_root()
    core = _runtime_import()
    try:
        if a.action == "init":
            with pakem_lock(root):
                policy_created = core.ensure_policy(root, TEMPLATE_DIR / "POLICY.json")
                workflow = core.init_workflow(root, a.goal or "", new=a.new)
                _runtime_event(root, "runtime.workflow.initialized", workflow,
                               {"workflow_id": workflow["workflowId"], "goal": workflow.get("goal", "")})
            result = {"workflow": workflow, "policy_created": policy_created}
        elif a.action == "status":
            workflow = core.load_workflow(root)
            policy = core.load_policy(root)
            checkpoints = (workflow or {}).get("checkpointIds", [])
            result = {"workflow": workflow, "autonomy": policy["autonomy"],
                      "max_autonomous_risk": policy["maxAutonomousRisk"],
                      "checkpoint_count": len(checkpoints),
                      "next_action": ("start_planning" if not workflow else
                                      {"planning": "prepare_spec_and_plan", "ready": "begin_task",
                                       "executing": "continue_task", "verifying": "run_verification",
                                       "blocked": "resolve_blocker", "recovering": "inspect_repo_then_resume",
                                       "completed": "workflow_completed", "failed": "recover_or_restart",
                                       "initialized": "prepare_plan"}.get(workflow["state"], "inspect_workflow"))}
        elif a.action == "transition":
            with pakem_lock(root):
                workflow, checkpoint = core.transition_workflow(root, a.to_state, a.reason or "", a.task_id)
                _runtime_event(root, "runtime.state.transitioned", workflow,
                               {"workflow_id": workflow["workflowId"], "from": workflow["lastTransition"]["from"],
                                "to": workflow["state"], "revision": workflow["revision"],
                                "checkpoint_id": checkpoint["checkpointId"] if checkpoint else None})
            result = {"workflow": workflow, "automatic_checkpoint": checkpoint["checkpointId"] if checkpoint else None}
        elif a.action == "checkpoint":
            with pakem_lock(root):
                checkpoint = core.create_checkpoint(root, a.label or "manual")
                workflow = core.load_workflow(root)
                _runtime_event(root, "runtime.checkpoint.created", workflow,
                               {"workflow_id": checkpoint["workflowId"], "checkpoint_id": checkpoint["checkpointId"],
                                "label": checkpoint["label"]})
            result = {"checkpoint": checkpoint}
        elif a.action == "recover":
            with pakem_lock(root):
                workflow, recovery = core.recover_workflow(root, a.checkpoint_id)
                _runtime_event(root, "runtime.recovered", workflow,
                               {"workflow_id": workflow["workflowId"], "checkpoint_id": recovery["checkpoint_id"],
                                "drift": recovery["drift"]})
            result = {"workflow": workflow, "recovery": recovery,
                      "warning": "Only workflow metadata is restored; source code is not reverted. Inspect the Git diff before continuing."}
        elif a.action == "hook":
            payload = {}
            if a.payload_file:
                try:
                    payload = json.loads(read(Path(a.payload_file).expanduser()))
                except (OSError, json.JSONDecodeError) as exc:
                    die(f"cannot read hook payload: {exc}")
            with pakem_lock(root):
                result = core.dispatch_hook(root, a.event, payload, a.approval_id)
                _runtime_event(root, "runtime.hook.dispatched", core.load_workflow(root),
                               {"hook": a.event, "decision": result["decision"],
                                "category": result["category"], "risk": result["risk"],
                                "approval_id": result.get("approvalId")})
        else:
            die("unknown runtime action")
    except ValueError as exc:
        die(str(exc), 1)

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if a.action == "status":
            wf = result.get("workflow")
            print("Workflow: " + (wf["workflowId"] if wf else "not initialized"))
            print("State: " + (wf["state"] if wf else "none"))
            print("Autonomy: " + result["autonomy"] + " | max risk: " + result["max_autonomous_risk"])
            print("Next: " + result["next_action"])
        elif a.action == "hook":
            print(f"Hook {result['hook']}: {result['decision']} — {result['reason']}")
        elif a.action == "recover":
            print(f"Workflow recovered from checkpoint {result['recovery']['checkpoint_id']} to state recovering.")
            print("WARNING: source code is not reverted. Inspect the Git diff before continuing.")
            if any(result["recovery"]["drift"].values()):
                print("[WARN] repository state differs from the checkpoint.")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    if a.action == "hook":
        return 0 if result["decision"] == "allow" else (3 if result["decision"] == "require_approval" else 1)
    return 0


def cmd_policy(a):
    root = need_root()
    core = _runtime_import()
    try:
        if a.action == "show":
            policy = core.load_policy(root)
            result = {"policy": policy, "schema": ".pakem/policy/v1/policy.schema.json"}
        elif a.action == "approve":
            with pakem_lock(root):
                approval = core.grant_approval(root, a.category, a.risk, a.target or "", a.reason or "")
                _runtime_event(root, "policy.approval.granted", core.load_workflow(root),
                               {"approval_id": approval["approvalId"], "category": a.category,
                                "risk": a.risk, "workflow_id": approval.get("workflowId")})
            result = {"approval": approval,
                      "warning": "This is a local approval record. The runtime host must still ensure this command was triggered by trusted user confirmation."}
        elif a.action == "check":
            with pakem_lock(root):
                decision = core.evaluate_policy(root, a.category, a.risk, a.target or "", a.approval_id)
                _runtime_event(root, "policy.decision", core.load_workflow(root),
                               {"decision": decision["decision"], "category": a.category,
                                "risk": a.risk, "approval_id": decision.get("approvalId")})
            result = decision
        else:
            die("unknown policy action")
    except ValueError as exc:
        die(str(exc), 1)

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif a.action == "show":
        print(json.dumps(result["policy"], ensure_ascii=False, indent=2))
        print("Schema: " + result["schema"])
    elif a.action == "approve":
        print("Approval created: " + result["approval"]["approvalId"])
        print(result["warning"])
    else:
        print(f"Policy decision: {result['decision']} — {result['reason']}")
    if a.action == "check":
        return 0 if result["decision"] == "allow" else (3 if result["decision"] == "require_approval" else 1)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="pakem", description="Pakem - working discipline for coding agents.")
    p.add_argument("--version", action="version", version=f"pakem {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="install .pakem/ in the current folder")
    s.add_argument("--type", choices=list(PROFILES), default="app")
    s.add_argument("--verify", default=None, help="verify command (default: auto-detect)")
    s.add_argument("--adapter", default="claude,codex,cursor",
                   help=f"comma-separated list of: {', '.join(ADAPTERS)}; or 'none'")
    s.add_argument("--existing", action="store_true", help="force existing-repo mode")
    s.add_argument("--fresh", action="store_true", help="force new-project mode")
    s.add_argument("--force", action="store_true")
    s.add_argument("--hook", action="store_true", help="install git pre-commit hook")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("start", help="start a session (or resume an interrupted one)")
    s.add_argument("goal")
    s.add_argument("--prompt")
    s.add_argument("--agent")
    s.add_argument("--new", action="store_true", help="ignore the active session and start fresh")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("step", help="record a finished step + the next step")
    s.add_argument("text")
    s.add_argument("--next")
    s.set_defaults(fn=cmd_step)

    s = sub.add_parser("status", help="project and session summary")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("integrity", help="compare CLI/Core with what was pinned at session start")
    s.add_argument("--session", help="inspect a specific session (default: active session)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--re-pin", action="store_true", help="re-pin after an intentional change")
    s.add_argument("--reason", help="re-pin reason (required with --re-pin)")
    s.set_defaults(fn=cmd_integrity)

    s = sub.add_parser("report", help="work roll-up: sessions, tasks, verify evidence, ledger")
    s.add_argument("--json", action="store_true", help="structured JSON output")
    s.add_argument("--session", help="limit to one session")
    s.add_argument("--limit", type=int, default=0, help="only the N newest sessions")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("context", help="workflow context snapshot for agents")
    s.add_argument("--json", action="store_true", help="structured JSON output")
    s.set_defaults(fn=cmd_context)

    s = sub.add_parser("graph", help="build a static project dependency graph")
    s.add_argument("--json", action="store_true", help="JSON output for agents/tools")
    s.add_argument("--output", help="save graph JSON to a path (relative to the project root)")
    s.add_argument("--exclude-tests", action="store_true", help="do not include test files in the graph")
    s.set_defaults(fn=cmd_graph)

    s = sub.add_parser("impact", help="analyze change impact and tests to prioritize")
    s.add_argument("--files", nargs="+", help="changed files; relative or absolute paths")
    s.add_argument("--base", help="compare the working tree with REF (commits, edits, and deleted files)")
    s.add_argument("--staged", action="store_true", help="analyze staged changes")
    s.add_argument("--json", action="store_true", help="JSON output for agents/tools")
    s.add_argument("--strict", action="store_true", help="exit 1 when HIGH risk is detected")
    s.set_defaults(fn=cmd_impact)

    s = sub.add_parser("reconcile", help="compare actual changes with plan scope and spec acceptance")
    s.add_argument("--base", help="compare the working tree with REF (commits, edits, and deleted files)")
    s.add_argument("--staged", action="store_true", help="only staged changes")
    s.add_argument("--json", action="store_true", help="JSON output for agents/tools")
    s.add_argument("--strict", action="store_true", help="exit 1 when code is outside scope or acceptance is unchecked")
    s.set_defaults(fn=cmd_reconcile)

    s = sub.add_parser("events", help="view the append-only workflow event ledger")
    s.add_argument("--session", help="filter by session ID")
    s.add_argument("--limit", type=int, default=50, help="number of newest events (0 = all)")
    s.add_argument("--json", action="store_true", help="JSON output for agents")
    s.add_argument("--strict", action="store_true", help="exit 1 when the ledger has corrupt lines")
    s.add_argument("--verify", action="store_true", help="check the hash chain and signature seals")
    s.add_argument("--sign", action="store_true", help="seal the ledger with an Ed25519 identity")
    s.add_argument("--identity", help="agent ID for sealing")
    s.add_argument("--key", help="external private key for the seal (default: env PAKEM_SEAL_KEY)")
    s.add_argument("--expect-head", help="expected head hash")
    s.set_defaults(fn=cmd_events)

    s = sub.add_parser("protocol", help="Pakem Protocol information and validation")
    ps = s.add_subparsers(dest="action", required=True)
    pi = ps.add_parser("info", help="show the protocol contract")
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(fn=cmd_protocol)
    pv = ps.add_parser("validate-event", help="validate one event JSON")
    pv.add_argument("file", help="path to the event JSON file")
    pv.add_argument("--json", action="store_true")
    pv.set_defaults(fn=cmd_protocol)
    psess = ps.add_parser("validate-session", help="validate one session JSON")
    psess.add_argument("file", help="path to the session JSON file")
    psess.add_argument("--json", action="store_true")
    psess.set_defaults(fn=cmd_protocol)
    pn = ps.add_parser("negotiate", help="negotiate version and capabilities with a Pakem peer")
    pn.add_argument("--peer-version", required=True)
    pn.add_argument("--capability", action="append", default=[], help="peer capability; repeatable")
    pn.add_argument("--json", action="store_true")
    pn.set_defaults(fn=cmd_protocol)

    s = sub.add_parser("identity", help="Ed25519 agent identity, signed attestations, and scoped delegation tokens")
    ids = s.add_subparsers(dest="action", required=True)
    ic = ids.add_parser("create", help="create an Ed25519 keypair; the private key is stored in user config, not the project")
    ic.add_argument("agent_id")
    ic.add_argument("--key-out", help="write the private key to this path (e.g. a CI secret directory)")
    ic.add_argument("--json", action="store_true")
    ic.set_defaults(fn=cmd_identity)
    il = ids.add_parser("list", help="list public identities and revocation status")
    il.add_argument("--json", action="store_true")
    il.set_defaults(fn=cmd_identity)
    ir = ids.add_parser("revoke", help="revoke an agent identity")
    ir.add_argument("agent_id")
    ir.add_argument("--reason", default="")
    ir.add_argument("--json", action="store_true")
    ir.set_defaults(fn=cmd_identity)
    iro = ids.add_parser("rotate", help="create a new keypair; the old public key is kept as retired metadata")
    iro.add_argument("agent_id")
    iro.add_argument("--reason", default="")
    iro.add_argument("--json", action="store_true")
    iro.set_defaults(fn=cmd_identity)
    iim = ids.add_parser("import", help="register a public key from another host (no private key)")
    iim.add_argument("agent_id")
    iim.add_argument("--public-key", required=True, help="base64 Ed25519 32 bytes, or a path to a file containing base64")
    iim.add_argument("--replace", action="store_true", help="overwrite the existing agent entry")
    iim.add_argument("--json", action="store_true")
    iim.set_defaults(fn=cmd_identity)
    isig = ids.add_parser("sign", help="sign a JSON payload with the agent private key")
    isig.add_argument("agent_id")
    isig.add_argument("--file", required=True, help="payload JSON file")
    isig.add_argument("--key", help="external private key path (raw 32 bytes or PEM)")
    isig.add_argument("--output", help="signed envelope output file; default stdout")
    isig.add_argument("--json", action="store_true")
    isig.set_defaults(fn=cmd_identity)
    ii = ids.add_parser("issue", help="issue an Ed25519 delegation token with audience/action/expiry")
    ii.add_argument("agent_id")
    ii.add_argument("--audience", required=True)
    ii.add_argument("--action", dest="action_scope", action="append", required=True,
                    help="action scope; repeatable or comma-separated")
    ii.add_argument("--ttl-seconds", type=int, default=900)
    ii.add_argument("--json", action="store_true")
    ii.set_defaults(fn=cmd_identity)
    iv = ids.add_parser("verify", help="verify signature, revocation, expiry, audience, and action")
    iv.add_argument("file", help="signed envelope JSON")
    iv.add_argument("--audience")
    iv.add_argument("--action", dest="action_scope")
    iv.add_argument("--json", action="store_true")
    iv.set_defaults(fn=cmd_identity)

    s = sub.add_parser("mcp", help="MCP stateless stdio adapter")
    ms = s.add_subparsers(dest="action", required=True)
    mserve = ms.add_parser("serve", help="run the MCP server over stdin/stdout")
    mserve.add_argument("--agent-id", help="agent identity bound by the host; required for write mode")
    mserve.add_argument("--allow-write", action="store_true", help="expose team mutation tools (default read-only)")
    mserve.set_defaults(fn=cmd_mcp)

    s = sub.add_parser("worktree", help="isolate agent work with local Git worktrees")
    ws = s.add_subparsers(dest="action", required=True)
    wc = ws.add_parser("create", help="create an isolated task/agent worktree")
    wc.add_argument("task_id")
    wc.add_argument("--agent", required=True)
    wc.add_argument("--base", default="HEAD")
    wc.add_argument("--json", action="store_true")
    wc.set_defaults(fn=cmd_worktree)
    wl = ws.add_parser("list", help="list all Git worktrees")
    wl.add_argument("--json", action="store_true")
    wl.set_defaults(fn=cmd_worktree)
    wr = ws.add_parser("remove", help="delete a Pakem worktree (dirty only with --force)")
    wr.add_argument("path")
    wr.add_argument("--force", action="store_true", help="allow discarding uncommitted local changes")
    wr.add_argument("--json", action="store_true")
    wcl = ws.add_parser("cleanup", help="delete task worktrees merged into HEAD and clean")
    wcl.add_argument("task_id", nargs="?", help="only this task (default: all pakem/* worktrees)")
    wcl.add_argument("--dry-run", action="store_true", help="show without deleting")
    wcl.add_argument("--json", action="store_true")
    wcl.set_defaults(fn=cmd_worktree)
    wr.set_defaults(fn=cmd_worktree)
    wsc = ws.add_parser("scope", help="compare worktree changes with its task scope")
    wsc.add_argument("name", help="worktree name: T1--solo, T1/solo, or a path")
    wsc.add_argument("--json", action="store_true")
    wsc.add_argument("--strict", action="store_true", help="exit 1 when code is outside scope")
    wsc.set_defaults(fn=cmd_worktree)

    s = sub.add_parser("runtime", help="workflow state machine, checkpoints, recovery, and lifecycle hooks")
    rs = s.add_subparsers(dest="action", required=True)
    ri = rs.add_parser("init", help="initialize the runtime workflow")
    ri.add_argument("goal", nargs="?", default="")
    ri.add_argument("--new", action="store_true", help="archive the terminal workflow and create a new one")
    ri.add_argument("--json", action="store_true")
    ri.set_defaults(fn=cmd_runtime)
    rst = rs.add_parser("status", help="runtime workflow status")
    rst.add_argument("--json", action="store_true")
    rst.set_defaults(fn=cmd_runtime)
    rt = rs.add_parser("transition", help="change workflow state through an allowed transition")
    rt.add_argument("to_state", choices=["planning", "ready", "executing", "verifying", "blocked", "recovering", "completed", "failed"])
    rt.add_argument("--reason", default="")
    rt.add_argument("--task-id")
    rt.add_argument("--json", action="store_true")
    rt.set_defaults(fn=cmd_runtime)
    rc = rs.add_parser("checkpoint", help="create a workflow + Git state snapshot")
    rc.add_argument("--label", default="manual")
    rc.add_argument("--json", action="store_true")
    rc.set_defaults(fn=cmd_runtime)
    rr = rs.add_parser("recover", help="restore workflow metadata from a checkpoint; does not revert source")
    rr.add_argument("checkpoint_id", nargs="?")
    rr.add_argument("--json", action="store_true")
    rr.set_defaults(fn=cmd_runtime)
    rh = rs.add_parser("hook", help="dispatch a lifecycle hook and evaluate policy")
    rh.add_argument("event", choices=["session.start", "task.before", "task.after", "verification.before", "session.finish", "handover"])
    rh.add_argument("--payload-file", help="JSON object file; do not include secrets or full commands")
    rh.add_argument("--approval-id")
    rh.add_argument("--json", action="store_true", help="decision output for the runtime host")
    rh.set_defaults(fn=cmd_runtime)

    s = sub.add_parser("policy", help="view and evaluate autonomy/approval policy")
    ps = s.add_subparsers(dest="action", required=True)
    pshow = ps.add_parser("show", help="show POLICY.json")
    pshow.add_argument("--json", action="store_true")
    pshow.set_defaults(fn=cmd_policy)
    pcheck = ps.add_parser("check", help="evaluate whether an action may run")
    pcheck.add_argument("--category", required=True, choices=["read", "write", "command", "destructive", "deploy", "security", "policy_change", "gate_change"])
    pcheck.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    pcheck.add_argument("--target", default="", help="target label/path, not a full command or secret")
    pcheck.add_argument("--approval-id")
    pcheck.add_argument("--json", action="store_true")
    pcheck.set_defaults(fn=cmd_policy)
    papprove = ps.add_parser("approve", help="create a one-time approval bound to the workflow and scope")
    papprove.add_argument("--category", required=True, choices=["read", "write", "command", "destructive", "deploy", "security", "policy_change", "gate_change"])
    papprove.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="high")
    papprove.add_argument("--target", default="", help="approved target label/path")
    papprove.add_argument("--reason", required=True)
    papprove.add_argument("--json", action="store_true")
    papprove.set_defaults(fn=cmd_policy)

    s = sub.add_parser("team", help="multi-agent coordination through a shared task board, leases, handoff, and review")
    ts = s.add_subparsers(dest="action", required=True)
    ti = ts.add_parser("init", help="initialize the shared team board")
    ti.add_argument("--json", action="store_true")
    ti.set_defaults(fn=cmd_team)
    tst = ts.add_parser("status", help="view agents, tasks, leases, and summary")
    tst.add_argument("--json", action="store_true")
    tst.set_defaults(fn=cmd_team)
    treg = ts.add_parser("register", help="register an agent and capabilities")
    treg.add_argument("agent_id")
    treg.add_argument("--role", choices=["worker", "reviewer", "lead", "coordinator", "observer"], default="worker")
    treg.add_argument("--name")
    treg.add_argument("--capability", action="append", default=[], help="repeatable")
    treg.add_argument("--fingerprint", help="identity fingerprint (default: from the agent identity registry)")
    treg.add_argument("--json", action="store_true")
    treg.set_defaults(fn=cmd_team)
    tadd = ts.add_parser("add", help="create a task with dependencies, file scope, and capabilities")
    tadd.add_argument("task_id")
    tadd.add_argument("--title", required=True)
    tadd.add_argument("--description", default="")
    tadd.add_argument("--depends-on", action="append", default=[], help="task dependency; repeatable")
    tadd.add_argument("--files", action="append", nargs="+", default=[], help="file scope; repeatable")
    tadd.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    tadd.add_argument("--capability", action="append", default=[], help="required capability; repeatable")
    tadd.add_argument("--json", action="store_true")
    tadd.set_defaults(fn=cmd_team)
    tas = ts.add_parser("assign", help="assign a task as lead/coordinator")
    tas.add_argument("task_id")
    tas.add_argument("--agent", required=True)
    tas.add_argument("--by", required=True, help="ID agent lead/coordinator")
    tas.add_argument("--json", action="store_true")
    tas.set_defaults(fn=cmd_team)
    tc = ts.add_parser("claim", help="claim a task with an exclusive lease")
    tc.add_argument("task_id")
    tc.add_argument("--agent", required=True)
    tc.add_argument("--lease-seconds", type=int, default=900)
    tc.add_argument("--json", action="store_true")
    tc.set_defaults(fn=cmd_team)
    thb = ts.add_parser("heartbeat", help="renew the active lease")
    thb.add_argument("task_id")
    thb.add_argument("--agent", required=True)
    thb.add_argument("--lease-seconds", type=int, default=900)
    thb.add_argument("--json", action="store_true")
    thb.set_defaults(fn=cmd_team)
    trel = ts.add_parser("release", help="release a claimed task")
    trel.add_argument("task_id")
    trel.add_argument("--agent", required=True)
    trel.add_argument("--reason", required=True)
    trel.add_argument("--json", action="store_true")
    trel.set_defaults(fn=cmd_team)
    th = ts.add_parser("handoff", help="hand off a task to another agent")
    th.add_argument("task_id")
    th.add_argument("--from-agent", required=True)
    th.add_argument("--to-agent", required=True)
    th.add_argument("--note", required=True)
    th.add_argument("--json", action="store_true")
    th.set_defaults(fn=cmd_team)
    tsub = ts.add_parser("submit", help="submit task results with evidence for independent review")
    tsub.add_argument("task_id")
    tsub.add_argument("--agent", required=True)
    tsub.add_argument("--summary", required=True)
    tsub.add_argument("--evidence", action="append", required=True, help="evidence reference; repeatable")
    tsub.add_argument("--sign", action="store_true", help="sign the submission with the agent identity (Ed25519)")
    tsub.add_argument("--json", action="store_true")
    tsub.set_defaults(fn=cmd_team)
    trv = ts.add_parser("review", help="approve or request rework (reviewer differs from implementer)")
    trv.add_argument("task_id")
    trv.add_argument("--reviewer", required=True)
    trv.add_argument("--decision", choices=["approve", "rework"], required=True)
    trv.add_argument("--sign", action="store_true", help="sign the review with the reviewer identity (Ed25519)")
    trv.add_argument("--note", default="")
    trv.add_argument("--json", action="store_true")
    trv.set_defaults(fn=cmd_team)
    tb = ts.add_parser("block", help="block a task with a reason")
    tb.add_argument("task_id")
    tb.add_argument("--agent", required=True)
    tb.add_argument("--reason", required=True)
    tb.add_argument("--json", action="store_true")
    tb.set_defaults(fn=cmd_team)
    tub = ts.add_parser("unblock", help="reopen a task as lead/coordinator")
    tub.add_argument("task_id")
    tub.add_argument("--by", required=True)
    tub.add_argument("--reason", required=True)
    tub.add_argument("--json", action="store_true")
    tub.set_defaults(fn=cmd_team)
    tver = ts.add_parser("verify", help="verify submit/review signatures against agent identities")
    tver.add_argument("--json", action="store_true")
    tver.set_defaults(fn=cmd_team)
    tev = ts.add_parser("events", help="read the append-only coordination ledger")
    tev.add_argument("--limit", type=int, default=50)
    tev.add_argument("--json", action="store_true")
    tev.set_defaults(fn=cmd_team)
    tsi = ts.add_parser("storage", help="view or migrate the team storage backend")
    sis = tsi.add_subparsers(dest="storage_action", required=True)
    sshow = sis.add_parser("info", help="view the active backend")
    sshow.add_argument("--json", action="store_true")
    sshow.set_defaults(fn=lambda a: cmd_team_storage(a, "storage-info"))
    smig = sis.add_parser("migrate", help="migrate the board and event JSONL to local SQLite")
    smig.add_argument("--to", dest="to_backend", choices=["sqlite"], default="sqlite")
    smig.add_argument("--json", action="store_true")
    smig.set_defaults(fn=lambda a: cmd_team_storage(a, "storage-migrate"))
    sbak = sis.add_parser("backup", help="create a consistent SQLite database snapshot")
    sbak.add_argument("--output", required=True, help="destination backup file path")
    sbak.add_argument("--force", action="store_true", help="replace an existing backup file")
    sbak.add_argument("--json", action="store_true")
    sbak.set_defaults(fn=lambda a: cmd_team_storage(a, "storage-backup"))

    s = sub.add_parser("audit", help="classify project artifacts (read-only): required/recommended/not needed")
    s.add_argument("--json", action="store_true", help="JSON output for agents")
    s.add_argument("--strict", action="store_true", help="exit 1 when REQUIRED artifacts are missing")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("doctor", help="diagnose setup: config, placeholders, git, hooks, adapters, sessions")
    s.add_argument("--json", action="store_true", help="JSON output for agents")
    s.add_argument("--verify", action="store_true", help="also run the verify command")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("prune", help="prune old session history (dry-run by default)")
    s.add_argument("--keep", type=int, default=20, help="number of newest history entries to keep")
    s.add_argument("--days", type=int, default=90, help="only delete entries older than N days (0 = ignore age)")
    s.add_argument("--yes", action="store_true", help="actually delete; without this it is only a dry-run")
    s.add_argument("--json", action="store_true", help="output JSON")
    s.set_defaults(fn=cmd_prune)

    s = sub.add_parser("ci", help="create .github/workflows/ci.yml that runs pakem check")
    s.add_argument("--force", action="store_true", help="overwrite the existing workflow")
    s.set_defaults(fn=cmd_ci)

    s = sub.add_parser("upgrade", help="update CLI/flags/adapters without touching project documents")
    s.add_argument("--from", dest="from_path", default=None,
                   help="source scripts/pakem.py path (default: the running CLI)")
    s.add_argument("--dry-run", action="store_true", help="show the plan without writing")
    s.set_defaults(fn=cmd_upgrade)

    s = sub.add_parser("check", help="run gates without closing the session")
    s.add_argument("--skip-verify", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("finish", help="run all gates; pass = session closed")
    s.add_argument("--summary", default="")
    s.add_argument("--next")
    s.add_argument("--fixed-bug", action="store_true",
                   help="this work fixes a bug: a `pakem bug` entry is required in this session")
    s.add_argument("--strict", action="store_true",
                   help="fail if rules/CLI changed, verify is not pass, or REQUIRED audit gaps remain")
    s.set_defaults(fn=cmd_finish)

    s = sub.add_parser("bug", help="record a fixed bug in BUG-HISTORY.md")
    s.add_argument("title")
    s.add_argument("--symptom")
    s.add_argument("--cause")
    s.add_argument("--fix")
    s.add_argument("--prevent")
    s.set_defaults(fn=cmd_bug)

    s = sub.add_parser("adr", help="create a new ADR")
    s.add_argument("title")
    s.set_defaults(fn=cmd_adr)

    s = sub.add_parser("handover", help="create a single HANDOVER.md (status, access, remaining work)")
    s.add_argument("--force", action="store_true", help="overwrite the existing HANDOVER.md")
    s.add_argument("--stamp", action="store_true",
                   help="update the HEAD stamp after the HANDOVER.md contents are final")
    s.add_argument("--check", action="store_true",
                   help="check whether the stamp still matches HEAD (exit 1 when stale)")
    s.set_defaults(fn=cmd_handover)

    s = sub.add_parser("spec", help="create/approve SPEC.md (problem, non-goals, acceptance)")
    s.add_argument("title", nargs="?")
    s.add_argument("--approve", action="store_true", help="set Status: approved after placeholders are filled")
    s.add_argument("--force", action="store_true", help="overwrite the existing SPEC.md")
    s.set_defaults(fn=cmd_spec)

    s = sub.add_parser("plan", help="manage PLAN.md: small tasks + files + verify")
    s.add_argument("action", nargs="?", choices=["list", "add", "done", "drop"], default="list")
    s.add_argument("target", nargs="?", help="task text (add) or id T1 (done/drop)")
    s.add_argument("--files")
    s.add_argument("--verify")
    s.add_argument("--reason")
    s.add_argument("--no-verify", action="store_true",
                   help="mark done without running the task verify (requires --reason)")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("adapt", help="regenerate agent adapters")
    s.add_argument("--adapter", default="claude,codex,cursor")
    s.set_defaults(fn=cmd_adapt)

    s = sub.add_parser("hook", help="manage git hooks")
    s.add_argument("action", choices=["install"])
    s.add_argument("--skip-verify", action="store_true")
    s.set_defaults(fn=cmd_hook)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # `pakem report | head` is not a command failure: the pipe was closed first.
        try:
            sys.stdout.close()
        finally:
            sys.exit(0)
