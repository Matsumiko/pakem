"""Pakem 1.2.0 — rekonsiliasi artefak (scope + acceptance) dan identitas di team board."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pakem.py"
sys.path.insert(0, str(ROOT / "scripts"))

from pakem_core import reconcile as rec  # noqa: E402

HAS_GIT = bool(shutil.which("git"))
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

NEEDS_GIT = unittest.skipUnless(HAS_GIT, "git tidak tersedia")
NEEDS_CRYPTO = unittest.skipUnless(HAS_CRYPTO, "cryptography tidak terpasang")
NEEDS_JSONSCHEMA = unittest.skipUnless(HAS_JSONSCHEMA, "jsonschema tidak terpasang")


def run(cwd: Path, *args: str, timeout: int = 60):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=timeout)


def fill(tmp: Path) -> None:
    for f in (tmp / ".pakem").glob("*.md"):
        t = f.read_text(encoding="utf-8")
        t = re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "terisi", t)
        if f.name == "PROJECT.md":
            t = re.sub(r"(?m)^verify:.*$", 'verify: python3 -c "print(1)"', t)
        f.write_text(t, encoding="utf-8")


def pakem_cli_module():
    """Muat CLI sebagai modul untuk menguji gate tanpa subprocess."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("pakem_cli_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.test", "-c", "user.name=test", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


class ReconcileUnit(unittest.TestCase):
    """Fungsi murni: tanpa repo, tanpa git."""

    def test_matches_exact_dir_and_glob(self):
        self.assertTrue(rec.matches("src/a.py", "src/a.py"))
        self.assertTrue(rec.matches("src/a.py", "src"))
        self.assertTrue(rec.matches("src/deep/a.py", "src/"))
        self.assertTrue(rec.matches("src/a.py", "src/*.py"))
        self.assertFalse(rec.matches("srcx/a.py", "src"))
        self.assertFalse(rec.matches("src/a.py", "tests"))

    def test_code_and_non_code_split(self):
        result = rec.reconcile(["src/a.py", "README.md", "package.json"],
                               [{"taskId": "T1", "done": False, "files": ["src/a.py"]}], [])
        self.assertEqual(result["in_scope"], ["src/a.py"])
        self.assertEqual(result["code_out_of_scope"], [])
        self.assertEqual(sorted(result["out_of_scope"]), ["README.md", "package.json"])
        self.assertTrue(result["ok"])

        code_result = rec.reconcile(["src/a.py", "src/b.py"],
                                    [{"taskId": "T1", "done": False, "files": ["src/a.py"]}], [])
        self.assertEqual(code_result["code_out_of_scope"], ["src/b.py"])
        self.assertFalse(code_result["ok"])

    def test_acceptance_gate_on_unchecked(self):
        acceptance = [{"text": "satu", "checked": True}, {"text": "dua", "checked": False}]
        result = rec.reconcile([], [], acceptance)
        self.assertEqual(result["acceptance"]["unchecked"], ["dua"])
        self.assertFalse(result["ok"])

    def test_no_plan_means_everything_out_of_scope(self):
        result = rec.reconcile(["src/a.py"], [], [])
        self.assertEqual(result["declared_scope"], [])
        self.assertEqual(result["out_of_scope"], ["src/a.py"])
        self.assertFalse(result["ok"])


