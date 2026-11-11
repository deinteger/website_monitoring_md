#!/usr/bin/env python3
"""범정부 UI/UX 가이드라인 AI 화면 검토 (표준 라이브러리만 사용).

자동 규칙(policy_check.py --pack uiux)이 다루지 못하는 스타일·컴포넌트 규칙(색상, 타이포그래피, 레이아웃, 컴포넌트 사용성 등)을
**일부 페이지(기본 15개, 사용자 지정 가능)**에 대해 AI가 화면과 가이드라인 원문으로 검토한다. 이 스크립트는
  plan  : 검토할 페이지 선택 → HTML 컴포넌트 탐지 → 가이드라인 목차의 해당 쪽 범위 매핑 → (가능하면) 화면 캡처·계산된 스타일·명도 대비 수집
          → uiux-review-queue.json (AI가 읽을 대기열)
  merge : AI가 작성한 uiux-review.json 을 검증(가이드라인 쪽·원문 인용 확인)해 uiux-review.csv/.md 로 정리
를 한다. 판단(준수/미준수)은 AI가 하며 core/uiux-review-guide.md 를 따른다.

  python scripts/uiux_review.py plan  --workspace workspace --sample 15            # 자동 표본
  python scripts/uiux_review.py plan  --workspace workspace --pages https://www.example.go.kr/a,https://www.example.go.kr/b
  python scripts/uiux_review.py merge --workspace workspace
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guidelines as gl  # noqa: E402
import monlib as ml  # noqa: E402
import policy_check as pc  # noqa: E402

try:
    import render as rd
except Exception:  # pragma: no cover
    rd = None

SKIP_A = re.compile(r"<a\b[^>]*href\s*=\s*[\"']#[^\"']*[\"'][^>]*>(?:\s*<[^>]+>)*[^<]{0,40}(?:바로\s*가기|건너뛰기)")
COMPONENTS = [  # (이름, HTML 탐지 정규식, 가이드라인 목차 제목 키워드) — 우선순위 순
    ("공식 배너", re.compile(r"masthead|이\s*누리집은\s*대한민국\s*공식"), "공식 배너"),
    ("운영기관 식별자", re.compile(r"이\s*누리집은.{1,40}?운영하는\s*누리집"), "운영기관 식별자"),
    ("헤더", re.compile(r"<header\b|(?:class|id)\s*=\s*[\"'][^\"']*header", re.I), "헤더"),
    ("푸터", re.compile(r"<footer\b|(?:class|id)\s*=\s*[\"'][^\"']*footer", re.I), "푸터"),
    ("건너뛰기 링크", SKIP_A, "건너뛰기 링크"),
    ("메인 메뉴", re.compile(r"<nav\b|(?:class|id)\s*=\s*[\"'][^\"']*(?:gnb|main[-_]?menu)", re.I), "메인 메뉴"),
    ("브레드크럼", re.compile(r"breadcrumb|bread-crumb|navi_path|page_path|location_?path", re.I), "브레드크럼"),
    ("사이드 메뉴", re.compile(r"(?:class|id)\s*=\s*[\"'][^\"']*(?:lnb|side[-_]?(?:menu|nav)|snb)", re.I), "사이드 메뉴"),
    ("페이지네이션", re.compile(r"pagina|paging|pageing", re.I), "페이지네이션"),
    ("탭", re.compile(r"role\s*=\s*[\"']tablist|(?:class|id)\s*=\s*[\"'][^\"']*\btabs?\b", re.I), "탭바"),
    ("표", re.compile(r"<table\b", re.I), "표(Table)"),
    ("버튼", re.compile(r"<button\b|type\s*=\s*[\"'](?:submit|button)", re.I), "버튼(Button)"),
    ("텍스트 입력·검색", re.compile(r"type\s*=\s*[\"'](?:text|search)|<textarea\b", re.I), "텍스트 영역"),
    ("셀렉트", re.compile(r"<select\b", re.I), "셀렉트"),
    ("라디오 버튼", re.compile(r"type\s*=\s*[\"']radio", re.I), "라디오 버튼"),
    ("체크박스", re.compile(r"type\s*=\s*[\"']checkbox", re.I), "체크박스"),
    ("날짜 입력", re.compile(r"type\s*=\s*[\"']date|datepicker", re.I), "날짜 입력 필드"),
    ("툴팁", re.compile(r"tooltip", re.I), "툴팁"),
    ("모달", re.compile(r"role\s*=\s*[\"']dialog|(?:class|id)\s*=\s*[\"'][^\"']*modal", re.I), "모달"),
    ("아코디언", re.compile(r"accordion", re.I), "아코디언"),
    ("캐러셀", re.compile(r"swiper|slick|carousel", re.I), "캐러셀"),
    ("언어 변경", re.compile(r"lang(?:uage)?[-_]?(?:select|switch|change)|>\s*English\s*<", re.I), "언어 변경"),
]
STYLE_KEYS = [("색상", "색상(Color)"), ("타이포그래피", "타이포그래피"), ("형태", "형태(Shape)"), ("레이아웃", "레이아웃(Layout)"), ("아이콘", "아이콘(Icon)")]
HOW_TO = ("각 page 에 대해: (1) 화면 캡처(screenshots)를 열어 보거나 브라우저로 url 을 연다(needs_browser=true 이면 반드시 브라우저로 본다). "
          "(2) components 의 guideline pages 와 style_sections 중 필요한 쪽만 `python scripts/guidelines.py pages uiux <시작>-<끝>`(41쪽 미만)로 읽는다. "
          "(3) 가이드라인의 사용성·접근성·상호작용 요건과 화면을 대조해 준수/미준수/확인불가를 판단한다. 본 것만 쓰고, 보지 못한 것은 확인불가로 한다. "
          "(4) 모든 항목에 guideline_page 와 guideline_quote(원문 그대로)를 적는다. 인용이 원문에 없으면 확인불가로 낮춰진다. "
          "(5) computed_styles·contrast 는 측정값이다. 명도 대비 등 기준값은 추측하지 말고 가이드라인 원문에서 확인해 인용한다. "
          "(6) 결과는 uiux-review.json 에 저장하고 `uiux_review.py merge` 로 병합한다. 자세한 기준: core/uiux-review-guide.md")
SCHEMA = {"model": "사용한 모델/도구", "items": [{"page_id": "P01", "component": "푸터", "guideline_page": 249, "guideline_quote": "원문 그대로의 구절",
                                               "verdict": "준수|미준수|확인불가", "observation": "화면에서 본 내용(20자 이상)", "severity": "높음|보통|낮음",
                                               "confidence": "high|medium|low", "evidence_ref": "스크린샷 경로 또는 선택자"}]}


def toc_range(entries, keyword, lo, hi):
    for e in entries:
        if keyword in e["title"] and lo <= e["page"] <= hi:
            return [e["page"], e["end_page"]], e["title"]
    return None, None


def select_pages(profile, ws, sample, explicit):
    """검토할 페이지 선택. 사용자 지정 > 프로필 policy.uiux_pages > 자동 표본(홈, 대표 페이지, 게시판 유형별 목록·상세, 정적 페이지)."""
    pol = profile.get("policy") or {}
    chosen = list(explicit) or list(pol.get("uiux_pages") or [])
    out, seen = [], set()

    def add(kind, url):
        u = (url or "").split("#")[0]
        if u and u not in seen:
            seen.add(u)
            out.append((kind, u))
    if chosen:
        for u in chosen:
            add("지정", u)
        return out[: max(1, sample)] if not explicit else out
    cache = ml.load_json(os.path.join(ws, "cache.json"), {"boards": {}}) or {"boards": {}}
    add("홈", pol.get("home_url") or profile.get("base_url") or profile["boards"][0]["url"])
    for u in (pol.get("pages") or {}).values():
        add("대표 페이지", u)
    sig = {}
    for b in profile["boards"]:
        if b.get("exclude") or b.get("type") == "static":
            continue
        k = json.dumps(b.get("region"), sort_keys=True)
        if sig.get(k, 0) >= 2:
            continue
        sig[k] = sig.get(k, 0) + 1
        add("게시판 목록", b["url"])
        rp = [p for p in ((cache["boards"].get(b["id"]) or {}).get("recent_posts") or []) if p.get("url")]
        if rp:
            add("게시글 상세", rp[0]["url"])
    for b in profile["boards"]:
        if b.get("type") == "static" and not b.get("exclude"):
            add("정적 페이지", b["url"])
    return out[: max(1, sample)]


def detect_components(html, toc, per_page):
    found = []
    for name, rx, kw in COMPONENTS:
        hits = len(rx.findall(html))
        if not hits:
            continue
        rng, title = toc_range(toc, kw, 220, 760)
        if rng:
            m = rx.search(html)
            found.append({"name": name, "guideline_title": title, "pages": rng, "hits": hits, "snippet": re.sub(r"\s+", " ", html[max(0, m.start() - 20): m.start() + 160])})
    return found[:per_page]


def main_plan(args):
    ws = args.workspace
    settings = ml.load_settings(ws)
    try:
        profile = ml.load_profile(ws)
    except ml.ProfileError as e:
        print("[설정 오류] %s" % e, file=sys.stderr)
        return 1
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    gdir = args.guidelines_dir or os.path.join(pc.ROOT, "guidelines")
    meta, _, ver, base = pc.load_pack(gdir, "uiux")
    tocj = ml.load_json(os.path.join(base, "source", "toc.json"))
    if not tocj:
        print("[오류] 가이드라인 목차(source/toc.json)가 없습니다. 이 기능은 저장소 원본(원문 포함)에서 실행하세요.", file=sys.stderr)
        return 1
    toc = tocj["entries"]
    explicit = [x for x in (args.pages or "").split(",") if x.strip()]
    if args.pages_file:
        explicit += [l.strip() for l in open(args.pages_file, encoding="utf-8") if l.strip() and not l.startswith("#")]
    sel = select_pages(profile, ws, args.sample, explicit)
    fetcher = ml.Fetcher(settings, profile["allowed_domains"])
    for _, u in sel:
        if not fetcher.host_allowed(u):
            print("[거부] 허용 도메인 밖의 주소입니다: %s" % u, file=sys.stderr)
            return 1
    if args.dry_run:
        print(json.dumps({"pages": [{"kind": k, "url": u} for k, u in sel], "page_requests": len(sel), "render": args.render,
                          "estimate_note": "렌더링(화면 캡처) 사용 시 페이지당 브라우저 요청이 추가됩니다"}, ensure_ascii=False, indent=2))
        return 0
    try:
        pages = pc.fetch_pages([("P%02d" % (i + 1), u) for i, (_, u) in enumerate(sel)], fetcher)
    except ml.Blocked as e:
        print("[중단] %s" % e, file=sys.stderr)
        return 2
    renderer, render_note = None, None
    if args.render != "off" and rd is not None:
        r = rd.Renderer(settings, fetcher.host_allowed, fetcher.ua)
        try:
            r.start()
            renderer = r
        except rd.RenderUnavailable as e:
            render_note = str(e)
    elif args.render != "off":
        render_note = "render 모듈 없음"
    outdir = os.path.join(ws, "runs", str(today))
    items = []
    for i, (kind, url) in enumerate(sel):
        pid = "P%02d" % (i + 1)
        p = pages[pid]
        item = {"id": pid, "kind": kind, "url": url, "final_url": p["final_url"], "title": p["title"], "status": p["status"], "rendered": False,
                "screenshots": {"desktop": None, "mobile": None}, "needs_browser": True, "computed_styles": [], "contrast": [], "components": [], "style_sections": []}
        html = p["html"]
        if renderer and p["ok"]:
            shots = [{"name": "desktop", "path": os.path.join(outdir, "uiux", "shots", "%s-desktop.png" % pid), "width": 1280, "height": 900, "full_page": True},
                     {"name": "mobile", "path": os.path.join(outdir, "uiux", "shots", "%s-mobile.png" % pid), "width": 390, "height": 844, "full_page": False}]
            cap = renderer.capture(p["final_url"], shots)
            if cap.get("html"):
                html, item["rendered"] = cap["html"], True
                item["screenshots"] = dict((k, cap["shots"].get(k)) for k in ("desktop", "mobile"))
                item["needs_browser"] = not all(item["screenshots"].values())
                item["computed_styles"] = cap.get("styles") or []
                item["contrast"] = [{"selector": s["selector"], "text": s["text"], "ratio": rd.contrast_ratio(s["color"], s["background"]), "fontSize": s["fontSize"]}
                                    for s in item["computed_styles"] if s["text"]]
            if cap.get("error"):
                item["capture_note"] = cap["error"]
        text = ml.html_parse(html)[0] if html else ""
        item["components"] = detect_components(html, toc, args.components_per_page) if p["ok"] and not p.get("thin") else []
        if p.get("thin"):
            item["note"] = "본문이 비어 있음(스크립트 렌더링 페이지 추정): 브라우저로 직접 확인 필요"
        item["text_excerpt"] = ml.mask_pii(text[:1200])
        for label, kw in STYLE_KEYS:
            rng, title = toc_range(toc, kw, 60, 220)
            if rng:
                item["style_sections"].append({"name": label, "guideline_title": title, "pages": rng})
        items.append(item)
    if renderer:
        renderer.close()
    q = {"date": str(today), "guideline_version": ver, "how_to": HOW_TO, "result_schema": SCHEMA, "render_note": render_note,
         "guideline_source": os.path.relpath(os.path.join(base, "source"), pc.ROOT), "pages": items}
    ml.save_json(os.path.join(outdir, "uiux-review-queue.json"), q)
    print(json.dumps({"date": str(today), "pages": len(items), "rendered": sum(1 for i in items if i["rendered"]), "needs_browser": sum(1 for i in items if i["needs_browser"]),
                      "components_total": sum(len(i["components"]) for i in items), "render_note": render_note, "requests": fetcher.request_count,
                      "queue": os.path.join(outdir, "uiux-review-queue.json")}, ensure_ascii=False, indent=2))
    return 0


def main_merge(args):
    ws = args.workspace
    runs = os.path.join(ws, "runs")
    day = args.date or next((d for d in sorted(os.listdir(runs), reverse=True) if os.path.exists(os.path.join(runs, d, "uiux-review-queue.json"))), "") if os.path.isdir(runs) else ""
    if not day:
        print("[오류] uiux-review-queue.json 이 없습니다. 먼저 plan 을 실행하세요.", file=sys.stderr)
        return 1
    rd_ = os.path.join(runs, day)
    queue = ml.load_json(os.path.join(rd_, "uiux-review-queue.json"))
    res = ml.load_json(os.path.join(rd_, "uiux-review.json"))
    if res is None:
        print("[오류] %s 가 없습니다 (스키마: 대기열의 result_schema)." % os.path.join(rd_, "uiux-review.json"), file=sys.stderr)
        return 1
    gdir = args.guidelines_dir or os.path.join(pc.ROOT, "guidelines")
    meta, _, ver, base = pc.load_pack(gdir, "uiux")
    src = gl.load_source_pages(base, meta)
    if src is None:
        print("[오류] 가이드라인 원문이 없어 인용을 검증할 수 없습니다.", file=sys.stderr)
        return 1
    pid_map = dict((p["id"], p) for p in queue["pages"])
    rows, rejected = [], []
    for it in res.get("items", []):
        why = None
        gp = it.get("guideline_page")
        if it.get("page_id") not in pid_map:
            why = "대기열에 없는 page_id"
        elif it.get("verdict") not in ("준수", "미준수", "확인불가"):
            why = "verdict 는 준수/미준수/확인불가"
        elif not isinstance(gp, int) or gp not in src:
            why = "guideline_page 가 원문에 없음"
        elif len((it.get("observation") or "").strip()) < 20:
            why = "observation(화면에서 본 내용)이 없거나 너무 짧음"
        elif not (it.get("component") or "").strip():
            why = "component 가 없음"
        elif it.get("verdict") == "미준수" and not (it.get("evidence_ref") or "").strip():
            why = "미준수는 evidence_ref(스크린샷 경로 또는 선택자)가 필요"
        if why:
            rejected.append({"page_id": it.get("page_id"), "component": it.get("component"), "reason": why})
            continue
        verified = gl.norm(it.get("guideline_quote") or "") != "" and gl.norm(it["guideline_quote"]) in gl.norm(src[gp])
        verdict, note = it["verdict"], ""
        if not verified:     # 원문에 없는 인용(환각)이면 판정을 확인불가로 낮춘다
            verdict, note = "확인불가", "원문 인용 검증 실패: 판정을 '확인불가'로 하향(원래: %s)" % it["verdict"]
        rows.append({"page_id": it["page_id"], "url": pid_map[it["page_id"]]["url"], "component": it["component"], "verdict": verdict, "observation": it["observation"].strip(),
                     "severity": it.get("severity") if it.get("severity") in ("높음", "보통", "낮음") else "보통", "confidence": it.get("confidence") if it.get("confidence") in ("high", "medium", "low") else "low",
                     "guideline_page": gp, "guideline_quote": it.get("guideline_quote", ""), "evidence_ref": it.get("evidence_ref", ""), "quote_verified": verified, "note": note})
    order = {"미준수": 0, "확인불가": 1, "준수": 2}
    rows.sort(key=lambda r: (order[r["verdict"]], r["page_id"]))
    with open(os.path.join(rd_, "uiux-review.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["페이지ID", "URL", "컴포넌트", "판정", "관찰 내용", "심각도", "신뢰도", "가이드라인 쪽", "원문 인용", "근거 참조", "인용 검증", "비고"])
        for r in rows:
            w.writerow([r["page_id"], r["url"], r["component"], r["verdict"], r["observation"], r["severity"], r["confidence"], r["guideline_page"], r["guideline_quote"],
                        r["evidence_ref"], "통과" if r["quote_verified"] else "실패", r["note"]])
    from collections import Counter
    c = Counter(r["verdict"] for r in rows)
    imgdir = os.path.relpath(os.path.join(base, "source", "digital_gov_guideline_pages"), pc.ROOT)
    L = ["# UI/UX 가이드라인 AI 화면 검토 결과 (%s, 가이드라인 %s)\n" % (day, ver), "- 검토 페이지 %d개, 항목 %d건: %s" % (len(queue["pages"]), len(rows), ", ".join("%s %d" % kv for kv in c.most_common())),
         "- 검토자: %s" % res.get("model", "(미기재)"), "- **주의**: AI의 화면 판단이며 사람의 최종 확인 전 참고 결과입니다. 원문 인용이 검증되지 않은 항목은 확인불가로 낮춰 표시됩니다."]
    if rejected:
        L.append("- 형식 오류로 제외된 항목 %d건: %s" % (len(rejected), "; ".join("%s/%s(%s)" % (x["page_id"], x["component"], x["reason"]) for x in rejected[:6])))
    L.append("")
    cur = None
    for r in sorted(rows, key=lambda r: (r["page_id"], order[r["verdict"]])):
        if r["page_id"] != cur:
            cur = r["page_id"]
            L.append("\n## %s %s\n" % (cur, pid_map[cur]["url"]))
        L.append("- **[%s / %s]** %s — %s\n  - 근거: 가이드라인 %d쪽 \"%s\" (인용 %s) · 쪽 이미지 `%s/page_%04d.jpg`%s%s" % (
            r["verdict"], r["severity"], r["component"], r["observation"], r["guideline_page"], r["guideline_quote"][:80], "검증됨" if r["quote_verified"] else "검증 실패", imgdir,
            r["guideline_page"], (" · 화면 근거: %s" % r["evidence_ref"]) if r["evidence_ref"] else "", (" · " + r["note"]) if r["note"] else ""))
    open(os.path.join(rd_, "uiux-review.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps({"date": day, "applied": len(rows), "verdicts": dict(c), "rejected": rejected}, ensure_ascii=False, indent=2))
    return 0 if not rejected else 3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--workspace", default="workspace")
    pl.add_argument("--sample", type=int, default=15, help="자동 표본 페이지 수(10~20 권장)")
    pl.add_argument("--pages", default="", help="검토할 페이지 주소(쉼표 구분). 지정하면 자동 표본을 쓰지 않는다")
    pl.add_argument("--pages-file", default="")
    pl.add_argument("--components-per-page", type=int, default=8)
    pl.add_argument("--render", choices=["off", "auto"], default="auto", help="auto: Playwright 가 있으면 화면 캡처·계산된 스타일 수집")
    pl.add_argument("--guidelines-dir", default="")
    pl.add_argument("--today", default="")
    pl.add_argument("--dry-run", action="store_true")
    mg = sub.add_parser("merge")
    mg.add_argument("--workspace", default="workspace")
    mg.add_argument("--date", default="")
    mg.add_argument("--guidelines-dir", default="")
    args = ap.parse_args(argv)
    return main_plan(args) if args.cmd == "plan" else main_merge(args)


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
