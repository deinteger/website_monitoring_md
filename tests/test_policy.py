import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import check_index_links  # noqa: E402
import fixture_site as fx  # noqa: E402
import guidelines  # noqa: E402
import policy_check  # noqa: E402
import portal_plan  # noqa: E402
import run_checks  # noqa: E402

LONG = "기관 안내 본문입니다. " * 20
GOOD = ('<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>홈</title></head><body>'
        '<a href="#main">본문 바로가기</a><div class="masthead">이 누리집은 대한민국 공식 전자정부 누리집입니다. 대한민국 디지털 정부</div>'
        '<header class="header"><img src="/img/ok.png" alt="국립OO원"><a href="/about">소개</a></header>'
        '<main id="main"><h1>본문</h1><img src="/img/ok.png" alt="사진"><p>%s<script src="//dapi.kakao.com/v2/maps/sdk.js"></script></p>'
        '<a href="http://localhost:{port}/ext-dead">외부 기관</a> <a href="http://localhost:{port}/ext-ok">외부 정상</a></main>'
        '<footer><p>주소 전북 OO시 전화 063-111-2222 이메일 a@b.go.kr</p><a href="/privacy">개인정보 처리방침</a> <a href="/access">웹 접근성 안내</a>'
        '<p>Copyright 2026. All rights reserved.</p><section><img src="/img/ok.png" alt="OO부 로고"> 이 누리집은 OO부에서 운영하는 누리집입니다.</section>'
        '<img src="http://localhost:{port}/pixel.gif" width="1" height="1" border="0"><img src="/img/ok.png" style="display:none"></footer></body></html>') % LONG
def good_page(title, body):
    return ('<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>%s</title></head><body>'
            '<a href="#main">본문 바로가기</a><div class="masthead">이 누리집은 대한민국 공식 전자정부 누리집입니다.</div>'
            '<header class="header"><img src="/img/ok.png" alt="국립OO원"></header><main id="main">%s</main>'
            '<footer><p>주소 전북 OO시 전화 063-111-2222</p><a href="/privacy">개인정보 처리방침</a><p>Copyright 2026</p>'
            '<section>이 누리집은 OO부에서 운영하는 누리집입니다.</section></footer></body></html>') % (title, body)


BAD = ('<html><head><title>나쁜 예</title></head><body><a href="/">홈</a><div class="masthead">대한민국 공식 전자정부 웹사이트</div>'
       '<header><img src="/img/ok.png" alt="정부 로고"></header><a href="#nowhere">본문 바로가기</a><main>%s</main>'
       '<div class="foot"><img src="/img/ok.png"><a href="/privacy">개인정보보호정책</a></div></body></html>') % LONG


def quiet(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
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
        fx.STATE.pages.update({
            "/": GOOD.replace("{port}", str(self.port)), "/bad": BAD,
            "/about": good_page("소개", "조직도 최종수정일 : 2026-03-02 문의 063-111-2222 팩스 063-111-3333 1234-5678"),
            "/privacy": good_page("개인정보 처리방침", LONG), "/access": good_page("웹 접근성", LONG),
            "/ext-ok": "<html><body>ok</body></html>"})

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def setup_ws(self, home="/", sample=None, settings=None, agency="OO부"):
        fx.write_workspace(self.ws, self.port, [{"id": "about", "name": "소개", "url": "/about", "type": "static", "cycle": "monthly"}], settings)
        p = os.path.join(self.ws, "site-profile.json")
        prof = json.load(open(p, encoding="utf-8"))
        prof["policy"] = {"home_url": self.base + home, "agency_name": agency, "pages": {"org_chart": self.base + "/about", "contact": self.base + "/about"},
                          "sample_pages": [self.base + x for x in (sample or [])]}
        json.dump(prof, open(p, "w", encoding="utf-8"), ensure_ascii=False)

    def run_pc(self, *args):
        return quiet(policy_check.main, ["--workspace", self.ws, "--today", "2026-08-26"] + list(args))

    def results(self, pack):
        d = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "policy-%s.json" % pack), encoding="utf-8"))
        return dict((r["id"], r) for r in d["results"]), d


