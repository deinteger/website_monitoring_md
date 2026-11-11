import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import collect  # noqa: E402
import fixture_site as fx  # noqa: E402
import monlib as ml  # noqa: E402

D = dt.date


class LibTests(unittest.TestCase):
    def test_add_months_clamp(self):
        self.assertEqual(ml.add_months(D(2026, 5, 31), -3), D(2026, 2, 28))
        self.assertEqual(ml.add_months(D(2026, 8, 26), -3), D(2026, 5, 26))
        self.assertEqual(ml.add_months(D(2026, 1, 15), -3), D(2025, 10, 15))

    def test_stale_boundary(self):
        today = D(2026, 7, 30)  # core/recency-rules.md 예시
        self.assertFalse(ml.is_stale(D(2026, 5, 1), today))
        self.assertTrue(ml.is_stale(D(2026, 4, 30), today))
        self.assertTrue(ml.is_stale(D(2026, 4, 29), today))

    def test_due_by_cycle(self):
        t = D(2026, 8, 26)
        self.assertTrue(ml.due_by_cycle("daily", D(2026, 8, 26), t))
        self.assertFalse(ml.due_by_cycle("weekly", D(2026, 8, 20), t))
        self.assertTrue(ml.due_by_cycle("weekly", D(2026, 8, 19), t))
        self.assertFalse(ml.due_by_cycle("monthly", D(2026, 7, 27), t))
        self.assertTrue(ml.due_by_cycle("monthly", D(2026, 7, 26), t))
        self.assertTrue(ml.due_by_cycle("quarterly", D(2026, 5, 26), t))
        self.assertFalse(ml.due_by_cycle("quarterly", D(2026, 5, 27), t))
        self.assertTrue(ml.due_by_cycle("weekly", None, t))

    def test_parse_dates_formats(self):
        txt = "등록 2026-08-24 / 2026.8.3 / 2026/07/01 / 2026년 6월 5일 / 2026-13-40"
        self.assertEqual(ml.parse_dates(txt), [D(2026, 8, 24), D(2026, 8, 3), D(2026, 7, 1), D(2026, 6, 5)])

    def test_mask_pii(self):
        s = ml.mask_pii("문의 031-123-4567, 010-1234-5678 a.b@example.go.kr 901010-1234567")
        self.assertNotIn("4567", s)
        self.assertNotIn("5678", s)
        self.assertNotIn("a.b@", s)
        self.assertNotIn("1234567", s)
        self.assertIn("031-***-****", s)
        self.assertIn("@example.go.kr", s)

    def test_find_elements_nested(self):
        html = '<div class="a"><div class="b">x</div><div class="b">y</div></div><div class="a">z</div>'
        self.assertEqual(ml.find_elements(html, "div", "a"), ['<div class="b">x</div><div class="b">y</div>', "z"])


