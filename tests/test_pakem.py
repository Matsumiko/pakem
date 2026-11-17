import json
import re
import runpy
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pakem.py"


def run(cwd, *args, vendored=False):
    script = (Path(cwd) / ".pakem" / "pakem.py") if vendored else SCRIPT
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=30)


def fill(tmp: Path, verify='python3 -c "print(1)"'):
    for f in (tmp / ".pakem").glob("*.md"):
        t = f.read_text(encoding="utf-8")
        t = re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "terisi", t)
        if f.name == "PROJECT.md":
            t = re.sub(r"(?m)^verify:.*$", "verify: " + verify, t)
        f.write_text(t, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def init_app(self, *extra):
        r = run(self.tmp, "init", "--type", "app", *extra)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r


class PakemTests(Base):

    def test_init_fresh_app_scaffolds(self):
        self.init_app()
        for f in ("CONTEXT.md", "PROJECT.md", "MODULE-MAP.md", "DECISIONS.md", "BUG-HISTORY.md", "pakem.py"):
            self.assertTrue((self.tmp / ".pakem" / f).exists(), f)
        self.assertTrue((self.tmp / "tests" / ".gitkeep").exists())
        self.assertTrue((self.tmp / "docs" / "adr" / "TEMPLATE.md").exists())
        self.assertFalse((self.tmp / "docs" / "research").exists())
        for f in ("CLAUDE.md", "AGENTS.md", ".cursor/rules/pakem.mdc"):
            self.assertIn("pakem:begin", (self.tmp / f).read_text(encoding="utf-8"))
        self.assertIn(".pakem/sessions/", (self.tmp / ".gitignore").read_text(encoding="utf-8"))
        # tidak ada {{...}} yang tersisa dari template
        for f in (self.tmp / ".pakem").glob("*.md"):
            self.assertNotIn("{{", f.read_text(encoding="utf-8"), f.name)

    def test_oneoff_readme_is_advised_not_required(self):
        run(self.tmp, "init", "--type", "oneoff", "--adapter", "none")
        fill(self.tmp, verify='python3 -c "print(1)"')
        data = json.loads(run(self.tmp, "audit", "--json", vendored=True).stdout)
        readme = next(r for r in data["rows"] if r["label"] == "README.md")
        self.assertEqual(readme["tier"], "recommended")
        self.assertEqual(data["summary"]["wajib_gap"], 0)

    def test_oneoff_finish_strict_passes_without_readme(self):
        run(self.tmp, "init", "--type", "oneoff", "--adapter", "none")
        fill(self.tmp, verify='python3 -c "print(1)"')
        self.assertEqual(run(self.tmp, "start", "skrip sekali pakai", vendored=True).returncode, 0)
        r = run(self.tmp, "finish", "--summary", "skrip selesai, dibuktikan output nyata", "--strict", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[EVIDENCE] verify: pass", r.stdout)
        self.assertFalse((self.tmp / "README.md").exists())

    def test_oneoff_has_minimal_files(self):
        r = run(self.tmp, "init", "--type", "oneoff", "--adapter", "none")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.tmp / "tests").exists())
        self.assertFalse((self.tmp / ".pakem" / "MODULE-MAP.md").exists())
        fill(self.tmp)
        self.assertEqual(run(self.tmp, "check", vendored=True).returncode, 0)

    def test_check_fails_on_placeholders_then_passes(self):
        self.init_app()
        r = run(self.tmp, "check", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("placeholder", r.stdout)
        fill(self.tmp)
        r = run(self.tmp, "check", vendored=True)
        self.assertEqual(r.returncode, 1)  # tests/ masih kosong
        self.assertIn("rule.tests=required", r.stdout)
        (self.tmp / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
        r = run(self.tmp, "check", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_verify_failure_blocks(self):
        self.init_app()
        fill(self.tmp, verify='python3 -c "import sys; sys.exit(3)"')
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "check", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("verify exit 3", r.stdout)
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_skip_requires_reason(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        p = self.tmp / ".pakem" / "PROJECT.md"
        t = p.read_text(encoding="utf-8").replace("rule.research: when-needed", "rule.research: skip")
        p.write_text(t, encoding="utf-8")
        r = run(self.tmp, "check", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("reason.research", r.stdout)
        t = re.sub(r"(?m)^reason.research:.*$", "reason.research: tidak ada eksplorasi", t)
        p.write_text(t, encoding="utf-8")
        self.assertEqual(run(self.tmp, "check", vendored=True).returncode, 0)

    def test_session_resume_and_finish(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "finish", "--summary", "ringkasan panjang cukup", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no active session", r.stdout)

        self.assertEqual(run(self.tmp, "start", "bikin todo", vendored=True).returncode, 0)
        run(self.tmp, "step", "model selesai", "--next", "bikin endpoint", vendored=True)
        r = run(self.tmp, "start", "goal lain", vendored=True)
        self.assertIn("CONTINUE", r.stdout)
        self.assertIn("bikin endpoint", r.stdout)
        self.assertEqual(len(list((self.tmp / ".pakem" / "sessions").glob("*.json"))), 1)

        r = run(self.tmp, "finish", "--summary", "pendek", vendored=True)
        self.assertEqual(r.returncode, 1)
        r = run(self.tmp, "finish", "--summary", "todo selesai, test lolos", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(data["status"], "finished")
        # finish pertama gagal sebelum ada sesi (tak tercatat); hanya summary "pendek" yang tercatat
        self.assertEqual(len(data["gateFailures"]), 1)
        self.assertEqual(data["gateFailures"][0]["failed"], ["session"])

    def test_start_new_abandons_old(self):
        self.init_app()
        run(self.tmp, "start", "satu", vendored=True)
        r = run(self.tmp, "start", "--new", "dua", vendored=True)
        self.assertEqual(r.returncode, 0)
        statuses = sorted(json.loads(p.read_text())["status"]
                          for p in (self.tmp / ".pakem" / "sessions").glob("*.json"))
        self.assertEqual(statuses, ["abandoned", "active"])

    def test_drift_detects_missing_path(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        mm = self.tmp / ".pakem" / "MODULE-MAP.md"
        mm.write_text(mm.read_text(encoding="utf-8") + "\n- `src/ghost.py` - modul hantu\n", encoding="utf-8")
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/ghost.py", r.stdout)
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "ghost.py").write_text("")
        self.assertEqual(run(self.tmp, "check", "--skip-verify", vendored=True).returncode, 0)

    def test_adr_flow(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "adr", "Pilih database", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        adr = next((self.tmp / "docs" / "adr").glob("0001-*.md"))
        self.assertIn("docs/adr/" + adr.name, (self.tmp / ".pakem" / "DECISIONS.md").read_text())
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("placeholder", r.stdout)
        adr.write_text(re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "ok", adr.read_text()))
        self.assertEqual(run(self.tmp, "check", "--skip-verify", vendored=True).returncode, 0)
        run(self.tmp, "adr", "Pilih cache", vendored=True)
        self.assertTrue(list((self.tmp / "docs" / "adr").glob("0002-*.md")))

    def test_existing_repo_is_not_restructured(self):
        (self.tmp / "package.json").write_text(json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}))
        (self.tmp / "src").mkdir()
        r = run(self.tmp, "init", "--type", "app", "--adapter", "none")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.tmp / "tests").exists())
        self.assertFalse((self.tmp / "docs").exists())
        proj = (self.tmp / ".pakem" / "PROJECT.md").read_text()
        self.assertIn("verify: npm test && npm run lint", proj)
        self.assertIn("rule.tests: skip", proj)
        self.assertIn("FOLLOW the existing pattern", proj)

    def test_adapter_preserves_existing_content(self):
        (self.tmp / "CLAUDE.md").write_text("# Aturan saya\n\njangan hapus ini\n")
        self.init_app()
        t = (self.tmp / "CLAUDE.md").read_text()
        self.assertIn("jangan hapus ini", t)
        self.assertEqual(t.count("pakem:begin"), 1)
        run(self.tmp, "adapt", vendored=True)
        t = (self.tmp / "CLAUDE.md").read_text()
        self.assertEqual(t.count("pakem:begin"), 1)
        self.assertIn("jangan hapus ini", t)

    def test_hook_install(self):
        (self.tmp / ".git").mkdir()
        self.init_app()
        r = run(self.tmp, "hook", "install", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        hook = self.tmp / ".git" / "hooks" / "pre-commit"
        self.assertIn("pakem.py check", hook.read_text())
        self.assertTrue(hook.stat().st_mode & 0o100)

    def test_init_twice_requires_force(self):
        self.init_app()
        r = run(self.tmp, "init", "--type", "app")
        self.assertEqual(r.returncode, 2)


def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


class V02Tests(Base):
    """Fitur v0.2: deteksi pelonggaran aturan, cek repo saat resume, perintah bug, hook lintas OS."""

    def ready(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        self.assertEqual(run(self.tmp, "start", "kerja", vendored=True).returncode, 0)

    def test_loosened_rule_warns_but_passes(self):
        self.ready()
        p = self.tmp / ".pakem" / "PROJECT.md"
        t = p.read_text(encoding="utf-8").replace("rule.tests: required", "rule.tests: skip")
        t = re.sub(r"(?m)^reason.tests:.*$", "reason.tests: dirasa tidak perlu", t)
        p.write_text(t, encoding="utf-8")
        r = run(self.tmp, "finish", "--summary", "selesai dengan aturan longgar", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[WARN]", r.stdout)
        self.assertIn("rule.tests relaxed: required -> skip", r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(len(data["warnings"]), 1)

    def test_verify_change_warns(self):
        self.ready()
        p = self.tmp / ".pakem" / "PROJECT.md"
        p.write_text(re.sub(r"(?m)^verify:.*$", "verify: true", p.read_text(encoding="utf-8")), encoding="utf-8")
        r = run(self.tmp, "check", vendored=True)
        self.assertIn("verify changed", r.stdout)
        self.assertIn("WARNING", r.stdout)

    def test_cli_modification_warns(self):
        self.ready()
        cli = self.tmp / ".pakem" / "pakem.py"
        cli.write_text(cli.read_text(encoding="utf-8") + "\n# diubah agent\n", encoding="utf-8")
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertIn(".pakem/pakem.py modified", r.stdout)

    def test_no_warning_when_untouched(self):
        self.ready()
        r = run(self.tmp, "finish", "--summary", "selesai tanpa mengubah aturan", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("[WARN]", r.stdout)

    def test_bug_flow_and_gate(self):
        self.ready()
        r = run(self.tmp, "finish", "--summary", "perbaikan bug selesai", "--fixed-bug", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[FAIL] bug", r.stdout)

        r = run(self.tmp, "bug", "Crash saat input kosong", "--symptom", "error 500", "--cause", "tidak ada validasi",
                "--fix", "tambah guard", "--prevent", "test input kosong", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        run(self.tmp, "bug", "Timeout lambat", "--symptom", "s", "--cause", "c", "--fix", "f", "--prevent", "p",
            vendored=True)
        bh = (self.tmp / ".pakem" / "BUG-HISTORY.md").read_text(encoding="utf-8")
        self.assertNotIn("No bugs recorded yet", bh)
        self.assertLess(bh.index("BUG-002"), bh.index("BUG-001"))  # terbaru di atas

        r = run(self.tmp, "finish", "--summary", "perbaikan bug selesai", "--fixed-bug", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(data["bugs"], ["BUG-001", "BUG-002"])

    def test_bug_without_fields_leaves_placeholders(self):
        self.ready()
        run(self.tmp, "bug", "Bug setengah", vendored=True)
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BUG-HISTORY.md", r.stdout)

    def test_legacy_bug_history_still_gets_entry_on_top(self):
        """Projects initialized before 1.2.1 use `## Entri` and the Indonesian empty marker."""
        self.ready()
        p = self.tmp / ".pakem" / "BUG-HISTORY.md"
        p.write_text("# BUG-HISTORY\n\n## Entri\n\n_Belum ada bug tercatat._\n", encoding="utf-8")
        r = run(self.tmp, "bug", "Legacy", "--symptom", "s", "--cause", "c", "--fix", "f",
                "--prevent", "p", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = p.read_text(encoding="utf-8")
        self.assertIn("## BUG-001 - Legacy", body)
        self.assertNotIn("Belum ada bug tercatat", body)
        self.assertLess(body.index("## Entri"), body.index("## BUG-001"))

    def test_legacy_decisions_placeholder_is_replaced(self):
        self.ready()
        p = self.tmp / ".pakem" / "DECISIONS.md"
        p.write_text("# DECISIONS\n\n## Daftar\n\n_Belum ada keputusan tercatat._\n", encoding="utf-8")
        r = run(self.tmp, "adr", "Pilih cache", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = p.read_text(encoding="utf-8")
        self.assertNotIn("Belum ada keputusan tercatat", body)
        self.assertIn("docs/adr/", body)

    def test_bug_creates_history_for_oneoff(self):
        run(self.tmp, "init", "--type", "oneoff", "--adapter", "none")
        self.assertEqual(run(self.tmp, "bug", "x", "--symptom", "a", "--cause", "b", "--fix", "c",
                             "--prevent", "d", vendored=True).returncode, 0)
        self.assertIn("BUG-001", (self.tmp / ".pakem" / "BUG-HISTORY.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(__import__("shutil").which("git"), "git tidak tersedia")
    def test_resume_reports_new_commit_and_dirty_files(self):
        sh(self.tmp, "git", "init", "-q")
        (self.tmp / "a.txt").write_text("a")
        sh(self.tmp, "git", "add", "a.txt")
        sh(self.tmp, *GIT, "commit", "-q", "-m", "awal")
        self.init_app()
        run(self.tmp, "start", "kerja git", vendored=True)
        run(self.tmp, "step", "langkah 1", "--next", "langkah 2", vendored=True)

        r = run(self.tmp, "start", "x", vendored=True)
        self.assertIn("Repo state is unchanged", r.stdout)

        (self.tmp / "b.txt").write_text("b")
        sh(self.tmp, "git", "add", "b.txt")
        sh(self.tmp, *GIT, "commit", "-q", "-m", "commit lain")
        (self.tmp / "c.txt").write_text("c")
        r = run(self.tmp, "start", "x", vendored=True)
        self.assertIn("CHECK", r.stdout)
        self.assertIn("HEAD changed (1 new commit)", r.stdout)
        self.assertIn("c.txt", r.stdout)

        run(self.tmp, "step", "sinkron lagi", vendored=True)
        self.assertIn("Repo state is unchanged", run(self.tmp, "start", "x", vendored=True).stdout)

    def test_resume_without_git_is_silent(self):
        self.init_app()
        run(self.tmp, "start", "tanpa git", vendored=True)
        r = run(self.tmp, "start", "x", vendored=True)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("CHECK", r.stdout)

    def test_hook_probes_interpreters(self):
        (self.tmp / ".git").mkdir()
        self.init_app()
        run(self.tmp, "hook", "install", vendored=True)
        t = (self.tmp / ".git" / "hooks" / "pre-commit").read_text()
        self.assertIn('py -3', t)
        self.assertIn(".pakem/pakem.py check", t)

    @unittest.skipUnless(__import__("shutil").which("git"), "git tidak tersedia")
    def test_hook_respects_core_hooks_path(self):
        sh(self.tmp, "git", "init", "-q")
        sh(self.tmp, "git", "config", "core.hooksPath", ".githooks")
        (self.tmp / "a.txt").write_text("a")
        sh(self.tmp, "git", "add", "a.txt")
        sh(self.tmp, *GIT, "commit", "-q", "-m", "awal")
        self.init_app()
        r = run(self.tmp, "hook", "install", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / ".githooks" / "pre-commit").exists())
        self.assertFalse((self.tmp / ".git" / "hooks" / "pre-commit").exists())
        self.assertIn("core.hooksPath", r.stdout)

    @unittest.skipUnless(__import__("shutil").which("git"), "git tidak tersedia")
    def test_hook_install_in_worktree(self):
        sh(self.tmp, "git", "init", "-q")
        (self.tmp / "a.txt").write_text("a")
        sh(self.tmp, "git", "add", "a.txt")
        sh(self.tmp, *GIT, "commit", "-q", "-m", "awal")
        self.init_app()
        sh(self.tmp, "git", "add", "-A")
        sh(self.tmp, *GIT, "commit", "-q", "-m", "pakem")
        wt = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, wt, True)
        sh(self.tmp, "git", "worktree", "add", "-q", str(wt), "-b", "wt-hook")
        r = run(wt, "hook", "install", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / ".git" / "hooks" / "pre-commit").exists())
        self.assertIn("Hook installed", r.stdout)

    @unittest.skipUnless(__import__("shutil").which("git"), "git tidak tersedia")
    def test_installed_hook_blocks_commit_until_gates_pass(self):
        sh(self.tmp, "git", "init", "-q")
        self.init_app()
        run(self.tmp, "hook", "install", vendored=True)
        sh(self.tmp, "git", "add", "-A")

        def commit(msg):
            return subprocess.run(["git", *GIT[1:], "commit", "-qm", msg],
                                  cwd=self.tmp, capture_output=True, text=True)

        r = commit("belum siap")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gate failed", r.stderr)

        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        sh(self.tmp, "git", "add", "-A")
        r = commit("sudah siap")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)


class V03Tests(Base):
    """Fitur v0.3: audit artefak proporsional, flag risiko, sesi atomik dan korup."""

    def flags(self, **kw):
        p = self.tmp / ".pakem" / "PROJECT.md"
        t = p.read_text(encoding="utf-8")
        for key, value in kw.items():
            t = re.sub(rf"(?m)^{key}:.*$", f"{key}: {value}", t)
        p.write_text(t, encoding="utf-8")

    def ready(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        self.assertEqual(run(self.tmp, "start", "kerja", vendored=True).returncode, 0)

    def test_audit_classifies_by_risk_flags(self):
        self.init_app()
        r = run(self.tmp, "audit", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REQUIRED", r.stdout)
        self.assertIn("NOT NEEDED", r.stdout)
        self.assertIn("LICENSE", r.stdout)
        self.assertIn("private repo", r.stdout)
        self.assertNotIn("DEPLOYMENT.md", r.stdout)

        self.flags(exposure="public", deploy="production", sensitive="true", handover="true")
        r = run(self.tmp, "audit", vendored=True)
        self.assertIn("exposure=public", r.stdout)
        self.assertIn("[gap] LICENSE", r.stdout)
        self.assertIn("DEPLOYMENT.md", r.stdout)
        self.assertIn("RUNBOOK.md", r.stdout)
        self.assertIn("SECURITY.md", r.stdout)
        self.assertIn("HANDOVER.md", r.stdout)

    def test_audit_json_and_strict(self):
        self.init_app()
        r = run(self.tmp, "audit", "--json", vendored=True)
        data = json.loads(r.stdout)
        self.assertEqual(data["surface"]["exposure"], "private")
        self.assertGreater(data["summary"]["wajib_gap"], 0)
        self.assertEqual(run(self.tmp, "audit", "--strict", vendored=True).returncode, 1)

        (self.tmp / "README.md").write_text("# x\n")
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        self.assertEqual(run(self.tmp, "audit", "--strict", vendored=True).returncode, 0)

    def test_unknown_surface_value_warns(self):
        self.init_app()
        self.flags(deploy="productionn")
        r = run(self.tmp, "audit", vendored=True)
        self.assertIn("[WARN]", r.stdout)
        self.assertIn("deploy='productionn' unknown", r.stdout)

    def test_surface_downgrade_warns(self):
        self.init_app()
        self.flags(exposure="public", deploy="production", handover="true")
        run(self.tmp, "start", "kerja", vendored=True)
        self.flags(exposure="private", deploy="none", handover="false")
        r = run(self.tmp, "audit", vendored=True)
        self.assertIn("exposure downgraded: public -> private", r.stdout)
        self.assertIn("deploy downgraded: production -> none", r.stdout)
        self.assertIn("handover downgraded: true -> false", r.stdout)

    def test_init_prints_artifact_plan(self):
        r = run(self.tmp, "init", "--type", "app", "--adapter", "none")
        self.assertIn("Artifact plan:", r.stdout)
        self.assertIn("REQUIRED missing", r.stdout)
        self.assertIn("not needed", r.stdout)

    def test_finish_warns_risky_gaps_without_blocking(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        self.flags(deploy="production")
        self.assertEqual(run(self.tmp, "start", "rilis", vendored=True).returncode, 0)
        r = run(self.tmp, "finish", "--summary", "fitur selesai, test lolos", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[WARN] risk:", r.stdout)
        self.assertIn("DEPLOYMENT.md", r.stdout)
        self.assertIn("RUNBOOK.md", r.stdout)
        self.assertIn("advisory, non-blocking", r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(len(data["riskWarnings"]), 3)

    def test_finish_no_risk_warning_when_flags_off(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        r = run(self.tmp, "finish", "--summary", "selesai, test lolos", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("[WARN] risk:", r.stdout)

    def test_handover_single_file_flow(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "handover", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`handover` flag", r.stdout)
        p = self.tmp / "HANDOVER.md"
        self.assertTrue(p.exists())
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HANDOVER.md", r.stdout)
        p.write_text(re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "terisi", p.read_text()), encoding="utf-8")
        self.assertEqual(run(self.tmp, "check", "--skip-verify", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "handover", vendored=True).returncode, 2)  # tanpa --force
        self.flags(handover="true")
        r = run(self.tmp, "audit", vendored=True)
        self.assertIn("[ok]  HANDOVER.md", r.stdout)
        self.assertNotIn("[gap] catatan akses", r.stdout)

    def test_doctor_reports_setup_and_placeholders(self):
        self.init_app()
        r = run(self.tmp, "doctor", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DOCTOR", r.stdout)
        self.assertIn("placeholder:", r.stdout)
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "doctor", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[OK  ] config:", r.stdout)
        self.assertIn("[WARN] not a git repo", r.stdout)

    def test_doctor_detects_stale_adapter(self):
        self.init_app()
        p = self.tmp / "CLAUDE.md"
        p.write_text(p.read_text(encoding="utf-8").replace("work protocol", "old protocol"),
                     encoding="utf-8")
        r = run(self.tmp, "doctor", vendored=True)
        self.assertIn("stale block", r.stdout)

    def test_doctor_verify_failure(self):
        self.init_app()
        fill(self.tmp, verify='python3 -c "import sys; sys.exit(3)"')
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        r = run(self.tmp, "doctor", "--verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("verify exit 3", r.stdout)

    def test_prune_dry_run_then_delete_keeps_active(self):
        self.init_app()
        run(self.tmp, "start", "aktif", vendored=True)
        sessions = self.tmp / ".pakem" / "sessions"
        for i in range(3):
            (sessions / f"aaa-{i}.json").write_text(
                json.dumps({"id": f"aaa-{i}", "status": "finished", "goal": f"lama {i}"}),
                encoding="utf-8")
        (sessions / "rusak.json").write_text("{x", encoding="utf-8")
        r = run(self.tmp, "prune", "--keep", "1", "--days", "0", vendored=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Prune candidates (2)", r.stdout)
        self.assertIn("Dry-run", r.stdout)
        self.assertEqual(len(list(sessions.glob("*.json"))), 5)
        r = run(self.tmp, "prune", "--keep", "1", "--days", "0", "--yes", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Deleted 2 sessions", r.stdout)
        self.assertIn("corrupt session left untouched", r.stdout)
        names = {p.name for p in sessions.glob("*.json")}
        self.assertIn("rusak.json", names)
        self.assertIn("aaa-2.json", names)
        self.assertEqual(len([n for n in names if n.startswith("2026-")]), 1)

    def test_ci_generates_workflow_and_detects_stack(self):
        self.init_app()
        r = run(self.tmp, "ci", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.tmp / ".github" / "workflows" / "ci.yml"
        self.assertIn("pakem.py check", w.read_text())
        self.assertEqual(run(self.tmp, "ci", vendored=True).returncode, 2)
        (self.tmp / "package.json").write_text('{"scripts":{"test":"true"}}')
        (self.tmp / "package-lock.json").write_text("{}")
        r = run(self.tmp, "ci", "--force", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = w.read_text()
        self.assertIn("npm ci", text)
        self.assertIn("setup-node", text)
        self.assertIn("cache: npm", text)

    def test_doctor_warns_duplicate_test_dirs(self):
        self.init_app()
        (self.tmp / "test").mkdir()
        r = run(self.tmp, "doctor", vendored=True)
        self.assertIn("multiple test folders", r.stdout)

    def test_audit_lockfile_only_when_dependencies_exist(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        (self.tmp / "package.json").write_text('{"scripts":{"test":"true"}}')
        r = run(self.tmp, "audit", "--json", vendored=True)
        self.assertFalse(any("lockfile" in x["label"] for x in json.loads(r.stdout)["rows"]))
        (self.tmp / "package.json").write_text('{"dependencies":{"left-pad":"1.0.0"}}')
        r = run(self.tmp, "audit", "--json", vendored=True)
        self.assertTrue(any("lockfile" in x["label"] for x in json.loads(r.stdout)["rows"]))

    def test_finish_stores_verify_evidence(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        r = run(self.tmp, "finish", "--summary", "selesai, bukti verify", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[EVIDENCE] verify: pass exit=0 hash=", r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        ev = data["verifyEvidence"]
        self.assertEqual(ev["status"], "pass")
        self.assertEqual(ev["exit"], 0)
        self.assertEqual(len(ev["outputHash"]), 16)
        self.assertIn("cmd", ev)

    def test_finish_strict_fails_on_loosened_rule(self):
        self.ready()
        p = self.tmp / ".pakem" / "PROJECT.md"
        t = p.read_text(encoding="utf-8").replace("rule.tests: required", "rule.tests: skip")
        t = re.sub(r"(?m)^reason.tests:.*$", "reason.tests: dirasa tidak perlu", t)
        p.write_text(t, encoding="utf-8")
        r = run(self.tmp, "finish", "--summary", "selesai dengan aturan longgar", "--strict", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[FAIL] strict:", r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(data["status"], "active")
        self.assertIn("strict", data["gateFailures"][-1]["failed"])

    def test_finish_strict_fails_on_audit_gap(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        r = run(self.tmp, "finish", "--summary", "selesai tanpa README", "--strict", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[WARN] required: README.md", r.stdout)
        self.assertIn("[FAIL] strict:", r.stdout)

    def test_finish_warns_audit_wajib_but_passes(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        r = run(self.tmp, "finish", "--summary", "selesai tanpa README", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[WARN] required: README.md", r.stdout)
        data = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertIn("README.md", data["auditGaps"])

    def test_upgrade_restores_flags_and_preserves_docs(self):
        self.init_app()
        fill(self.tmp)
        context = self.tmp / ".pakem" / "CONTEXT.md"
        context.write_text(context.read_text(encoding="utf-8") + "\nSENTINEL-DOC\n", encoding="utf-8")
        p = self.tmp / ".pakem" / "PROJECT.md"
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"(?m)^(exposure|deploy|handover):.*\n", "", t)
        p.write_text(t, encoding="utf-8")

        r = run(self.tmp, "upgrade", "--from", str(SCRIPT), "--dry-run", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY-RUN", r.stdout)
        self.assertIsNone(re.search(r"(?m)^exposure:", p.read_text(encoding="utf-8")))

        r = run(self.tmp, "upgrade", "--from", str(SCRIPT), vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = p.read_text(encoding="utf-8")
        self.assertIn("exposure: private", text)
        self.assertIn("deploy: none", text)
        self.assertIn("handover: false", text)
        self.assertIn("SENTINEL-DOC", context.read_text(encoding="utf-8"))
        self.assertIn("Upgrade complete", r.stdout)

    def test_spec_approval_flow(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        r = run(self.tmp, "spec", "Fitur A", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = self.tmp / ".pakem" / "SPEC.md"
        self.assertIn("Status: draft", spec.read_text(encoding="utf-8"))
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("spec", r.stdout)
        self.assertIn("placeholder", r.stdout)
        r = run(self.tmp, "spec", "--approve", vendored=True)
        self.assertEqual(r.returncode, 2)  # masih placeholder
        spec.write_text(re.sub(r"\[(?:ISI|FILL)[^\]]*\]", "terisi", spec.read_text(encoding="utf-8")),
                        encoding="utf-8")
        r = run(self.tmp, "spec", "--approve", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Status: approved", spec.read_text(encoding="utf-8"))
        self.assertEqual(run(self.tmp, "check", "--skip-verify", vendored=True).returncode, 0)

    def test_plan_pending_and_drop(self):
        # Subjek tes ini bookkeeping plan/sesi; verify task harus lulus di repo kosong.
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# x\n")
        (self.tmp / "tests" / "test_x.py").write_text("x = 1\n")
        run(self.tmp, "start", "kerja", vendored=True)
        self.assertIn("No PLAN.md", run(self.tmp, "plan", vendored=True).stdout)
        self.assertEqual(run(self.tmp, "plan", "add", "buat a", "--files", "src/a.js",
                             "--verify", 'python3 -c "print(1)"', vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "add", "buat b", "--files", "src/b.js",
                             "--verify", 'python3 -c "print(1)"', vendored=True).returncode, 0)
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("2 tasks not done", r.stdout)
        run(self.tmp, "plan", "done", "T1", vendored=True)
        sess = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertEqual(sess["nextStep"], "T2 - buat b")
        r = run(self.tmp, "check", "--skip-verify", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("T2", r.stdout)
        self.assertEqual(run(self.tmp, "plan", "drop", "T2", "--reason", "tidak perlu",
                             vendored=True).returncode, 0)
        sess = json.loads(next((self.tmp / ".pakem" / "sessions").glob("*.json")).read_text())
        self.assertIn("done - run pakem finish", sess["nextStep"])
        self.assertEqual(run(self.tmp, "check", "--skip-verify", vendored=True).returncode, 0)
        plan = (self.tmp / ".pakem" / "PLAN.md").read_text(encoding="utf-8")
        self.assertIn("Status: 2/2 done", plan)
        self.assertIn("[dropped: tidak perlu]", plan)
        r = run(self.tmp, "finish", "--summary", "dua task selesai, test lolos", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_plan_verify_preserves_shell_pipe(self):
        self.init_app("--adapter", "none")
        run(self.tmp, "plan", "add", "jalankan test dan ringkas", "--files", "tests/test_x.py",
            "--verify", "python3 -m pytest -q | tail -3", vendored=True)
        plan = (self.tmp / ".pakem" / "PLAN.md").read_text(encoding="utf-8")
        self.assertIn("verify: python3 -m pytest -q | tail -3", plan)
        listed = run(self.tmp, "plan", "list", vendored=True)
        self.assertIn("python3 -m pytest -q | tail -3", listed.stdout)

    def test_plan_add_requires_files_and_verify(self):
        self.init_app()
        r = run(self.tmp, "plan", "add", "task tanpa detail", vendored=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--files and --verify are required", r.stderr)

    def test_finish_blocks_pending_plan(self):
        self.ready()
        run(self.tmp, "plan", "add", "task tertunda", "--files", "src/a.js",
            "--verify", "node --test", vendored=True)
        r = run(self.tmp, "finish", "--summary", "belum semua task selesai", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("plan", r.stdout)
        self.assertIn("1 task not done", r.stdout)

    def test_context_protocol_sync(self):
        self.init_app()
        p = self.tmp / ".pakem" / "CONTEXT.md"
        original = p.read_text(encoding="utf-8")
        p.write_text(original.replace("Read `.pakem/CONTEXT.md`", "Read context"), encoding="utf-8")
        r = run(self.tmp, "doctor", vendored=True)
        self.assertIn("CONTEXT.md: stale", r.stdout)
        r = run(self.tmp, "upgrade", "--from", str(SCRIPT), vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("protocol block synced", r.stdout)
        self.assertIn("Read `.pakem/CONTEXT.md`", p.read_text(encoding="utf-8"))
        r = run(self.tmp, "doctor", vendored=True)
        self.assertNotIn("CONTEXT.md: stale", r.stdout)

    def test_corrupt_session_is_reported_not_hidden(self):
        self.init_app()
        run(self.tmp, "start", "kerja", vendored=True)
        (self.tmp / ".pakem" / "sessions" / "rusak.json").write_text("{bukan json", encoding="utf-8")
        r = run(self.tmp, "status", vendored=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("[WARN] corrupt session ignored", r.stdout)
        self.assertIn("rusak.json", r.stdout)
        r = run(self.tmp, "start", "lanjut", vendored=True)
        self.assertIn("[WARN] corrupt session ignored", r.stdout)
        self.assertIn("CONTINUE", r.stdout)
        r = run(self.tmp, "audit", "--json", vendored=True)
        data = json.loads(r.stdout)
        self.assertIn("rusak.json", data["corrupt_sessions"])

    def test_session_save_is_atomic(self):
        self.init_app()
        run(self.tmp, "start", "kerja", vendored=True)
        run(self.tmp, "step", "satu", "--next", "dua", vendored=True)
        files = sorted((self.tmp / ".pakem" / "sessions").glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertFalse(list((self.tmp / ".pakem" / "sessions").glob("*.tmp")))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data["nextStep"], "dua")

class SchemaContractTests(Base):
    """Kontrak schema harus bisa di-resolve tanpa jaringan dan tanpa domain pihak lain."""

    def test_schema_ids_are_pakem_urns_and_refs_resolve(self):
        schemas = sorted(SCRIPT.parent.parent.rglob("*.schema.json"))
        self.assertTrue(schemas)
        ids = {}
        for path in schemas:
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("$id", doc, path.name)
            schema_id = doc["$id"]
            self.assertTrue(schema_id.startswith("urn:pakem:"), f"{path.name}: $id {schema_id} bukan URN pakem")
            self.assertNotIn(schema_id, ids, f"$id duplikat: {schema_id}")
            ids[schema_id] = path
        for path in schemas:
            text = path.read_text(encoding="utf-8")
            for ref in re.findall(r'"\$ref":\s*"([^"]+)"', text):
                if ref.startswith("#"):
                    continue
                self.assertIn(ref, ids, f"{path.name}: $ref {ref} tidak menunjuk schema yang ada")

    def test_no_schema_points_at_a_third_party_domain(self):
        external = "pakem" + ".dev"
        for path in sorted(SCRIPT.parent.parent.rglob("*.json")):
            self.assertNotIn(external, path.read_text(encoding="utf-8"),
                             f"{path.name} masih menunjuk domain eksternal")


class EvalRunnerTests(Base):
    """Runner evals: harness-nya harus nyata, penilaian tetap milik judge."""

    def runner(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT.parent / "run_evals.py"), *args],
                              cwd=self.tmp, capture_output=True, text=True, timeout=120)

    def stub_agent(self, body="print('agent selesai')"):
        path = self.tmp / "agent.py"
        path.write_text("import sys\nprint('prompt:', (sys.stdin.read() or '').strip()[:40])\n"
                        + body + "\n", encoding="utf-8")
        return f"{sys.executable} {path}"

    def stub_judge(self, mode="pass"):
        path = self.tmp / "judge.py"
        body = ["import json, sys",
                "payload = json.loads(sys.stdin.read())",
                f"mode = {mode!r}",
                "results = [{'assertion': a, 'pass': mode == 'pass', 'why': 'stub'} for a in payload['assertions']]",
                "print(json.dumps({'results': results}))"]
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return f"{sys.executable} {path}"

    def test_broken_agent_command_is_reported_not_swallowed(self):
        broken = self.tmp / "broken.py"
        broken.write_text("import sys\nsys.stderr.write(\"can't open file: agent.py\\n\")\nsys.exit(2)\n",
                          encoding="utf-8")
        r = self.runner("--agent-cmd", f"{sys.executable} {broken}", "--eval", "1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("! agent exit 2", r.stdout)
        self.assertIn("can't open file", r.stdout)

    def test_real_evals_file_is_well_formed(self):
        r = self.runner("--validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("struktur sehat", r.stdout)
        self.assertIn("24 eval", r.stdout)

    def test_runner_records_without_judge(self):
        r = self.runner("--agent-cmd", self.stub_agent(), "--eval", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[REKAM]", r.stdout)
        self.assertIn("assertion tidak dinilai", r.stdout)

    def test_runner_grades_every_assertion_and_fails_loudly(self):
        agent = self.stub_agent()
        ok = self.runner("--agent-cmd", agent, "--judge-cmd", self.stub_judge("pass"), "--eval", "1")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("[PASS] eval 1", ok.stdout)
        bad = self.runner("--agent-cmd", agent, "--judge-cmd", self.stub_judge("fail"), "--eval", "1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("[FAIL] eval 1", bad.stdout)

    def test_judge_that_skips_assertions_scores_them_failed(self):
        agent = self.stub_agent()
        lazy = self.tmp / "lazy_judge.py"
        lazy.write_text("import json,sys\njson.loads(sys.stdin.read())\nprint(json.dumps({'results': []}))\n",
                        encoding="utf-8")
        r = self.runner("--agent-cmd", agent, "--judge-cmd", f"{sys.executable} {lazy}", "--eval", "1",
                        "--json")
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        report = data["reports"][0]
        self.assertEqual(report["passed"], 0)
        self.assertGreater(report["total"], 0)
        self.assertIn("judge tidak menilai", report["results"][0]["why"])


if __name__ == "__main__":
    unittest.main()

class ProtocolV1Tests(Base):
    def test_event_schema_matches_cli_event_registry(self):
        schema = json.loads((SCRIPT.parent.parent / "protocol" / "v1" / "event.schema.json").read_text(encoding="utf-8"))
        registry = runpy.run_path(str(SCRIPT))["PROTOCOL_EVENTS"]
        self.assertEqual(set(schema["properties"]["event"]["enum"]), registry)

    def test_init_installs_protocol_contract_and_machine_context(self):
        self.init_app()
        schema_dir = self.tmp / ".pakem" / "protocol" / "v1"
        event_schema = json.loads((schema_dir / "event.schema.json").read_text(encoding="utf-8"))
        session_schema = json.loads((schema_dir / "session.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(event_schema["$id"], "urn:pakem:protocol:v1:event")
        self.assertIn("status", session_schema["properties"])
        ignored = (self.tmp / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".pakem/events/", ignored)

        r = run(self.tmp, "context", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["protocol_version"], "1.0")
        self.assertEqual(data["recommended_next"], "resolve_project_gates")
        self.assertIn("placeholder_gate_failed", data["blockers"])
        self.assertIn("rules", data["gates"])
        self.assertEqual(data["plan"]["pending"], 0)

    def test_session_lifecycle_events_are_recorded_and_queryable(self):
        self.init_app()
        self.assertEqual(run(self.tmp, "start", "buat endpoint", "--agent", "codex", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "start", "lanjutkan pekerjaan", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "step", "model selesai", "--next", "buat test", vendored=True).returncode, 0)
        r = run(self.tmp, "events", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        names = [item["event"] for item in data["events"]]
        self.assertEqual(names, ["session.started", "session.resumed", "session.step_recorded"])
        self.assertEqual(data["events"][0]["actor"]["name"], "codex")
        self.assertEqual(data["events"][2]["payload"]["next_step"], "buat test")
        for item in data["events"]:
            self.assertEqual(run(self.tmp, "protocol", "validate-event", self._write_event(item), vendored=True).returncode, 0)

    def _write_event(self, item):
        p = self.tmp / "event-to-validate.json"
        p.write_text(json.dumps(item), encoding="utf-8")
        return str(p)

    def test_plan_events_cover_add_complete_and_drop(self):
        # Subjek tes ini urutan event; sejak 1.2.0 `plan done` menjalankan verify,
        # jadi perintahnya harus benar-benar lulus di repo kosong.
        self.init_app()
        self.assertEqual(run(self.tmp, "plan", "add", "buat parser", "--files", "src/parser.py",
                             "--verify", 'python3 -c "print(1)"', vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "done", "T1", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "add", "hapus modul lama", "--files", "src/old.py",
                             "--verify", 'python3 -c "print(1)"', vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "plan", "drop", "T2", "--reason", "tidak diperlukan",
                             vendored=True).returncode, 0)
        data = json.loads(run(self.tmp, "events", "--json", vendored=True).stdout)
        names = [item["event"] for item in data["events"]]
        self.assertEqual(names, ["task.added", "task.completed", "task.added", "task.dropped"])

    def test_protocol_validator_rejects_invalid_envelope(self):
        self.init_app()
        p = self.tmp / "bad-event.json"
        p.write_text(json.dumps({"protocol": "other", "event": "made.up"}), encoding="utf-8")
        r = run(self.tmp, "protocol", "validate-event", str(p), "--json", vendored=True)
        self.assertEqual(r.returncode, 1)
        result = json.loads(r.stdout)
        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_protocol_session_validator_accepts_legacy_and_v1(self):
        self.init_app()
        legacy = {
            "id": "legacy-001",
            "goal": "legacy session",
            "status": "active",
            "startedAt": "2026-11-09T02:00:00+07:00",
            "steps": [],
        }
        p = self.tmp / "legacy-session.json"
        p.write_text(json.dumps(legacy), encoding="utf-8")
        result = run(self.tmp, "protocol", "validate-session", str(p), "--json", vendored=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])

        current = {**legacy, "id": "v1-001", "schemaVersion": 1,
                   "extension": {"source": "another-runtime"}}
        p.write_text(json.dumps(current), encoding="utf-8")
        result = run(self.tmp, "protocol", "validate-session", str(p), "--json", vendored=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])

        current["schemaVersion"] = True
        p.write_text(json.dumps(current), encoding="utf-8")
        result = run(self.tmp, "protocol", "validate-session", str(p), "--json", vendored=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["valid"])

    def test_upgrade_restores_protocol_schemas_and_event_ignore(self):
        self.init_app()
        shutil.rmtree(self.tmp / ".pakem" / "protocol")
        gi = self.tmp / ".gitignore"
        gi.write_text("", encoding="utf-8")
        r = run(self.tmp, "upgrade", "--from", str(SCRIPT), vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.tmp / ".pakem" / "protocol" / "v1" / "event.schema.json").is_file())
        self.assertIn(".pakem/events/", gi.read_text(encoding="utf-8"))

    def test_decision_bug_and_handover_events_are_recorded(self):
        self.init_app()
        self.assertEqual(run(self.tmp, "adr", "pilih database", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "bug", "input kosong", "--symptom", "crash",
                             "--cause", "validasi hilang", "--fix", "tambah validasi",
                             "--prevent", "test input kosong", vendored=True).returncode, 0)
        self.assertEqual(run(self.tmp, "handover", vendored=True).returncode, 0)
        data = json.loads(run(self.tmp, "events", "--json", vendored=True).stdout)
        names = [item["event"] for item in data["events"]]
        self.assertEqual(names, ["decision.recorded", "bug.recorded", "handover.created"])

    def test_finish_records_verification_and_terminal_event(self):
        self.init_app()
        fill(self.tmp)
        (self.tmp / "README.md").write_text("# Demo\n", encoding="utf-8")
        (self.tmp / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        self.assertEqual(run(self.tmp, "start", "selesaikan demo", vendored=True).returncode, 0)
        r = run(self.tmp, "finish", "--summary", "demo selesai dan test lolos", vendored=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        data = json.loads(run(self.tmp, "events", "--json", vendored=True).stdout)
        names = [item["event"] for item in data["events"]]
        self.assertEqual(names[-2:], ["verification.completed", "session.finished"])
        self.assertEqual(data["events"][-2]["payload"]["status"], "pass")

    def test_doctor_reports_corrupt_event_ledger(self):
        self.init_app()
        event_dir = self.tmp / ".pakem" / "events"
        event_dir.mkdir(parents=True, exist_ok=True)
        (event_dir / "project.jsonl").write_text("{broken json\n", encoding="utf-8")
        r = run(self.tmp, "doctor", "--json", vendored=True)
        self.assertEqual(r.returncode, 1, r.stderr)  # init sengaja masih punya placeholder/gap
        data = json.loads(r.stdout)
        self.assertTrue(any("event ledger" in issue["message"] for issue in data["issues"]))


class IntelligenceTests(Base):

    def setUp(self):
        super().setUp()
        self.init_app("--adapter", "none")
        self.core = self.tmp / ".pakem" / "pakem_core"
        self.intelligence_schemas = self.tmp / ".pakem" / "intelligence" / "v1"
        self.assertTrue((self.core / "intelligence.py").is_file(), "core module must be vendored")
        self.assertTrue((self.intelligence_schemas / "dependency-graph.schema.json").is_file())
        self.assertTrue((self.intelligence_schemas / "impact-analysis.schema.json").is_file())

    def write(self, rel, content):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_graph_discovers_python_reverse_dependencies_and_tests(self):
        self.write("domain/model.py", "class User: pass\n")
        self.write("service/auth.py", "from domain.model import User\n")
        self.write("app.py", "from service.auth import User\n")
        self.write("tests/test_auth.py", "from service.auth import User\n")
        self.write("node_modules/ignored/index.py", "raise RuntimeError('must not scan')\n")
        r = run(self.tmp, "graph", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        graph = json.loads(r.stdout)
        edges = {(e["from"], e["to"]) for e in graph["edges"]}
        self.assertIn(("service/auth.py", "domain/model.py"), edges)
        self.assertIn(("app.py", "service/auth.py"), edges)
        self.assertIn(("tests/test_auth.py", "service/auth.py"), edges)
        self.assertNotIn("node_modules/ignored/index.py", {n["path"] for n in graph["nodes"]})

    def test_impact_follows_direct_and_transitive_dependents(self):
        self.write("src/auth/session.py", "class Session: pass\n")
        self.write("src/auth/api.py", "from src.auth.session import Session\n")
        self.write("src/app.py", "from src.auth.api import Session\n")
        self.write("tests/test_session.py", "from src.auth.session import Session\n")
        r = run(self.tmp, "impact", "--files", "src/auth/session.py", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        result = json.loads(r.stdout)
        self.assertEqual(result["changed_files"], ["src/auth/session.py"])
        self.assertIn("src/auth/api.py", result["direct_dependents"])
        self.assertIn("src/app.py", result["transitive_dependents"])
        self.assertIn("tests/test_session.py", result["affected_tests"])
        self.assertEqual(result["risk"]["level"], "high")

    def test_impact_flags_dependency_lockfile_for_compatibility_review(self):
        self.write("package-lock.json", '{"lockfileVersion": 3}\n')
        r = run(self.tmp, "impact", "--files", "package-lock.json", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        result = json.loads(r.stdout)
        self.assertEqual(result["risk"]["level"], "medium")
        self.assertTrue(any("lockfile" in reason for reason in result["risk"]["reasons"]))

    def test_impact_strict_blocks_high_risk(self):
        self.write("src/auth/token.py", "TOKEN = 'placeholder'\n")
        r = run(self.tmp, "impact", "--files", "src/auth/token.py", "--strict", "--json", vendored=True)
        self.assertEqual(r.returncode, 1)
        result = json.loads(r.stdout)
        self.assertEqual(result["risk"]["level"], "high")
        self.assertTrue(result["strict_blocked"])

    def test_graph_output_file_and_exclude_tests(self):
        self.write("src/main.ts", "import { api } from './api';\n")
        self.write("src/api.ts", "export const api = 1;\n")
        self.write("tests/main.test.ts", "import '../src/main';\n")
        r = run(self.tmp, "graph", "--json", "--exclude-tests", "--output", "artifacts/graph.json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        stdout_graph = json.loads(r.stdout)
        graph = json.loads((self.tmp / "artifacts/graph.json").read_text(encoding="utf-8"))
        self.assertEqual(stdout_graph["node_count"], graph["node_count"])
        self.assertEqual(graph["node_count"], 2)
        self.assertEqual(graph["edge_count"], 1)
        self.assertNotIn("tests/main.test.ts", {n["path"] for n in graph["nodes"]})

    def test_graph_resolves_go_and_java_local_packages(self):
        self.write("go.mod", "module example.com/demo\n\ngo 1.22\n")
        self.write("cmd/main.go", 'package main\nimport "example.com/demo/pkg"\nfunc main() { pkg.Run() }\n')
        self.write("pkg/lib.go", "package pkg\nfunc Run() {}\n")
        self.write("java/src/com/example/app/Main.java", "package com.example.app;\nimport com.example.service.UserService;\nclass Main {}\n")
        self.write("java/src/com/example/service/UserService.java", "package com.example.service;\nclass UserService {}\n")
        r = run(self.tmp, "graph", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        graph = json.loads(r.stdout)
        edges = {(e["from"], e["to"]) for e in graph["edges"]}
        self.assertIn(("cmd/main.go", "pkg/lib.go"), edges)
        self.assertIn(("java/src/com/example/app/Main.java", "java/src/com/example/service/UserService.java"), edges)

    def test_impact_rejects_mixed_file_and_git_selectors(self):
        r = run(self.tmp, "impact", "--files", "src/a.py", "--staged", "--json", vendored=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("use exactly one of", r.stderr)

    def test_impact_rejects_paths_outside_project(self):
        r = run(self.tmp, "impact", "--files", "../outside.py", "--json", vendored=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("outside the project root", r.stderr)

    def test_impact_requires_explicit_files_or_git_changes(self):
        r = run(self.tmp, "impact", "--json", vendored=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a Git repository", r.stderr)

    def test_upgrade_syncs_core_package(self):
        shutil.rmtree(self.core)
        shutil.rmtree(self.intelligence_schemas)
        vendored_cli = self.tmp / ".pakem" / "pakem.py"
        current = re.search(r'(?m)^VERSION = "([^"]+)"', SCRIPT.read_text(encoding="utf-8")).group(1)
        legacy_text = vendored_cli.read_text(encoding="utf-8").replace(f'VERSION = "{current}"',
                                                                       'VERSION = "1.0.0"', 1)
        vendored_cli.write_text(legacy_text, encoding="utf-8")
        context_before = (self.tmp / ".pakem" / "CONTEXT.md").read_text(encoding="utf-8")
        r = run(self.tmp, "upgrade", "--from", str(SCRIPT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        target = self.core / "intelligence.py"
        self.assertTrue(target.is_file())
        self.assertIn("build_dependency_graph", target.read_text(encoding="utf-8"))
        self.assertTrue((self.intelligence_schemas / "impact-analysis.schema.json").is_file())
        self.assertTrue((self.core / "runtime.py").is_file())
        self.assertTrue((self.core / "coordination.py").is_file())
        self.assertTrue((self.tmp / ".pakem" / "coordination" / "v1" / "board.schema.json").is_file())
        self.assertTrue((self.tmp / ".pakem" / "runtime" / "v1" / "workflow.schema.json").is_file())
        self.assertTrue((self.tmp / ".pakem" / "runtime" / "v1" / "hook-decision.schema.json").is_file())
        self.assertTrue((self.tmp / ".pakem" / "policy" / "v1" / "policy.schema.json").is_file())
        self.assertIn(f'VERSION = "{current}"', vendored_cli.read_text(encoding="utf-8"))
        context_after = (self.tmp / ".pakem" / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertEqual(context_before, context_after)


class AutonomousRuntimeTests(Base):
    def init_runtime(self):
        self.init_app("--adapter", "none")
        r = run(self.tmp, "runtime", "init", "bangun fitur auth", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)["workflow"]

    def test_init_installs_runtime_policy_and_schemas(self):
        self.init_app("--adapter", "none")
        for rel in (
            ".pakem/POLICY.json",
            ".pakem/pakem_core/runtime.py",
            ".pakem/runtime/v1/workflow.schema.json",
            ".pakem/runtime/v1/checkpoint.schema.json",
            ".pakem/runtime/v1/hook-payload.schema.json",
            ".pakem/runtime/v1/hook-decision.schema.json",
            ".pakem/policy/v1/policy.schema.json",
        ):
            self.assertTrue((self.tmp / rel).is_file(), rel)
        policy = json.loads((self.tmp / ".pakem/POLICY.json").read_text())
        self.assertEqual(policy["autonomy"], "assisted")
        self.assertIn(".pakem/runtime/", (self.tmp / ".gitignore").read_text())

    def test_workflow_transitions_and_rejects_invalid_transition(self):
        workflow = self.init_runtime()
        self.assertEqual(workflow["state"], "planning")
        for state in ("ready", "executing", "verifying", "completed"):
            r = run(self.tmp, "runtime", "transition", state, "--reason", "test transition", "--json", vendored=True)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        status = json.loads(run(self.tmp, "runtime", "status", "--json", vendored=True).stdout)
        self.assertEqual(status["workflow"]["state"], "completed")
        r = run(self.tmp, "runtime", "transition", "executing", vendored=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("transition not allowed", r.stderr)

    def test_checkpoint_recovery_only_restores_workflow_metadata(self):
        self.init_runtime()
        run(self.tmp, "runtime", "transition", "ready", vendored=True)
        run(self.tmp, "runtime", "transition", "executing", vendored=True)
        marker = self.tmp / "source-changes-stay.txt"
        marker.write_text("keep me")
        cp = run(self.tmp, "runtime", "checkpoint", "--label", "before interruption", "--json", vendored=True)
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)
        checkpoint_id = json.loads(cp.stdout)["checkpoint"]["checkpointId"]
        run(self.tmp, "runtime", "transition", "verifying", vendored=True)
        recovered = run(self.tmp, "runtime", "recover", checkpoint_id, "--json", vendored=True)
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        result = json.loads(recovered.stdout)
        self.assertEqual(result["workflow"]["state"], "recovering")
        self.assertEqual(marker.read_text(), "keep me")
        self.assertIn("source code is not reverted", result["warning"])

    def test_recovery_reports_git_worktree_drift(self):
        if not shutil.which("git"):
            self.skipTest("git no tersedia")
        self.init_runtime()
        subprocess.run(["git", "init"], cwd=self.tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "pakem-test@example.invalid"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "Pakem Test"], cwd=self.tmp, check=True)
        (self.tmp / "tracked.txt").write_text("baseline")
        subprocess.run(["git", "add", "."], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=self.tmp, capture_output=True, check=True)
        run(self.tmp, "runtime", "transition", "ready", vendored=True)
        run(self.tmp, "runtime", "transition", "executing", vendored=True)
        cp = run(self.tmp, "runtime", "checkpoint", "--label", "clean git", "--json", vendored=True)
        checkpoint_id = json.loads(cp.stdout)["checkpoint"]["checkpointId"]
        (self.tmp / "tracked.txt").write_text("user changes must stay")
        recovered = run(self.tmp, "runtime", "recover", checkpoint_id, "--json", vendored=True)
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        data = json.loads(recovered.stdout)
        self.assertTrue(data["recovery"]["drift"]["working_tree_changed"])
        self.assertEqual((self.tmp / "tracked.txt").read_text(), "user changes must stay")

    def test_active_workflow_cannot_be_replaced(self):
        self.init_runtime()
        r = run(self.tmp, "runtime", "init", "different goal", "--new", vendored=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("active workflow must not be overwritten", r.stderr)

    def test_policy_requires_high_risk_and_one_time_approval(self):
        self.init_runtime()
        args = ("policy", "check", "--category", "deploy", "--risk", "high", "--target", "staging", "--json")
        r = run(self.tmp, *args, vendored=True)
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        self.assertEqual(json.loads(r.stdout)["decision"], "require_approval")
        grant = run(self.tmp, "policy", "approve", "--category", "deploy", "--risk", "high",
                    "--target", "staging", "--reason", "user approved staging release", "--json", vendored=True)
        self.assertEqual(grant.returncode, 0, grant.stderr + grant.stdout)
        approval_id = json.loads(grant.stdout)["approval"]["approvalId"]
        check = run(self.tmp, "policy", "check", "--category", "deploy", "--risk", "high",
                    "--target", "staging", "--approval-id", approval_id, "--json", vendored=True)
        self.assertEqual(check.returncode, 0, check.stderr + check.stdout)
        self.assertEqual(json.loads(check.stdout)["decision"], "allow")
        reused = run(self.tmp, "policy", "check", "--category", "deploy", "--risk", "high",
                     "--target", "staging", "--approval-id", approval_id, "--json", vendored=True)
        self.assertEqual(reused.returncode, 3)
        self.assertEqual(json.loads(reused.stdout)["decision"], "require_approval")

    def test_approval_is_bound_to_scope_and_workflow(self):
        self.init_runtime()
        grant = run(self.tmp, "policy", "approve", "--category", "destructive", "--risk", "critical",
                    "--target", "db/prod", "--reason", "maintenance approval", "--json", vendored=True)
        approval_id = json.loads(grant.stdout)["approval"]["approvalId"]
        wrong_target = run(self.tmp, "policy", "check", "--category", "destructive", "--risk", "critical",
                           "--target", "db/staging", "--approval-id", approval_id, "--json", vendored=True)
        self.assertEqual(wrong_target.returncode, 3)

    def test_denied_policy_cannot_be_overridden_by_approval(self):
        self.init_runtime()
        path = self.tmp / ".pakem" / "POLICY.json"
        policy = json.loads(path.read_text())
        policy["deniedCategories"] = ["security"]
        path.write_text(json.dumps(policy))
        r = run(self.tmp, "policy", "check", "--category", "security", "--risk", "critical", "--json", vendored=True)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout)["decision"], "deny")

    def test_lifecycle_hook_dispatch_is_policy_aware_and_does_not_log_payload(self):
        self.init_runtime()
        secret_like = "DO_NOT_PERSIST_THIS_PAYLOAD"
        payload_file = self.tmp / "hook.json"
        payload_file.write_text(json.dumps({"category": "deploy", "risk": "critical",
                                            "target": "production", "note": secret_like}))
        r = run(self.tmp, "runtime", "hook", "task.before", "--payload-file", str(payload_file), "--json", vendored=True)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(json.loads(r.stdout)["decision"], "require_approval")
        receipt = (self.tmp / ".pakem" / "runtime" / "hooks.jsonl").read_text()
        self.assertNotIn(secret_like, receipt)
        self.assertIn("payloadHash", receipt)

    def test_approval_command_requires_reason(self):
        self.init_runtime()
        r = run(self.tmp, "policy", "approve", "--category", "deploy", vendored=True)
        self.assertNotEqual(r.returncode, 0)

    def test_upgrade_installs_runtime_but_preserves_user_policy(self):
        self.init_app("--adapter", "none")
        policy_path = self.tmp / ".pakem" / "POLICY.json"
        policy = json.loads(policy_path.read_text())
        policy["autonomy"] = "guarded_autonomous"
        policy_path.write_text(json.dumps(policy))
        (self.tmp / ".pakem" / "pakem_core" / "runtime.py").unlink()
        shutil.rmtree(self.tmp / ".pakem" / "runtime" / "v1")
        r = run(self.tmp, "upgrade")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue((self.tmp / ".pakem" / "pakem_core" / "runtime.py").is_file())
        self.assertTrue((self.tmp / ".pakem" / "runtime" / "v1" / "workflow.schema.json").is_file())
        self.assertEqual(json.loads(policy_path.read_text())["autonomy"], "guarded_autonomous")


    def test_autonomy_modes_have_distinct_command_behavior(self):
        self.init_runtime()
        # Assisted allows routine code edits, but pauses for medium-risk shell commands.
        write_decision = run(self.tmp, "policy", "check", "--category", "write", "--risk", "medium", "--json", vendored=True)
        self.assertEqual(json.loads(write_decision.stdout)["decision"], "allow")
        command_decision = run(self.tmp, "policy", "check", "--category", "command", "--risk", "medium", "--json", vendored=True)
        self.assertEqual(command_decision.returncode, 3)
        path = self.tmp / ".pakem" / "POLICY.json"
        policy = json.loads(path.read_text())
        policy["autonomy"] = "guarded_autonomous"
        path.write_text(json.dumps(policy))
        guarded = run(self.tmp, "policy", "check", "--category", "command", "--risk", "medium", "--json", vendored=True)
        self.assertEqual(guarded.returncode, 0, guarded.stdout + guarded.stderr)
        policy["autonomy"] = "manual"
        path.write_text(json.dumps(policy))
        manual = run(self.tmp, "policy", "check", "--category", "write", "--risk", "low", "--json", vendored=True)
        self.assertEqual(manual.returncode, 3)

    def test_context_snapshot_exposes_runtime_state_and_policy(self):
        self.init_runtime()
        r = run(self.tmp, "context", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        data = json.loads(r.stdout)
        self.assertTrue(data["runtime"]["enabled"])
        self.assertEqual(data["runtime"]["workflow"]["state"], "planning")
        self.assertEqual(data["runtime"]["autonomy"], "assisted")
        self.assertIn(".pakem/POLICY.json", data["read_first"])

    def test_policy_validation_rejects_unknown_and_duplicate_fields(self):
        self.init_runtime()
        path = self.tmp / ".pakem" / "POLICY.json"
        policy = json.loads(path.read_text())
        policy["approvalRequiredFor"] = ["deploy", "deploy"]
        path.write_text(json.dumps(policy))
        r = run(self.tmp, "policy", "show", "--json", vendored=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("array of unique", r.stderr)

    def test_lifecycle_hook_allows_low_risk_verified_command(self):
        self.init_runtime()
        r = run(self.tmp, "runtime", "hook", "verification.before", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(json.loads(r.stdout)["decision"], "allow")

    def test_runtime_protocol_events_are_validated(self):
        self.init_runtime()
        run(self.tmp, "runtime", "transition", "ready", vendored=True)
        events = run(self.tmp, "events", "--json", vendored=True)
        self.assertEqual(events.returncode, 0, events.stderr)
        names = {item["event"] for item in json.loads(events.stdout)["events"]}
        self.assertIn("runtime.workflow.initialized", names)
        self.assertIn("runtime.state.transitioned", names)



class MultiAgentCoordinationTests(Base):
    def init_team(self):
        self.init_app("--adapter", "none")
        r = run(self.tmp, "team", "init", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def register(self, agent_id, role="worker", *capabilities):
        args = ["team", "register", agent_id, "--role", role]
        for cap in capabilities:
            args += ["--capability", cap]
        r = run(self.tmp, *args, "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def add(self, task_id="T1", title="Implement a feature", *extra):
        r = run(self.tmp, "team", "add", task_id, "--title", title, *extra, "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def test_init_installs_coordination_core_schema_and_gitignore(self):
        self.init_app("--adapter", "none")
        for rel in (
            ".pakem/pakem_core/coordination.py",
            ".pakem/coordination/v1/README.md",
            ".pakem/coordination/v1/board.schema.json",
            ".pakem/coordination/v1/event.schema.json",
            ".pakem/coordination/v1/status.schema.json",
        ):
            self.assertTrue((self.tmp / rel).is_file(), rel)
        self.assertIn(".pakem/team/", (self.tmp / ".gitignore").read_text())

    def test_review_requires_reviewer_role(self):
        self.init_team()
        self.register("worker", "worker")
        self.register("peer", "worker")
        self.register("qa", "reviewer")
        self.add("T1", "Implement module")
        run(self.tmp, "team", "claim", "T1", "--agent", "worker", vendored=True)
        run(self.tmp, "team", "submit", "T1", "--agent", "worker", "--summary", "done",
            "--evidence", "tests/test_x.py", vendored=True)
        # worker lain bukan implementer, tapi tetap tidak boleh review: butuh role.
        blocked = run(self.tmp, "team", "review", "T1", "--reviewer", "peer", "--decision", "approve", vendored=True)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("role reviewer", blocked.stderr)
        allowed = run(self.tmp, "team", "review", "T1", "--reviewer", "qa", "--decision", "approve",
                      "--json", vendored=True)
        self.assertEqual(allowed.returncode, 0, allowed.stderr + allowed.stdout)
        self.assertEqual(json.loads(allowed.stdout)["state"], "done")

    def test_dependency_gate_and_two_phase_independent_review(self):
        self.init_team()
        self.register("lead", "lead")
        self.register("worker", "reviewer", "python")
        self.register("reviewer", "reviewer")
        self.add("T1", "Implement module", "--files", "src/mod.py", "tests/test_mod.py", "--capability", "python")
        self.add("T2", "Integrate module", "--depends-on", "T1", "--files", "src/app.py")
        blocked = run(self.tmp, "team", "claim", "T2", "--agent", "worker", "--json", vendored=True)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("dependencies not done yet", blocked.stderr)
        run(self.tmp, "team", "assign", "T1", "--agent", "worker", "--by", "lead", vendored=True)
        run(self.tmp, "team", "claim", "T1", "--agent", "worker", vendored=True)
        submitted = run(self.tmp, "team", "submit", "T1", "--agent", "worker", "--summary", "Implemented module",
                        "--evidence", "tests/test_mod.py", "--evidence", "commit:abc123", "--json", vendored=True)
        self.assertEqual(submitted.returncode, 0, submitted.stderr + submitted.stdout)
        self.assertEqual(json.loads(submitted.stdout)["state"], "review")
        self_review = run(self.tmp, "team", "review", "T1", "--reviewer", "worker", "--decision", "approve", vendored=True)
        self.assertEqual(self_review.returncode, 2)
        self.assertIn("reviewer must not be the implementer", self_review.stderr)
        approved = run(self.tmp, "team", "review", "T1", "--reviewer", "reviewer", "--decision", "approve", "--json", vendored=True)
        self.assertEqual(approved.returncode, 0, approved.stderr + approved.stdout)
        self.assertEqual(json.loads(approved.stdout)["state"], "done")
        claim_child = run(self.tmp, "team", "claim", "T2", "--agent", "worker", "--json", vendored=True)
        self.assertEqual(claim_child.returncode, 0, claim_child.stderr + claim_child.stdout)

    def test_claim_lease_is_exclusive_and_expired_lease_can_be_reclaimed(self):
        self.init_team()
        self.register("alpha")
        self.register("beta")
        self.add()
        first = run(self.tmp, "team", "claim", "T1", "--agent", "alpha", "--json", vendored=True)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        second = run(self.tmp, "team", "claim", "T1", "--agent", "beta", "--json", vendored=True)
        self.assertEqual(second.returncode, 2)
        self.assertIn("is claimed by", second.stderr)
        board_path = self.tmp / ".pakem" / "team" / "board.json"
        board = json.loads(board_path.read_text())
        board["tasks"]["T1"]["leaseExpiresAt"] = "2000-01-01T00:00:00+00:00"
        board_path.write_text(json.dumps(board))
        reclaimed = run(self.tmp, "team", "claim", "T1", "--agent", "beta", "--json", vendored=True)
        self.assertEqual(reclaimed.returncode, 0, reclaimed.stderr + reclaimed.stdout)
        self.assertEqual(json.loads(reclaimed.stdout)["ownerAgent"], "beta")

    def test_two_processes_cannot_claim_the_same_open_task(self):
        self.init_team()
        self.register("alpha")
        self.register("beta")
        self.add()
        script = str(self.tmp / ".pakem" / "pakem.py")
        commands = [[sys.executable, script, "team", "claim", "T1", "--agent", agent, "--json"]
                    for agent in ("alpha", "beta")]
        processes = [subprocess.Popen(cmd, cwd=self.tmp, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for cmd in commands]
        results = [proc.communicate(timeout=20) + (proc.returncode,) for proc in processes]
        self.assertEqual(sorted(item[2] for item in results), [0, 2], results)
        status = json.loads(run(self.tmp, "team", "status", "--json", vendored=True).stdout)
        self.assertEqual(status["summary"]["claimed"], 1)

    def test_handoff_requires_current_owner_and_capability_match(self):
        self.init_team()
        self.register("alpha", "worker", "python")
        self.register("beta", "worker", "python")
        self.register("gamma", "worker", "rust")
        self.add("T1", "Python task", "--capability", "python")
        run(self.tmp, "team", "claim", "T1", "--agent", "alpha", vendored=True)
        mismatch = run(self.tmp, "team", "handoff", "T1", "--from-agent", "alpha", "--to-agent", "gamma", "--note", "wrong skill", vendored=True)
        self.assertEqual(mismatch.returncode, 2)
        handoff = run(self.tmp, "team", "handoff", "T1", "--from-agent", "alpha", "--to-agent", "beta", "--note", "Continue implementation", "--json", vendored=True)
        self.assertEqual(handoff.returncode, 0, handoff.stderr + handoff.stdout)
        self.assertEqual(json.loads(handoff.stdout)["assignedAgent"], "beta")
        self.assertEqual(json.loads(handoff.stdout)["state"], "open")
        old_owner = run(self.tmp, "team", "claim", "T1", "--agent", "alpha", vendored=True)
        self.assertEqual(old_owner.returncode, 2)
        new_owner = run(self.tmp, "team", "claim", "T1", "--agent", "beta", vendored=True)
        self.assertEqual(new_owner.returncode, 0, new_owner.stderr + new_owner.stdout)

    def test_rework_reopens_task_and_preserves_review_receipt(self):
        self.init_team()
        self.register("worker")
        self.register("reviewer", "reviewer")
        self.add()
        run(self.tmp, "team", "claim", "T1", "--agent", "worker", vendored=True)
        run(self.tmp, "team", "submit", "T1", "--agent", "worker", "--summary", "First pass",
            "--evidence", "tests/result.txt", vendored=True)
        r = run(self.tmp, "team", "review", "T1", "--reviewer", "reviewer", "--decision", "rework", "--note", "Add edge test", "--json", vendored=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        task = json.loads(r.stdout)
        self.assertEqual(task["state"], "open")
        self.assertEqual(task["lastReview"]["decision"], "rework")
        self.assertEqual(task["assignedAgent"], "worker")
        self.assertIsNone(task["submission"])

    def test_file_scope_rejects_traversal_absolute_and_windows_drive(self):
        self.init_team()
        for item in ("../secret", "/etc/passwd", "C:\\Windows\\system.ini"):
            r = run(self.tmp, "team", "add", "T" + str(len(item)), "--title", "Unsafe", "--files", item, vendored=True)
            self.assertEqual(r.returncode, 2, item)
            self.assertIn("relative path", r.stderr)

    def test_context_doctor_and_event_ledger_surface_team_state(self):
        self.init_team()
        self.register("worker")
        self.add()
        context = run(self.tmp, "context", "--json", vendored=True)
        self.assertEqual(context.returncode, 0, context.stderr + context.stdout)
        parsed = json.loads(context.stdout)
        self.assertTrue(parsed["team"]["enabled"])
        self.assertIn("multi_agent_coordination", parsed["interfaces"])
        events = run(self.tmp, "team", "events", "--json", vendored=True)
        self.assertEqual(events.returncode, 0, events.stderr + events.stdout)
        event_data = json.loads(events.stdout)
        self.assertEqual(event_data["total"], 2)
        self.assertEqual(event_data["corruptLines"], [])
        doctor = run(self.tmp, "doctor", "--json", vendored=True)
        self.assertIn(doctor.returncode, (0, 1), doctor.stderr + doctor.stdout)
        levels = [x["message"] for x in json.loads(doctor.stdout)["issues"]]
        self.assertTrue(any("Coordination module installed" in x for x in levels))
        self.assertTrue(any("team board: 1 agents, 1 tasks" in x for x in levels))

    def test_coordination_json_schemas_validate_board_and_events(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        self.init_team()
        self.register("worker")
        self.add()
        board = json.loads((self.tmp / ".pakem" / "team" / "board.json").read_text())
        schema = json.loads((self.tmp / ".pakem" / "coordination" / "v1" / "board.schema.json").read_text())
        jsonschema.validate(board, schema)
        status = json.loads(run(self.tmp, "team", "status", "--json", vendored=True).stdout)
        status_schema = json.loads((self.tmp / ".pakem" / "coordination" / "v1" / "status.schema.json").read_text())
        jsonschema.validate(status, status_schema)
        events = json.loads(run(self.tmp, "team", "events", "--json", vendored=True).stdout)["events"]
        event_schema = json.loads((self.tmp / ".pakem" / "coordination" / "v1" / "event.schema.json").read_text())
        for event in events:
            jsonschema.validate(event, event_schema)

    def test_upgrade_installs_coordination_and_preserves_team_board(self):
        self.init_team()
        self.register("worker")
        self.add()
        board_before = (self.tmp / ".pakem" / "team" / "board.json").read_text()
        policy_path = self.tmp / ".pakem" / "POLICY.json"
        policy_before = json.loads(policy_path.read_text())
        policy_before["autonomy"] = "guarded_autonomous"
        policy_path.write_text(json.dumps(policy_before))
        (self.tmp / ".pakem" / "pakem_core" / "coordination.py").unlink()
        shutil.rmtree(self.tmp / ".pakem" / "coordination" / "v1")
        r = run(self.tmp, "upgrade")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue((self.tmp / ".pakem" / "pakem_core" / "coordination.py").is_file())
        self.assertTrue((self.tmp / ".pakem" / "coordination" / "v1" / "board.schema.json").is_file())
        self.assertTrue((self.tmp / ".pakem" / "coordination" / "v1" / "status.schema.json").is_file())
        self.assertEqual((self.tmp / ".pakem" / "team" / "board.json").read_text(), board_before)
        self.assertEqual(json.loads(policy_path.read_text())["autonomy"], "guarded_autonomous")
