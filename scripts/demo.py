#!/usr/bin/env python3
"""데모 모드 (표준 라이브러리만 사용): 외부 접속·API 키 없이 처음부터 끝까지 구동해 볼 수 있다.

로컬에 **모의 기관 사이트**(의도적인 결함 포함)와 **모의 LLM**(규칙 기반, 실제 AI 모델이 아님)을 띄우고
전체 점검(게시판·게시글 오타·정책정보 확인주간·UI/UX 가이드라인·검색 포털)을 실행한 뒤 결과 위치를 안내한다.

  python scripts/demo.py                       # 실행 후 요약 출력 (결과: workspace/demo/runs/<날짜>/)
  python scripts/demo.py --serve               # 모의 사이트를 계속 띄워 브라우저로 볼 수 있게 함 (Ctrl+C 종료)
  python scripts/demo.py --workspace out/demo  # 결과 위치 지정

실제 AI 모델 연결(2종 이상 모델 교체 구동): docs/운영가이드.md 6절 — LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 환경변수만 바꾸면 된다.
이 데모의 모든 기관명·연락처·게시글은 가공한 모의 데이터이며 실제 기관과 무관하다.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import http.server
import io
import json
import os
import re
import shutil
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402
import recent_changes  # noqa: E402
import run_checks  # noqa: E402

MARK = ".demo-workspace"


def page(title, body, banner=True, skip=True, logo_alt="모의기관 심볼", privacy=True, identifier=True, viewport=True):
    head = '<meta charset="utf-8">' + ('<meta name="viewport" content="width=device-width, initial-scale=1">' if viewport else "")
    return ('<!DOCTYPE html><html lang="ko"><head>%s<title>%s</title></head><body>'
            '%s%s<header class="header"><img src="/img/logo.png" alt="%s"><nav><a href="/board/notice">공지사항</a> <a href="/board/press">보도자료</a> '
            '<a href="/board/data">자료실</a> <a href="/about/org">조직도</a> <a href="/about/contact">연락처</a></nav></header>'
            '<main id="main">%s</main><footer><p>주소 가상시 모의로 1 전화 031-000-0000 이메일 demo@example.go.kr</p>%s<a href="/access">웹 접근성</a>'
            '<p>Copyright 2026 모의기관 All rights reserved.</p>%s</footer></body></html>') % (
        head, title, '<a href="#main">본문 바로가기</a>' if skip else "",
        '<div class="masthead">이 누리집은 대한민국 공식 전자정부 누리집입니다.</div>' if banner else "", logo_alt, body,
        '<a href="/privacy">개인정보 처리방침</a>' if privacy else "",
        '<section>이 누리집은 모의기관에서 운영하는 누리집입니다.</section>' if identifier else "")


def board(rows, attach=""):
    trs = "".join('<tr><td>%d</td><td><a href="/view/%s">%s</a></td><td>%s</td></tr>' % (i, rid, t, d) for i, (rid, t, d) in enumerate(rows, 1))
    if attach:
        trs += '<tr><td colspan="3">%s</td></tr>' % attach
    return '<h2>게시판</h2><table class="board"><tr><th>번호</th><th>제목</th><th>등록일</th></tr>%s</table>' % trs


def build_pages(today):
    d = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
    posts = {
        "notice-3": ("신청 방법 안내", d(5), "이번 사업은 누구나 신청 하실수 있습니다. 문의는 기획과로 연락 주시기 바랍니다. 연락처 031-000-0000"),
        "notice-2": ("정기 점검 안내", d(12), "시스템 정기 점검이 있습니다. 불편을 드려 죄송합니다."),
        "notice-1": ("운영 계획 공지", d(40), "올해 운영 계획을 안내 드립니다니다. 자세한 내용은 첨부를 확인하세요."),
        "press-2": ("연구성과 발표", d(120), "새 품종 연구성과 발표회가 개최 되었습니다. 많은 관심 부탁드립니다."),
        "press-1": ("보도자료 안내", d(150), "전년도 성과를 정리했습니다."),
        "data-3": ("서식 모음", d(2), "서식 자료를 올립니다."),
        "data-2": ("교육 자료", d(30), "교육 자료입니다."),
        "data-1": ("지침 자료", d(70), "지침 자료입니다."),
    }
    pages = {"/": '<html><head><title>모의기관</title><script>document.location.href="/home"</script></head></html>',
             "/img/logo.png": None, "/files/guide.pdf": None}
    pages["/home"] = page("모의기관 홈", "<h1>모의기관 누리집</h1>" + "<p>모의 기관 안내입니다. </p>" * 12, logo_alt="모의기관 로고", viewport=False)
    pages["/board/notice"] = page("공지사항", board([(k, v[0], v[1]) for k, v in posts.items() if k.startswith("notice")],
                                                 '<a href="/files/guide.pdf">안내문</a> <a href="/files/old-form.hwp">양식(구)</a>'))
    pages["/board/press"] = page("보도자료", board([(k, v[0], v[1]) for k, v in posts.items() if k.startswith("press")]))
    pages["/board/data"] = page("자료실", board([(k, v[0], v[1]) for k, v in posts.items() if k.startswith("data")]))
    for k, (t, dd, body) in posts.items():
        pages["/view/" + k] = page(t, '<div class="view-content">%s</div>' % body)
    pages["/about/org"] = page("조직도", "<p>조직도 최종수정일 : %s 대표 전화 031-000-0000 팩스 031-000-0001</p>" % d(20))
    pages["/about/contact"] = page("연락처", "<p>담당부서 : 기획과 담당자 : 홍길동 전화 : 031-000-0000 이메일 demo@example.go.kr</p>")
    pages["/privacy"] = page("개인정보 처리방침", "<p>개인정보 처리방침 안내입니다. </p>" * 12)
    pages["/access"] = page("웹 접근성", "<p>웹 접근성 안내입니다. </p>" * 12)
    pages["/community/77"] = page("자유게시판 글", "<p>호빠 알바 문의 텔레 문의</p>" + "<p>광고성 글입니다. </p>" * 12, banner=False, skip=False)
    pages["/community/78"] = page("자유게시판 일반 글", "<p>일반 안내 글입니다. </p>" * 12)
    return pages


class SiteHandler(http.server.BaseHTTPRequestHandler):
    pages = {}

    def log_message(self, *a):
        pass

    def _serve(self, head):
        path = self.path.split("?")[0]
        if path in ("/img/logo.png", "/files/guide.pdf"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if path.endswith("png") else "application/pdf")
            self.send_header("Content-Length", "4")
            self.end_headers()
            if not head:
                self.wfile.write(b"%PDF")
            return
        body = self.pages.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


TYPOS = [("하실수 있습니다", "하실 수 있습니다", "띄어쓰기"), ("안내 드립니다니다", "안내 드립니다", "오탈자"), ("개최 되었습니다", "개최되었습니다", "띄어쓰기")]


class MockLLM(http.server.BaseHTTPRequestHandler):
    """모의 LLM(규칙 기반). OpenAI 호환 /v1/chat/completions 형식으로 응답한다. 실제 AI 모델이 아니다."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        system, user = body["messages"][0]["content"], json.loads(body["messages"][1]["content"])
        items = []
        for it in user["items"]:
            if "post_key" in it:                                  # 게시글 오타 점검
                issues = [{"type": ty, "quote": q, "suggestion": s, "reason": "모의 LLM: 규칙 기반 탐지"} for q, s, ty in TYPOS if q in it["text"]]
                items.append({"post_key": it["post_key"], "issues": issues, "confidence": "medium", "note": "모의 LLM(데모)"})
            else:                                                 # 게시판 현행화·문구 판단
                late = it.get("status") == "게시 최신성 지연"
                items.append({"board_id": it["board_id"], "verdict": "담당자 확인 필요" if late else "정상", "severity": "보통", "confidence": "low",
                              "needs_human": late, "issues": [], "note": "모의 LLM(데모): 최신 게시일 경과, 아카이브·비정기 영역인지 담당자 확인 필요" if late else "모의 LLM(데모): 특이사항 없음"})
        data = json.dumps({"choices": [{"message": {"content": json.dumps({"items": items}, ensure_ascii=False)}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(handler):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def quiet(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, out.getvalue(), err.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=os.path.join("workspace", "demo"))
    ap.add_argument("--today", default="")
    ap.add_argument("--serve", action="store_true", help="실행 후 모의 사이트를 계속 띄움")
    args = ap.parse_args(argv)
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    ws = args.workspace
    if os.path.exists(ws):
        if not os.path.exists(os.path.join(ws, MARK)):
            print("[중단] %s 는 데모 작업 폴더가 아닙니다(%s 표식 없음). 다른 --workspace 를 지정하세요." % (ws, MARK), file=sys.stderr)
            return 1
        shutil.rmtree(ws)
    os.makedirs(ws)
    open(os.path.join(ws, MARK), "w").write("demo\n")

    SiteHandler.pages = build_pages(today)
    site, llm = start(SiteHandler), start(MockLLM)
    base = "http://127.0.0.1:%d" % site.server_address[1]
    boards = [
        {"id": "notice", "name": "공지사항", "url": base + "/board/notice", "cycle": "daily", "owner": "총무과", "region": {"tag": "table", "class": "board"},
         "body_region": {"tag": "div", "class": "view-content"}},
        {"id": "press", "name": "보도자료", "url": base + "/board/press", "cycle": "weekly", "owner": "홍보담당관", "region": {"tag": "table", "class": "board"},
         "body_region": {"tag": "div", "class": "view-content"}},
        {"id": "data", "name": "자료실", "url": base + "/board/data", "cycle": "weekly", "owner": "기획과", "region": {"tag": "table", "class": "board"},
         "body_region": {"tag": "div", "class": "view-content"}},
        {"id": "org", "name": "조직도", "url": base + "/about/org", "type": "static", "cycle": "monthly", "owner": "기획과"},
        {"id": "contact", "name": "연락처", "url": base + "/about/contact", "type": "static", "cycle": "monthly", "owner": "기획과"},
    ]
    profile = {"site_name": "모의기관(데모)", "base_url": base + "/", "boards": boards,
               "policy": {"agency_name": "모의기관", "home_url": base + "/", "pages": {"org_chart": base + "/about/org", "contact": base + "/about/contact"},
                          "sample_pages": [base + "/board/notice"]}}
    ml.save_json(os.path.join(ws, "site-profile.json"), profile)
    ml.save_json(os.path.join(ws, "settings.json"), {
        "min_interval_sec": 0, "retries": 0, "retry_wait_sec": 0, "max_concurrency": 2, "contact": "데모(모의 데이터)",
        "typo_check": {"enabled": True, "max_posts_per_board": 3, "max_posts_per_run": 20},
        "llm": {"allowed": True, "provider": "openai", "base_url": "http://127.0.0.1:%d/v1" % llm.server_address[1], "model": "demo-mock-llm"}})
    os.makedirs(os.path.join(ws, "index"))
    with open(os.path.join(ws, "index", "google.txt"), "w", encoding="utf-8") as f:       # 검색 포털 수집 결과(모의)
        f.write("%s/community/77\t자유게시판 글\t호빠\n%s/community/78\t자유게시판 일반 글\t호빠\n%s/old/gone\t삭제된 글\t\n" % (base, base, base))
    os.environ.update({"LLM_API_KEY": "demo-not-a-secret", "LLM_MODEL": "demo-mock-llm", "LLM_BASE_URL": "http://127.0.0.1:%d/v1" % llm.server_address[1]})

    print("== 데모 시작 (모의 기관 사이트 %s, 모의 LLM) ==" % base)
    code, out, err = quiet(run_checks.main, ["--workspace", ws, "--checks", "all", "--mode", "full", "--judge", "yes", "--today", str(today)])
    rd = os.path.join(ws, "runs", str(today))
    print(out.strip())
    if code not in (0, 4):
        print("[오류] 점검 실행 실패(종료코드 %s): %s" % (code, err.strip()[:300]), file=sys.stderr)
        return 1
    quiet(recent_changes.main, ["--workspace", ws, "--latest", "--quiet", "--today", str(today)])

    summ = ml.load_json(os.path.join(rd, "run-summary.json"), {})
    typo = ml.load_json(os.path.join(rd, "typo-judgement.json"), {"items": []})
    uiux = ml.load_json(os.path.join(rd, "policy-uiux.json"), {"results": []})
    from collections import Counter
    print("\n== 결과 요약 ==")
    print("- 게시판 점검: 판정 %s / 지적 %d건 (신규 %d)" % (summ.get("status_counts"), summ.get("findings", 0), summ.get("findings_new", 0)))
    print("- 게시글 오타 점검: %d건 점검, 지적 %d건" % (len(typo["items"]), sum(len(i["issues"]) for i in typo["items"])))
    print("- UI/UX 가이드라인(자동 점검): %s" % dict(Counter(r["auto"] for r in uiux["results"])))
    pj = ml.load_json(os.path.join(rd, "search-index-summary.json"), {})
    print("- 검색 포털 점검: URL %s건, 판정 %s" % (pj.get("checked"), pj.get("verdict_counts")))
    print("\n== 결과 파일 (%s) ==" % rd)
    for name in ("checks-summary.md", "inspection-summary.md", "recency-status.csv", "inspection-details.csv", "typo-judgement.json",
                 "policy-policy-week.csv", "policy-uiux.md", "search-index-links.csv"):
        mark = "O" if os.path.exists(os.path.join(rd, name)) else "-"
        print("  [%s] %s" % (mark, name))
    print("  [O] %s (최근 14일 요약)" % os.path.join(ws, "reports", "recent", "latest.md"))
    print("\n※ 위 AI 판단은 '모의 LLM'(규칙 기반)의 응답이며 실제 AI 모델이 아닙니다. 실제 모델 연결은 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 환경변수와")
    print("   workspace/settings.json 의 llm.allowed 로 합니다 (docs/운영가이드.md 6절). 모든 데이터는 가공한 모의 데이터입니다.")
    if args.serve:
        print("\n모의 사이트: %s/home  (Ctrl+C 로 종료)" % base)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
