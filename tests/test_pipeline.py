import contextlib
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import collect  # noqa: E402
import discover  # noqa: E402
import eval_judge  # noqa: E402
import fixture_site as fx  # noqa: E402
import judge  # noqa: E402
import make_release  # noqa: E402
import make_summary  # noqa: E402
import monlib as ml  # noqa: E402
import monthly_report  # noqa: E402
import run_all  # noqa: E402


def quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = fn(*a)
    return code, buf.getvalue()


class FakeLLM(http.server.BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLLM.calls.append((self.path, self.headers.get("Authorization"), body))
        payload = json.loads(body["messages"][1]["content"])
        out = []
        for it in payload["items"]:
            if it["board_id"] == "a":    # 원문에 실제 있는 구절을 인용
                out.append({"board_id": "a", "verdict": "현행화 의심", "severity": "보통", "confidence": "medium", "needs_human": True,
                            "issues": [{"type": "종료행사 현재형", "quote": "2024년 접수 중", "reason": "종료 시점 경과", "action": "문구 수정"}], "note": "x"})
            elif it["board_id"] == "b":  # 원문에 없는 구절 인용(환각)
                out.append({"board_id": "b", "verdict": "문구 개선", "severity": "낮음", "confidence": "high",
                            "issues": [{"type": "문구 오류", "quote": "존재하지 않는 문장", "reason": "r", "action": "a"}]})
            # c는 의도적으로 누락
        resp = {"choices": [{"message": {"content": "```json\n" + json.dumps({"items": out}, ensure_ascii=False) + "\n```"}}]}
        data = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class JudgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/v1" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        FakeLLM.calls.clear()
        d = os.path.join(self.ws, "runs", "2026-08-26")
        os.makedirs(d)
        items = [{"board_id": i, "name": "게시판" + i, "url": "http://127.0.0.1/" + i, "type": "board", "status": "정상", "irregular": False,
                  "recency_exempt": False, "latest_date": "2026-08-20", "previous_latest_date": None, "reasons": ["new_board"],
                  "latest_title": "t", "titles": ["2026-08-20 2024년 접수 중 안내"], "excerpt": "본문 내용"} for i in ("a", "b", "c")]
        with open(os.path.join(d, "ai-review-queue.json"), "w", encoding="utf-8") as f:
            json.dump({"date": "2026-08-26", "items": items}, f, ensure_ascii=False)
        os.environ.update({"LLM_API_KEY": "test-key", "LLM_MODEL": "m", "LLM_BASE_URL": self.base})

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)
        for k in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
            os.environ.pop(k, None)

    def test_refuses_without_opt_in(self):
        code, _ = quiet(judge.main, ["--workspace", self.ws])
        self.assertEqual(code, 3)
        self.assertEqual(FakeLLM.calls, [])      # 승인 전에는 아무것도 전송하지 않는다

    def test_dry_run(self):
        code, out = quiet(judge.main, ["--workspace", self.ws, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["items"], 3)
        self.assertEqual(FakeLLM.calls, [])

    def test_judgement_and_guardrails(self):
        code, _ = quiet(judge.main, ["--workspace", self.ws, "--yes-send-external"])
        self.assertEqual(code, 0)
        path, auth, body = FakeLLM.calls[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer test-key")
        self.assertIn("판단 기준", body["messages"][0]["content"])
        res = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "judgement.json"), encoding="utf-8"))
        by = dict((i["board_id"], i) for i in res["items"])
        self.assertEqual(by["a"]["verdict"], "현행화 의심")                 # 원문 인용 검증 통과
        self.assertTrue(by["a"]["issues"][0]["quote_verified"])
        self.assertEqual(by["b"]["verdict"], "담당자 확인 필요")            # 환각 인용은 하향
        self.assertIn("인용 검증 실패", by["b"]["note"])
        self.assertEqual(by["c"]["verdict"], "담당자 확인 필요")            # 누락 항목은 사람 확인
        self.assertEqual(len(res["items"]), 3)

    def test_max_items_guard(self):
        quiet(judge.main, ["--workspace", self.ws, "--yes-send-external", "--max-items", "1", "--batch-size", "1"])
        res = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "judgement.json"), encoding="utf-8"))
        self.assertEqual(len(res["items"]), 1)
        self.assertEqual(res["over_limit_skipped"], ["b", "c"])


