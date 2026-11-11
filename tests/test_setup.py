import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import setup as st  # noqa: E402
import monlib as ml  # noqa: E402


def run(ws, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = st.main(["--workspace", ws] + list(args))
    return code, out.getvalue(), err.getvalue()


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.ws = os.path.join(self.d.name, "ws")

    def tearDown(self):
        self.d.cleanup()

    def test_full_flow_two_agencies_sites(self):
        self.assertEqual(run(self.ws, "init", "--site-name", "A기관", "--base-url", "https://www.example.com/", "--contact", "총무과")[0], 0)
        self.assertEqual(run(self.ws, "board", "add", "--id", "n1", "--name", "공지", "--url", "https://www.example.com/n", "--cycle", "daily")[0], 0)
        self.assertEqual(run(self.ws, "board", "add", "--id", "n2", "--name", "공지B", "--system", "B시스템", "--url", "https://example.com/n")[0], 0)
        prof = ml.load_profile(self.ws)
        self.assertIn("example.com", prof["allowed_domains"])
        self.assertEqual(run(self.ws, "board", "set", "n1", "cycle=weekly", "owner=기획과")[0], 0)
        self.assertEqual(ml.load_profile(self.ws)["boards"][0]["owner"], "기획과")
        self.assertEqual(run(self.ws, "board", "remove", "n2")[0], 0)
        self.assertEqual(len(ml.load_profile(self.ws)["boards"]), 1)
        c, out, _ = run(self.ws, "show")
        self.assertEqual(c, 0)
        self.assertIn("공지", out)

    def test_invalid_input_rejected_without_change(self):
        run(self.ws, "init", "--site-name", "A")
        run(self.ws, "board", "add", "--id", "n1", "--name", "공지", "--url", "https://www.example.com/n")
        before = open(os.path.join(self.ws, "site-profile.json"), encoding="utf-8").read()
        self.assertEqual(run(self.ws, "board", "add", "--id", "n1", "--name", "x", "--url", "https://www.example.com/")[0], 1)   # 중복
        self.assertEqual(run(self.ws, "board", "add", "--id", "bad id", "--name", "x", "--url", "https://www.example.com/")[0], 1)
        self.assertEqual(run(self.ws, "board", "add", "--id", "z", "--name", "x", "--url", "ftp://www.example.com/")[0], 1)
        self.assertEqual(run(self.ws, "board", "set", "n1", "foo=1")[0], 1)
        self.assertEqual(open(os.path.join(self.ws, "site-profile.json"), encoding="utf-8").read(), before)

    def test_settings_and_secret_guard(self):
        run(self.ws, "init")
        self.assertEqual(run(self.ws, "set", "stale_months", "2")[0], 0)
        self.assertEqual(ml.load_settings(self.ws)["stale_months"], 2)
        self.assertEqual(run(self.ws, "set", "typo_check.enabled", "yes")[0], 0)
        self.assertTrue(ml.load_settings(self.ws)["typo_check"]["enabled"])
        self.assertEqual(run(self.ws, "set", "nonexistent", "1")[0], 1)
        self.assertEqual(run(self.ws, "set", "stale_months", "abc")[0], 1)
        self.assertEqual(run(self.ws, "set", "llm.api_key", "sk-secret")[0], 1)
        self.assertNotIn("sk-secret", open(os.path.join(self.ws, "settings.json"), encoding="utf-8").read())

    def test_llm_command(self):
        run(self.ws, "init")
        c, out, _ = run(self.ws, "llm", "--provider", "anthropic", "--model", "m1", "--allow", "yes")
        self.assertEqual(c, 0)
        llm = ml.load_settings(self.ws)["llm"]
        self.assertTrue(llm["allowed"])
        self.assertEqual(llm["provider"], "anthropic")
        self.assertIn("LLM_API_KEY", out)
        self.assertEqual(run(self.ws, "llm", "--provider", "bogus")[0], 1)

    def test_import_draft(self):
        run(self.ws, "init", "--base-url", "https://www.example.com/")
        ml.save_json(os.path.join(self.ws, "site-profile.draft.json"), {"base_url": "https://www.example.com/", "boards": [
            {"id": "d1", "name": "초안1", "url": "https://www.example.com/d1", "cycle": "weekly"}]})
        self.assertEqual(run(self.ws, "board", "import-draft")[0], 0)
        self.assertEqual(ml.load_profile(self.ws)["boards"][0]["id"], "d1")


if __name__ == "__main__":
    unittest.main()
