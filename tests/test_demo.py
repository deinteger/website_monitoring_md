import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import demo  # noqa: E402


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.ws = os.path.join(tempfile.mkdtemp(), "demo")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.ws), ignore_errors=True)

    def run_demo(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = demo.main(["--workspace", self.ws, "--today", "2026-11-11"])
        return code, out.getvalue()

    def load(self, name):
        with open(os.path.join(self.ws, "runs", "2026-11-11", name), encoding="utf-8") as f:
            return json.load(f)

    def test_demo_runs_end_to_end_without_network_or_keys(self):
        code, out = self.run_demo()
        self.assertEqual(code, 0, out)
        summ = self.load("run-summary.json")
        self.assertEqual(summ["status_counts"], {"정상": 4, "게시 최신성 지연": 1})      # 보도자료(120일 전)만 지연
        self.assertEqual(summ["findings"], 2)                                          # 지연 1 + 깨진 첨부 1
        typo = self.load("typo-judgement.json")
        self.assertEqual(typo["model"], "openai/demo-mock-llm")
        quotes = sorted(x["quote"] for it in typo["items"] for x in it["issues"])
        self.assertEqual(quotes, ["개최 되었습니다", "안내 드립니다니다", "하실수 있습니다"])      # 인용 검증을 통과한 지적만
        uiux = self.load("policy-uiux.json")
        res = dict((r["id"], r["auto"]) for r in uiux["results"])
        self.assertEqual(res["UX-H2"], "미충족(자동)")                                  # 의도적 결함: 로고 대체텍스트에 '로고'
        self.assertEqual(Counter(res.values())["충족(자동)"], 12)
        self.assertTrue(any("스크립트로 이동하는 껍데기" in w for w in uiux["warnings"]))  # 메인 주소가 스크립트 이동 껍데기
        portal = self.load("search-index-summary.json")
        self.assertEqual(portal["verdict_counts"], {"불법광고의심": 1, "정상": 1, "404오류": 1})
        self.assertTrue(os.path.exists(os.path.join(self.ws, "reports", "recent", "latest.md")))
        self.assertIn("모의 LLM", out)                                                  # 실제 AI가 아님을 명시

    def test_refuses_to_wipe_non_demo_folder(self):
        os.makedirs(self.ws)
        open(os.path.join(self.ws, "important.txt"), "w").write("x")
        code, _ = self.run_demo()
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "important.txt")))         # 표식 없는 폴더는 지우지 않는다


if __name__ == "__main__":
    unittest.main()
