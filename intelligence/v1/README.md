# Pakem Intelligence v1

The first language-independent output contracts for source dependency discovery and change-impact analysis.

## Dependency graph

`pakem graph --json` emits `pakem.dependency-graph/v1`. Each edge points from the importer (`from`) to the imported local file (`to`). The scanner currently resolves common Python imports, relative JavaScript/TypeScript/Vue/Svelte imports, Go packages declared under the local `go.mod` module path, and Java/Kotlin package imports.

The graph is static and best-effort. Dynamic imports, reflection, dependency injection, generated sources, framework routing, path aliases, runtime configuration, and package-level semantics may not be fully represented. An absent edge is not proof that two files are unrelated.

## Impact analysis

`pakem impact --files FILE... --json` emits `pakem.impact-analysis/v1`. `--base REF` selects `REF...HEAD`; `--staged` selects the Git index; with no selector Pakem inspects the working tree diff plus untracked files. The analysis reports direct and transitive reverse dependents, likely affected tests, risk signals, and suggested verification.

Risk is a heuristic prioritization signal, not a security rating. `--strict` returns exit code 1 for a HIGH signal; it does not change project policy or run tests. Use the result to decide what to inspect, then run the project's actual verification commands and review the changes.

## Runtime and safety boundary

The scanner is read-only unless `graph --output PATH` is explicitly supplied. It does not execute source code, tests, package managers, build scripts, or network requests. Absolute paths outside the project root are rejected for impact input. The JSON contracts are independent of the CLI implementation and can be consumed by other runtimes.
