"""선택 모듈(Playwright) 테스트. playwright 가 없으면 건너뛴다.
실행 예) 가상환경의 파이썬으로: PW_TEST_CHROMIUM=/경로/chrome python -m unittest discover -s tests -k Render
"""
import contextlib
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

try:
    import playwright.sync_api  # noqa: F401
    HAVE_PW = True
except ImportError:
    HAVE_PW = False

CHROMIUM = os.environ.get("PW_TEST_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else "")
ROWS = [["JS 새 공지", "2026-08-24"], ["JS 공지2", "2026-08-20"], ["JS 공지3", "2026-08-01"]]


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.pages.clear()
        fx.STATE.pages["/js"] = fx.js_board(ROWS)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def setup_ws(self, board_extra=None, settings=None):
        b = {"id": "js", "name": "JS게시판", "url": "/js", "cycle": "daily", "region": {"tag": "table", "class": "board"}}
        b.update(board_extra or {})
        st = {"render": {"executable_path": CHROMIUM, "no_sandbox": True, "timeout_sec": 20}}
        st.update(settings or {})
        fx.write_workspace(self.ws, self.port, [b], st)

    def run_collect(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = collect.main(["--workspace", self.ws] + list(args))
        return code, buf.getvalue()

    def probe(self):
        code, out = self.run_collect("--probe", "js", "--today", "2026-08-26")
        self.assertEqual(code, 0)
        return json.loads(out[out.index("{"):])

    def test_static_mode_cannot_read_js_board(self):
        """기본(렌더링 없음): 스크립트는 글을 못 읽고 확인 대상으로 표시한다 — 기능 제한을 정직하게 드러내는지 검사."""
        self.setup_ws()
        data = self.probe()
        self.assertEqual(data["status"], "게시일 확인 불가")
        self.assertIn("js_suspected", data["reasons"])
        self.assertFalse(data["rendered"])

    @unittest.skipUnless(HAVE_PW and CHROMIUM, "playwright/chromium 없음")
    def test_board_level_render(self):
        self.setup_ws({"render": "playwright"})
        data = self.probe()
        self.assertEqual(data["latest_date"], "2026-08-24")
        self.assertEqual(data["status"], "정상")
        self.assertTrue(data["rendered"])
        self.assertEqual(data["titles"][0].split(" ", 1)[1], "JS 새 공지")

    @unittest.skipUnless(HAVE_PW and CHROMIUM, "playwright/chromium 없음")
    def test_auto_fallback_only_when_static_fails(self):
        self.setup_ws(settings={"js_fallback": "playwright"})
        data = self.probe()
        self.assertEqual(data["latest_date"], "2026-08-24")
        self.assertTrue(data["rendered"])
        # 서버 렌더링 게시판은 브라우저를 쓰지 않는다
        fx.STATE.pages["/js"] = fx.board([("a", "2026-08-24"), ("b", "2026-08-20"), ("c", "2026-08-01")])
        data = self.probe()
        self.assertEqual(data["latest_date"], "2026-08-24")
        self.assertFalse(data["rendered"])

    @unittest.skipUnless(HAVE_PW and CHROMIUM, "playwright/chromium 없음")
    def test_blocks_offsite_requests(self):
        fx.STATE.pages["/js"] = fx.js_board(ROWS).replace("</body>", '<img src="http://localhost:%d/tracker"></body>' % self.port)
        self.setup_ws({"render": "playwright"})
        self.probe()
        self.assertEqual(fx.STATE.hits.get("/tracker", 0), 0)    # 허용 도메인(127.0.0.1) 밖 요청은 브라우저에서도 차단

    def test_render_unavailable_falls_back_gracefully(self):
        self.setup_ws({"render": "playwright"}, {"render": {"executable_path": "/nonexistent/chrome", "no_sandbox": True}})
        data = self.probe()
        self.assertIn("render_unavailable", data["reasons"])
        self.assertEqual(data["status"], "게시일 확인 불가")       # 중단 없이 정적 수집 결과로 남고 에이전트 확인 대상이 된다
        self.assertIn("렌더링 불가", data["date_note"] or "")

    def test_invalid_render_value_rejected(self):
        self.setup_ws({"render": "selenium"})
        code, out = self.run_collect("--dry-run")
        self.assertEqual(code, 1)


class PolicyRenderTests(unittest.TestCase):
    """자바스크립트로 배너·푸터가 그려지는 페이지: 소스 기준으로는 판정 보류, 렌더링하면 점검된다."""

    JSHOME = ('<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>JS 홈</title></head><body><div id="root"></div><script>'
              'document.getElementById("root").innerHTML = \'<a href="#m">본문 바로가기</a><div class="masthead">이 누리집은 대한민국 공식 전자정부 누리집입니다.</div>\''
              ' + \'<main id="m">\' + "긴 본문입니다. ".repeat(40) + \'</main><footer>이 누리집은 모의기관에서 운영하는 누리집입니다.</footer>\';</script></body></html>')

    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.pages.clear()
        fx.STATE.pages["/jshome"] = self.JSHOME
        fx.write_workspace(self.ws, self.port, [{"id": "x", "name": "x", "url": "/jshome", "type": "static"}],
                           {"render": {"executable_path": CHROMIUM, "no_sandbox": True, "timeout_sec": 20}})
        pth = os.path.join(self.ws, "site-profile.json")
        prof = json.load(open(pth, encoding="utf-8"))
        prof["policy"] = {"home_url": "http://127.0.0.1:%d/jshome" % self.port}
        json.dump(prof, open(pth, "w", encoding="utf-8"), ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_uiux(self, render):
        import policy_check
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            policy_check.main(["--workspace", self.ws, "--pack", "uiux", "--render", render, "--today", "2026-08-26"])
        d = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "policy-uiux.json"), encoding="utf-8"))
        return dict((r["id"], r["auto"]) for r in d["results"]), d

    def test_static_source_is_held_back_not_failed(self):
        res, d = self.run_uiux("off")
        self.assertTrue(res["UX-M2"].startswith("확인 필요"))                # 소스에 내용이 없어도 '미충족'으로 단정하지 않는다
        self.assertNotIn("미충족", res["UX-M2"])

    @unittest.skipUnless(HAVE_PW and CHROMIUM, "playwright/chromium 없음")
    def test_render_auto_evaluates_dom_after_javascript(self):
        res, d = self.run_uiux("auto")
        self.assertEqual(res["UX-M2"], "충족(자동)")                         # 렌더링한 DOM에서 배너 문구 확인
        self.assertEqual(res["UX-I1"], "충족(자동)")
        self.assertEqual(res["UX-F1"], "충족(자동)")
        self.assertTrue([p for p in d["pages"] if p["name"] == "home"][0]["rendered"])
        self.assertTrue(any("렌더링한 DOM" in w for w in d["warnings"]))

    def test_render_unavailable_falls_back_to_source_with_reason(self):
        sp = os.path.join(self.ws, "settings.json")
        st = json.load(open(sp, encoding="utf-8"))
        st["render"] = {"executable_path": "/nonexistent/chrome", "no_sandbox": True}
        json.dump(st, open(sp, "w", encoding="utf-8"))
        res, d = self.run_uiux("auto")
        self.assertTrue(res["UX-M2"].startswith("확인 필요"))
        self.assertTrue(any("렌더링을 사용할 수 없어" in w for w in d["warnings"]))


if __name__ == "__main__":
    unittest.main()