@NEEDS_GIT
class ReconcileCLI(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "a.py").write_text("def a():\n    return 1\n")
        (self.tmp / "src" / "b.py").write_text("def b():\n    return 2\n")
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n")
        (self.tmp / "README.md").write_text("# x\n")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        self.assertEqual(run(self.tmp, "start", "fitur a").returncode, 0)
        self.assertEqual(run(self.tmp, "spec", "fitur a").returncode, 0)
        spec = self.tmp / ".pakem" / "SPEC.md"
        text = re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "terisi", spec.read_text())
        text = re.sub(r"(?m)^- \[ \] terisi$", "- [x] satu\n- [ ] dua", text, count=1)
        spec.write_text(text)
        self.assertEqual(run(self.tmp, "spec", "--approve").returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "add", "tulis a", "--files", "src/a.py",
                             "--verify", 'python3 -c "print(1)"').returncode, 0)

    def tearDown(self):
        self._td.cleanup()

    def test_out_of_scope_code_and_open_acceptance_fail(self):
        (self.tmp / "src" / "a.py").write_text("def a():\n    return 10\n")
        (self.tmp / "src" / "b.py").write_text("def b():\n    return 20\n")

        out = run(self.tmp, "reconcile", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["in_scope"], ["src/a.py"])
        self.assertEqual(data["code_out_of_scope"], ["src/b.py"])
        self.assertEqual(data["acceptance"]["unchecked"], ["dua"])
        self.assertFalse(data["ok"])

        self.assertEqual(run(self.tmp, "reconcile", "--strict").returncode, 1)

        check = run(self.tmp, "check")
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("[FAIL] scope:", check.stdout)
        self.assertIn("src/b.py", check.stdout)
        # approval cukup untuk `check`; acceptance baru ditagih saat `finish`
        self.assertIn("[PASS] spec:", check.stdout)
        self.assertNotIn("acceptance", check.stdout)

        finish = run(self.tmp, "finish", "--summary",
                     "mengerjakan fitur a dengan bukti reconcile dan check")
        self.assertNotEqual(finish.returncode, 0)
        self.assertIn("[FAIL] acceptance:", finish.stdout)
        self.assertIn("dua", finish.stdout)

    def test_scope_and_acceptance_clean_after_declaring_work(self):
        (self.tmp / "src" / "a.py").write_text("def a():\n    return 10\n")
        (self.tmp / "src" / "b.py").write_text("def b():\n    return 20\n")
        spec = self.tmp / ".pakem" / "SPEC.md"
        spec.write_text(spec.read_text().replace("- [ ] dua", "- [x] dua"))
        run(self.tmp, "plan", "add", "tulis b", "--files", "src/b.py",
            "--verify", 'python3 -c "print(1)"')
        run(self.tmp, "plan", "done", "T1")
        run(self.tmp, "plan", "done", "T2")

        data = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertEqual(data["out_of_scope"], [])
        self.assertTrue(data["ok"])
        self.assertEqual(run(self.tmp, "reconcile", "--strict").returncode, 0)

        check = run(self.tmp, "check")
        self.assertIn("[PASS] scope:", check.stdout)
        self.assertIn("[PASS] spec:", check.stdout)
        finish = run(self.tmp, "finish", "--summary",
                     "fitur a selesai; scope plan dan acceptance sudah selaras")
        self.assertIn("[PASS] acceptance:", finish.stdout)
        self.assertEqual(finish.returncode, 0, finish.stdout + finish.stderr)

    def test_non_code_outside_scope_does_not_fail(self):
        (self.tmp / "NOTES.md").write_text("catatan\n")
        data = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertEqual(data["out_of_scope"], ["NOTES.md"])
        self.assertEqual(data["code_out_of_scope"], [])
        check = run(self.tmp, "check")
        self.assertIn("[PASS] scope:", check.stdout)
        self.assertIn("non-code files outside scope", check.stdout)

    def test_committed_out_of_scope_code_fails_gate(self):
        """Commit dulu bukan cara melewati gate: patokannya HEAD saat sesi mulai."""
        (self.tmp / "src" / "b.py").write_text("def b():\n    return 20\n")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "kerja di luar scope")

        data = json.loads(run(self.tmp, "reconcile", "--base", "HEAD~1", "--json").stdout)
        self.assertEqual(data["code_out_of_scope"], ["src/b.py"])
        check = run(self.tmp, "check")
        self.assertIn("[FAIL] scope:", check.stdout)
        self.assertIn("src/b.py", check.stdout)

    def test_committed_in_scope_code_passes_gate(self):
        (self.tmp / "src" / "a.py").write_text("def a():\n    return 11\n")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "kerja T1 dalam scope")
        check = run(self.tmp, "check")
        self.assertIn("[PASS] scope:", check.stdout)
        self.assertIn("within task scope", check.stdout)

    def test_deleted_file_is_counted(self):
        """File yang dihapus juga perubahan kode, bukan ketiadaan perubahan."""
        (self.tmp / "src" / "b.py").unlink()

        data = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertIn("src/b.py", data["changed_files"])
        self.assertEqual(data["code_out_of_scope"], ["src/b.py"])
        check = run(self.tmp, "check")
        self.assertIn("[FAIL] scope:", check.stdout)
        self.assertIn("src/b.py", check.stdout)

    def test_untracked_new_file_outside_scope_fails_gate(self):
        """Diff terhadap HEAD saat start tidak memuat file baru; status yang menambalnya."""
        (self.tmp / "src" / "c.py").write_text("def c():\n    return 3\n")
        check = run(self.tmp, "check")
        self.assertIn("[FAIL] scope:", check.stdout)
        self.assertIn("src/c.py", check.stdout)

    def test_glob_scope_covers_new_file(self):
        run(self.tmp, "plan", "add", "semua src", "--files", "src/*.py",
            "--verify", 'python3 -c "print(1)"')
        (self.tmp / "src" / "c.py").write_text("def c():\n    return 3\n")
        data = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertIn("src/c.py", data["in_scope"])
        self.assertEqual(data["code_out_of_scope"], [])

    @NEEDS_JSONSCHEMA
    def test_json_output_matches_schema(self):
        data = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        schema = json.loads((ROOT / "intelligence" / "v1" / "reconciliation.schema.json").read_text())
        jsonschema.validate(data, schema)


