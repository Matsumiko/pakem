"""Project dependency discovery and change-impact analysis for Pakem.

This module is intentionally standard-library-only and has no dependency on the
CLI. It is a first reference implementation: edges are static, best-effort
signals, not proof of runtime reachability.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections import defaultdict, deque
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".pakem", "node_modules", "vendor", ".venv",
    "venv", "__pycache__", "dist", "build", "target", ".next", ".nuxt",
    ".turbo", ".cache", "coverage", "site-packages", ".tox",
}
CODE_EXTS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue",
    ".svelte", ".go", ".java", ".kt", ".rb", ".rs", ".php", ".cs",
}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
TEST_RE = re.compile(
    r"(^test_.*\.py$|_test\.py$|_test\.go$|\.(test|spec)\.[cm]?[jt]sx?$|"
    r"Tests?\.(java|kt|cs)$|_spec\.rb$)", re.I
)
JS_IMPORT_RE = re.compile(
    r"(?:\bimport\s+(?:[^;\n]*?\s+from\s+)?|\bexport\s+[^;\n]*?\s+from\s+|"
    r"\brequire\s*\(|\bimport\s*\()\s*[\"']([^\"']+)[\"']",
    re.M,
)
GO_IMPORT_RE = re.compile(r"(?m)^\s*(?:import\s+)?\"([^\"]+)\"\s*$")
JAVA_IMPORT_RE = re.compile(r"(?m)^\s*import\s+(?:static\s+)?([\w.*]+)\s*;")

class NoChangesDetected(ValueError):
    """No diff to analyse; an empty result, not a broken repo."""


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_test(path: Path) -> bool:
    return any(part.lower() in TEST_DIRS for part in path.parts) or bool(TEST_RE.search(path.name))


def _language(path: Path) -> str:
    return {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte",
        ".go": "go", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
        ".rs": "rust", ".php": "php", ".cs": "csharp",
    }.get(path.suffix.lower(), "unknown")


def _iter_files(root: Path, include_tests: bool = True):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        base = Path(current)
        for name in sorted(files):
            path = base / name
            if path.suffix.lower() not in CODE_EXTS or (not include_tests and _is_test(path.relative_to(root))):
                continue
            try:
                if path.is_symlink() or path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            yield path


def _strip_jsonc(text: str) -> str:
    """Strip comments and trailing commas, because tsconfig is written as JSONC."""
    out: list[str] = []
    i, size = 0, len(text)
    in_string = False
    while i < size:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < size:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = size if end < 0 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = size if end < 0 else end + 2
            continue
        out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _extends_candidates(base: Path, spec: str):
    spec = spec.strip()
    if not spec:
        return
    if spec.startswith((".", "/")):
        target = (base / spec).resolve()
        yield target if target.suffix else target.with_suffix(".json")
        yield target / "tsconfig.json"
    else:
        package = base / "node_modules" / spec
        yield package / "tsconfig.json"
        if not spec.endswith(".json"):
            yield package


def _tsconfig_options(path: Path, seen: set[Path] | None = None) -> dict:
    """Merged compilerOptions: `extends` first, then the file itself."""
    seen = set() if seen is None else seen
    if path in seen or not path.is_file():
        return {}
    seen.add(path)
    try:
        data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8", errors="replace")))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    merged: dict = {}
    parents = data.get("extends")
    parents = parents if isinstance(parents, list) else [parents] if isinstance(parents, str) else []
    for parent in parents:
        for candidate in _extends_candidates(path.parent, str(parent)):
            if candidate.is_file():
                merged.update(_tsconfig_options(candidate, seen))
                break
    options = data.get("compilerOptions")
    if isinstance(options, dict):
        merged.update(options)
    return merged


def _js_config(root: Path) -> dict:
    """Aliases and baseUrl from tsconfig/jsconfig, when present.

    Without this, `@/lib/util` is read as a scoped npm package and every edge in
    the TypeScript project disappears without a trace.
    """
    for name in ("tsconfig.json", "jsconfig.json"):
        path = root / name
        if not path.is_file():
            continue
        options = _tsconfig_options(path)
        base_url = options.get("baseUrl")
        base = ((root / str(base_url)).resolve() if isinstance(base_url, str) else root)
        rules = []
        paths = options.get("paths")
        if isinstance(paths, dict):
            for prefix, targets in paths.items():
                if not isinstance(targets, list) or not prefix:
                    continue
                rules.append({"prefix": str(prefix),
                              "targets": [str(t) for t in targets if isinstance(t, str)],
                              "source": name})
        try:
            base_rel = base.relative_to(root).as_posix() or "."
        except ValueError:
            base_rel = "."
        return {"base": base, "base_rel": base_rel, "rules": rules, "source": name,
                "has_base_url": isinstance(base_url, str)}
    return {"base": root, "base_rel": ".", "rules": [], "source": None, "has_base_url": False}


def _js_candidates(root: Path, base: Path) -> list[str]:
    try:
        relbase = _relative(root, base)
    except ValueError:
        return []
    if relbase in {"", "."}:
        return []
    candidates = [relbase]
    if not Path(relbase).suffix:
        candidates.extend(relbase + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".json"))
        candidates.extend(f"{relbase}/index{ext}" for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"))
    elif Path(relbase).suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        stem = str(Path(relbase).with_suffix(""))
        candidates.extend(stem + ext for ext in (".ts", ".tsx", ".js", ".jsx"))
    return candidates


def _alias_targets(specifier: str, rule: dict) -> list[str] | None:
    prefix = rule["prefix"]
    if prefix.endswith("*"):
        head = prefix[:-1]
        if not specifier.startswith(head):
            return None
        rest = specifier[len(head):]
        return [target.replace("*", rest) for target in rule["targets"]]
    if specifier == prefix:
        return list(rule["targets"])
    return None


def _resolve_js(root: Path, importer: Path, specifier: str, file_index: set[str],
                config: dict | None = None) -> tuple[str | None, str | None]:
    """Return (path, None) when resolved, or (None, reason) when not.

    The reason is used by the caller to report missing imports instead of silently
    dropping them as before.
    """
    config = config or {"base": root, "rules": [], "has_base_url": False}
    if specifier.startswith("."):
        for candidate in _js_candidates(root, (importer.parent / specifier).resolve()):
            if candidate in file_index:
                return candidate, None
        return None, "relative"
    matched = [(rule, targets) for rule in config["rules"]
               for targets in [_alias_targets(specifier, rule)] if targets is not None]
    matched.sort(key=lambda item: -len(item[0]["prefix"]))
    for rule, targets in matched:
        for target in targets:
            for candidate in _js_candidates(root, (config["base"] / target).resolve()):
                if candidate in file_index:
                    return candidate, None
        return None, "alias"
    if config.get("has_base_url"):
        for candidate in _js_candidates(root, (config["base"] / specifier).resolve()):
            if candidate in file_index:
                return candidate, None
        # Report only when the first segment points at a directory/file in the repo;
        # everything else is a plain npm package and not the graph's business.
        head = specifier.split("/", 1)[0]
        if head and (root / head).exists():
            return None, "baseUrl"
    return None, None


def _python_imports(root: Path, path: Path, text: str, file_index: set[str]) -> set[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                _resolve_python_module(root, path, module, 0, file_index, found)
        elif isinstance(node, ast.ImportFrom):
            _resolve_python_module(root, path, node.module or "", node.level, file_index, found)
    return found


def _resolve_python_module(root: Path, importer: Path, module: str, level: int,
                           file_index: set[str], found: set[str]):
    parts = [p for p in module.split(".") if p]
    bases: list[Path] = []
    if level:
        base = importer.parent
        for _ in range(max(0, level - 1)):
            base = base.parent
        bases.append(base)
    else:
        bases.extend([root, root / "src", root / "app"])
    for base in bases:
        target = base.joinpath(*parts) if parts else base
        try:
            rel = _relative(root, target)
        except ValueError:
            continue
        candidates = [rel + ".py", rel + "/__init__.py"]
        if not parts:
            candidates = [_relative(root, importer.parent / "__init__.py")]
        for candidate in candidates:
            if candidate in file_index and candidate != _relative(root, importer):
                found.add(candidate)
                return


def _circular_dependencies(nodes: list[str], edges: list[tuple[str, str]],
                           limit: int = 20) -> tuple[list[list[str]], int]:
    """Strongly connected components (SCC) that contain a cycle.

    Iterative so large repos do not hit the recursion limit. Returns a list of
    components (each necessarily has a cycle) and the total count before truncation.
    """
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0
    for start in nodes:
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, position = work.pop()
            if position == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            neighbours = adjacency.get(node, [])
            descended = False
            for offset in range(position, len(neighbours)):
                neighbour = neighbours[offset]
                if neighbour not in index:
                    work.append((node, offset + 1))
                    work.append((neighbour, 0))
                    descended = True
                    break
                if neighbour in on_stack:
                    low[node] = min(low[node], index[neighbour])
            if descended:
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.append(popped)
                    if popped == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, ()):
                    components.append(sorted(component))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    components.sort(key=lambda comp: (-len(comp), comp))
    return components[:limit], len(components)


def build_dependency_graph(root: str | Path, include_tests: bool = True) -> dict:
    """Build a best-effort, local-file dependency graph for a project."""
    root = Path(root).resolve()
    paths = list(_iter_files(root, include_tests=include_tests))
    rels = sorted(_relative(root, p) for p in paths)
    index = set(rels)
    path_by_rel = {_relative(root, p): p for p in paths}
    module_name = None
    java_package_index: dict[str, list[str]] = defaultdict(list)
    for candidate_rel, candidate_path in path_by_rel.items():
        if candidate_path.suffix.lower() not in {".java", ".kt"}:
            continue
        try:
            candidate_text = candidate_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        package_match = re.search(r"(?m)^\s*package\s+([\w.]+)", candidate_text)
        if package_match:
            java_package_index[package_match.group(1)].append(candidate_rel)
    go_mod = root / "go.mod"
    if go_mod.is_file():
        try:
            go_mod_text = go_mod.read_text(encoding="utf-8", errors="replace")
        except OSError:
            go_mod_text = ""
        m = re.search(r"(?m)^module\s+([^\s]+)", go_mod_text)
        module_name = m.group(1) if m else None

    nodes = []
    edges = set()
    unresolved: list[dict] = []
    config = _js_config(root)
    for rel in rels:
        path = path_by_rel[rel]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        local: set[str] = set()
        suffix = path.suffix.lower()
        if suffix == ".py":
            local = _python_imports(root, path, text, index)
        elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"}:
            for spec in JS_IMPORT_RE.findall(text):
                resolved, reason = _resolve_js(root, path, spec, index, config)
                if resolved:
                    local.add(resolved)
                elif reason:
                    unresolved.append({"from": rel, "specifier": spec, "reason": reason})
        elif suffix == ".go" and module_name:
            for spec in GO_IMPORT_RE.findall(text):
                if spec.startswith(module_name + "/"):
                    tail = spec[len(module_name) + 1:]
                    # Go dependencies are package-level; connect to all local Go files in the package.
                    prefix = tail.rstrip("/") + "/"
                    matches = [item for item in rels if item.startswith(prefix) and item.endswith(".go")]
                    local.update(matches)
        elif suffix in {".java", ".kt"}:
            # Resolve the longest matching local package prefix without scanning
            # every package for each import.
            for imported in JAVA_IMPORT_RE.findall(text):
                parts = imported.split(".")
                for end in range(len(parts), 0, -1):
                    package_files = java_package_index.get(".".join(parts[:end]))
                    if package_files:
                        local.update(package_files)
                        break
        for target in local:
            if target != rel:
                edges.add((rel, target))
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0
        nodes.append({
            "path": rel,
            "language": _language(path),
            "is_test": _is_test(Path(rel)),
            "size_bytes": size_bytes,
            "imports": sorted(local),
        })

    edge_list = [{"from": src, "to": dst} for src, dst in sorted(edges)]
    ordered_unresolved = sorted(unresolved, key=lambda x: (x["from"], x["specifier"]))
    cycles, cycle_count = _circular_dependencies([node["path"] for node in nodes],
                                                 [(edge["from"], edge["to"]) for edge in edge_list])
    limitations = [
        "Static best-effort analysis; dynamic imports, reflection, generated code, and runtime wiring may be missed.",
        "Edges point from importer to imported local file.",
    ]
    if config["rules"]:
        limitations.append(f"Aliases read from {config['source']} "
                           f"({len(config['rules'])} rules, baseUrl: {config['base_rel']}).")
    elif config["source"]:
        limitations.append(f"{config['source']} exists but does not declare `paths`; "
                           "non-relative imports are resolved only via baseUrl.")
    return {
        "schema_version": "pakem.dependency-graph/v1",
        "root": ".",
        "node_count": len(nodes),
        "edge_count": len(edge_list),
        "nodes": nodes,
        "edges": edge_list,
        "unresolved_relative_imports": [item for item in ordered_unresolved if item["reason"] == "relative"],
        "unresolved_imports": ordered_unresolved,
        "aliases": [{"prefix": rule["prefix"], "targets": rule["targets"], "source": rule["source"]}
                    for rule in config["rules"]],
        "circular_dependencies": cycles,
        "circular_dependency_count": cycle_count,
        "limitations": limitations,
    }


def _git_changed_files(root: Path, base: str | None = None, staged: bool = False) -> list[str]:
    if base and staged:
        raise ValueError("--base and --staged cannot be used together")
    if base:
        # `git diff REF` (without a range) compares REF against the working tree:
        # commits since REF, uncommitted edits, and deleted files are all visible.
        # `REF...HEAD` previously saw only commits and hid the working tree.
        cmd = ["git", "diff", "--name-only", base]
    elif staged:
        cmd = ["git", "diff", "--cached", "--name-only"]
    else:
        cmd = ["git", "diff", "HEAD", "--name-only"]
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"failed to read Git changes: {exc}") from exc
    if proc.returncode:
        raise ValueError("project is not a Git repository or REF is not valid; pass --files explicitly")
    result = set(line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip())
    if not staged:
        # New files have no entry in any diff yet; add them from status.
        try:
            extra = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root,
                                   capture_output=True, text=True, timeout=15)
            if extra.returncode == 0:
                result.update(line.strip().replace("\\", "/") for line in extra.stdout.splitlines() if line.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    return sorted(result)


def _normalize_changed(root: Path, files: list[str]) -> list[str]:
    result = set()
    for value in files:
        raw = Path(value).expanduser()
        full = (raw if raw.is_absolute() else root / raw).resolve()
        try:
            rel = full.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"changed path is outside the project root: {value}") from exc
        if rel in {".", ".pakem"} or rel.startswith(".pakem/"):
            continue
        result.add(rel)
    return sorted(result)


def analyze_impact(root: str | Path, changed_files: list[str], graph: dict | None = None) -> dict:
    """Analyze reverse dependency reach and tests affected by changed files."""
    root = Path(root).resolve()
    changed = _normalize_changed(root, changed_files)
    graph = graph or build_dependency_graph(root)
    nodes = {n["path"]: n for n in graph.get("nodes", [])}
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges", []):
        reverse[edge["to"]].add(edge["from"])

    direct: set[str] = set()
    transitive: set[str] = set()
    queue = deque((item, 1) for item in changed if item in nodes)
    seen = set(changed)
    while queue:
        target, depth = queue.popleft()
        for dependent in sorted(reverse.get(target, ())):
            if dependent in seen:
                continue
            seen.add(dependent)
            (direct if depth == 1 else transitive).add(dependent)
            queue.append((dependent, depth + 1))

    impacted = direct | transitive
    affected_tests = {p for p in impacted if nodes.get(p, {}).get("is_test")}
    changed_tests = {p for p in changed if nodes.get(p, {}).get("is_test")}
    affected_tests.update(changed_tests)
    # A same-stem test is a useful fallback when imports are not explicit.
    changed_stems = {Path(p).stem.removeprefix("test_").removesuffix(".test").removesuffix(".spec") for p in changed}
    for rel, item in nodes.items():
        if item.get("is_test") and any(stem and stem in Path(rel).stem for stem in changed_stems):
            affected_tests.add(rel)

    sensitive = re.compile(r"(^|[/_.-])(auth|security|crypto|payment|billing|secret|permission|policy|migration|schema)([/_.-]|$)", re.I)
    critical_names = {name.lower() for name in {
        "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "composer.json", "Gemfile",
        "Dockerfile", "docker-compose.yml", "Makefile", "tox.ini", "pytest.ini",
    }}
    dependency_lock_names = {
        "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
        "requirements.txt", "requirements.lock", "poetry.lock", "uv.lock", "Pipfile.lock",
        "go.sum", "Cargo.lock", "composer.lock", "Gemfile.lock",
    }
    reasons = []
    score = 0
    for rel in changed:
        lower = rel.lower()
        if sensitive.search(lower):
            score += 4
            reasons.append(f"{rel}: path name indicates a sensitive area")
        if Path(lower).name in critical_names or lower.startswith(".github/workflows/"):
            score += 3
            reasons.append(f"{rel}: configuration/build/deployment file with broad impact")
        if Path(lower).name in {name.lower() for name in dependency_lock_names}:
            score += 2
            reasons.append(f"{rel}: dependency/lockfile change needs compatibility verification")
        if Path(lower).name == ".env" or Path(lower).name.startswith(".env.") or lower.endswith((".pem", ".key")):
            score += 4
            reasons.append(f"{rel}: environment file or key material requires security review")
        if lower.endswith((".sql",)) or "/migrations/" in lower:
            score += 3
            reasons.append(f"{rel}: database/migration change requires focused review")
    if len(impacted) >= 10:
        score += 2
        reasons.append(f"{len(impacted)} dependent files reachable from the change")
    if len(changed) >= 8:
        score += 1
        reasons.append("changed file count is relatively large")
    unresolved = graph.get("unresolved_imports", graph.get("unresolved_relative_imports", [])) or []
    cycles = graph.get("circular_dependencies", []) or []
    changed_in_cycle = [rel for rel in changed if any(rel in component for component in cycles)]
    if changed_in_cycle:
        reasons.append("changed files are in a dependency cycle: " + ", ".join(changed_in_cycle[:3]))
    level = "high" if score >= 4 else "medium" if score >= 2 else "low"

    recommendations = ["Run the relevant tests before full verification."]
    if affected_tests:
        recommendations.insert(0, "Prioritize tests: " + ", ".join(sorted(affected_tests)))
    else:
        recommendations.insert(0, "No related tests detected; decide the appropriate manual verification.")
    if level == "high":
        recommendations.append("Request additional review for affected security, data, or configuration.")
    if impacted:
        recommendations.append("Review compatibility on direct and transitive dependents.")
    if unresolved:
        recommendations.append(
            f"Graph has {len(unresolved)} unresolved imports (alias/baseUrl/relative); "
            "dependents may go undetected — check tsconfig/jsconfig or verify manually.")

    return {
        "schema_version": "pakem.impact-analysis/v1",
        "changed_files": changed,
        "direct_dependents": sorted(direct),
        "transitive_dependents": sorted(transitive),
        "affected_tests": sorted(affected_tests),
        "risk": {"level": level, "score": score, "reasons": reasons},
        "summary": {
            "changed_count": len(changed), "direct_dependent_count": len(direct),
            "transitive_dependent_count": len(transitive), "affected_test_count": len(affected_tests),
        },
        "graph_health": {
            "alias_rules": len(graph.get("aliases", []) or []),
            "unresolved_imports": len(unresolved),
            "circular_dependencies": int(graph.get("circular_dependency_count") or len(cycles)),
            "complete": not unresolved,
        },
        "recommendations": recommendations,
        "analysis_limits": [
            "Impact is inferred from static local imports and filename heuristics; verify the result against actual architecture.",
            "A missing edge does not prove that a file is unaffected.",
        ],
    }


def changed_files_for_impact(root: str | Path, files: list[str] | None = None,
                             base: str | None = None, staged: bool = False) -> list[str]:
    root = Path(root).resolve()
    if files and (base or staged):
        raise ValueError("use exactly one of --files, --base, or --staged")
    if files:
        return _normalize_changed(root, files)
    detected = _git_changed_files(root, base=base, staged=staged)
    if not detected:
        raise NoChangesDetected("no changes detected; use --files FILE... to specify files")
    return _normalize_changed(root, detected)


def render_graph_text(graph: dict) -> str:
    lines = [f"Dependency Graph: {graph['node_count']} nodes, {graph['edge_count']} edges", ""]
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in graph.get("edges", []):
        incoming[edge["to"]].append(edge["from"])
    for node in graph.get("nodes", []):
        suffix = " [test]" if node.get("is_test") else ""
        lines.append(f"{node['path']} ({node['language']}){suffix}")
        consumers = sorted(incoming.get(node["path"], []))
        if consumers:
            lines.append("  used by: " + ", ".join(consumers))
    aliases = graph.get("aliases", [])
    if aliases:
        lines.extend(["", f"Aliases ({len(aliases)}):"])
        lines.extend(f"  {rule['prefix']} -> {', '.join(rule['targets'])}" for rule in aliases[:10])
    unresolved = graph.get("unresolved_imports", graph.get("unresolved_relative_imports", []))
    if unresolved:
        lines.extend(["", f"Unresolved imports: {len(unresolved)}"])
        lines.extend(f"  {x['from']} -> {x['specifier']} ({x.get('reason', 'relative')})"
                     for x in unresolved[:20])
    cycles = graph.get("circular_dependencies", [])
    if cycles:
        total = graph.get("circular_dependency_count", len(cycles))
        lines.extend(["", f"Circular dependencies: {total}"])
        for component in cycles[:5]:
            shown = ", ".join(component[:6]) + (" ..." if len(component) > 6 else "")
            lines.append(f"  {shown}")
    lines.extend(["", "Note: static best-effort graph; validate important paths manually."])
    return "\n".join(lines)


def render_impact_text(result: dict) -> str:
    lines = [f"Impact Analysis: {result['risk']['level'].upper()} risk (score {result['risk']['score']})", ""]
    for label, key in (("Changed", "changed_files"), ("Direct dependents", "direct_dependents"),
                       ("Transitive dependents", "transitive_dependents"), ("Affected tests", "affected_tests")):
        lines.append(f"{label} ({len(result[key])}):")
        lines.extend("  - " + item for item in result[key])
        if not result[key]:
            lines.append("  - (none detected)")
    if result["risk"]["reasons"]:
        lines.extend(["", "Risk signals:"])
        lines.extend("  - " + reason for reason in result["risk"]["reasons"])
    lines.extend(["", "Recommendations:"])
    lines.extend("  - " + item for item in result["recommendations"])
    health = result.get("graph_health")
    if health:
        state = "complete" if health.get("complete") else f"{health.get('unresolved_imports')} unresolved imports"
        lines.extend(["", f"Graph: {state}, {health.get('alias_rules', 0)} aliases, "
                          f"{health.get('circular_dependencies', 0)} cycles."])
    lines.extend(["", "Static analysis is advisory; a missing edge does not prove no impact."])
    return "\n".join(lines)
