#!/usr/bin/env python3
"""점검 범위 선택 실행기 (표준 라이브러리만 사용).

  python scripts/run_checks.py --list                         # 선택 가능한 점검과 비용·네트워크·AI 사용 안내
  python scripts/run_checks.py --interactive                  # 번호로 고르기
  python scripts/run_checks.py --checks all --dry-run         # 요청량만 확인
  python scripts/run_checks.py --checks board,uiux            # 게시판 점검 + UI/UX 가이드라인 점검
  python scripts/run_checks.py --checks policy,portal         # 정책정보 확인주간 + 검색 포털 점검

점검 종류
  all     전체: board + policy + uiux + uiux-ai + portal (+ 설정에서 켠 경우 typo)
  board   게시판 점검: 접속·링크 오류, 3개월 최신성, 변경 감지, 현행화 의심·문구(AI 선택)
  typo    게시글 본문 오타 점검(신규 글만, 상한·1회). 게시판 점검 과정에서 수집한다
  policy  정책정보 확인주간 체크리스트 점검 (guidelines/policy-week)
  uiux    범정부 UI/UX 가이드라인 준수 점검 (guidelines/uiux)
  uiux-ai UI/UX 화면 AI 검토: 일부 페이지(기본 15, --ui-pages 로 지정 가능)를 AI가 화면·가이드라인 원문으로 검토하는 대기열 생성
  portal  검색 포털(구글·네이버·다음) 점검: URL 수집 계획 생성 → 수집한 URL 점검

종료코드: 0 정상, 2 차단·장애 의심 중단(부분 결과), 4 포털 점검에 URL 수집이 필요함, 1 설정 오류·기타 실패
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_index_links  # noqa: E402
import collect  # noqa: E402
import monlib as ml  # noqa: E402
import policy_check  # noqa: E402
import portal_plan  # noqa: E402
import run_all  # noqa: E402
import uiux_review  # noqa: E402

CHECKS = [
    ("board", "게시판 점검", "접속·링크 오류, 3개월 최신성, 변경 감지 (AI 판단은 선택)", "사이트 요청: 목록 수 + 링크", "선택"),
    ("typo", "게시글 본문 오타 점검", "신규 게시글 본문의 맞춤법·띄어쓰기·오탈자 (게시판 점검 과정에서 수집)", "사이트 요청: 신규 글 상세(상한 있음)", "필요"),
    ("policy", "정책정보 확인주간 점검", "체크리스트 22개 항목 + 붙임: 자동 확인·증거 수집, 사람 응답 문항 분리", "사이트 요청: 대표 페이지 최대 8개 + 자원 크기", "불필요"),
    ("uiux", "범정부 UI/UX 가이드라인 점검", "공식 배너·식별자·헤더·푸터·건너뛰기 링크 (원문 쪽 근거)", "사이트 요청: 대표 페이지 최대 8개", "불필요"),
    ("uiux-ai", "UI/UX 화면 AI 검토(일부 페이지)", "자동 점검이 못 다루는 스타일·컴포넌트 규칙을 AI가 화면·원문으로 검토 (기본 15페이지, 지정 가능)", "사이트 요청: 검토 페이지 수 + 화면 캡처", "필요"),
    ("portal", "검색 포털 점검(구글·네이버·다음)", "site: 검색 결과의 깨진 링크·소프트404·불법 광고 의심", "검색 URL 수집(브라우저) + 결과 URL 점검", "불필요"),
]
ORDER = [c[0] for c in CHECKS]


def parse_selection(spec, settings):
    items = [x.strip() for x in spec.split(",") if x.strip()]
    sel = []
    for it in items:
        if it == "all":
            sel += ["board", "policy", "uiux", "uiux-ai", "portal"] + (["typo"] if (settings.get("typo_check") or {}).get("enabled") else [])
        elif it in ORDER:
            sel.append(it)
        else:
            raise SystemExit("[오류] 알 수 없는 점검 '%s' (all, board, typo, policy, uiux, portal)" % it)
    out = [c for c in ORDER if c in sel]
    return out


def interactive():
    """메뉴·프롬프트는 표준 오류로 보내 표준 출력(결과)이 섞이지 않게 한다."""
    w = lambda x: sys.stderr.write(x + "\n")  # noqa: E731
    w("점검 범위를 고르세요 (번호를 쉼표로, 예: 2,4):")
    w("  1) 전체 (게시판 + 정책정보 확인주간 + UI/UX + 검색 포털)")
    for i, (k, name, desc, net, ai) in enumerate(CHECKS, 2):
        w("  %d) %s — %s" % (i, name, desc))
    sys.stderr.write("번호: ")
    sys.stderr.flush()
    raw = input().strip()
    keys = []
    for tok in [t.strip() for t in raw.split(",") if t.strip()]:
        if not tok.isdigit() or not 1 <= int(tok) <= len(CHECKS) + 1:
            raise SystemExit("[오류] 잘못된 번호: %s" % tok)
        keys.append("all" if tok == "1" else CHECKS[int(tok) - 2][0])
    return ",".join(keys)


def _quiet(fn, argv):
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, buf.getvalue(), err.getvalue()


def _json_of(text):
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {}


def portal_inputs(ws):
    files = sorted(glob.glob(os.path.join(ws, "index", "*.txt")))
    return [("%s=%s" % (os.path.splitext(os.path.basename(f))[0], f)) for f in files if os.path.getsize(f) > 0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--checks", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental", help="게시판 점검 모드")
    ap.add_argument("--judge", choices=["auto", "yes", "no"], default="no", help="게시판 AI 판단(외부 AI 전송은 보안 승인 후)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", default="")
    ap.add_argument("--guidelines-dir", default="")
    ap.add_argument("--engines", default="google,naver,daum")
    ap.add_argument("--keywords", default="1-30")
    ap.add_argument("--render", choices=["off", "auto", "always"], default="auto", help="자바스크립트 렌더링(선택 모듈 Playwright) 사용 방식")
    ap.add_argument("--ui-sample", type=int, default=15, help="UI/UX 화면 AI 검토 자동 표본 페이지 수")
    ap.add_argument("--ui-pages", default="", help="UI/UX 화면 AI 검토 대상 페이지 주소(쉼표 구분, 지정 시 자동 표본 미사용)")
    args = ap.parse_args(argv)

    if args.list:
        print("선택 가능한 점검 (--checks all|board|typo|policy|uiux|portal, 쉼표로 조합):\n")
        for k, name, desc, net, ai in CHECKS:
            print("%-7s %s\n        %s\n        네트워크: %s / AI: %s\n" % (k, name, desc, net, ai))
        print("all     전체 = board + policy + uiux + uiux-ai + portal (+ typo: settings.json에서 켠 경우)")
        return 0
    ws = args.workspace
    settings = ml.load_settings(ws)
    spec = args.checks or (interactive() if args.interactive else "")
    if not spec:
        print("[안내] 점검 범위를 --checks 로 지정하거나 --interactive 로 고르세요 (--list 로 목록 확인).", file=sys.stderr)
        return 1
    sel = parse_selection(spec, settings)
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    tflag = ["--today", args.today] if args.today else []
    gflag = ["--guidelines-dir", args.guidelines_dir] if args.guidelines_dir else []
    run_board = "board" in sel or "typo" in sel
    notes = []
    if "typo" in sel and "board" not in sel:
        notes.append("오타 점검은 게시판 점검 과정에서 수집하므로 게시판 점검을 함께 실행합니다")
    results = []

    def add(check, status, code, detail):
        results.append({"check": check, "status": status, "exit_code": code, "detail": detail})

    # ---- dry-run
    if args.dry_run:
        out = {"selected": sel, "notes": notes, "plans": {}}
        if run_board:
            c, o, e = _quiet(collect.main, ["--workspace", ws, "--mode", args.mode, "--dry-run"] + tflag + (["--typo-check"] if "typo" in sel else []))
            out["plans"]["board"] = _json_of(o) if c == 0 else {"error": e.strip() or o.strip()}
        pk = [p for p in ("policy-week" if "policy" in sel else "", "uiux" if "uiux" in sel else "") if p]
        if pk:
            c, o, e = _quiet(policy_check.main, ["--workspace", ws, "--pack", "all" if len(pk) == 2 else pk[0], "--dry-run"] + gflag)
            out["plans"]["policy_uiux"] = _json_of(o) if c == 0 else {"error": e.strip() or o.strip()}
        if "uiux-ai" in sel:
            c, o, e = _quiet(uiux_review.main, ["plan", "--workspace", ws, "--dry-run", "--sample", str(args.ui_sample)] + (["--pages", args.ui_pages] if args.ui_pages else []) + gflag)
            out["plans"]["uiux_ai"] = _json_of(o) if c == 0 else {"error": e.strip() or o.strip()}
        if "portal" in sel:
            ins = portal_inputs(ws)
            if ins:
                c, o, e = _quiet(check_index_links.main, ["--workspace", ws, "--dry-run"] + sum([["--input", i] for i in ins], []))
                out["plans"]["portal"] = _json_of(o) if c == 0 else {"error": e.strip() or o.strip()}
            else:
                out["plans"]["portal"] = {"note": "수집된 URL 파일(workspace/index/*.txt)이 없어 실행하면 검색 계획만 생성합니다 (종료코드 4)"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 실행
    outdir = os.path.join(ws, "runs", str(today))
    if run_board:
        argv_b = ["--workspace", ws, "--mode", args.mode, "--judge", args.judge] + tflag + (["--typo-check"] if "typo" in sel else [])
        code, o, e = _quiet(run_all.main, argv_b)
        summ = ml.load_json(os.path.join(outdir, "run-summary.json"), {}) or {}
        add("board", "완료" if code == 0 else ("중단(차단·장애 의심)" if code == 2 else "실패"), code,
            "%s: 방문 %s, 지적 %s건 (신규 %s)%s" % (os.path.join(outdir, "inspection-summary.md"), summ.get("visited"), summ.get("findings"), summ.get("findings_new"),
                                                    (", 오타 대상 %s건" % summ.get("typo_items")) if "typo" in sel else ""))
        if "typo" in sel:
            add("typo", "수집 완료(AI 판단 필요)" if code == 0 else "미실시", code, "typo-review-queue.json → 판단은 core/typo-guide.md (judge.py --task typo)")
    pk = [p for p in ("policy-week" if "policy" in sel else "", "uiux" if "uiux" in sel else "") if p]
    if pk:
        code, o, e = _quiet(policy_check.main, ["--workspace", ws, "--pack", "all" if len(pk) == 2 else pk[0], "--render", args.render] + tflag + gflag)
        info = _json_of(o)
        for name, key in (("policy", "policy-week"), ("uiux", "uiux")):
            if name in sel:
                f = (info.get("packs") or {}).get(key, {}).get("files")
                add(name, "완료" if code == 0 and f else ("중단" if code == 2 else "실패"), code, ("%s.md" % f) if f else (e.strip() or "결과 없음"))
    if "uiux-ai" in sel:
        c, o, e = _quiet(uiux_review.main, ["plan", "--workspace", ws, "--sample", str(args.ui_sample), "--render", "off" if args.render == "off" else "auto"]
                         + (["--pages", args.ui_pages] if args.ui_pages else []) + tflag + gflag)
        info = _json_of(o)
        add("uiux-ai", "AI 검토 대기" if c == 0 else ("중단" if c == 2 else "실패"), 4 if c == 0 else c,
            ("검토 페이지 %s개(화면 캡처 %s개, 브라우저 확인 필요 %s개) → %s — AI가 core/uiux-review-guide.md 로 검토 후 uiux_review.py merge" % (info.get("pages"), info.get("rendered"), info.get("needs_browser"), info.get("queue")))
            if c == 0 else (e.strip() or o.strip())[:200])
    if "portal" in sel:
        ins = portal_inputs(ws)
        if not ins:
            c, o, e = _quiet(portal_plan.main, ["--workspace", ws, "--engines", args.engines, "--keywords", args.keywords] + gflag)
            add("portal", "URL 수집 필요", 4 if c == 0 else 1, "검색 계획: %s (엔진별 결과를 workspace/index/<엔진>.txt 로 저장한 뒤 다시 실행)" % os.path.join(ws, "index", "plan.md"))
        else:
            c, o, e = _quiet(check_index_links.main, ["--workspace", ws, "--check-images"] + sum([["--input", i] for i in ins], []) + tflag)
            info = _json_of(o)
            add("portal", "완료" if c == 0 else ("중단" if c == 2 else "실패"), c,
                "URL %s건 점검, 문제 %s건 → %s" % (info.get("checked"), info.get("problems"), os.path.join(outdir, "search-index-links.csv")))

    os.makedirs(outdir, exist_ok=True)
    summary = {"date": str(today), "selected": sel, "notes": notes, "results": results}
    ml.save_json(os.path.join(outdir, "checks-summary.json"), summary)
    L = ["# 점검 실행 요약 (%s)\n" % today, "- 선택: %s" % ", ".join(sel)] + ["- 참고: " + n for n in notes] + ["", "| 점검 | 상태 | 내용 |", "| --- | --- | --- |"]
    L += ["| %s | %s | %s |" % (r["check"], r["status"], r["detail"].replace("|", "\\|")) for r in results]
    open(os.path.join(outdir, "checks-summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    codes = [r["exit_code"] for r in results]
    if 2 in codes:
        return 2
    if 1 in codes:
        return 1
    return 4 if 4 in codes else 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