@NEEDS_CRYPTO
@NEEDS_GIT
class TeamSignatures(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        self.assertEqual(run(self.tmp, "team", "init").returncode, 0)
        for agent in ("impl1", "rev1"):
            self.assertEqual(run(self.tmp, "identity", "create", agent).returncode, 0)
        self.assertEqual(run(self.tmp, "team", "register", "impl1", "--name", "Implementer").returncode, 0)
        self.assertEqual(run(self.tmp, "team", "register", "rev1", "--role", "reviewer").returncode, 0)
        self.assertEqual(run(self.tmp, "team", "add", "T1", "--title", "tulis parser",
                             "--files", "src/a.py").returncode, 0)
        self.assertEqual(run(self.tmp, "team", "claim", "T1", "--agent", "impl1").returncode, 0)

    def tearDown(self):
        self._td.cleanup()

    def _board_path(self) -> Path:
        return self.tmp / ".pakem" / "team" / "board.json"

    def _submit(self, *extra: str):
        return run(self.tmp, "team", "submit", "T1", "--agent", "impl1",
                   "--summary", "parser selesai", "--evidence", "tests/test_a.py:12", *extra)

    def _review(self, *extra: str):
        return run(self.tmp, "team", "review", "T1", "--reviewer", "rev1",
                   "--decision", "approve", "--note", "ok", *extra)

    def test_register_binds_identity_fingerprint(self):
        status = json.loads(run(self.tmp, "team", "status", "--json").stdout)
        agents = status["agents"] if isinstance(status["agents"], list) else list(status["agents"].values())
        impl = [a for a in agents if a.get("agentId") == "impl1"][0]
        registry = json.loads((self.tmp / ".pakem" / "identity" / "registry.json").read_text())
        self.assertEqual(impl["fingerprint"], registry["agents"]["impl1"]["fingerprint"])

    def test_signed_submission_and_review_verify(self):
        submitted = self._submit("--sign")
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        self.assertIn("signed with Ed25519", submitted.stdout)
        reviewed = self._review("--sign")
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)

        verify = run(self.tmp, "team", "verify", "--json")
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        data = json.loads(verify.stdout)
        self.assertEqual(data["checked"], 2)
        self.assertEqual(data["valid"], 2)
        self.assertEqual(data["invalid"], [])
        self.assertEqual(data["unsignedSubmissions"], 0)
        self.assertEqual(data["unsignedReviews"], 0)

    def test_tampered_board_detected(self):
        self._submit("--sign")
        self._review("--sign")
        board = json.loads(self._board_path().read_text())
        tasks = board["tasks"] if isinstance(board["tasks"], dict) else {t["taskId"]: t for t in board["tasks"]}
        tasks["T1"]["submission"]["summary"] = "parser selesai (diubah setelah ditandatangani)"
        self._board_path().write_text(json.dumps(board))

        verify = run(self.tmp, "team", "verify", "--json")
        self.assertEqual(verify.returncode, 1)
        data = json.loads(verify.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["invalid"][0]["kind"], "submission")
        self.assertIn("differs", data["invalid"][0]["reason"])

    def test_revoked_identity_invalidates_signature(self):
        self._submit("--sign")
        self.assertEqual(run(self.tmp, "identity", "revoke", "impl1").returncode, 0)
        verify = run(self.tmp, "team", "verify", "--json")
        self.assertEqual(verify.returncode, 1)
        data = json.loads(verify.stdout)
        self.assertIn("revoked", data["invalid"][0]["reason"])

    def test_unsigned_submission_is_reported_not_failed(self):
        self.assertEqual(self._submit().returncode, 0)
        verify = run(self.tmp, "team", "verify", "--json")
        self.assertEqual(verify.returncode, 0)
        data = json.loads(verify.stdout)
        self.assertEqual(data["checked"], 0)
        self.assertEqual(data["unsignedSubmissions"], 1)

    def test_sign_without_identity_fails_clearly(self):
        self.assertEqual(run(self.tmp, "team", "register", "ghost", "--role", "worker").returncode, 0)
        self.assertEqual(run(self.tmp, "team", "add", "T2", "--title", "lain",
                             "--files", "src/b.py").returncode, 0)
        run(self.tmp, "team", "claim", "T2", "--agent", "ghost")
        out = run(self.tmp, "team", "submit", "T2", "--agent", "ghost",
                  "--summary", "x", "--evidence", "e", "--sign")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("has no active identity", out.stdout + out.stderr)