class CollectTests(unittest.TestCase):
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
        fx.STATE.pages.update({
            "/notice": fx.board([("새 공지", "2026-08-24"), ("공지2", "2026-08-20"), ("공지3", "2026-08-01")],
                                '<a href="/files/a.pdf">첨부</a> <a href="/files/missing.pdf">깨진첨부</a>'),
            "/stale": fx.board([("옛글", "2026-05-26"), ("더옛글", "2026-04-01")]),
            "/edge": fx.board([("경계 다음날", "2026-05-27"), ("옛글", "2026-04-01")]),
            "/irregular": fx.board([("연례", "2025-11-04")]),
            "/nodate": "<html><head><title>빈</title></head><body><p>안내 문구만 있음</p></body></html>",
            "/about": "<html><head><title>소개</title></head><body>기관 소개 2020-01-01 설립</body></html>",
            "/view/1": "<html>ok</html>",
        })
        boards = [
            {"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily", "region": {"tag": "table", "class": "board"}},
            {"id": "stale", "name": "지연", "url": "/stale", "cycle": "weekly", "region": {"tag": "table", "class": "board"}},
            {"id": "edge", "name": "경계", "url": "/edge", "cycle": "weekly", "region": {"tag": "table", "class": "board"}},
            {"id": "irreg", "name": "비정기", "url": "/irregular", "cycle": "monthly", "irregular": True},
            {"id": "nodate", "name": "무날짜", "url": "/nodate", "cycle": "daily"},
            {"id": "gone", "name": "삭제", "url": "/gone", "cycle": "daily"},
            {"id": "about", "name": "소개", "url": "/about", "type": "static", "cycle": "monthly"},
            {"id": "skip", "name": "제외", "url": "/skip", "exclude": True, "exclude_reason": "테스트 제외"},
        ]
        fx.write_workspace(self.ws, self.port, boards)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_collect(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = collect.main(["--workspace", self.ws] + list(args))
        return code, buf.getvalue()

    def load(self, day, name):
        with open(os.path.join(self.ws, "runs", day, name), encoding="utf-8") as f:
            return json.load(f)

    def statuses(self, day):
        return dict((b["id"], b["status"]) for b in self.load(day, "findings.json")["boards"])

    def test_full_run_statuses(self):
        code, _ = self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 0)
        st = self.statuses("2026-08-26")
        self.assertEqual(st["notice"], "정상")
        self.assertEqual(st["stale"], "게시 최신성 지연")        # 정확히 3개월 전 = 지연
        self.assertEqual(st["edge"], "정상")                     # 하루 뒤는 정상
        self.assertEqual(st["irreg"], "담당자 확인 필요")
        self.assertEqual(st["nodate"], "게시일 확인 불가")
        self.assertEqual(st["gone"], "404오류")
        self.assertEqual(st["about"], "정상")
        self.assertEqual(st["skip"], "제외")
        self.assertEqual(fx.STATE.hits.get("/skip", 0), 0)       # 제외 대상은 접속하지 않는다
        f = self.load("2026-08-26", "findings.json")["findings"]
        kinds = sorted((x["board_id"], x["kind"]) for x in f)
        self.assertIn(("notice", "link"), kinds)                 # 깨진 첨부
        links = [x for x in f if x["kind"] == "link"]
        self.assertEqual(len(links), 1)                          # 정상 첨부(a.pdf)·정상 글 링크는 오류 아님
        self.assertTrue(links[0]["detail"].startswith("첨부파일 오류") and "missing.pdf" in links[0]["detail"])
        self.assertTrue(all(x["state"] == "신규" for x in f))
        # 보고서 필드·파일
        for name in ("recency-status.csv", "inspection-details.csv", "ai-review-queue.json", "run-summary.json"):
            self.assertTrue(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", name)), name)
        with open(os.path.join(self.ws, "runs", "2026-08-26", "recency-status.csv"), encoding="utf-8-sig") as fh:
            header = fh.readline().strip().replace('"', "").split(",")
        self.assertEqual(header[:3], ["번호", "시스템구분", "콘텐츠영역"])
        self.assertTrue(os.path.exists(os.path.join(self.ws, "history", "2026-08-26.json")))

    def test_incremental_skips_recomputes_and_detects_change(self):
        self.run_collect("--mode", "full", "--today", "2026-08-26")
        fx.STATE.hits.clear()
        # 다음 날: 변경 없음. weekly/monthly 게시판은 방문하지 않아야 한다.
        self.run_collect("--mode", "incremental", "--today", "2026-08-27")
        self.assertEqual(fx.STATE.hits.get("/stale", 0), 0)      # 이미 지연: 방문하지 않고 날짜만 재계산
        self.assertEqual(fx.STATE.hits.get("/about", 0), 0)
        self.assertGreaterEqual(fx.STATE.hits.get("/edge", 0), 1)  # 오늘 새로 지연이 되는 게시판은 1회 재확인
        self.assertGreaterEqual(fx.STATE.hits.get("/notice", 0), 1)
        st = self.statuses("2026-08-27")
        self.assertEqual(st["edge"], "게시 최신성 지연")        # 2026-05-27은 8/27에 3개월 경계 -> 지연 전환
        stale_f = [x for x in self.load("2026-08-27", "findings.json")["findings"] if x["board_id"] == "stale"][0]
        self.assertEqual(stale_f["state"], "지속")
        self.assertEqual(stale_f["elapsed"], "약 3개월")
        q = self.load("2026-08-27", "ai-review-queue.json")["items"]
        reasons = dict((i["board_id"], i["reasons"]) for i in q)
        self.assertIn("newly_stale", reasons["edge"])             # 방문 없이도 신규 지연 감지
        self.assertNotIn("notice", reasons)                       # 변경 없는 게시판은 AI 대상 아님
        summ = self.load("2026-08-27", "run-summary.json")
        self.assertGreater(summ["from_cache"], 0)
        # 새 글 등록 -> 변경 감지
        fx.STATE.pages["/notice"] = fx.board([("더 새 공지", "2026-08-28"), ("새 공지", "2026-08-24"), ("공지2", "2026-08-20"), ("공지3", "2026-08-01")])
        self.run_collect("--mode", "incremental", "--today", "2026-08-28")
        q = self.load("2026-08-28", "ai-review-queue.json")["items"]
        r = dict((i["board_id"], i["reasons"]) for i in q)
        self.assertIn("changed", r["notice"])
        findings = self.load("2026-08-28", "findings.json")
        # 깨진 첨부 링크가 사라졌으므로 해결 처리
        self.assertTrue(any(x["kind"] == "link" for x in findings["resolved"]))
        self.assertEqual(self.statuses("2026-08-28")["notice"], "정상")

    def test_continuing_and_resolved(self):
        self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.run_collect("--mode", "incremental", "--today", "2026-08-27")
        f = self.load("2026-08-27", "findings.json")
        gone = [x for x in f["findings"] if x["board_id"] == "gone"][0]
        self.assertEqual(gone["state"], "지속")
        self.assertEqual(gone["first_seen"], "2026-08-26")
        fx.STATE.pages["/gone"] = fx.board([("복구", "2026-08-28")])
        self.run_collect("--mode", "incremental", "--today", "2026-08-28")
        f = self.load("2026-08-28", "findings.json")
        self.assertTrue(any(x["board_id"] == "gone" for x in f["resolved"]))

    def test_dry_run_makes_no_requests(self):
        code, out = self.run_collect("--dry-run", "--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertEqual(plan["to_fetch"], 7)
        self.assertEqual(sum(fx.STATE.hits.values()), 0)
        self.assertIn("user_agent", plan["request_policy"])

    def test_limit_and_resume(self):
        self.run_collect("--mode", "full", "--limit", "2", "--today", "2026-08-26")
        summ = self.load("2026-08-26", "run-summary.json")
        self.assertEqual(summ["visited"], 2)
        fx.STATE.hits.clear()
        self.run_collect("--mode", "full", "--resume", "--today", "2026-08-26")
        self.assertEqual(self.load("2026-08-26", "run-summary.json")["visited"], 7)

    def test_blocked_aborts(self):
        boards = [{"id": "b%d" % i, "name": "b", "url": "/blocked", "cycle": "daily"} for i in range(6)]
        fx.write_workspace(self.ws, self.port, boards, {"abort_after_blocked": 2, "max_concurrency": 1})
        code, _ = self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 2)
        self.assertLess(fx.STATE.hits.get("/blocked", 0), 6)       # 전부 두드리지 않고 중단
        self.assertTrue(self.load("2026-08-26", "run-summary.json")["partial"])

    def test_offsite_redirect(self):
        fx.write_workspace(self.ws, self.port, [{"id": "r", "name": "r", "url": "/redirect", "cycle": "daily"}])
        self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertEqual(self.statuses("2026-08-26")["r"], "리다이렉트오류")
        self.assertEqual(fx.STATE.hits.get("/elsewhere", 0), 0)    # 외부로 가는 리다이렉트는 따라가지 않는다

    def test_slow_response_hits_total_deadline(self):
        fx.write_workspace(self.ws, self.port, [{"id": "s", "name": "느림", "url": "/slow", "cycle": "daily"}],
                           {"max_total_sec": 1, "retries": 0})
        import time
        t0 = time.monotonic()
        self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertLess(time.monotonic() - t0, 2.9)                  # 서버는 3초 뒤 응답하지만 1초에 포기
        st = self.statuses("2026-08-26")["s"]
        self.assertEqual(st, "접속오류")
        cache = json.load(open(os.path.join(self.ws, "cache.json"), encoding="utf-8"))
        self.assertIn("시간 초과", cache["boards"]["s"]["fetch_error"])

    def test_consecutive_connection_failures_abort(self):
        boards = [{"id": "d%d" % i, "name": "d", "url": "/x", "cycle": "daily"} for i in range(8)]
        fx.write_workspace(self.ws, self.port, boards, {"abort_after_failures": 3, "max_concurrency": 1, "retries": 0})
        prof = json.load(open(os.path.join(self.ws, "site-profile.json"), encoding="utf-8"))
        for b in prof["boards"]:
            b["url"] = "http://127.0.0.1:1/x"                       # 아무도 듣지 않는 포트
        prof["allowed_domains"] = ["127.0.0.1"]
        json.dump(prof, open(os.path.join(self.ws, "site-profile.json"), "w", encoding="utf-8"), ensure_ascii=False)
        code, _ = self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 2)                                    # 계속 두드리지 않고 중단
        summ = self.load("2026-08-26", "run-summary.json")
        self.assertTrue(summ["partial"])
        self.assertTrue(any("연속" in w for w in summ["warnings"]))

    def test_korean_contact_in_user_agent_does_not_break_requests(self):
        """회귀: settings의 contact에 한글이 있으면 User-Agent 헤더 인코딩 오류로 모든 요청이 실패하던 결함."""
        fx.write_workspace(self.ws, self.port, [{"id": "n", "name": "공지", "url": "/notice", "cycle": "daily", "region": {"tag": "table", "class": "board"}}],
                           {"contact": "기획과 홍길동 (031-000-0000)", "user_agent": "점검키트/1.0"})
        code, _ = self.run_collect("--mode", "full", "--today", "2026-08-26")
        self.assertEqual(code, 0)
        self.assertEqual(self.statuses("2026-08-26")["n"], "정상")
        ua = ml.Fetcher(ml.load_settings(self.ws), []).ua
        ua.encode("ascii")                                            # 헤더로 보낼 수 있는 ASCII
        self.assertIn("%", ua)

    def test_probe(self):
        code, out = self.run_collect("--probe", "notice", "--today", "2026-08-26")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["latest_date"], "2026-08-24")
        self.assertTrue(data["region_found"])
        self.assertFalse(os.path.exists(os.path.join(self.ws, "cache.json")))


if __name__ == "__main__":
    unittest.main()


class HeadUnsupportedTests(unittest.TestCase):
    def test_host_without_head_support_is_not_asked_twice(self):
        import http.server
        import threading
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                seen.append("HEAD")
                self.send_response(405)
                self.end_headers()

            def do_GET(self):
                seen.append("GET")
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            f = ml.Fetcher(dict(ml.DEFAULT_SETTINGS, min_interval_sec=0, retry_wait_sec=0))
            base = "http://127.0.0.1:%d/" % srv.server_port
            for i in range(3):
                self.assertEqual(f.check_url(base + "p%d" % i).status, 200)
            self.assertEqual(seen.count("HEAD"), 1)
            self.assertEqual(seen.count("GET"), 3)
        finally:
            srv.shutdown()
            srv.server_close()