class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.hits.clear()
        fx.STATE.pages.clear()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def collect(self, *args):
        return quiet(collect.main, ["--workspace", self.ws] + list(args))

    def test_monthly_numbers(self):
        region = {"tag": "table", "class": "board"}
        fx.write_workspace(self.ws, self.port, [
            {"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily", "region": region, "owner": "총무과"},
            {"id": "data", "name": "자료실", "url": "/data", "cycle": "weekly", "region": region, "owner": "기획과"}])
        fx.STATE.pages["/notice"] = fx.board([("n3", "2026-08-24"), ("n2", "2026-08-20"), ("n1", "2026-08-01"), ("j2", "2026-07-05"), ("j1", "2026-07-03")])
        fx.STATE.pages["/data"] = fx.board([("d2", "2026-05-26"), ("d1", "2026-04-01")])
        self.collect("--mode", "full", "--today", "2026-08-26")
        self.collect("--mode", "incremental", "--today", "2026-08-31")
        fx.STATE.pages["/notice"] = fx.board([("s3", "2026-09-09"), ("s2", "2026-09-08"), ("s1", "2026-09-02"), ("n3", "2026-08-24"),
                                              ("n2", "2026-08-20"), ("n1", "2026-08-01"), ("j2", "2026-07-05"), ("j1", "2026-07-03")])
        fx.STATE.pages["/data"] = fx.board([("d3", "2026-09-05"), ("d2", "2026-05-26"), ("d1", "2026-04-01")])
        self.collect("--mode", "incremental", "--today", "2026-09-10")

        code, _ = quiet(monthly_report.main, ["--workspace", self.ws, "--month", "2026-09"])
        self.assertEqual(code, 0)
        m = json.load(open(os.path.join(self.ws, "reports", "2026-09", "monthly-metrics.json"), encoding="utf-8"))
        self.assertEqual(m["recency"]["normal_rate"], 100.0)            # 2/2
        self.assertEqual(m["recency_prev"]["normal_rate"], 50.0)        # 8월말: 공지 정상, 자료실 지연 -> 1/2
        self.assertEqual(m["content_total"], 4)                         # 9월: 공지 3 + 자료실 1
        self.assertEqual(m["content_total_prev"], 3)                    # 8월: 공지 3 + 자료실 0
        self.assertEqual(sorted(m["updated"]), ["data", "notice"])
        self.assertEqual(m["transitions"]["improved"], ["data"])        # 지연 -> 정상
        self.assertEqual(m["findings"]["resolved"], 1)                  # 자료실 최신성 지적 해결
        self.assertEqual(m["findings"]["new"], 0)
        md = open(os.path.join(self.ws, "reports", "2026-09", "monthly-report.md"), encoding="utf-8").read()
        self.assertIn("+50.0%p", md)
        self.assertIn("총무과", md)
        self.assertIn("AI_COMMENT", md)
        self.assertIn("신규 등록 콘텐츠(게시글) 건수 | 4 | 3 | +1", md)

        # 첫 달(비교 기준 없음)도 오류 없이 생성
        code, _ = quiet(monthly_report.main, ["--workspace", self.ws, "--month", "2026-08"])
        self.assertEqual(code, 0)
        md8 = open(os.path.join(self.ws, "reports", "2026-08", "monthly-report.md"), encoding="utf-8").read()
        self.assertIn("비교 기준 없음", md8)

    def test_summary_without_ai_is_explicit(self):
        fx.STATE.pages["/notice"] = fx.board([("a", "2026-08-24"), ("b", "2026-08-20"), ("c", "2026-08-01")])
        fx.write_workspace(self.ws, self.port, [{"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily"},
                                                {"id": "gone", "name": "없음", "url": "/gone", "cycle": "daily"}])
        code, _ = quiet(run_all.main, ["--workspace", self.ws, "--mode", "full", "--today", "2026-08-26", "--judge", "no"])
        self.assertEqual(code, 0)
        md = open(os.path.join(self.ws, "runs", "2026-08-26", "inspection-summary.md"), encoding="utf-8").read()
        self.assertIn("AI 판단 미실시", md)
        self.assertIn("404오류", md)
        for sec in ("1. 점검 개요", "2. 종합 결과", "3. 확정 오류", "4. 게시 최신성 지연", "5. 현행화 의심", "6. 문구 개선사항",
                    "7. 담당자 확인 필요사항", "8. 점검 한계", "9. 후속 조치 제안"):
            self.assertIn(sec, md)

    def test_discover_builds_loadable_profile(self):
        base = "http://127.0.0.1:%d/" % self.port
        fx.STATE.pages["/"] = '<html><head><title>메인</title></head><body><a href="/notice">공지</a> <a href="/about">소개</a> <a href="/login">로그인</a></body></html>'
        fx.STATE.pages["/notice"] = fx.board([("a", "2026-08-24"), ("b", "2026-08-20"), ("c", "2026-08-01")])
        fx.STATE.pages["/about"] = "<html><head><title>소개</title></head><body>소개글</body></html>"
        os.makedirs(self.ws, exist_ok=True)
        with open(os.path.join(self.ws, "settings.json"), "w") as f:
            json.dump({"min_interval_sec": 0, "retries": 0}, f)
        code, _ = quiet(discover.main, ["--workspace", self.ws, "--base-url", base, "--today", "2026-08-26"])
        self.assertEqual(code, 0)
        draft = json.load(open(os.path.join(self.ws, "site-profile.draft.json"), encoding="utf-8"))
        types = dict((b["url"].split("/")[-1], b["type"]) for b in draft["boards"])
        self.assertEqual(types["notice"], "board")
        self.assertEqual(types["about"], "static")
        self.assertNotIn("login", types)                                 # 로그인류 URL 제외
        self.assertFalse(any("/view/" in b["url"] for b in draft["boards"]))   # 게시글 상세는 따라가지 않음
        nb = [b for b in draft["boards"] if b["type"] == "board"][0]
        self.assertEqual(nb["region"], {"tag": "table", "class": "board"})
        self.assertEqual(nb["cycle"], "daily")
        shutil.copy(os.path.join(self.ws, "site-profile.draft.json"), os.path.join(self.ws, "site-profile.json"))
        self.assertTrue(ml.load_profile(self.ws)["boards"])              # 초안이 그대로 수집기에서 로드 가능
        self.assertEqual(self.collect("--mode", "full", "--today", "2026-08-26")[0], 0)


class EvalTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "eval", "judgement-cases.json"), encoding="utf-8") as f:
            self.cases = json.load(f)["cases"]

    def test_cases_are_well_formed(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for c in self.cases:
            self.assertIn(c["expected"], judge.VERDICTS)
            self.assertTrue(c["item"]["board_id"] == c["id"])
            self.assertRegex(c["today"], r"^\d{4}-\d{2}-\d{2}$")

    def test_score(self):
        wrong_ids = set(["c01", "c02"])
        ask = lambda c: {"verdict": "정상" if c["id"] in wrong_ids and c["expected"] != "정상" else (  # noqa: E731
            "문구 개선" if c["id"] in wrong_ids else c["expected"]), "note": ""}
        acc, wrong, rows = eval_judge.score(self.cases, ask)
        self.assertEqual(len(rows), len(self.cases))
        self.assertEqual(sorted(w["id"] for w in wrong), ["c01", "c02"])
        self.assertAlmostEqual(acc, (len(self.cases) - 2) / float(len(self.cases)))

    def test_quote_basis_exists_for_flagged_cases(self):
        """정답 세트의 '의심' 사례가 입력 안에 근거 구절을 갖고 있는지(인용 검증이 통과 가능한지) 확인."""
        for c in self.cases:
            if c["expected"] in ("현행화 의심", "문구 개선"):
                src = " ".join(c["item"]["titles"]) + " " + c["item"]["excerpt"]
                self.assertTrue(len(src.strip()) > 10, c["id"])


class ReleaseTests(unittest.TestCase):
    def test_host_scan_flags_unknown_domain(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "a.md"), "w", encoding="utf-8") as f:
                f.write("문의 " + "https:" + "//www.realagency.go.kr/x 및 https://example.go.kr/")
            bad = make_release.scan_hosts(d, ["a.md"])
            self.assertEqual(list(bad), ["www.realagency.go.kr"])
        finally:
            shutil.rmtree(d)

    def test_release_excludes_workspace_data(self):
        ws_marker = os.path.join(make_release.ROOT, "workspace", "zz_private_marker.txt")
        with open(ws_marker, "w") as f:
            f.write("private")
        try:
            code, _ = quiet(make_release.main)
            self.assertEqual(code, 0)
            out = os.path.join(make_release.ROOT, "dist", "website-monitoring-kit-v%s" % ml.VERSION)
            allf = [os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs]
            self.assertFalse(any(x.startswith("workspace" + os.sep) and not x.endswith(".gitkeep") for x in allf))
            self.assertIn(os.path.join("scripts", "collect.py"), allf)
            self.assertIn(os.path.join(".claude", "skills", "homepage-inspection", "SKILL.md"), allf)
        finally:
            os.remove(ws_marker)


if __name__ == "__main__":
    unittest.main()
