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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import fixture_site as fx  # noqa: E402
import uiux_review  # noqa: E402

try:
    import playwright.sync_api  # noqa: F401
    HAVE_PW = True
except ImportError:
    HAVE_PW = False
CHROMIUM = os.environ.get("PW_TEST_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else "")

PAGE = ('<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>목록</title><style>body{color:#222;background:#fff}a{color:#00f}</style></head><body>'
        '<a href="#main">본문 바로가기</a><div class="masthead">이 누리집은 대한민국 공식 전자정부 누리집입니다.</div>'
        '<header class="header"><nav><a href="/">홈</a></nav></header><div class="breadcrumb">홈 &gt; 게시판</div>'
        '<main id="main"><h1>게시판</h1><table class="board"><tr><th>제목</th></tr><tr><td><a href="/view/1">글</a></td></tr></table>'
        '<div class="pagination"><a href="?page=1">1</a></div><button type="submit">검색</button><input type="text" name="q"></main>'
        '<footer>Copyright 이 누리집은 모의기관에서 운영하는 누리집입니다.</footer></body></html>')


def quiet(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, out.getvalue(), err.getvalue()


class UiuxReviewTests(unittest.TestCase):
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
        fx.STATE.pages.clear()
        for path in ("/", "/b1", "/b2", "/b3", "/about", "/post"):
            fx.STATE.pages[path] = PAGE
        fx.STATE.pages["/stub"] = '<html><head><title>x</title><!-- 빈 페이지 --></head></html>'
        region = {"tag": "table", "class": "board"}
        fx.write_workspace(self.ws, self.port, [
            {"id": "b1", "name": "공지", "url": "/b1", "cycle": "daily", "region": region},
            {"id": "b2", "name": "보도", "url": "/b2", "cycle": "daily", "region": region},
            {"id": "b3", "name": "자료", "url": "/b3", "cycle": "daily", "region": region},
            {"id": "about", "name": "소개", "url": "/about", "type": "static"}])
        p = os.path.join(self.ws, "site-profile.json")
        prof = json.load(open(p, encoding="utf-8"))
        prof["policy"] = {"home_url": self.base + "/", "pages": {"contact": self.base + "/about"}}
        json.dump(prof, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"boards": {"b1": {"recent_posts": [{"url": self.base + "/post", "date": "2026-08-20", "title": "t", "key": "k"}]}}},
                  open(os.path.join(self.ws, "cache.json"), "w", encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def plan(self, *args):
        return quiet(uiux_review.main, ["plan", "--workspace", self.ws, "--today", "2026-08-26", "--render", "off"] + list(args))

    def queue(self):
        return json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "uiux-review-queue.json"), encoding="utf-8"))

    def test_explicit_pages_and_component_mapping_to_guideline_ranges(self):
        code, out, _ = self.plan("--pages", "%s/b1,%s/b2" % (self.base, self.base))
        self.assertEqual(code, 0, out)
        q = self.queue()
        self.assertEqual([p["url"].replace(self.base, "") for p in q["pages"]], ["/b1", "/b2"])
        comps = dict((c["name"], c) for c in q["pages"][0]["components"])
        self.assertEqual(comps["공식 배너"]["pages"], [220, 226])
        self.assertEqual(comps["페이지네이션"]["pages"], [317, 338])
        self.assertEqual(comps["브레드크럼"]["pages"], [280, 292])
        self.assertEqual(comps["푸터"]["guideline_title"], "04. 푸터(Footer)")
        self.assertEqual([s["name"] for s in q["pages"][0]["style_sections"]], ["색상", "타이포그래피", "형태", "레이아웃", "아이콘"])
        self.assertEqual(dict((s["name"], s["pages"]) for s in q["pages"][0]["style_sections"])["색상"], [74, 101])
        self.assertTrue(q["pages"][0]["needs_browser"])                    # 화면 캡처가 없으면 브라우저 확인이 필요하다고 표시
        self.assertIn("확인불가", q["how_to"])

    def test_auto_sample_is_capped_deduped_and_grouped(self):
        code, out, _ = self.plan("--sample", "4")
        self.assertEqual(code, 0)
        q = self.queue()
        kinds = [(p["kind"], p["url"].replace(self.base, "")) for p in q["pages"]]
        self.assertEqual(len(kinds), 4)                                    # 상한
        self.assertEqual(kinds[0], ("홈", "/"))                             # 홈이 먼저
        self.assertEqual(len(set(u for _, u in kinds)), 4)                 # 중복 없음
        self.assertIn(("대표 페이지", "/about"), kinds)
        # 같은 게시판 유형(region)은 최대 2개 + 캐시된 게시글 상세 1개
        q2 = self.plan("--sample", "20")
        kinds = [k for k, _ in [(p["kind"], p["url"]) for p in self.queue()["pages"]]]
        self.assertEqual(kinds.count("게시판 목록"), 2)
        self.assertEqual(kinds.count("게시글 상세"), 1)

    def test_user_pages_and_domain_guard_and_dry_run(self):
        code, _, err = self.plan("--pages", "https://www.example.com/x")
        self.assertEqual(code, 1)
        self.assertIn("허용 도메인 밖", err)
        before = sum(fx.STATE.hits.values())
        code, out, _ = self.plan("--dry-run", "--sample", "3")
        self.assertEqual(sum(fx.STATE.hits.values()), before)              # 요청하지 않음
        self.assertEqual(len(json.loads(out)["pages"]), 3)

    def test_thin_page_is_flagged_for_browser_review(self):
        self.plan("--pages", self.base + "/stub")
        p = self.queue()["pages"][0]
        self.assertEqual(p["components"], [])
        self.assertIn("브라우저로 직접 확인", p["note"])

    # ---- merge ----------------------------------------------------------
    def write_result(self, items):
        json.dump({"model": "test-agent", "items": items}, open(os.path.join(self.ws, "runs", "2026-08-26", "uiux-review.json"), "w", encoding="utf-8"), ensure_ascii=False)

    def merge(self):
        return quiet(uiux_review.main, ["merge", "--workspace", self.ws, "--date", "2026-08-26"])

    def test_merge_verifies_quotes_and_rejects_bad_items(self):
        self.plan("--pages", self.base + "/b1")
        good = {"page_id": "P01", "component": "건너뛰기 링크", "guideline_page": 258, "guideline_quote": "건너뛰기 링크의 개수는 3개 이내로 제공한다.",
                "verdict": "준수", "observation": "상단에 건너뛰기 링크 1개가 있어 3개 이내 요건을 충족한다", "severity": "낮음", "confidence": "high", "evidence_ref": "P01-desktop.png"}
        halluc = dict(good, component="푸터", verdict="미준수", guideline_page=249, guideline_quote="푸터에는 반드시 광고를 넣어야 한다",
                      observation="푸터에 광고가 없어 가이드라인을 위반하고 있다고 판단함", evidence_ref="footer")
        real_ng = dict(good, component="푸터", verdict="미준수", guideline_page=249, guideline_quote="개인정보 처리방침은 반드시 웹사이트에 공개해야 한다.",
                       observation="푸터에 개인정보 처리방침 링크가 보이지 않는다(저작권 문구만 있음)", severity="높음", evidence_ref="footer")
        self.write_result([good, halluc, real_ng,
                           dict(good, page_id="P99"),                                       # 없는 페이지
                           dict(good, verdict="좋음"),                                      # 잘못된 판정
                           dict(good, guideline_page=99999),                                # 없는 쪽
                           dict(good, observation="짧음"),                                  # 관찰 내용 부족
                           dict(real_ng, evidence_ref="")])                                 # 미준수인데 근거 참조 없음
        code, out, _ = self.merge()
        self.assertEqual(code, 3)
        res = json.loads(out)
        self.assertEqual(res["applied"], 3)
        self.assertEqual(len(res["rejected"]), 5)
        self.assertEqual(res["verdicts"], {"미준수": 1, "확인불가": 1, "준수": 1})       # 환각 인용은 확인불가로 하향
        with open(os.path.join(self.ws, "runs", "2026-08-26", "uiux-review.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["판정"], "미준수")                                        # 미준수가 먼저
        by = dict((r["컴포넌트"] + r["판정"], r) for r in rows)
        self.assertEqual(by["푸터확인불가"]["인용 검증"], "실패")
        self.assertIn("하향", by["푸터확인불가"]["비고"])
        self.assertEqual(by["건너뛰기 링크준수"]["인용 검증"], "통과")
        md = open(os.path.join(self.ws, "runs", "2026-08-26", "uiux-review.md"), encoding="utf-8").read()
        self.assertIn("page_0249.jpg", md)                                                # 원문 쪽 이미지 경로
        self.assertIn("사람의 최종 확인 전", md)

    def test_merge_requires_result_file(self):
        self.plan("--pages", self.base + "/b1")
        code, _, err = self.merge()
        self.assertEqual(code, 1)
        self.assertIn("uiux-review.json", err)

    @unittest.skipUnless(HAVE_PW and CHROMIUM, "playwright/chromium 없음")
    def test_capture_screenshots_styles_and_contrast(self):
        sp = os.path.join(self.ws, "settings.json")
        st = json.load(open(sp, encoding="utf-8"))
        st["render"] = {"executable_path": CHROMIUM, "no_sandbox": True, "timeout_sec": 20}
        json.dump(st, open(sp, "w", encoding="utf-8"))
        code, out, _ = quiet(uiux_review.main, ["plan", "--workspace", self.ws, "--today", "2026-08-26", "--render", "auto", "--pages", self.base + "/b1"])
        self.assertEqual(code, 0, out)
        p = self.queue()["pages"][0]
        self.assertTrue(p["rendered"])
        self.assertFalse(p["needs_browser"])
        self.assertTrue(os.path.getsize(p["screenshots"]["desktop"]) > 500 and os.path.getsize(p["screenshots"]["mobile"]) > 500)
        body = [c for c in p["contrast"] if c["selector"] == "body"][0]
        self.assertGreater(body["ratio"], 12)                                              # #222 on #fff
        link = [c for c in p["contrast"] if c["selector"] == "a"][0]
        self.assertGreater(link["ratio"], 7)                                               # #00f on #fff ≈ 8.6


if __name__ == "__main__":
    unittest.main()
