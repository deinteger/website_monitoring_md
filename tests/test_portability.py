"""다중 AI 호환·로컬 출력 보장 검사."""
import http.server
import json
import os
import subprocess
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import judge  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    seen = {}

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        Handler.seen = {"path": self.path, "body": json.loads(self.rfile.read(n))}
        out = json.dumps({"output": [{"type": "message", "content": [{"type": "output_text", "text": "{\"ok\": 1}"}]}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class Portability(unittest.TestCase):
    def test_responses_provider(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            cfg = {"provider": "openai-responses", "model": "m", "api_key": "k", "base_url": "http://127.0.0.1:%d/v1" % srv.server_port}
            self.assertEqual(judge.call_llm("sys", "usr", cfg), '{"ok": 1}')
            self.assertEqual(Handler.seen["path"], "/v1/responses")
            self.assertEqual(Handler.seen["body"]["instructions"], "sys")
        finally:
            srv.shutdown()

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, ".git")), "git 저장소가 아님(배포본)")
    def test_workspace_is_gitignored(self):
        for rel in ("workspace/profile.json", "workspace/runs/x.csv", "dist/a.zip"):
            r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT)
            self.assertEqual(r.returncode, 0, rel)

    def test_gitignore_has_workspace_rule(self):
        t = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
        self.assertIn("workspace/*", t)

    def test_entry_files(self):
        for f in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "SKILL.md", ".clinerules/homepage-inspection.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f)


if __name__ == "__main__":
    unittest.main()


class GptBundle(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "scripts", "make_gpt_bundle.py")) and os.path.isdir(os.path.join(ROOT, ".git")), "저장소에서만")
    def test_bundle_builds(self):
        import make_gpt_bundle
        import zipfile
        self.assertLessEqual(len(make_gpt_bundle.INSTRUCTIONS), make_gpt_bundle.LIMIT)
        self.assertEqual(make_gpt_bundle.main(()), 0)
        out = os.path.join(ROOT, "dist", "gpt-bundle")
        self.assertTrue(os.path.isfile(os.path.join(out, "instructions.txt")))
        self.assertTrue(os.path.isfile(os.path.join(out, "knowledge", "rules.md")))
        names = zipfile.ZipFile(os.path.join(out, "kit.zip")).namelist()
        self.assertTrue(any(n.endswith("scripts/setup.py") for n in names))
        self.assertFalse(any("/workspace/" in n and not n.endswith(".gitkeep") for n in names))
