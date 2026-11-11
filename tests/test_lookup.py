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
import lookup  # noqa: E402

DEPT = ('<html><head><title>기획 안내</title></head><body><div class="contents"><h2>사업 안내</h2>'
        '<table><tr><th>담당부서</th><td>기획과</td><th>담당자</th><td>홍길동</td><th>전화</th><td>031-123-4567</td></tr></table></div>'
        '<div id="footer">대표전화 02-111-2222 | 팩스 02-111-3333 | webmaster@example.go.kr</div></body></html>')


class LookupTests(unittest.TestCase):
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
        fx.STATE.pages.update({"/dept": DEPT, "/none": "<html><head><title>빈</title></head><body>안내 문구만 있음</body></html>",
                               "/notice": fx.board([("n2", "2026-08-24"), ("n1", "2026-08-01")])})
        fx.write_workspace(self.ws, self.port, [
            {"id": "dept", "name": "사업안내", "url": "/dept", "type": "static", "owner": "기획과"},
            {"id": "notice", "name": "공지사항", "url": "/notice", "cycle": "daily", "region": {"tag": "table", "class": "board"}, "owner": "총무과"},
            {"id": "notice_en", "name": "공지사항(영문)", "url": "/none", "type": "static"},
            {"id": "data", "name": "자료실", "url": "/none", "type": "static"}])

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lookup.main(["--workspace", self.ws] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_contact_separates_page_and_footer(self):
        code, out, _ = self.run_cli("--json", "contact", "사업안내")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["owner_in_profile"], "기획과")
        main, foot = d["contacts"][0], d["contacts"][1]
        self.assertEqual((main["부서"], main["담당자"], main["전화"], main["위치"], main["신뢰도"]),
                         ("기획과", "홍길동", ["031-123-4567"], "본문", "높음"))
        self.assertEqual((foot["전화"], foot["팩스"], foot["이메일"]), (["02-111-2222"], ["02-111-3333"], ["webmaster@example.go.kr"]))
        self.assertTrue(foot["위치"].startswith("푸터"))
        self.assertIn("031-123-4567", main["원문"])                         # 근거 원문 제공

    def test_markdown_and_mask(self):
        code, out, _ = self.run_cli("contact", "사업안내")
        self.assertIn("담당자: 홍길동", out)
        self.assertIn("031-123-4567", out)
        code, out, _ = self.run_cli("contact", "사업안내", "--mask")
        self.assertNotIn("4567", out)
        self.assertIn("031-***-****", out)

    def test_no_contact_is_reported_not_guessed(self):
        code, out, _ = self.run_cli("contact", "자료실")
        self.assertEqual(code, 0)
        self.assertIn("찾지 못했습니다", out)
        self.assertNotIn("담당자:", out)

    def test_ambiguous_query_lists_candidates(self):
        code, out, _ = self.run_cli("contact", "공지")
        self.assertEqual(code, 3)
        self.assertIn("notice", out)
        self.assertIn("notice_en", out)
        self.assertEqual(fx.STATE.hits.get("/none", 0), 0)                  # 추측해서 접속하지 않음
        code, out, _ = self.run_cli("find", "공지사항")                      # 이름이 정확히 같으면 하나로 확정
        self.assertEqual(code, 0)
        self.assertIn("notice : 공지사항", out)

    def test_latest_post_contact(self):
        import zlib
        post = "/view/%d" % zlib.crc32("n2".encode("utf-8"))
        fx.STATE.pages[post] = ('<html><head><title>n2</title></head><body><div class="view">본문 내용<br>'
                                '문의: 연구기획과 김철수 063-111-2345</div></body></html>')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collect.main(["--workspace", self.ws, "--mode", "full", "--today", "2026-08-26"])
        code, out, _ = self.run_cli("--json", "contact", "공지사항", "--latest-post")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertIn("최신 글: n2", d["title"])
        self.assertEqual(d["contacts"][0]["전화"], ["063-111-2345"])
        self.assertEqual(d["contacts"][0]["부서"], "연구기획과")
        code, _, err = self.run_cli("contact", "사업안내", "--latest-post")   # 게시글 링크가 없는 정적 페이지
        self.assertEqual(code, 1)

    def test_url_option_enforces_allowed_domains(self):
        code, out, err = self.run_cli("contact", "--url", "https://www.example.com/x")
        self.assertEqual(code, 1)
        self.assertIn("허용 도메인 밖", err)
        code, out, _ = self.run_cli("contact", "--url", "http://127.0.0.1:%d/dept" % self.port)
        self.assertEqual(code, 0)
        self.assertIn("홍길동", out)

    def test_status_and_overview_are_offline(self):
        code, out, _ = self.run_cli("status", "자료실")                      # 점검 전: 프로필에만 있는 게시판
        self.assertIn("점검 이력 없음", out)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            collect.main(["--workspace", self.ws, "--mode", "full", "--today", "2026-08-26"])
        fx.STATE.hits.clear()
        code, out, _ = self.run_cli("status", "공지사항")
        self.assertEqual(code, 0)
        self.assertIn("판정: **정상**", out)
        self.assertIn("최신 게시일: 2026-08-24", out)
        self.assertIn("2026-08-24 n2", out)                                 # 최근 게시물
        code, out, _ = self.run_cli("overview")
        self.assertIn("점검 대상 게시판", out)
        self.assertEqual(sum(fx.STATE.hits.values()), 0)                    # 현황·전체 현황은 사이트에 요청하지 않는다


if __name__ == "__main__":
    unittest.main()
