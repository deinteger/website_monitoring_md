"""Claude 채팅용 스킬 zip: 구조 검사 + 압축을 푼 폴더만으로 실제 점검이 동작하는지 검증."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import chat_state  # noqa: E402
import fixture_site as fx  # noqa: E402
import make_claude_skill  # noqa: E402


class ChatSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]
        assert make_claude_skill.main() == 0
        cls.zip = os.path.join(ROOT, "dist", "homepage-inspection-claude-skill.zip")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(self.tmp)
        self.skill = os.path.join(self.tmp, "homepage-inspection")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_structure(self):
        with zipfile.ZipFile(self.zip) as z:
            names = z.namelist()
        self.assertTrue(all(n.startswith("homepage-inspection/") for n in names))     # 폴더 하나로 압축
        self.assertIn("homepage-inspection/SKILL.md", names)
        self.assertFalse([n for n in names if "/tests/" in n or "/workspace/" in n or "make_release" in n])
        text = open(os.path.join(self.skill, "SKILL.md"), encoding="utf-8").read()
        m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
        self.assertEqual(m.group(1), "homepage-inspection")
        self.assertLess(len(m.group(2)), 1024)
        for ref in re.findall(r"`((?:core|scripts|config\.example)/[\w./\-]+)`", text):
            self.assertTrue(os.path.exists(os.path.join(self.skill, ref)), ref)
        for ref in re.findall(r"SKILL_DIR/(scripts/[\w./]+\.py)", text):
            self.assertTrue(os.path.exists(os.path.join(self.skill, ref)), ref)

    def run_py(self, script, *args):
        r = subprocess.run([sys.executable, os.path.join(self.skill, "scripts", script)] + list(args), capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")

    def test_standalone_flow_with_state_roundtrip(self):
        fx.STATE.pages.clear()
        fx.STATE.pages["/notice"] = fx.board([("a", "2026-08-24"), ("b", "2026-08-20"), ("c", "2026-08-01")])
        ws1, ws2 = os.path.join(self.tmp, "ws1"), os.path.join(self.tmp, "ws2")
        fx.write_workspace(ws1, self.port, [{"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily",
                                              "region": {"tag": "table", "class": "board"}}])
        code, out = self.run_py("collect.py", "--workspace", ws1, "--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 0, out)
        state = os.path.join(self.tmp, "state.zip")
        code, out = self.run_py("chat_state.py", "pack", "--workspace", ws1, "--output", state)
        self.assertEqual(code, 0, out)
        with zipfile.ZipFile(state) as z:
            names = set(z.namelist())
        self.assertTrue({"site-profile.json", "cache.json", "history/2026-08-26.json"} <= names)
        self.assertFalse([n for n in names if n.startswith("runs/")])
        # 새 대화(새 컨테이너)에서 상태를 올려 이어서 증분 점검
        code, out = self.run_py("chat_state.py", "unpack", "--input", state, "--workspace", ws2)
        self.assertEqual(code, 0, out)
        code, out = self.run_py("collect.py", "--workspace", ws2, "--mode", "incremental", "--today", "2026-08-27")
        self.assertEqual(code, 0, out)
        summ = json.load(open(os.path.join(ws2, "runs", "2026-08-27", "run-summary.json"), encoding="utf-8"))
        self.assertFalse(summ["boards_total"] == 0)
        self.assertEqual(summ["ai_review_items"], 0)       # 이전 상태가 이어져 변경 없는 게시판은 AI 대상이 아님

    def test_unpack_rejects_path_traversal(self):
        evil = os.path.join(self.tmp, "evil.zip")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../escape.txt", "x")
        with self.assertRaises(SystemExit):
            chat_state.unpack(evil, os.path.join(self.tmp, "ws"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.txt")))
        evil2 = os.path.join(self.tmp, "evil2.zip")
        with zipfile.ZipFile(evil2, "w") as z:
            z.writestr("unexpected.py", "x")
        with self.assertRaises(SystemExit):
            chat_state.unpack(evil2, os.path.join(self.tmp, "ws"))


if __name__ == "__main__":
    unittest.main()
