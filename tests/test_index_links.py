import contextlib
import csv
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

import check_index_links as cil  # noqa: E402
import fixture_site as fx  # noqa: E402


class IndexLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]
        cls.base = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.hits.clear()
        long_text = "기관 안내 본문입니다. " * 20
        fx.STATE.pages.clear()
        fx.STATE.pages.update({
            "/": "<html><head><title>메인</title></head><body>" + long_text + "</body></html>",
            "/ok": '<html><head><title>정상 안내 | 테스트기관</title></head><body>%s<img src="/img/ok.png"></body></html>' % long_text,
            "/soft": "<html><head><title>안내</title></head><body>요청하신 페이지를 찾을 수 없습니다.</body></html>",
            "/badimg": '<html><head><title>이미지 페이지</title></head><body>%s<img src="/img/missing.png"></body></html>' % long_text,
            "/mismatch": "<html><head><title>완전히 다른 주제의 글</title></head><body>" + long_text + "</body></html>",
            "/empty": "<html><head><title>빈</title></head><body></body></html>",
        })
        fx.write_workspace(self.ws, self.port, [{"id": "x", "name": "x", "url": "/", "cycle": "daily"}])
        self.files = {}
        urls = {
            "google": [("/ok", "정상 안내"), ("/gone", "삭제된 글"), ("/soft", "소프트 글"), ("/badimg", "이미지 페이지"),
                       ("/mismatch", "원래 제목 이야기"), ("/to-root", "메인으로 갈 글"), ("/redirect", "외부 이동"), ("/empty", "")],
            "naver": [("/ok", "정상 안내"), ("/gone", "삭제된 글")],      # 구글과 중복되는 URL
            "daum": [("/ok", "정상 안내")],
        }
        for eng, lst in urls.items():
            p = os.path.join(self.ws, "%s.txt" % eng)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 주석\n")
                for path, title in lst:
                    f.write("%s%s\t%s\n" % (self.base, path, title))
                if eng == "daum":
                    f.write("https://www.example.com/external\t외부 글\n")
            self.files[eng] = p

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_cli(self, *extra):
        args = ["--workspace", self.ws, "--today", "2026-08-26"]
        for eng, p in self.files.items():
            args += ["--input", "%s=%s" % (eng, p)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cil.main(args + list(extra))
        return code, buf.getvalue()

    def rows(self):
        with open(os.path.join(self.ws, "runs", "2026-08-26", "search-index-links.csv"), encoding="utf-8-sig") as f:
            return dict((r["검색결과URL"].replace(self.base, ""), r) for r in csv.DictReader(f))

    def test_verdicts(self):
        code, _ = self.run_cli("--check-images")
        self.assertEqual(code, 0)
        r = self.rows()
        self.assertEqual(r["/ok"]["판정"], "정상")
        self.assertEqual(r["/ok"]["검색엔진"], "google/naver/daum")      # 중복 URL은 한 번만 점검하고 엔진을 합침
        self.assertEqual(r["/gone"]["판정"], "404오류")
        self.assertEqual(r["/soft"]["판정"], "소프트404")
        self.assertEqual(r["/soft"]["실제접속상태"], "200")
        self.assertEqual(r["/badimg"]["판정"], "깨진이미지")
        self.assertEqual(r["/mismatch"]["판정"], "제목불일치")
        self.assertEqual(r["/to-root"]["판정"], "리다이렉트오류")        # 메인으로 이동
        self.assertEqual(r["/redirect"]["판정"], "리다이렉트오류")       # 외부로 이동은 따라가지 않음
        self.assertEqual(r["/empty"]["판정"], "빈페이지의심")
        ext = [v for k, v in r.items() if "example.com" in k][0]
        self.assertEqual(ext["판정"], "제외")                             # 외부 도메인은 접속하지 않고 기록만
        self.assertEqual(fx.STATE.hits.get("/elsewhere", 0), 0)
        self.assertEqual(fx.STATE.hits.get("/ok", 0), 1)                 # 중복 요청 없음

    def test_images_checked_only_when_requested(self):
        self.run_cli()
        self.assertEqual(self.rows()["/badimg"]["판정"], "정상")

    def test_dry_run_and_summary(self):
        code, out = self.run_cli("--dry-run")
        self.assertEqual(json.loads(out)["external_skipped"], 1)
        self.assertEqual(sum(fx.STATE.hits.values()), 0)
        self.run_cli()
        s = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "search-index-summary.json"), encoding="utf-8"))
        self.assertGreaterEqual(s["problems"], 5)

    def test_title_match_truncated_search_title(self):
        self.assertEqual(cil.title_match("연구성과 발표 안내...", "연구성과 발표 안내 | 국립기관"), "일치")
        self.assertEqual(cil.title_match("", "제목"), "확인불가")


if __name__ == "__main__":
    unittest.main()
