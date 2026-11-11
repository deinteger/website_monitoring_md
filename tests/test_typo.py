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
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import collect  # noqa: E402
import fixture_site as fx  # noqa: E402
import judge  # noqa: E402
import make_summary  # noqa: E402
import monlib as ml  # noqa: E402

REGION = {"tag": "table", "class": "board"}
BODY = {"tag": "div", "class": "view-content"}


def post_page(text):
    return ('<html><head><title>글</title></head><body><div class="nav">메뉴 오타메뉴</div>'
            '<div class="view-content">%s</div><div id="footer">대표전화 02-111-2222</div></body></html>' % text)


def vk(title):
    return "/view/%d" % zlib.crc32(title.encode("utf-8"))


class FakeTypoLLM(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        payload = json.loads(body["messages"][1]["content"])
        out = []
        for it in payload["items"]:
            issues = []
            if "하실수" in it["text"]:
                issues.append({"type": "띄어쓰기", "quote": "하실수 있습니다", "suggestion": "하실 수 있습니다", "reason": "의존명사 띄어쓰기"})
            issues.append({"type": "오탈자", "quote": "본문에없는문장", "suggestion": "고침", "reason": "환각"})   # 버려져야 함
            issues.append({"type": "맞춤법", "quote": "신청", "suggestion": "신청", "reason": "수정안이 같음"})  # 버려져야 함
            out.append({"post_key": it["post_key"], "issues": issues, "confidence": "medium"})
        data = json.dumps({"choices": [{"message": {"content": json.dumps({"items": out}, ensure_ascii=False)}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TypoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]
        cls.llm = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeTypoLLM)
        threading.Thread(target=cls.llm.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.llm.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.hits.clear()
        fx.STATE.pages.clear()
        self.rows = [("n3", "2026-08-24"), ("n2", "2026-08-20"), ("n1", "2026-08-01")]
        fx.STATE.pages["/notice"] = fx.board(self.rows)
        for t, _ in self.rows:
            fx.STATE.pages[vk(t)] = post_page("신청 하실수 있습니다. 문의 031-123-4567 a@b.go.kr %s 본문입니다." % t)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)
        for k in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
            os.environ.pop(k, None)

    def setup_ws(self, board_extra=None, typo=None, boards=None):
        b = {"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily", "region": REGION, "body_region": BODY}
        b.update(board_extra or {})
        tc = {"enabled": True, "max_posts_per_board": 2, "max_posts_per_run": 30}
        tc.update(typo or {})
        fx.write_workspace(self.ws, self.port, boards or [b], {"typo_check": tc, "check_links": False})

    def collect(self, today, mode="incremental"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            return collect.main(["--workspace", self.ws, "--mode", mode, "--today", today])

    def queue(self, day):
        return json.load(open(os.path.join(self.ws, "runs", day, "typo-review-queue.json"), encoding="utf-8"))

    def test_newest_posts_only_with_body_masked_and_nav_excluded(self):
        self.setup_ws()
        self.collect("2026-08-26", "full")
        q = self.queue("2026-08-26")
        self.assertEqual([i["title"] for i in q["items"]], ["n3", "n2"])             # 게시판당 최신 2건
        t = q["items"][0]["text"]
        self.assertIn("하실수 있습니다", t)
        self.assertNotIn("오타메뉴", t)                                              # 본문 영역만 (메뉴 제외)
        self.assertNotIn("02-111-2222", t)                                           # 푸터 제외
        self.assertNotIn("4567", t)
        self.assertNotIn("a@b", t)                                                   # 개인정보 마스킹
        self.assertEqual(q["items"][0]["body_method"], "body_region")
        self.assertEqual(sum(fx.STATE.hits.get(vk(x), 0) for x, _ in self.rows), 2)  # 상세 요청은 2건뿐

    def test_each_post_checked_once_and_new_posts_queued(self):
        self.setup_ws()
        self.collect("2026-08-26", "full")
        self.collect("2026-08-27")
        self.assertEqual([i["title"] for i in self.queue("2026-08-27")["items"]], ["n1"])    # 남은 글
        self.collect("2026-08-28")
        self.assertEqual(self.queue("2026-08-28")["items"], [])                              # 재점검 없음
        hits_before = fx.STATE.hits.get(vk("n3"), 0)
        fx.STATE.pages[vk("n4")] = post_page("새 글 본문입니다.")
        fx.STATE.pages["/notice"] = fx.board([("n4", "2026-08-29")] + self.rows)
        self.collect("2026-08-29")
        self.assertEqual([i["title"] for i in self.queue("2026-08-29")["items"]], ["n4"])
        self.assertEqual(fx.STATE.hits.get(vk("n3"), 0), hits_before)                        # 이미 점검한 글은 다시 요청하지 않음

    def test_disabled_by_default_and_per_board_opt_out(self):
        fx.write_workspace(self.ws, self.port, [{"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily", "region": REGION}],
                           {"check_links": False})
        self.collect("2026-08-26", "full")
        self.assertFalse(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", "typo-review-queue.json")))
        self.assertEqual(sum(fx.STATE.hits.get(vk(x), 0) for x, _ in self.rows), 0)
        self.setup_ws({"typo_check": False})
        self.collect("2026-08-27", "full")
        self.assertEqual(self.queue("2026-08-27")["items"], [])

    def test_heuristic_body_when_no_profile_hint(self):
        for t, _ in self.rows:
            fx.STATE.pages[vk(t)] = ('<html><body><div class="gnb">메뉴 오타메뉴 메뉴 메뉴</div><div class="contents-wrap">%s</div>'
                                     '<div class="side">관련 링크 안내 광고</div></body></html>' % ("신청 하실수 있습니다. " * 8))
        self.setup_ws({"body_region": None})
        self.collect("2026-08-26", "full")
        it = self.queue("2026-08-26")["items"][0]
        self.assertEqual(it["body_method"], "heuristic")
        self.assertNotIn("오타메뉴", it["text"])

    def test_body_not_found_is_reported_and_not_retried(self):
        fx.STATE.pages[vk("n3")] = "<html><body><p>본문 영역 표시 없음</p></body></html>"
        self.setup_ws({"body_region": {"tag": "div", "class": "nothing"}}, {"max_posts_per_board": 1})
        self.collect("2026-08-26", "full")
        q = self.queue("2026-08-26")
        self.assertEqual(q["items"], [])
        self.assertTrue(any("body_region" in x["reason"] for x in q["skipped"]))
        h = fx.STATE.hits.get(vk("n3"), 0)
        self.collect("2026-08-27")
        self.assertEqual(fx.STATE.hits.get(vk("n3"), 0), h)         # 같은 글을 매일 다시 요청하지 않음

    def test_run_budget_defers_to_next_run(self):
        self.setup_ws(typo={"max_posts_per_board": 3, "max_posts_per_run": 1})
        self.collect("2026-08-26", "full")
        q = self.queue("2026-08-26")
        self.assertEqual(len(q["items"]), 1)
        self.assertTrue(any("상한" in x["reason"] for x in q["skipped"]))
        self.collect("2026-08-27")
        self.assertEqual(len(self.queue("2026-08-27")["items"]), 1)  # 못 한 글은 다음 실행에서 이어서 점검

    def test_judge_typo_and_summary(self):
        self.setup_ws()
        self.collect("2026-08-26", "full")
        os.environ.update({"LLM_API_KEY": "k", "LLM_MODEL": "m", "LLM_BASE_URL": "http://127.0.0.1:%d/v1" % self.llm.server_address[1]})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self.assertEqual(judge.main(["--workspace", self.ws, "--task", "typo"]), 3)          # 승인 전 거부
            self.assertEqual(judge.main(["--workspace", self.ws, "--task", "typo", "--yes-send-external"]), 0)
        j = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "typo-judgement.json"), encoding="utf-8"))
        self.assertEqual(len(j["items"]), 2)
        for it in j["items"]:
            self.assertEqual([x["quote"] for x in it["issues"]], ["하실수 있습니다"])       # 환각·무변경 수정안은 버림
            self.assertEqual(it["issues"][0]["suggestion"], "하실 수 있습니다")
        self.assertEqual(j["dropped_unverified"], 4)
        with contextlib.redirect_stdout(buf):
            make_summary.main(["--workspace", self.ws])
        md = open(os.path.join(self.ws, "runs", "2026-08-26", "inspection-summary.md"), encoding="utf-8").read()
        self.assertIn("게시글 본문 오타 점검", md)
        self.assertIn("하실 수 있습니다", md)
        self.assertIn("점검 2건 중 오류 없음 0건, 지적 2건", md)

    def test_summary_without_ai_says_not_judged(self):
        self.setup_ws()
        self.collect("2026-08-26", "full")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            make_summary.main(["--workspace", self.ws])
        md = open(os.path.join(self.ws, "runs", "2026-08-26", "inspection-summary.md"), encoding="utf-8").read()
        self.assertIn("게시글 본문 오타 점검", md)
        self.assertIn("AI 판단 미실시: 수집한 게시글 본문의 오타는 점검되지 않았습니다", md)


if __name__ == "__main__":
    unittest.main()