class UiuxRuleTests(Base):
    def test_compliant_page_passes_auto_rules(self):
        self.setup_ws()
        code, _, _ = self.run_pc("--pack", "uiux")
        self.assertEqual(code, 0)
        r, _ = self.results("uiux")
        for rid in ("UX-M1", "UX-M2", "UX-M3", "UX-I1", "UX-I3", "UX-H1", "UX-H2", "UX-F1", "UX-F3", "UX-F5", "UX-S1", "UX-S2", "UX-S4"):
            self.assertEqual(r[rid]["auto"], "충족(자동)", "%s: %s" % (rid, [c["evidence"] for c in r[rid]["checks"]]))
            self.assertEqual(r[rid]["suggest"], "네(제안)")
        self.assertTrue(r["UX-F2"]["auto"].startswith("확인 필요"))          # assist 는 충족으로 단정하지 않는다
        self.assertEqual(r["UX-H3"]["auto"], "사람 응답 필요")              # attest 는 자동으로 채우지 않는다
        self.assertEqual(r["UX-H3"]["suggest"], "")

    def test_violations_are_reported_with_evidence(self):
        self.setup_ws(home="/bad")
        self.run_pc("--pack", "uiux")
        r, _ = self.results("uiux")
        ev = lambda rid: " ".join(e for c in r[rid]["checks"] for e in c["evidence"])  # noqa: E731
        for rid in ("UX-M1", "UX-M2", "UX-M3", "UX-I1", "UX-I3", "UX-H1", "UX-H2", "UX-F1", "UX-F3", "UX-S4"):
            self.assertEqual(r[rid]["auto"], "미충족(자동)", rid)
            self.assertEqual(r[rid]["suggest"], "아니오(제안)")
        self.assertIn("변형 문구 발견", ev("UX-M2"))                        # 피해야 할 사례 문구를 알아봄
        self.assertIn("'로고'", ev("UX-H2"))
        self.assertIn("#nowhere", ev("UX-S4"))
        self.assertEqual(r["UX-S1"]["auto"], "충족(자동)")                  # 건너뛰기 링크 자체는 있음
        self.assertIn("첫 링크가 건너뛰기 링크가 아님", ev("UX-H1"))

    def test_rules_carry_source_page_and_quote(self):
        self.setup_ws()
        self.run_pc("--pack", "uiux")
        r, d = self.results("uiux")
        self.assertEqual(r["UX-M2"]["source_ref"], "p.224")
        self.assertFalse(d["meta"]["reviewed"])

    def test_draft_rules_are_reference_only(self):
        gd = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "guidelines"), os.path.join(gd, "guidelines"))
            p = os.path.join(gd, "guidelines", "uiux", "2025.08", "rules.json")
            data = json.load(open(p, encoding="utf-8"))
            for x in data["rules"]:
                x["status"] = "draft"
            json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            self.setup_ws()
            self.run_pc("--pack", "uiux", "--guidelines-dir", os.path.join(gd, "guidelines"))
            r, _ = self.results("uiux")
            self.assertTrue(r["UX-M1"]["auto"].startswith("참고(검수 전 규칙)"))
            self.assertEqual(r["UX-M1"]["suggest"], "")
        finally:
            shutil.rmtree(gd)