@NEEDS_GIT
class ReconcileEdgeCases(unittest.TestCase):
    """Repo bersih dan repo tanpa commit bukan error yang sama."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)

    def tearDown(self):
        self._td.cleanup()

    def test_repo_without_commit_is_explained(self):
        out = run(self.tmp, "reconcile")
        self.assertEqual(out.returncode, 2)
        self.assertIn("repo has no commits", out.stdout + out.stderr)

    def test_clean_repo_reports_aligned(self):
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        out = run(self.tmp, "reconcile", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["changed_files"], [])
        self.assertTrue(data["ok"])


@NEEDS_GIT
class WorktreeScope(unittest.TestCase):
    """Diff sebuah worktree dibandingkan dengan scope task-nya sendiri."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
        (self.tmp / "src" / "b.py").write_text("def b(): return 2\n", encoding="utf-8")
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# w\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        added = run(self.tmp, "plan", "add", "T1", "--files", "src/a.py",
                    "--verify", 'python3 -c "print(1)"')
        self.assertEqual(added.returncode, 0, added.stderr)
        created = run(self.tmp, "worktree", "create", "T1", "--agent", "solo", "--json")
        self.assertEqual(created.returncode, 0, created.stderr)
        self.wt = self.tmp / ".pakem" / "worktrees" / "T1--solo"

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.tmp, capture_output=True)
        self._td.cleanup()

    def _scope(self, *extra):
        return run(self.tmp, "worktree", "scope", "T1--solo", *extra)

    def test_change_inside_scope_is_aligned(self):
        (self.wt / "src" / "a.py").write_text("def a(): return 10\n", encoding="utf-8")
        out = self._scope("--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["in_scope"], ["src/a.py"])
        self.assertTrue(data["ok"])

    def test_change_outside_scope_fails_gate(self):
        (self.wt / "src" / "b.py").write_text("def b(): return 20\n", encoding="utf-8")
        out = self._scope("--strict")
        self.assertEqual(out.returncode, 1)
        self.assertIn("src/b.py", out.stdout)
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[FAIL] worktree:", check.stdout)
        self.assertIn("src/b.py", check.stdout)

    def test_committed_work_is_still_counted(self):
        (self.wt / "src" / "b.py").write_text("def b(): return 20\n", encoding="utf-8")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "kerja T1")
        data = json.loads(self._scope("--json").stdout)
        self.assertIn("src/b.py", data["code_out_of_scope"])

    def test_untracked_file_is_counted(self):
        (self.wt / "src" / "baru.py").write_text("x = 1\n", encoding="utf-8")
        data = json.loads(self._scope("--json").stdout)
        self.assertIn("src/baru.py", data["code_out_of_scope"])

    def test_inside_worktree_uses_main_state(self):
        (self.wt / "src" / "b.py").write_text("def b(): return 20\n", encoding="utf-8")
        inside = subprocess.run([sys.executable, str(SCRIPT), "worktree", "scope",
                                 "T1--solo", "--json"], cwd=self.wt,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(inside.returncode, 0, inside.stderr)
        data = json.loads(inside.stdout)
        self.assertIn("src/b.py", data["code_out_of_scope"])

    def test_unknown_worktree_is_explained(self):
        out = run(self.tmp, "worktree", "scope", "T1--hantu")
        self.assertEqual(out.returncode, 2)
        self.assertIn("not found", out.stdout + out.stderr)
        self.assertIn("T1--solo", out.stdout + out.stderr)

    def test_board_scope_counts_without_plan_entry(self):
        (self.tmp / "src" / "c.py").write_text("def c(): return 3\n", encoding="utf-8")
        before = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertIn("src/c.py", before["code_out_of_scope"])
        self.assertEqual(run(self.tmp, "team", "init").returncode, 0)
        added = run(self.tmp, "team", "add", "T7", "--title", "API", "--files", "src/c.py")
        self.assertEqual(added.returncode, 0, added.stderr)
        after = json.loads(run(self.tmp, "reconcile", "--json").stdout)
        self.assertIn("src/c.py", after["in_scope"])
        self.assertEqual(after["code_out_of_scope"], [])


@NEEDS_GIT
class IntelligencePaths(unittest.TestCase):
    """Graph harus membaca alias tsconfig, bukan membuang import non-relatif."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        (self.tmp / "src" / "lib").mkdir(parents=True)
        (self.tmp / "src" / "app").mkdir(parents=True)

    def tearDown(self):
        self._td.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _graph(self) -> dict:
        out = run(self.tmp, "graph", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def _impact(self, rel: str) -> dict:
        out = run(self.tmp, "impact", "--files", rel, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_tsconfig_alias_resolves_edge(self):
        self._write("tsconfig.json", json.dumps({
            "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}))
        self._write("src/lib/util.ts", "export const u = 1;\n")
        self._write("src/app/main.ts", 'import { u } from "@/lib/util";\n')
        graph = self._graph()
        self.assertEqual(graph["aliases"], [{"prefix": "@/*", "targets": ["src/*"],
                                             "source": "tsconfig.json"}])
        self.assertIn({"from": "src/app/main.ts", "to": "src/lib/util.ts"}, graph["edges"])
        self.assertEqual(graph["unresolved_imports"], [])
        impact = self._impact("src/lib/util.ts")
        self.assertEqual(impact["direct_dependents"], ["src/app/main.ts"])
        self.assertTrue(impact["graph_health"]["complete"])

    def test_alias_target_missing_is_reported(self):
        self._write("tsconfig.json", json.dumps({"compilerOptions": {"paths": {"@/*": ["src/*"]}}}))
        self._write("src/lib/util.ts", "export const u = 1;\n")
        self._write("src/app/main.ts", 'import { x } from "@/lib/hilang";\n')
        graph = self._graph()
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["unresolved_imports"],
                         [{"from": "src/app/main.ts", "specifier": "@/lib/hilang", "reason": "alias"}])
        impact = self._impact("src/lib/util.ts")
        self.assertFalse(impact["graph_health"]["complete"])
        self.assertTrue(any("unresolved imports" in item for item in impact["recommendations"]))

    def test_extends_chain_and_comments_are_followed(self):
        self._write("tsconfig.base.json",
                    '{\n  // komentar JSONC\n  "compilerOptions": {"paths": {"@/*": ["src/*"],},},\n}\n')
        self._write("tsconfig.json", json.dumps({"extends": "./tsconfig.base.json"}))
        self._write("src/lib/util.ts", "export const u = 1;\n")
        self._write("src/app/main.ts", 'import { u } from "@/lib/util";\n')
        graph = self._graph()
        self.assertIn({"from": "src/app/main.ts", "to": "src/lib/util.ts"}, graph["edges"])

    def test_cycle_is_reported_and_flagged_in_impact(self):
        self._write("src/lib/a.ts", 'import { b } from "./b";\nexport const a = b;\n')
        self._write("src/lib/b.ts", 'import { a } from "./a";\nexport const b = a;\n')
        graph = self._graph()
        self.assertEqual(graph["circular_dependencies"], [["src/lib/a.ts", "src/lib/b.ts"]])
        self.assertEqual(graph["circular_dependency_count"], 1)
        impact = self._impact("src/lib/a.ts")
        self.assertTrue(any("dependency cycle" in reason for reason in impact["risk"]["reasons"]))

    def test_external_packages_are_not_reported(self):
        self._write("tsconfig.json", json.dumps({"compilerOptions": {"baseUrl": "."}}))
        self._write("src/app/main.ts", 'import React from "react";\n')
        graph = self._graph()
        self.assertEqual(graph["unresolved_imports"], [])


@NEEDS_GIT
class TaskEvidence(unittest.TestCase):
    """`plan done` harus menjalankan verify task, bukan cuma mencentang kotak."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# t\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")

    def tearDown(self):
        self._td.cleanup()

    def _add(self, verify: str, files: str = "src/a.py"):
        added = run(self.tmp, "plan", "add", "tulis a", "--files", files, "--verify", verify)
        self.assertEqual(added.returncode, 0, added.stderr)

    def _evidence(self) -> dict:
        path = self.tmp / ".pakem" / "verify" / "tasks.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def test_plan_done_runs_verify_and_records_proof(self):
        self._add('python3 -c "print(7)"')
        done = run(self.tmp, "plan", "done", "T1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("[EVIDENCE] T1: pass exit=0", done.stdout)
        entry = self._evidence()["tasks"]["T1"]
        self.assertEqual(entry["status"], "pass")
        self.assertEqual(entry["exit"], 0)
        self.assertIn("src/a.py", entry["files"])
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[PASS] task-verify: 1 task proven", check.stdout)

    def test_failing_verify_keeps_task_open(self):
        self._add('python3 -c "import sys; sys.exit(3)"')
        done = run(self.tmp, "plan", "done", "T1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("verify failed", done.stdout + done.stderr)
        self.assertIn("[ ] T1", run(self.tmp, "plan", "list").stdout)
        self.assertEqual(self._evidence()["tasks"]["T1"]["status"], "fail")

    def test_stale_evidence_fails_gate_until_refreshed(self):
        self._add('python3 -c "print(1)"')
        self.assertEqual(run(self.tmp, "plan", "done", "T1").returncode, 0)
        (self.tmp / "src" / "a.py").write_text("def a(): return 2\n", encoding="utf-8")
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[FAIL] task-verify:", check.stdout)
        self.assertIn("stale", check.stdout)
        refreshed = run(self.tmp, "plan", "done", "T1")
        self.assertEqual(refreshed.returncode, 0, refreshed.stdout + refreshed.stderr)
        self.assertIn("[PASS] task-verify: 1 task proven",
                      run(self.tmp, "check", "--skip-verify").stdout)

    def test_dropped_task_needs_no_proof(self):
        self._add('python3 -c "print(1)"')
        self.assertEqual(run(self.tmp, "plan", "add", "buat b", "--files", "src/b.py",
                             "--verify", 'python3 -c "print(1)"').returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "done", "T1").returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "drop", "T2", "--reason", "tidak perlu").returncode, 0)
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[PASS] task-verify: 1 task proven", check.stdout)
        self.assertIn("dropped", check.stdout)

    def test_waiver_needs_reason_then_passes_with_note(self):
        self._add('python3 -c "import sys; sys.exit(1)"')
        refused = run(self.tmp, "plan", "done", "T1", "--no-verify")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--reason", refused.stdout + refused.stderr)
        waived = run(self.tmp, "plan", "done", "T1", "--no-verify",
                     "--reason", "butuh service eksternal")
        self.assertEqual(waived.returncode, 0, waived.stdout + waived.stderr)
        self.assertIn("[WAIVER] T1", waived.stdout)
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("waived: T1: butuh service eksternal", check.stdout)


