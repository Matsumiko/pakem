import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pakem.py"
sys.path.insert(0, str(ROOT / "scripts"))

from pakem_core import git_worktree, mcp_server, protocol


def run(cwd: Path, *args: str, timeout: int = 30):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          text=True, capture_output=True, timeout=timeout, check=False)


def modern(method: str, params=None, request_id=1, version="2026-07-28"):
    values = dict(params or {})
    values["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "pakem-test", "version": "1.0"},
    }
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": values}


class Release100Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def init_project(self):
        result = run(self.tmp, "init", "--type", "oneoff", "--adapter", "none")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def init_git_project(self):
        self.init_project()
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "pakem-test@example.invalid"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "Pakem Test"], cwd=self.tmp, check=True)
        (self.tmp / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=self.tmp, check=True)

    def test_protocol_negotiation_intersection(self):
        result = protocol.negotiate("1.0", ["events.v1", "coordination.v1", "context.snapshot.v1", "future.ext"])
        self.assertTrue(result["compatible"])
        self.assertEqual(result["selected_version"], "1.0")
        self.assertEqual(result["common_capabilities"], ["context.snapshot.v1", "coordination.v1", "events.v1"])
        self.assertEqual(result["unsupported_peer_capabilities"], ["future.ext"])

    def test_protocol_negotiation_rejects_version_mismatch(self):
        result = protocol.negotiate("2.0", ["events.v1"])
        self.assertFalse(result["compatible"])
        self.assertIsNone(result["selected_version"])

    def test_init_installs_all_v1_capability_schema_and_core_modules(self):
        self.init_project()
        self.assertTrue((self.tmp / ".pakem/protocol/v1/capabilities.schema.json").is_file())
        self.assertTrue((self.tmp / ".pakem/pakem_core/protocol.py").is_file())
        self.assertTrue((self.tmp / ".pakem/pakem_core/mcp_server.py").is_file())
        self.assertTrue((self.tmp / ".pakem/pakem_core/git_worktree.py").is_file())
        self.assertTrue((self.tmp / ".pakem/adapters/mcp/v1/README.md").is_file())
        self.assertTrue((self.tmp / ".pakem/adapters/git-worktree/v1/README.md").is_file())
        self.assertIn(".pakem/worktrees/", (self.tmp / ".gitignore").read_text(encoding="utf-8"))

    def test_cli_protocol_negotiate(self):
        self.init_project()
        result = run(self.tmp, "protocol", "negotiate", "--peer-version", "1.0",
                     "--capability", "events.v1", "--json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["compatible"])

    def test_doctor_detects_protocol_mcp_and_worktree_installation(self):
        self.init_project()
        result = run(self.tmp, "doctor", "--json")
        self.assertIn(result.returncode, (0, 1), result.stderr + result.stdout)
        report = json.loads(result.stdout)
        messages = "\n".join(item["message"] for item in report["issues"])
        self.assertIn("Protocol negotiation installed", messages)
        self.assertIn("MCP stdio adapter installed", messages)
        self.assertIn("Git worktree adapter installed", messages)

    def test_mcp_discovery_and_tool_listing(self):
        self.init_project()
        response = mcp_server.handle_message(modern("server/discover"), self.tmp)
        self.assertEqual(response["result"]["supportedVersions"], ["2026-07-28"])
        self.assertEqual(response["result"]["capabilities"], {"tools": {"listChanged": False}})
        tools = mcp_server.handle_message(modern("tools/list"), self.tmp)
        names = [item["name"] for item in tools["result"]["tools"]]
        self.assertIn("pakem.context", names)
        self.assertIn("pakem.impact", names)
        self.assertNotIn("pakem.team.claim", names)

    def test_mcp_requires_per_request_meta_and_rejects_unknown_version(self):
        missing = mcp_server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}, self.tmp)
        self.assertEqual(missing["error"]["code"], -32602)
        wrong = mcp_server.handle_message(modern("server/discover", version="2025-11-25"), self.tmp)
        self.assertEqual(wrong["error"]["code"], -32022)
        self.assertEqual(wrong["error"]["data"]["supported"], ["2026-07-28"])

    def test_mcp_stdio_has_json_only_stdout(self):
        self.init_project()
        request = modern("server/discover")
        process = subprocess.run([sys.executable, str(self.tmp / ".pakem/pakem.py"), "mcp", "serve"],
                                 cwd=self.tmp, input=json.dumps(request) + "\n", text=True,
                                 capture_output=True, timeout=15, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        messages = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(messages), 1)
        self.assertIn("result", messages[0])

    def test_mcp_write_tools_are_bound_and_reviewer_role_scoped(self):
        self.init_project()
        from pakem_core import coordination
        coordination.initialize(self.tmp)
        coordination.register_agent(self.tmp, "worker", "worker", capabilities=[])
        coordination.register_agent(self.tmp, "reviewer", "reviewer", capabilities=[])
        worker_response = mcp_server.handle_message(modern("tools/list"), self.tmp,
                                                     allow_write=True, bound_agent_id="worker")
        worker_names = {x["name"] for x in worker_response["result"]["tools"]}
        self.assertIn("pakem.team.claim", worker_names)
        self.assertNotIn("pakem.team.review", worker_names)
        reviewer_response = mcp_server.handle_message(modern("tools/list"), self.tmp,
                                                       allow_write=True, bound_agent_id="reviewer")
        reviewer_names = {x["name"] for x in reviewer_response["result"]["tools"]}
        self.assertIn("pakem.team.review", reviewer_names)
        self.assertNotIn("pakem.team.assign", reviewer_names)

    def test_mcp_team_claim_uses_bound_agent_not_tool_argument(self):
        self.init_project()
        from pakem_core import coordination
        coordination.initialize(self.tmp)
        coordination.register_agent(self.tmp, "worker-a", "worker")
        coordination.register_agent(self.tmp, "worker-b", "worker")
        coordination.add_task(self.tmp, "T1", "test claim")
        response = mcp_server.handle_message(
            modern("tools/call", {"name": "pakem.team.claim", "arguments": {"task_id": "T1", "agent_id": "worker-b"}}),
            self.tmp, allow_write=True, bound_agent_id="worker-a")
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["ownerAgent"], "worker-a")

    def test_worktree_lifecycle_and_dirty_remove_guard(self):
        self.init_git_project()
        created = git_worktree.create(self.tmp, "T1", "worker")
        self.assertTrue(created["created"])
        child = self.tmp / created["path"]
        self.assertTrue(child.is_dir())
        listed = git_worktree.list_worktrees(self.tmp)
        self.assertEqual(listed["managed_count"], 1)
        (child / "dirty.txt").write_text("not committed\n", encoding="utf-8")
        with self.assertRaises(ValueError) as blocked:
            git_worktree.remove(self.tmp, created["path"])
        self.assertIn("uncommitted changes", str(blocked.exception))
        self.assertNotIn("fatal:", str(blocked.exception))
        removed = git_worktree.remove(self.tmp, created["path"], force=True)
        self.assertTrue(removed["removed"])
        self.assertFalse(child.exists())

    def test_worktree_rejects_paths_outside_managed_directory(self):
        self.init_git_project()
        outside = self.tmp / "outside"
        outside.mkdir()
        with self.assertRaises(ValueError):
            git_worktree.remove(self.tmp, str(outside))


if __name__ == "__main__":
    unittest.main()