class StubPageTests(Base):
    """실제 사이트에서 발견된 결함 재발 방지: 메인 주소가 빈 껍데기(스크립트 이동)인 경우."""

    def test_follows_script_redirect_stub_to_real_home(self):
        fx.STATE.pages["/stub"] = '<html><head><title>기관</title><script>document.location.href="/"</script></head></html>'
        self.setup_ws(home="/stub")
        self.run_pc("--pack", "uiux")
        r, d = self.results("uiux")
        self.assertEqual(r["UX-M2"]["auto"], "충족(자동)")                  # 껍데기가 아니라 실제 홈을 점검
        self.assertEqual(r["UX-F1"]["auto"], "충족(자동)")
        pg = [p for p in d["pages"] if p["name"] == "home"][0]
        self.assertTrue(pg["final_url"].endswith("/") and not pg["thin"])
        self.assertTrue(any("스크립트로 이동하는 껍데기" in w for w in d["warnings"]))

    def test_commented_out_redirect_is_ignored_and_empty_page_is_not_a_failure(self):
        fx.STATE.pages["/empty"] = '<html><head><title>기관</title><!-- <script>document.location.href="/"</script> --></head></html>'
        self.setup_ws(home="/empty")
        self.run_pc("--pack", "uiux")
        r, d = self.results("uiux")
        for rid in ("UX-M1", "UX-M2", "UX-F1", "UX-F3", "UX-S1", "UX-H1"):
            self.assertTrue(r[rid]["auto"].startswith("확인 필요"), "%s: %s" % (rid, r[rid]["auto"]))     # 미충족이 아니라 판정 보류
            self.assertNotIn("미충족", r[rid]["auto"])
        self.assertIn("제외된 페이지: home", " ".join(e for c in r["UX-M1"]["checks"] for e in c["evidence"]))
        self.assertIn("본문이 비어 있습니다", " ".join(e for c in r["UX-M2"]["checks"] for e in c["evidence"]))      # 홈 단독 검사는 보류 사유를 설명
        self.assertTrue(any("점검에서 제외" in w for w in d["warnings"]))

    def test_redirect_loop_is_bounded(self):
        fx.STATE.pages["/a"] = '<html><head><script>location.href="/b"</script></head></html>'
        fx.STATE.pages["/b"] = '<html><head><script>location.href="/a"</script></head></html>'
        self.setup_ws(home="/a")
        self.run_pc("--pack", "uiux")
        self.assertLessEqual(fx.STATE.hits.get("/a", 0) + fx.STATE.hits.get("/b", 0), 3)
        r, _ = self.results("uiux")
        self.assertNotIn("미충족", r["UX-M1"]["auto"])

    def test_tracking_pixels_are_not_logo_failures(self):
        """실제 사이트에서 발견된 오탐: 푸터의 접속 통계 추적 픽셀(외부·1x1·숨김)은 로고 대체텍스트 점검 대상이 아니다."""
        self.setup_ws()
        self.run_pc("--pack", "uiux")
        r, _ = self.results("uiux")
        self.assertEqual(r["UX-I3"]["auto"], "충족(자동)")
        self.assertIn("제외", " ".join(e for c in r["UX-I3"]["checks"] for e in c["evidence"]))
        self.assertEqual(fx.STATE.hits.get("/pixel.gif", 0), 0)

    def test_client_redirect_finder(self):
        import monlib as ml
        self.assertEqual(ml.find_client_redirect('<script>window.location="/x/main.do"</script>', "https://example.com/"), "https://example.com/x/main.do")
        self.assertEqual(ml.find_client_redirect('<meta http-equiv="refresh" content="0; url=/m">', "https://example.com/a/"), "https://example.com/m")
        self.assertEqual(ml.find_client_redirect("<script>location.replace('/r')</script>", "https://example.com/"), "https://example.com/r")
        self.assertIsNone(ml.find_client_redirect('<!-- <script>location.href="/c"</script> -->', "https://example.com/"))
        self.assertIsNone(ml.find_client_redirect("<p>일반 페이지</p>", "https://example.com/"))