@NEEDS_GIT
class LedgerIntegrity(unittest.TestCase):
    """Ledger event dirantai hash; sunting, hapus, dan tulis ulang harus ketahuan."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# l\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        self.assertEqual(run(self.tmp, "start", "kerja").returncode, 0)
        self.assertEqual(run(self.tmp, "step", "satu", "--next", "dua").returncode, 0)

    def tearDown(self):
        self._td.cleanup()

    def _ledger(self) -> Path:
        return sorted((self.tmp / ".pakem" / "events").glob("*.jsonl"))[-1]

    def _records(self) -> list[dict]:
        return [json.loads(line) for line in self._ledger().read_text().splitlines() if line.strip()]

    def _rewrite(self, records: list[dict]) -> None:
        self._ledger().write_text(
            "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n",
            encoding="utf-8")

    def test_events_form_a_chain(self):
        records = self._records()
        self.assertIsNone(records[0]["integrity"]["prev"])
        for previous, current in zip(records, records[1:]):
            self.assertEqual(current["integrity"]["prev"], previous["integrity"]["hash"])
        verify = run(self.tmp, "events", "--verify")
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertIn("LEDGER OK", verify.stdout)
        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[PASS] ledger:", check.stdout)

    def test_tampered_payload_is_detected(self):
        records = self._records()
        records[1]["payload"]["text"] = "dipalsukan"
        self._rewrite(records)
        verify = run(self.tmp, "events", "--verify")
        self.assertEqual(verify.returncode, 1)
        self.assertIn("hash mismatch", verify.stdout)

    def test_deleted_event_is_detected(self):
        # Butuh minimal 3 event: menghapus event terakhir tidak merusak rantai,
        # itu hanya bisa ketahuan lewat seal/head yang disepakati di luar ledger.
        self.assertEqual(run(self.tmp, "step", "dua", "--next", "tiga").returncode, 0)
        records = self._records()
        self.assertGreaterEqual(len(records), 3)
        del records[1]
        self._rewrite(records)
        verify = run(self.tmp, "events", "--verify")
        self.assertEqual(verify.returncode, 1)
        self.assertIn("prev mismatch", verify.stdout)

    def test_legacy_events_are_reported_not_failed(self):
        records = self._records()
        for record in records:
            record.pop("integrity", None)
        self._rewrite(records)
        verify = run(self.tmp, "events", "--verify")
        self.assertEqual(verify.returncode, 0, verify.stdout)
        self.assertIn("pre-chain", verify.stdout)

    @NEEDS_CRYPTO
    def test_rewritten_chain_is_caught_by_the_seal(self):
        import hashlib

        self.assertEqual(run(self.tmp, "identity", "create", "bot", "--json").returncode, 0)
        sealed = run(self.tmp, "events", "--sign", "--identity", "bot")
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        self.assertIn("[SEAL]", sealed.stdout)

        records = self._records()
        previous = None
        for record in records:
            record["payload"]["suntikan"] = 1
            body = {k: v for k, v in record.items() if k != "integrity"}
            body["prev"] = previous
            previous = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
            record["integrity"] = {"prev": body["prev"], "hash": previous}
        self._rewrite(records)

        verify = run(self.tmp, "events", "--verify")
        self.assertEqual(verify.returncode, 1)
        self.assertIn("ledger rewritten", verify.stdout)

    def test_expect_head_anchors_the_ledger(self):
        head = json.loads(run(self.tmp, "events", "--verify", "--json").stdout)["head"]
        self.assertTrue(head)
        ok = run(self.tmp, "events", "--verify", "--expect-head", head)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        wrong = ("0" * 64)
        bad = run(self.tmp, "events", "--verify", "--expect-head", wrong)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("does not match --expect-head", bad.stdout)

    @NEEDS_CRYPTO
    def test_seal_verifies_and_reports_head(self):
        self.assertEqual(run(self.tmp, "identity", "create", "bot", "--json").returncode, 0)
        self.assertEqual(run(self.tmp, "events", "--sign", "--identity", "bot").returncode, 0)
        verify = run(self.tmp, "events", "--verify", "--json")
        self.assertEqual(verify.returncode, 0, verify.stdout)
        data = json.loads(verify.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["seal_count"], 1)
        self.assertTrue(data["head"])


@NEEDS_GIT
class WorkReport(unittest.TestCase):
    """`pakem report` merangkum dari artefak: sesi, plan, bukti verify, ledger."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
        (self.tmp / "src" / "b.py").write_text("def b(): return 2\n", encoding="utf-8")
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# r\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        self.assertEqual(run(self.tmp, "start", "kerja satu").returncode, 0)
        self.assertEqual(run(self.tmp, "step", "menulis", "--next", "uji").returncode, 0)
        added = run(self.tmp, "plan", "add", "tulis a", "--files", "src/a.py", "--verify", "true")
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        self.assertEqual(run(self.tmp, "plan", "done", "T1").returncode, 0)
        added = run(self.tmp, "plan", "add", "tulis b", "--files", "src/b.py", "--verify", "true")
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        # T2 dicentang langsung di PLAN.md: selesai tanpa bukti, harus terlihat di laporan.
        plan = (self.tmp / ".pakem" / "PLAN.md").read_text(encoding="utf-8")
        (self.tmp / ".pakem" / "PLAN.md").write_text(plan.replace("- [ ] T2", "- [x] T2", 1),
                                                     encoding="utf-8")

    def tearDown(self):
        self._td.cleanup()

    def _report(self, *args: str) -> dict:
        out = run(self.tmp, "report", "--json", *args)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def test_totals_name_the_unproven_task(self):
        data = self._report()
        self.assertEqual(data["totals"]["sessions"], 1)
        self.assertEqual(data["totals"]["tasks"], 2)
        self.assertEqual(data["totals"]["tasks_done"], 2)
        self.assertEqual(data["totals"]["verified"], 1)
        self.assertEqual(data["totals"]["unproven_done"], 1)
        session = data["sessions"][0]
        self.assertEqual(session["goal"], "kerja satu")
        self.assertEqual(session["steps"], 1)
        self.assertGreater(session["events"], 0)
        self.assertIsNotNone(session["duration_ms"])
        task = {item["task_id"]: item for item in data["tasks"]}["T1"]
        self.assertEqual(task["verify_status"], "pass")
        self.assertEqual(task["evidence_files"], ["src/a.py"])
        self.assertIsInstance(task["verify_duration_ms"], int)

    def test_text_report_flags_missing_evidence(self):
        out = run(self.tmp, "report")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("WORK REPORT", out.stdout)
        self.assertIn("kerja satu", out.stdout)
        self.assertIn("without verify evidence", out.stdout)
        self.assertIn("LEDGER", out.stdout)

    def test_session_filter_and_unknown_session(self):
        session_id = self._report()["sessions"][0]["id"]
        filtered = self._report("--session", session_id)
        self.assertEqual(filtered["totals"]["sessions"], 1)
        self.assertEqual(filtered["scope"]["session"], session_id)
        missing = run(self.tmp, "report", "--session", "tidak-ada")
        self.assertEqual(missing.returncode, 2, "die() memakai exit 2, sama seperti perintah lain")
        self.assertIn("session not found", missing.stdout + missing.stderr)

    def test_broken_ledger_makes_report_fail(self):
        path = sorted((self.tmp / ".pakem" / "events").glob("*.jsonl"))[0]
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        records[1]["payload"]["summary"] = "diubah"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"))
                                  for r in records) + "\n", encoding="utf-8")
        out = run(self.tmp, "report")
        self.assertEqual(out.returncode, 1)
        self.assertIn("BROKEN", out.stdout)
        self.assertIn("broken ledger", out.stdout)

    @NEEDS_JSONSCHEMA
    def test_json_matches_schema(self):
        import jsonschema

        schema = json.loads((ROOT / "runtime" / "v1" / "work-report.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(self._report(), schema)

    def test_empty_project_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as other:
            tmp = Path(other)
            git(tmp, "init", "-q", ".")
            self.assertEqual(run(tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
            out = run(tmp, "report", "--json")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            data = json.loads(out.stdout)
            self.assertEqual(data["sessions"], [])
            self.assertEqual(data["tasks"], [])
            self.assertEqual(data["totals"]["duration_ms"], 0)


@NEEDS_GIT
class HandoverAndSurfaces(unittest.TestCase):
    """Serah-terima yang basi, pembersihan worktree, isi CI, dan tool sesi MCP."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "src" / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# s\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")

    def tearDown(self):
        self._td.cleanup()

    def _commit(self, name: str) -> None:
        (self.tmp / name).write_text("x\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", name)

    def test_handover_stamp_detects_drift(self):
        self.assertEqual(run(self.tmp, "handover").returncode, 0)
        fresh = run(self.tmp, "handover", "--check")
        self.assertEqual(fresh.returncode, 0, fresh.stdout)
        self.assertIn("[OK  ] stamp matches HEAD", fresh.stdout)

        self._commit("berubah.txt")
        stale = run(self.tmp, "handover", "--check")
        self.assertEqual(stale.returncode, 1)
        self.assertIn("stale", stale.stdout)
        self.assertIn("1 commit since the stamp", stale.stdout)

        gate = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[WARN] handover:", gate.stdout)
        self.assertNotIn("[FAIL] handover:", gate.stdout)

        self.assertEqual(run(self.tmp, "handover", "--stamp").returncode, 0)
        self.assertEqual(run(self.tmp, "handover", "--check").returncode, 0)
        gate = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[PASS] handover:", gate.stdout)

    def test_handover_is_advice_on_check_and_binding_on_finish(self):
        cli = pakem_cli_module()
        self.assertEqual(run(self.tmp, "handover").returncode, 0)
        self.assertEqual(cli.gate_handover(self.tmp, finishing=False)[0], "pass")
        self._commit("ubah.txt")
        self.assertEqual(cli.gate_handover(self.tmp, finishing=False)[0], "warn")
        self.assertEqual(cli.gate_handover(self.tmp, finishing=True)[0], "fail")
        self.assertEqual(run(self.tmp, "handover", "--stamp").returncode, 0)
        self.assertEqual(cli.gate_handover(self.tmp, finishing=True)[0], "pass")

    def test_handover_without_stamp_is_rejected(self):
        self.assertEqual(run(self.tmp, "handover").returncode, 0)
        path = self.tmp / "HANDOVER.md"
        text = re.sub(r"<!-- pakem:handover.*?-->", "", path.read_text(encoding="utf-8"),
                      flags=re.S).strip() + "\n"
        path.write_text(text, encoding="utf-8")
        result = run(self.tmp, "handover", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no HEAD stamp", result.stdout)

    def test_clean_worktree_is_removed_when_task_done(self):
        self.assertEqual(run(self.tmp, "start", "kerja").returncode, 0)
        added = run(self.tmp, "plan", "add", "tulis a", "--files", "src/a.py", "--verify", "true")
        self.assertEqual(added.returncode, 0, added.stdout)
        created = run(self.tmp, "worktree", "create", "T1", "--agent", "solo", "--json")
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        done = run(self.tmp, "plan", "done", "T1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("[WT ] pakem/T1/solo deleted", done.stdout)
        listed = json.loads(run(self.tmp, "worktree", "list", "--json").stdout)
        self.assertNotIn("pakem/T1/solo", [w.get("branch") for w in listed["worktrees"]])

    def test_worktree_with_unmerged_commit_is_kept(self):
        self.assertEqual(run(self.tmp, "start", "kerja").returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "add", "tulis a", "--files", "src/a.py",
                             "--verify", "true").returncode, 0)
        created = json.loads(run(self.tmp, "worktree", "create", "T1", "--agent", "solo", "--json").stdout)
        child = self.tmp / created["path"]
        (child / "src" / "extra.py").write_text("y = 1\n", encoding="utf-8")
        git(child, "add", "-A")
        git(child, "commit", "-qm", "kerja di worktree")
        done = run(self.tmp, "plan", "done", "T1")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("not merged", done.stdout)
        self.assertTrue(child.is_dir())

    def test_ci_runs_doctor_audit_and_ledger_verify(self):
        self.assertEqual(run(self.tmp, "ci").returncode, 0)
        body = (self.tmp / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("pakem.py check", body)
        self.assertIn("pakem.py doctor", body)
        self.assertIn("pakem.py audit --strict", body)
        self.assertIn("pakem.py events --verify", body)

    def test_mcp_session_tools_are_write_gated_and_work(self):
        from pakem_core import mcp_server

        def modern(method, params=None):
            return {"jsonrpc": "2.0", "id": 1, "method": method,
                    "params": {**(params or {}), "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientCapabilities": {}}}}

        read_only = mcp_server.handle_message(modern("tools/list"), self.tmp)
        read_names = {tool["name"] for tool in read_only["result"]["tools"]}
        self.assertNotIn("pakem.session.start", read_names)

        writer = mcp_server.handle_message(modern("tools/list"), self.tmp,
                                           allow_write=True, bound_agent_id="bot")
        write_names = {tool["name"] for tool in writer["result"]["tools"]}
        self.assertIn("pakem.session.start", write_names)
        self.assertIn("pakem.session.finish", write_names)

        started = mcp_server.handle_message(
            modern("tools/call", {"name": "pakem.session.start", "arguments": {"goal": "kerja mcp"}}),
            self.tmp, allow_write=True, bound_agent_id="bot")
        self.assertTrue(started["result"]["structuredContent"]["ok"],
                        started["result"]["structuredContent"])
        stepped = mcp_server.handle_message(
            modern("tools/call", {"name": "pakem.session.step",
                                  "arguments": {"text": "menulis", "next": "uji"}}),
            self.tmp, allow_write=True, bound_agent_id="bot")
        self.assertTrue(stepped["result"]["structuredContent"]["ok"])
        sessions = list((self.tmp / ".pakem" / "sessions").glob("*.json"))
        self.assertEqual(len(sessions), 1)
        self.assertEqual(json.loads(sessions[0].read_text(encoding="utf-8"))["agent"], "bot")


@NEEDS_GIT
class IntegrityPin(unittest.TestCase):
    """CLI + Core dipin saat start; suntingan modul Core harus kelihatan."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tmp / "README.md").write_text("# i\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        self.assertEqual(run(self.tmp, "start", "kerja").returncode, 0)

    def tearDown(self):
        self._td.cleanup()

    def _core_file(self) -> Path:
        return self.tmp / ".pakem" / "pakem_core" / "reconcile.py"

    def test_manifest_covers_core_modules(self):
        out = run(self.tmp, "integrity", "--json")
        self.assertEqual(out.returncode, 0, out.stdout)
        data = json.loads(out.stdout)
        self.assertGreaterEqual(data["pinned_count"], 8, "manifest harus mencakup pakem_core/*")
        self.assertEqual(data["drift"], [])

    def test_core_edit_is_detected_and_repin_records_reason(self):
        core = self._core_file()
        core.write_text(core.read_text(encoding="utf-8") + "\n# dilonggarkan\n", encoding="utf-8")

        drift = run(self.tmp, "integrity")
        self.assertEqual(drift.returncode, 1)
        self.assertIn("pakem_core/reconcile.py", drift.stdout)
        self.assertIn("changed since the session started", drift.stdout)

        check = run(self.tmp, "check", "--skip-verify")
        self.assertIn("[WARN] rules-changed: .pakem/pakem_core/reconcile.py modified", check.stdout)

        no_reason = run(self.tmp, "integrity", "--re-pin")
        self.assertEqual(no_reason.returncode, 2)
        self.assertIn("--reason", no_reason.stdout + no_reason.stderr)

        repinned = run(self.tmp, "integrity", "--re-pin", "--reason", "komentar saja")
        self.assertEqual(repinned.returncode, 0, repinned.stdout)
        self.assertEqual(run(self.tmp, "integrity").returncode, 0)
        events = run(self.tmp, "events", "--json", "--limit", "0")
        self.assertIn("integrity.repinned", events.stdout)

    def test_finish_strict_treats_core_edit_as_failure(self):
        core = self._core_file()
        core.write_text(core.read_text(encoding="utf-8") + "\n# longgar\n", encoding="utf-8")
        out = run(self.tmp, "finish", "--strict", "--summary", "coba")
        self.assertIn("strict", out.stdout)


@NEEDS_GIT
@NEEDS_CRYPTO
class ExternalKeys(unittest.TestCase):
    """Private key bisa hidup di luar host/repo: CI secret, kunci yang di-mount."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        git(self.tmp, "init", "-q", ".")
        self.assertEqual(run(self.tmp, "init", "--type", "app", "--adapter", "none").returncode, 0)
        fill(self.tmp)
        (self.tmp / "a.txt").write_text("x\n", encoding="utf-8")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-qm", "init")
        self.assertEqual(run(self.tmp, "start", "kerja").returncode, 0)
        self.keydir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.keydir, ignore_errors=True))
        self.key = self.keydir / "ci.ed25519"

    def _create(self) -> dict:
        out = run(self.tmp, "identity", "create", "ci", "--key-out", str(self.key), "--json")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def test_key_outside_repo_can_seal(self):
        created = self._create()
        self.assertEqual(Path(created["privateKeyPath"]), self.key)
        self.assertTrue(self.key.is_file())
        self.assertNotIn(str(self.key), str(self.tmp))
        sealed = run(self.tmp, "events", "--sign", "--identity", "ci", "--key", str(self.key))
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        self.assertIn("[SEAL]", sealed.stdout)
        verify = run(self.tmp, "events", "--verify", "--json")
        self.assertEqual(verify.returncode, 0, verify.stdout)
        self.assertEqual(json.loads(verify.stdout)["seal_count"], 1)

    def test_env_key_is_used_when_flag_is_absent(self):
        self._create()
        env = {"PAKEM_SEAL_KEY": str(self.key)}
        out = subprocess.run([sys.executable, str(SCRIPT), "events", "--sign", "--identity", "ci"],
                             cwd=self.tmp, capture_output=True, text=True, env={**os.environ, **env},
                             timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("[SEAL]", out.stdout)

    def test_pem_key_is_accepted(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        self._create()
        private = Ed25519PrivateKey.from_private_bytes(self.key.read_bytes())
        pem = self.keydir / "ci.pem"
        pem.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        out = run(self.tmp, "events", "--sign", "--identity", "ci", "--key", str(pem))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_import_public_registers_without_private_key(self):
        created = self._create()
        with tempfile.TemporaryDirectory() as other:
            clone = Path(other)
            git(clone, "init", "-q", ".")
            self.assertEqual(run(clone, "init", "--type", "app", "--adapter", "none").returncode, 0)
            imported = run(clone, "identity", "import", "ci", "--public-key", created["publicKey"], "--json")
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            listed = json.loads(run(clone, "identity", "list", "--json").stdout)
            self.assertEqual(listed["agents"][0]["fingerprint"], created["fingerprint"])
            (clone / "payload.json").write_text('{"x": 1}', encoding="utf-8")
            sign = run(clone, "identity", "sign", "ci", "--file", "payload.json")
            self.assertNotEqual(sign.returncode, 0)
            self.assertIn("private key", sign.stdout + sign.stderr)


if __name__ == "__main__":
    unittest.main()