class PolicyRuleTests(Base):
    def test_policy_pack_and_human_answers(self):
        self.setup_ws()
        code, _, _ = self.run_pc("--pack", "policy-week")
        self.assertEqual(code, 0)
        r, d = self.results("policy-week")
        self.assertEqual(len(r), 23)
        self.assertEqual(r["PW-22"]["auto"], "충족(자동)")                  # 용량·응답시간(근사)
        self.assertEqual(r["PW-03"]["auto"], "사람 응답 필요")
        self.assertTrue(r["PW-06"]["auto"].startswith("확인 필요"))          # 외부 링크 점검은 옵트인(기본 꺼짐)
        self.assertEqual(fx.STATE.hits.get("/ext-dead", 0) + fx.STATE.hits.get("/ext-ok", 0), 0)   # 외부 사이트에 요청하지 않음
        ev = " ".join(e for c in r["PW-05"]["checks"] for e in c["evidence"])
        self.assertIn("dapi.kakao.com", ev)                                  # 지도 사용 흔적을 목록으로 제시
        ev1 = " ".join(e for c in r["PW-01"]["checks"] for e in c["evidence"])
        self.assertIn("2026-03-02", ev1)
        self.assertIn("지역번호 없는 번호 의심 1건", ev1)
        with open(os.path.join(self.ws, "runs", "2026-08-26", "policy-policy-week.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 23)
        self.assertEqual(rows[0]["규칙ID"], "PW-01")
        # 사람 응답 기록 → 다음 점검에 반영, 버전이 다르면 재확인 표시
        c, out, _ = quiet(policy_check.main, ["answer", "PW-03", "--yes", "--note", "관리계획 수립", "--workspace", self.ws, "--today", "2026-08-26"])
        self.assertEqual(c, 0)
        self.run_pc("--pack", "policy-week")
        r, _ = self.results("policy-week")
        self.assertTrue(r["PW-03"]["answer"].startswith("네 (2026-08-26)"))
        ap = os.path.join(self.ws, "policy-answers.json")
        a = json.load(open(ap, encoding="utf-8"))
        a["PW-03"]["pack_version"] = "2025"
        json.dump(a, open(ap, "w", encoding="utf-8"))
        self.run_pc("--pack", "policy-week")
        r, _ = self.results("policy-week")
        self.assertIn("이전 버전 응답: 재확인 필요", r["PW-03"]["answer"])
        self.assertEqual(quiet(policy_check.main, ["answer", "NOPE-1", "--yes", "--workspace", self.ws])[0], 1)
        self.assertEqual(quiet(policy_check.main, ["answer", "PW-03", "--workspace", self.ws])[0], 1)     # --yes/--no 필수

    def test_external_links_opt_in(self):
        self.setup_ws(settings={"policy": {"check_external_links": True, "max_external_links": 10}})
        self.run_pc("--pack", "policy-week")
        r, _ = self.results("policy-week")
        self.assertEqual(r["PW-06"]["auto"], "미충족(자동)")
        self.assertIn("ext-dead", " ".join(e for c in r["PW-06"]["checks"] for e in c["evidence"]))
        self.assertGreaterEqual(fx.STATE.hits.get("/ext-dead", 0), 1)

    def test_pack_ref_aggregates_uiux_only_when_run(self):
        self.setup_ws()
        self.run_pc("--pack", "policy-week")
        r, _ = self.results("policy-week")
        self.assertIn("점검하지 않았습니다", " ".join(e for c in r["PW-19"]["checks"] for e in c["evidence"]))
        self.run_pc("--pack", "all")
        r, _ = self.results("policy-week")
        self.assertIn("규칙팩 uiux 결과", " ".join(e for c in r["PW-19"]["checks"] for e in c["evidence"]))

    def test_dry_run_makes_no_requests(self):
        self.setup_ws()
        code, out, _ = self.run_pc("--pack", "all", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(sum(fx.STATE.hits.values()), 0)
        d = json.loads(out)
        self.assertFalse(d["external_link_check"])
        self.assertIn("user_agent", d["request_policy"])


class GuidelineToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gd = os.path.join(self.tmp, "guidelines")
        shutil.copytree(os.path.join(ROOT, "guidelines"), self.gd)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def g(self, *args):
        return quiet(guidelines.main, ["--guidelines-dir", self.gd] + list(args))

    def test_repo_packs_validate_including_source_quotes(self):
        code, out, _ = self.g("validate", "--all-versions")
        self.assertEqual(code, 0, out)
        self.assertIn("오류 0", out)

    def test_tampered_quote_is_rejected(self):
        p = os.path.join(self.gd, "uiux", "2025.08", "rules.json")
        data = json.load(open(p, encoding="utf-8"))
        data["rules"][0]["source_quote"] = "원문에 없는 문장입니다"
        json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        code, out, _ = self.g("validate", "--pack", "uiux")
        self.assertEqual(code, 1)
        self.assertIn("인용 검증 실패", out)

    def test_active_rule_without_source_is_rejected_when_grounding_required(self):
        p = os.path.join(self.gd, "uiux", "2025.08", "rules.json")
        data = json.load(open(p, encoding="utf-8"))
        data["rules"][0].pop("source_quote")
        json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        self.assertEqual(self.g("validate", "--pack", "uiux")[0], 1)

    def test_unknown_check_type_and_duplicate_id_rejected(self):
        p = os.path.join(self.gd, "policy-week", "2026.02", "rules.json")
        data = json.load(open(p, encoding="utf-8"))
        data["rules"][5]["checks"] = [{"type": "nonexistent_check"}]
        data["rules"][1]["id"] = data["rules"][0]["id"]
        json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        code, out, _ = self.g("validate", "--pack", "policy-week")
        self.assertEqual(code, 1)
        self.assertIn("알 수 없는 검사 유형", out)
        self.assertIn("규칙 ID 중복", out)

    def test_yearly_update_flow(self):
        self.assertEqual(self.g("new", "uiux", "2026.08", "--from", "2025.08")[0], 0)
        new = os.path.join(self.gd, "uiux", "2026.08")
        data = json.load(open(os.path.join(new, "rules.json"), encoding="utf-8"))
        self.assertTrue(all(r["status"] == "draft" and r["needs_review"] for r in data["rules"]))
        code, out, err = self.g("use", "uiux", "2026.08")                 # 검수 전에는 전환 거부 (두 사유를 함께 안내)
        self.assertEqual(code, 1)
        self.assertIn("needs_review", err)
        self.assertIn("원문(source md)이 없음", err)
        # 규칙 1개 삭제·1개 변경·1개 추가 후 diff
        data["rules"] = [r for r in data["rules"] if r["id"] != "UX-X2"]
        data["rules"][0]["text"] = data["rules"][0]["text"] + " (개정)"
        data["rules"].append({"id": "UX-N1", "category": "신규", "text": "신규 규칙", "method": "attest", "status": "draft", "needs_review": True})
        json.dump(data, open(os.path.join(new, "rules.json"), "w", encoding="utf-8"), ensure_ascii=False)
        code, out, _ = self.g("diff", "uiux", "2025.08", "2026.08")
        self.assertIn("[추가] UX-N1", out)
        self.assertIn("[삭제] UX-X2", out)
        self.assertIn("[변경] UX-M1", out)
        for r in data["rules"]:                                            # 검수 완료 처리 후 전환
            r.pop("needs_review", None)
            r["status"] = "active"
            r.pop("prev_version_ref", None)
        data["rules"] = [r for r in data["rules"] if r["id"] != "UX-N1"]
        json.dump(data, open(os.path.join(new, "rules.json"), "w", encoding="utf-8"), ensure_ascii=False)
        meta = json.load(open(os.path.join(new, "meta.json"), encoding="utf-8"))
        meta["grounding"] = "none"                                         # 새 원문을 아직 넣지 않은 상태 가정
        json.dump(meta, open(os.path.join(new, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
        code, out, err = self.g("use", "uiux", "2026.08")
        self.assertEqual(code, 0, err)
        idx = json.load(open(os.path.join(self.gd, "index.json"), encoding="utf-8"))
        self.assertEqual(idx["packs"]["uiux"]["current"], "2026.08")

    def test_pages_reader(self):
        code, out, _ = self.g("pages", "uiux", "224")
        self.assertIn("배너 텍스트와 스타일을 변형하지 않는다", out)
        self.assertNotIn("![p.", out)                                      # 이미지 링크 제거
        code, out, _ = self.g("pages", "uiux", "--find", "건너뛰기 링크")
        self.assertIn("258", out)
        self.assertEqual(self.g("pages", "uiux", "1-100")[0], 1)           # 41쪽 이상 거부


class PortalAndSelectionTests(Base):
    def test_portal_plan(self):
        self.setup_ws()
        code, out, _ = quiet(portal_plan.main, ["--workspace", self.ws, "--engines", "google,daum", "--keywords", "21-24"])
        self.assertEqual(code, 0)
        plan = json.load(open(os.path.join(self.ws, "index", "plan.json"), encoding="utf-8"))
        self.assertEqual(plan["keyword_count"], 4)
        self.assertEqual(plan["queries"], 5)                               # site:도메인 1 + 키워드 4
        self.assertEqual(plan["total_searches"], 10)
        qs = [i["q"] for i in plan["items"] if i["engine"] == "google"]
        self.assertEqual(qs[0], "site:127.0.0.1")
        self.assertIn("site:127.0.0.1 호빠", qs)                           # 23번
        self.assertEqual(sum(1 for i in plan["items"] if i["engine"] == "google" and i["keyword"] == "호빠"), 1)
        self.assertTrue(any(i["url"].startswith("https://search.daum.net/search?q=site%3A127.0.0.1") for i in plan["items"]))
        dup, _, _ = quiet(portal_plan.main, ["--workspace", self.ws, "--keywords", "all"])
        plan = json.load(open(os.path.join(self.ws, "index", "plan.json"), encoding="utf-8"))
        self.assertEqual(plan["keyword_count"], 136)                       # 원문 137개 중 중복 1개 제거
        self.assertEqual(quiet(portal_plan.main, ["--workspace", self.ws, "--engines", "bing"])[0], 1)

    def test_illegal_ad_keyword_detection(self):
        self.setup_ws()
        fx.STATE.pages["/spam"] = "<html><head><title>글</title></head><body>%s 호빠 알바 문의 텔레그램</body></html>" % LONG
        fx.STATE.pages["/clean"] = "<html><head><title>글</title></head><body>%s</body></html>" % LONG
        f = os.path.join(self.ws, "g.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("%s/spam\t게시글\t호빠\n%s/clean\t게시글\t호빠\n" % (self.base, self.base))
        quiet(check_index_links.main, ["--workspace", self.ws, "--today", "2026-08-26", "--input", "google=" + f])
        with open(os.path.join(self.ws, "runs", "2026-08-26", "search-index-links.csv"), encoding="utf-8-sig") as fh:
            rows = dict((r["검색결과URL"].replace(self.base, ""), r) for r in csv.DictReader(fh))
        self.assertEqual(rows["/spam"]["판정"], "불법광고의심")
        self.assertIn("호빠", rows["/spam"]["비고"])
        self.assertEqual(rows["/clean"]["판정"], "정상")
        self.assertIn("현재 페이지에 없음", rows["/clean"]["비고"])          # 색인 캐시만 남은 경우를 구분

    def test_run_checks_selection(self):
        self.setup_ws()
        self.assertEqual(quiet(run_checks.main, ["--list"])[0], 0)
        self.assertEqual(quiet(run_checks.main, ["--workspace", self.ws])[0], 1)                          # 범위 미지정
        with self.assertRaises(SystemExit):
            quiet(run_checks.main, ["--workspace", self.ws, "--checks", "nope"])
        code, out, _ = quiet(run_checks.main, ["--workspace", self.ws, "--checks", "policy,uiux", "--today", "2026-08-26"])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", "policy-uiux.md")))
        self.assertTrue(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", "policy-policy-week.md")))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", "inspection-summary.md")))   # 선택하지 않은 점검은 실행 안 함
        summ = json.load(open(os.path.join(self.ws, "runs", "2026-08-26", "checks-summary.json"), encoding="utf-8"))
        self.assertEqual([r["check"] for r in summ["results"]], ["policy", "uiux"])

    def test_portal_needs_urls_then_runs(self):
        self.setup_ws()
        code, out, _ = quiet(run_checks.main, ["--workspace", self.ws, "--checks", "portal", "--today", "2026-08-26", "--keywords", "1-2"])
        self.assertEqual(code, 4)                                                    # URL 수집 필요
        self.assertTrue(os.path.exists(os.path.join(self.ws, "index", "plan.md")))
        with open(os.path.join(self.ws, "index", "google.txt"), "w", encoding="utf-8") as fh:
            fh.write("%s/privacy\t개인정보\n" % self.base)
        code, out, _ = quiet(run_checks.main, ["--workspace", self.ws, "--checks", "portal", "--today", "2026-08-26"])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "runs", "2026-08-26", "search-index-links.csv")))

    def test_all_and_dry_run_and_interactive(self):
        self.setup_ws()
        code, out, _ = quiet(run_checks.main, ["--workspace", self.ws, "--checks", "all", "--dry-run"])
        d = json.loads(out)
        self.assertEqual(d["selected"], ["board", "policy", "uiux", "portal"])
        self.assertIn("board", d["plans"])
        self.assertEqual(sum(fx.STATE.hits.values()), 0)
        with mock.patch("builtins.input", return_value="5"):
            code, out, _ = quiet(run_checks.main, ["--workspace", self.ws, "--interactive", "--dry-run"])
        self.assertEqual(json.loads(out)["selected"], ["uiux"])
        with mock.patch("builtins.input", return_value="9"):
            with self.assertRaises(SystemExit):
                quiet(run_checks.main, ["--workspace", self.ws, "--interactive"])


if __name__ == "__main__":
    unittest.main()
