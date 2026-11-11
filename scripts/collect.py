#!/usr/bin/env python3
"""홈페이지 수집·1차 판정 스크립트 (표준 라이브러리만 사용).

역할: HTTP 상태, 목록 파싱, 최신 게시일, 달력 기준 3개월 판정, 링크·첨부 점검,
      변경 감지, 신규/지속/해결 비교, AI 판단 대상(ai-review-queue.json) 선별.
AI가 해야 할 추론(현행화 의심, 문구, 연락처 이상 등)은 하지 않는다.

모드
  incremental (기본): 점검 주기가 도래한 게시판만 방문. 미방문 게시판도 캐시 날짜로 3개월 판정은 매번 재계산.
                      AI 판단 대상은 신규·변경·이상 건만.
  full              : 모든 게시판 방문, 링크 점검, AI 판단 대상 전체.

예) python scripts/collect.py --workspace workspace --dry-run
    python scripts/collect.py --workspace workspace --mode incremental
    python scripts/collect.py --workspace workspace --mode full --limit 20      # 시험 점검
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import random
import sys
import threading
import urllib.parse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

try:
    import render as rd
except Exception:  # pragma: no cover - 선택 모듈
    rd = None

ERROR_STATUSES = ("404오류", "500오류", "접속오류", "리다이렉트오류")
OK_FETCH = range(200, 400)

DETAIL_COLUMNS = ["번호", "시스템구분", "분류", "중요도", "메뉴또는영역", "페이지제목", "URL", "최신게시일", "기준일",
                  "경과기간", "발견내용", "판단근거", "권고조치", "스크린샷", "상태", "최초발견일"]
RECENCY_COLUMNS = ["번호", "시스템구분", "콘텐츠영역", "목록페이지제목", "목록URL", "최신게시물제목", "최신게시일", "기준일",
                   "3개월기준일", "경과기간", "판정", "비고"]


# ------------------------------------------------------------------ 판정

def evaluate(res, board, today, months):
    """(판정, 비고). 판정값은 core/report-fields.md 의 판정값을 따른다."""
    if board.get("exclude"):
        return "제외", board.get("exclude_reason", "")
    st, err = res.get("fetch_status"), res.get("fetch_error")
    if st is None:
        return "접속오류", err or "응답 없음"
    if st == 404:
        return "404오류", ""
    if st >= 500:
        return "500오류", "HTTP %d" % st
    if st >= 400:
        return "접속오류", "HTTP %d" % st
    if res.get("redirect_offsite"):
        return "리다이렉트오류", "허용 도메인 밖으로 이동: %s" % res.get("final_url")
    if board.get("type") == "static":
        return "정상", "정적 페이지(게시일 판정 대상 아님)"
    latest = ml.from_iso(res.get("latest_date"))
    if latest is None:
        return "게시일 확인 불가", res.get("date_note") or "목록에서 게시일을 찾지 못함"
    if ml.is_stale(latest, today, months):
        if board.get("recency_exempt"):
            return "정상", "최신성 판정 제외(연례 간행물·아카이브 등)"
        if board.get("irregular"):
            return "담당자 확인 필요", "비정기 게시 영역: 달력 기준 %d개월 경과" % months
        return "게시 최신성 지연", ""
    return "정상", ""


def make_findings(res, board, today, months):
    out = []
    base = {"board_id": res["id"], "system": res["system"], "area": res["name"], "page_title": res.get("page_title", ""),
            "url": res["url"], "latest_date": res.get("latest_date"), "owner": res.get("owner", "")}
    status = res["status"]
    cutoff = ml.add_months(today, -months)
    latest = ml.from_iso(res.get("latest_date"))

    def add(kind, target, category, severity, detail, evidence, action):
        f = dict(base)
        f.update({"key": "%s|%s|%s" % (res["id"], kind, target), "kind": kind, "category": category, "severity": severity,
                  "detail": detail, "evidence": evidence, "action": action,
                  "elapsed": ml.elapsed_text(latest, today) if latest else ""})
        out.append(f)

    if status in ("404오류", "500오류", "접속오류"):
        add("page", "page", "확정 오류", "높음", "페이지 접속 실패 (%s) %s" % (status, res.get("status_note", "")),
            "자동 재시도 후에도 동일 (HTTP %s)" % (res.get("fetch_status") or res.get("fetch_error")), "URL·서버 상태 확인, 메뉴 연결 점검")
    elif status == "리다이렉트오류":
        add("page", "page", "담당자 확인 필요", "보통", "허용 도메인 밖으로 리다이렉트: %s" % res.get("final_url"),
            "최종 URL 호스트가 허용 목록에 없음", "의도된 이동인지 확인")
    elif status == "게시 최신성 지연":
        add("recency", "recency", "게시 최신성 지연", "높음",
            "최신 게시일 %s (경과 %s)" % (res.get("latest_date"), ml.elapsed_text(latest, today)),
            "기준일 %s, %d개월 기준일 %s: 최신 게시일이 기준일 이전(경계 포함)" % (today, months, cutoff),
            "신규 게시 여부 또는 영역 폐지·아카이브 여부 확인")
    elif status == "담당자 확인 필요":
        add("recency", "recency", "담당자 확인 필요", "보통",
            "비정기 게시 영역의 최신 게시일 %s (경과 %s)" % (res.get("latest_date"), ml.elapsed_text(latest, today)),
            "기준일 %s, %d개월 기준일 %s 이전이나 비정기 영역으로 지정됨" % (today, months, cutoff), "게시 계획 확인")
    elif status == "게시일 확인 불가":
        add("nodate", "nodate", "담당자 확인 필요", "보통", "게시일을 확인하지 못함: %s" % res.get("status_note", ""),
            "목록 영역·날짜 형식 미인식 (프로필 보정 또는 AI 확인 필요)", "site-profile의 region/date_regex 보정 또는 직접 확인")
    for le in res.get("link_errors", []):
        label = "첨부파일" if le.get("kind") == "attachment" else "링크"
        detail = "%s 오류: %s (%s)" % (label, le["url"], le.get("status") or le.get("error"))
        if le.get("level") == "broken":
            add("link", le["url"], "확정 오류", "높음", detail, "재시도 후에도 실패", "대상 파일·페이지 복구 또는 링크 수정")
        else:
            add("link", le["url"], "담당자 확인 필요", "보통", detail, "접근 제한 가능성 (401/403/405 등)", "접근 가능 여부 확인")
    return out


# ------------------------------------------------------------------ 게시판 처리

class Ctx(object):
    pass


_LINK_CACHE = {}
_LINK_LOCK = threading.Lock()


def check_links(parsed, base_url, fetcher, settings):
    """목록 영역(region 미지정 시 페이지 전체)의 내부 링크·첨부를 점검한다. 같은 URL은 한 번만 요청한다."""
    seen, targets = set(), []
    for l in parsed["links"]:
        href = (l.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith(("javascript", "mailto:", "tel:")):
            continue
        u = urllib.parse.urldefrag(urllib.parse.urljoin(base_url, href))[0]
        if u in seen or not u.lower().startswith("http"):
            continue
        seen.add(u)
        targets.append(u)
    errors = []
    for u in targets[: int(settings["max_links_per_board"])]:
        if not fetcher.host_allowed(u):
            continue  # 외부 링크는 URL만 기록하고 접속하지 않는다
        with _LINK_LOCK:
            r = _LINK_CACHE.get(u)
        if r is None:
            r = fetcher.check_url(u)
            with _LINK_LOCK:
                _LINK_CACHE[u] = r
        kind = "attachment" if urllib.parse.urlsplit(u).path.lower().endswith(ml.ATTACHMENT_EXT) else "link"
        if r.error or r.status in (404, 410) or (r.status or 0) >= 500:
            errors.append({"url": u, "status": r.status, "error": r.error, "kind": kind, "level": "broken"})
        elif r.status is not None and r.status >= 400:
            errors.append({"url": u, "status": r.status, "error": None, "kind": kind, "level": "suspect"})
    return errors, len(targets)


def get_renderer(ctx):
    """선택 모듈 Renderer 를 필요할 때 한 번만 만든다. 사용 불가면 RenderUnavailable."""
    with ctx.render_lock:
        if ctx.renderer is None and ctx.render_error is None:
            if rd is None:
                ctx.render_error = "render 모듈을 불러오지 못함"
            else:
                r = rd.Renderer(ctx.settings, ctx.fetcher.host_allowed, ctx.fetcher.ua)
                try:
                    r.start()
                    ctx.renderer = r
                except rd.RenderUnavailable as e:
                    ctx.render_error = str(e)
                    sys.stderr.write("[안내] 렌더링 불가: %s\n" % e)
        if ctx.render_error:
            raise rd.RenderUnavailable(ctx.render_error) if rd else RuntimeError(ctx.render_error)
        return ctx.renderer


def rendered_fetch(url, board, ctx):
    """Playwright 로 렌더링해 FetchResult 형태로 돌려준다 (요청 간격은 Fetcher 와 공유)."""
    r = get_renderer(ctx)
    ctx.fetcher.throttle()
    out = r.fetch(url, board.get("render_wait"))
    fr = ml.FetchResult(url)
    fr.status, fr.final_url, fr.error = out["status"], out["final_url"], out["error"]
    fr.headers = {"Content-Type": "text/html; charset=utf-8"}
    fr.body = (out["html"] or "").encode("utf-8")
    return fr


def merge_recent_posts(prev, rows, ctx):
    """'최근 현행화된 게시물' 조회용 이력. 제목은 마스킹해 저장한다.
    first_seen: 이 키트가 처음 관측한 날짜. 게시판 최초 수집(기준선)에서 본 글은 null(알 수 없음)."""
    s, today = ctx.settings, ctx.today
    old = dict((p["key"], p) for p in ((prev or {}).get("recent_posts") or []))
    baseline = prev is None or "recent_posts" not in prev
    for r in rows:
        if r["key"] in old:
            continue
        old[r["key"]] = {"key": r["key"], "title": ml.mask_pii(r["title"]), "date": ml.iso(r["date"]), "url": r.get("href") if (r.get("href") or "").startswith("http") else None,
                         "first_seen": None if baseline else ml.iso(today)}
    keep_from = ml.iso(today - dt.timedelta(days=int(s["recent_posts_keep_days"])))
    kept = [p for p in old.values() if p["date"] >= keep_from]
    kept.sort(key=lambda p: p["date"], reverse=True)
    return kept[: int(s["recent_posts_cap"])]


def collect_typo_items(board, rows, prev, ctx, res):
    """신규(아직 오타 점검하지 않은) 게시글의 본문을 가져와 AI 오타 점검 대기열에 담는다.
    상한: 게시판당 max_posts_per_board, 실행당 max_posts_per_run. 한 번 점검한 글은 다시 요청하지 않는다."""
    tc = ctx.settings["typo_check"]
    checked = list((prev or {}).get("typo_checked") or [])
    res["typo_items"], res["typo_skipped"] = [], []
    res["typo_checked"] = checked
    if not (ctx.typo_enabled and board["type"] == "board" and board.get("typo_check", True) and rows):
        return
    done = set(checked)
    cands = [r for r in rows if r["key"] not in done and r.get("href") and not str(r["href"]).lower().startswith("javascript")]
    cands.sort(key=lambda r: r["date"], reverse=True)
    for r in cands[: int(tc["max_posts_per_board"])]:
        if not ctx.fetcher.host_allowed(r["href"]):
            continue
        with ctx.typo_lock:
            if ctx.typo_budget <= 0:
                res["typo_skipped"].append({"url": r["href"], "reason": "실행당 상한 초과(다음 실행에서 점검)"})
                continue
            ctx.typo_budget -= 1
        resp = ctx.fetcher.get(r["href"])
        if not resp.ok:
            res["typo_skipped"].append({"url": r["href"], "reason": "게시글 접속 실패(HTTP %s %s)" % (resp.status, resp.error or "")})
            continue  # 다음 실행에서 재시도
        body, how = ml.extract_post_body(ml.decode_body(resp.body, resp.headers.get("Content-Type", "")), board)
        checked.append(r["key"])
        if not body.strip():
            res["typo_skipped"].append({"url": r["href"], "reason": "본문을 찾지 못함(%s): site-profile의 body_region 지정 필요" % how})
            continue
        res["typo_items"].append({"board_id": board["id"], "name": board["name"], "system": board["system"], "post_key": r["key"],
                                  "title": ml.mask_pii(r["title"]), "date": ml.iso(r["date"]), "url": r["href"], "body_method": how,
                                  "text": ml.mask_pii(body[: int(tc["max_chars"])]), "truncated": len(body) > int(tc["max_chars"])})
    res["typo_checked"] = checked[-int(tc["checked_cap"]):]


def process_board(board, prev, ctx):
    s, today, f = ctx.settings, ctx.today, ctx.fetcher
    res = {"id": board["id"], "name": board["name"], "system": board["system"], "url": board["url"],
           "owner": board.get("owner", ""), "type": board["type"], "fetched": True, "fetch_status": None,
           "fetch_error": None, "final_url": board["url"], "page_title": "", "latest_date": None, "latest_title": None,
           "fingerprint": None, "changed": False, "window_oldest": None, "post_counting": False, "region_found": True,
           "reasons": [], "link_errors": [], "links_checked": None, "new_posts": 0, "baseline": prev is None,
           "excerpt": "", "titles": [], "date_note": None,
           "seen_posts": dict((prev or {}).get("seen_posts") or {})}   # 접속 실패 시에도 이력 유지
    rows, parsed_first = [], None
    for page in range(1, int(board.get("pages", 1)) + 1):
        url = board["url"] if page == 1 else board["page_url_template"].format(page=page)
        if not f.host_allowed(url):
            res["fetch_error"] = "허용 도메인 아님: %s" % url
            break
        want_render = board.get("render") == "playwright"
        if want_render:
            try:
                r = rendered_fetch(url, board, ctx)
                res["rendered"] = True
            except Exception as e:
                res["reasons"].append("render_unavailable")
                res["date_note"] = "렌더링 불가: %s" % e
                r = f.get(url)
        else:
            r = f.get(url)
        if page == 1:
            res.update(fetch_status=r.status, fetch_error=r.error, final_url=r.final_url)
            orig = urllib.parse.urlsplit(board["url"])
            fin = urllib.parse.urlsplit(r.final_url)
            if r.ok and fin.hostname and not f.host_allowed(r.final_url):
                res["redirect_offsite"] = True
            elif r.ok and fin.path.rstrip("/") != orig.path.rstrip("/"):
                res["reasons"].append("redirected")
        if page == 1 and r.status and 300 <= r.status < 400:
            loc = r.headers.get("Location") or r.headers.get("location") or ""
            res["final_url"] = urllib.parse.urljoin(url, loc)
            res["redirect_offsite"] = True
            break
        if not r.ok:
            break
        html = ml.decode_body(r.body, r.headers.get("Content-Type", ""))
        parsed = ml.parse_list_page(html, r.final_url, board)
        # 자동 보완: 정적 수집으로 목록을 못 읽었으면 렌더링으로 한 번 더 시도 (설정 시)
        if (page == 1 and ctx.settings.get("js_fallback") == "playwright" and not res.get("rendered")
                and board["type"] == "board" and not parsed["rows"] and not parsed["dates"]):
            try:
                r2 = rendered_fetch(url, board, ctx)
                if r2.ok:
                    parsed = ml.parse_list_page(ml.decode_body(r2.body, r2.headers.get("Content-Type", "")), r2.final_url, board)
                    res["rendered"] = True
                    res["final_url"] = r2.final_url
            except Exception as e:
                res["reasons"].append("render_unavailable")
                res["date_note"] = "렌더링 불가: %s" % e
        if page == 1:
            parsed_first = parsed
        rows.extend(parsed["rows"])

    if parsed_first is not None:
        res["page_title"] = parsed_first["page_title"]
        res["fingerprint"] = ml.fingerprint(parsed_first)
        res["region_found"] = parsed_first["region_found"]
        res["changed"] = bool(prev and prev.get("fingerprint") and prev["fingerprint"] != res["fingerprint"])
        res["post_counting"] = bool(rows)
        pool = [r for r in rows if r["date"] <= today]
        if pool:
            top = max(pool, key=lambda r: r["date"])
            res["latest_date"], res["latest_title"] = ml.iso(top["date"]), top["title"]
        elif not rows:
            dates = [d for d in parsed_first["dates"] if d <= today]
            if dates:
                res["latest_date"] = ml.iso(max(dates))
        if rows or parsed_first["dates"]:
            all_d = [r["date"] for r in rows] or parsed_first["dates"]
            res["window_oldest"] = ml.iso(min(all_d))
            if any(d > today for d in all_d):
                res["reasons"].append("future_date")
                if res["latest_date"] is None:
                    res["date_note"] = "미래 날짜만 존재(행사일·마감일 가능성)"
        # 게시글 키 기록 (월별 신규 콘텐츠 집계용)
        seen = dict((prev or {}).get("seen_posts") or {})
        if rows:
            res["new_posts"] = 0 if prev is None else sum(1 for r in rows if r["key"] not in seen)
            for r in rows:
                seen[r["key"]] = ml.iso(r["date"])
            cap = int(s["seen_posts_cap"])
            if len(seen) > cap:
                keep = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:cap]
                seen = dict(keep)
        res["seen_posts"] = seen
        res["excerpt"] = ml.mask_pii(parsed_first["text"][: int(s["excerpt_chars"])])
        res["titles"] = [ml.mask_pii("%s %s" % (r["date"], r["title"])) for r in rows[:15]]
        if board["type"] == "board" and not rows and not parsed_first["dates"]:
            res["reasons"].append("no_date")
            if parsed_first["js_suspected"]:
                res["reasons"].append("js_suspected")
        if not parsed_first["region_found"]:
            res["reasons"].append("region_not_found")

        res["post_links"] = [r["href"] for r in rows[:5] if r.get("href")]
        res["recent_posts"] = merge_recent_posts(prev, rows, ctx)
        collect_typo_items(board, rows, prev, ctx, res)

        # 링크·첨부 점검
        links_due = True
        if prev and prev.get("links_checked"):
            links_due = (today - ml.from_iso(prev["links_checked"])).days >= int(s["link_check_interval_days"])
        do_links = (s["check_links"] and not ctx.no_links and
                    (ctx.mode == "full" or res["changed"] or prev is None or links_due))
        if do_links:
            res["link_errors"], n = check_links(parsed_first, res["final_url"], f, s)
            res["links_checked"] = ml.iso(today)
        else:
            res["link_errors"] = (prev or {}).get("link_errors", [])
            res["links_checked"] = (prev or {}).get("links_checked")
    return res


def cached_result(board, prev):
    res = dict(prev)
    res.update({"id": board["id"], "name": board["name"], "system": board["system"], "url": board["url"],
                "owner": board.get("owner", ""), "type": board["type"], "fetched": False, "reasons": [],
                "excerpt": "", "titles": [], "new_posts": 0, "changed": False})
    return res


# ------------------------------------------------------------------ 계획

def build_plan(boards, cache, mode, today, only, limit, months):
    fetch, skip, excluded = [], [], []
    for b in boards:
        if b.get("exclude"):
            excluded.append(b)
            continue
        prev = cache["boards"].get(b["id"])
        if only:
            (fetch if b["id"] in only else skip).append(b)
            continue
        if mode == "full" or prev is None or prev.get("status") in ERROR_STATUSES:
            fetch.append(b)
            continue
        last = ml.from_iso(prev.get("last_checked"))
        if ml.due_by_cycle(b["cycle"], last, today):
            fetch.append(b)
            continue
        # 주기가 아니어도, 시간 경과로 오늘 새로 '지연'이 되는 게시판은 1회 방문해 재확인한다(신규 글·AI 판단 자료 확보)
        now_status, _ = evaluate(prev, b, today, months)
        if now_status in ("게시 최신성 지연", "담당자 확인 필요") and prev.get("status") != now_status:
            fetch.append(b)
        else:
            skip.append(b)
    if limit:
        extra = fetch[limit:]
        fetch, skip = fetch[:limit], skip + extra
    return fetch, skip, excluded


def estimate(fetch, settings, mode):
    reqs = sum(int(b.get("pages", 1)) for b in fetch)
    link_upper = len(fetch) * int(settings["max_links_per_board"]) if settings["check_links"] else 0
    interval = float(settings["min_interval_sec"])
    tc = settings["typo_check"]
    typo_upper = min(int(tc["max_posts_per_run"]), len(fetch) * int(tc["max_posts_per_board"])) if tc.get("enabled") else 0
    return {"list_requests": reqs, "link_requests_upper_bound": link_upper, "typo_post_requests_upper_bound": typo_upper,
            "est_minutes_min": round(reqs * interval / 60, 1), "est_minutes_max": round((reqs + link_upper + typo_upper) * interval / 60, 1)}


# ------------------------------------------------------------------ 출력

def write_csv(path, columns, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(columns)
        for i, r in enumerate(rows, 1):
            w.writerow([i] + r)


def month_counts(seen):
    c = Counter(d[:7] for d in (seen or {}).values())
    return dict(sorted(c.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    ap.add_argument("--sample-rate", type=float, default=0.0, help="변경 없는 방문 게시판 중 AI 판단에 추가 포함할 비율(0~1)")
    ap.add_argument("--only", default="", help="쉼표로 구분한 board id만 방문")
    ap.add_argument("--limit", type=int, default=0, help="방문 게시판 수 제한(시험 점검용)")
    ap.add_argument("--resume", action="store_true", help="같은 날짜 실행의 중단 지점부터 재개")
    ap.add_argument("--dry-run", action="store_true", help="요청하지 않고 계획·예상 요청량만 출력")
    ap.add_argument("--no-links", action="store_true")
    ap.add_argument("--typo-check", action="store_true", help="신규 게시글 본문을 수집해 AI 오타 점검 대상으로 담는다(settings의 typo_check.enabled와 동일)")
    ap.add_argument("--probe-post", action="store_true", help="--probe 와 함께: 첫 게시글 본문 추출 결과를 미리 본다")
    ap.add_argument("--today", default="", help="기준일(YYYY-MM-DD). 시험·소급 점검용")
    ap.add_argument("--probe", default="", help="board id 1개의 파싱 결과만 출력(캐시 변경 없음)")
    args = ap.parse_args(argv)

    ws = args.workspace
    try:
        settings = ml.load_settings(ws)
        profile = ml.load_profile(ws)
    except ml.ProfileError as e:
        print("[설정 오류] %s" % e, file=sys.stderr)
        return 1
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    months = int(settings["stale_months"])
    boards = profile["boards"]
    for b in boards:
        if int(b.get("pages", 1)) > 1 and "{page}" not in b.get("page_url_template", ""):
            print("[설정 오류] %s: pages>1 이면 page_url_template({page} 포함) 필요" % b["id"], file=sys.stderr)
            return 1

    fetcher = ml.Fetcher(settings, profile["allowed_domains"])
    _LINK_CACHE.clear()
    ctx = Ctx()
    ctx.settings, ctx.today, ctx.fetcher, ctx.mode, ctx.no_links = settings, today, fetcher, args.mode, args.no_links
    ctx.renderer, ctx.render_error, ctx.render_lock = None, None, threading.Lock()
    ctx.typo_enabled = bool(args.typo_check or settings["typo_check"].get("enabled"))
    ctx.typo_budget, ctx.typo_lock = int(settings["typo_check"]["max_posts_per_run"]), threading.Lock()

    if args.probe:
        b = next((x for x in boards if x["id"] == args.probe), None)
        if not b:
            print("board id 없음: %s" % args.probe, file=sys.stderr)
            return 1
        res = process_board(b, None, ctx)
        out = {k: res[k] for k in ("id", "url", "fetch_status", "fetch_error", "final_url", "page_title", "region_found",
                                    "latest_date", "latest_title", "window_oldest", "post_counting", "fingerprint", "reasons")}
        if args.probe_post and res.get("post_links"):
            pr = fetcher.get(res["post_links"][0])
            if pr.ok:
                body, how = ml.extract_post_body(ml.decode_body(pr.body, pr.headers.get("Content-Type", "")), b)
                out["post_preview"] = {"url": res["post_links"][0], "method": how, "chars": len(body), "text_head": ml.mask_pii(body[:300])}
            else:
                out["post_preview"] = {"url": res["post_links"][0], "error": "HTTP %s %s" % (pr.status, pr.error or "")}
        out["rendered"] = bool(res.get("rendered"))
        out["date_note"] = res.get("date_note")
        out["rows_seen"] = len(res.get("seen_posts", {}))
        if ctx.renderer:
            ctx.renderer.close()
        out["titles"] = res["titles"][:5]
        out["status"], out["note"] = evaluate(res, b, today, months)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    cache_path = os.path.join(ws, "cache.json")
    cache = ml.load_json(cache_path, None) or {"version": 1, "boards": {}}
    only = set(x for x in args.only.split(",") if x)
    fetch, skip, excluded = build_plan(boards, cache, args.mode, today, only, args.limit, months)
    est = estimate(fetch, settings, args.mode)
    plan = {"mode": args.mode, "today": str(today), "boards_total": len(boards), "to_fetch": len(fetch),
            "skipped_by_cycle": len(skip), "excluded": len(excluded), "estimate": est,
            "request_policy": {"max_concurrency": settings["max_concurrency"], "min_interval_sec": settings["min_interval_sec"],
                               "user_agent": fetcher.ua, "retries": settings["retries"],
                               "abort_after_blocked": settings["abort_after_blocked"]},
            "allowed_domains": profile["allowed_domains"],
            "js_handling": {"js_fallback": settings["js_fallback"],
                            "render_playwright_boards": sum(1 for b in fetch if b.get("render") == "playwright")}}
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    run_dir = os.path.join(ws, "runs", str(today))
    os.makedirs(run_dir, exist_ok=True)
    jl_path = os.path.join(run_dir, "results.jsonl")
    done = {}
    if args.resume and os.path.exists(jl_path):
        with open(jl_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    done[r["id"]] = r
    elif os.path.exists(jl_path):
        os.remove(jl_path)

    lock = threading.Lock()
    results, aborted = dict(done), {"v": False}

    def work(b):
        if b["id"] in done:
            return None
        try:
            r = process_board(b, cache["boards"].get(b["id"]), ctx)
        except ml.Blocked:
            aborted["v"] = True
            return None
        except Exception as e:  # 한 게시판의 예외가 전체를 멈추지 않게 한다
            r = {"id": b["id"], "name": b["name"], "system": b["system"], "url": b["url"], "owner": b.get("owner", ""),
                 "type": b["type"], "fetched": True, "fetch_status": None, "fetch_error": "내부 오류: %r" % (e,),
                 "reasons": [], "link_errors": [], "excerpt": "", "titles": []}
        with lock:
            with open(jl_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            results[b["id"]] = r
        return r

    try:
        with cf.ThreadPoolExecutor(max_workers=int(settings["max_concurrency"])) as ex:
            list(ex.map(work, fetch))
    finally:
        if ctx.renderer:
            ctx.renderer.close()

    # 판정·AI 대상 선별
    rng_rate = max(0.0, min(1.0, args.sample_rate))
    prev_findings = {}
    for bid, c in cache["boards"].items():
        for f in c.get("findings", []):
            prev_findings[f["key"]] = f
    all_findings, queue, final = [], [], {}
    board_ids = set()
    for b in boards:
        board_ids.add(b["id"])
        prev = cache["boards"].get(b["id"])
        if b["id"] in results:
            res = results[b["id"]]
        elif prev is not None or b.get("exclude"):
            res = cached_result(b, prev or {})
        else:
            continue  # 방문하지 못했고 캐시도 없음(limit/only 사용 시)
        res["status"], res["status_note"] = evaluate(res, b, today, months)
        res["note"] = res["status_note"]
        reasons = list(res.get("reasons", []))
        if res["fetched"] and res.get("fetch_status") in OK_FETCH and res["status"] != "제외":
            if prev is None:
                reasons.append("new_board")
            if res.get("changed"):
                reasons.append("changed")
            if res["status"] == "담당자 확인 필요":
                reasons.append("irregular_stale")
            if res["status"] == "게시 최신성 지연" and (prev or {}).get("status") != "게시 최신성 지연":
                reasons.append("newly_stale")
            if args.mode == "full":
                reasons.append("full_mode")
            elif not reasons and rng_rate and random.Random("%s:%s" % (today, b["id"])).random() < rng_rate:
                reasons.append("sample")
        res["reasons"] = sorted(set(reasons))
        res["findings"] = make_findings(res, b, today, months)
        final[b["id"]] = res
        all_findings.extend(res["findings"])
        if res["reasons"]:
            queue.append({"board_id": b["id"], "system": res["system"], "name": res["name"], "url": res["url"],
                          "owner": res.get("owner", ""), "type": res["type"], "status": res["status"],
                          "irregular": bool(b.get("irregular")), "recency_exempt": bool(b.get("recency_exempt")),
                          "latest_date": res.get("latest_date"), "latest_title": res.get("latest_title"),
                          "previous_latest_date": (prev or {}).get("latest_date"), "reasons": res["reasons"],
                          "titles": res.get("titles", []), "excerpt": res.get("excerpt", ""), "note": res["note"]})

    # 신규·지속·해결
    keys_now = set(f["key"] for f in all_findings)
    for f in all_findings:
        old = prev_findings.get(f["key"])
        f["state"] = "지속" if old else "신규"
        f["first_seen"] = old["first_seen"] if old else str(today)
    resolved = []
    for k, f in prev_findings.items():
        if k in keys_now or f["board_id"] not in final:
            continue
        # 방문한 게시판이거나, 방문하지 않았어도 날짜 재계산으로 사라진 최신성 지적은 해결로 본다
        if final[f["board_id"]]["fetched"] or f["kind"] == "recency":
            resolved.append(dict(f, state="해결", resolved_on=str(today)))
    # 캐시 갱신
    for bid, res in final.items():
        entry = {k: v for k, v in res.items() if k not in ("excerpt", "titles", "reasons", "changed", "new_posts", "fetched",
                                                               "typo_items", "typo_skipped", "post_links")}
        if res["fetched"]:
            entry["last_checked"] = str(today)
        else:
            entry["last_checked"] = cache["boards"].get(bid, {}).get("last_checked")
        entry["findings"] = [dict(f) for f in res["findings"]]
        for f in entry["findings"]:
            f.pop("state", None)
        cache["boards"][bid] = entry
    for bid in list(cache["boards"].keys()):
        if bid not in board_ids:
            del cache["boards"][bid]
    cache["last_run"] = str(today)
    full_scope = args.mode == "full" and not only and not args.limit and not aborted["v"]
    if full_scope:
        cache["last_full"] = str(today)
    ml.save_json(cache_path, cache)

    # 파일 출력
    ordered = [final[b["id"]] for b in boards if b["id"] in final]
    rec_rows = []
    for r in ordered:
        if r["type"] != "board":
            continue
        latest = ml.from_iso(r.get("latest_date"))
        rec_rows.append([r["system"], r["name"], r.get("page_title", ""), r["url"], r.get("latest_title") or "",
                         r.get("latest_date") or "", str(today), str(ml.add_months(today, -months)),
                         ml.elapsed_text(latest, today) if latest else "", r["status"],
                         (r["note"] + " " if r["note"] else "") + ("" if r["fetched"] else "캐시(미방문)")])
    write_csv(os.path.join(run_dir, "recency-status.csv"), RECENCY_COLUMNS, rec_rows)
    sev_order = {"긴급": 0, "높음": 1, "보통": 2, "낮음": 3}
    det_rows = [[f["system"], f["category"], f["severity"], f["area"], f["page_title"], f["url"], f.get("latest_date") or "",
                 str(today), f["elapsed"], f["detail"], f["evidence"], f["action"], "", f["state"], f["first_seen"]]
                for f in sorted(all_findings, key=lambda x: (sev_order.get(x["severity"], 9), x["board_id"]))]
    write_csv(os.path.join(run_dir, "inspection-details.csv"), DETAIL_COLUMNS, det_rows)

    typo_items = [it for r in ordered for it in r.get("typo_items", [])]
    typo_skipped = [dict(sk, board_id=r["id"]) for r in ordered for sk in r.get("typo_skipped", [])]
    unvisited = [b["id"] for b in boards if b["id"] not in final]
    status_counts = Counter(r["status"] for r in ordered)
    last_full = ml.from_iso(cache.get("last_full"))
    warnings = []
    if aborted["v"]:
        warnings.append("중단됨: %s. 부분 결과이며 --resume으로 재개 가능. 보안·운영 부서에 허용 목록 등록·서버 상태 확인을 요청하세요." % (fetcher.abort_reason or "차단·장애 의심"))
    if args.mode == "incremental" and (last_full is None or (today - last_full).days >= int(settings["full_every_days"])):
        warnings.append("마지막 전체 점검: %s. 전체 점검(--mode full) 권장" % (last_full or "이력 없음"))
    err_boards = sum(1 for r in ordered if r["status"] in ERROR_STATUSES)
    if ordered and err_boards / float(len(ordered)) >= 0.5:
        warnings.append("접속 오류 게시판이 50%% 이상(%d/%d): 서비스 장애 또는 차단 가능성. 긴급 여부 확인 필요" % (err_boards, len(ordered)))
    summary = {"date": str(today), "mode": args.mode, "partial": aborted["v"], "boards_total": len(boards),
               "visited": sum(1 for r in ordered if r["fetched"]), "from_cache": sum(1 for r in ordered if not r["fetched"]),
               "excluded": len(excluded), "unvisited_no_cache": unvisited, "status_counts": dict(status_counts),
               "findings": len(all_findings), "findings_new": sum(1 for f in all_findings if f["state"] == "신규"),
               "findings_continuing": sum(1 for f in all_findings if f["state"] == "지속"), "findings_resolved": len(resolved),
               "ai_review_items": len(queue), "typo_check": ctx.typo_enabled, "typo_items": len(typo_items),
               "typo_skipped": len(typo_skipped), "requests": fetcher.request_count, "warnings": warnings,
               "request_policy": plan["request_policy"]}
    ml.save_json(os.path.join(run_dir, "run-summary.json"), summary)
    ml.save_json(os.path.join(run_dir, "findings.json"), {"meta": summary, "findings": all_findings, "resolved": resolved,
                                                           "boards": [{k: v for k, v in r.items() if k not in ("excerpt", "titles", "findings", "seen_posts")} for r in ordered]})
    ml.save_json(os.path.join(run_dir, "ai-review-queue.json"), {"date": str(today), "items": queue})
    if ctx.typo_enabled:
        ml.save_json(os.path.join(run_dir, "typo-review-queue.json"), {"date": str(today), "items": typo_items, "skipped": typo_skipped})

    # 월간 집계용 이력 스냅샷 (캐시 전체 상태 기준)
    snap = {"date": str(today), "mode": args.mode, "summary": {k: summary[k] for k in ("visited", "from_cache", "status_counts", "requests", "partial")},
            "boards": {}, "findings": [{"key": f["key"], "category": f["category"], "severity": f["severity"], "board_id": f["board_id"], "state": f["state"]} for f in all_findings]}
    for bid, c in cache["boards"].items():
        snap["boards"][bid] = {"name": c["name"], "system": c["system"], "owner": c.get("owner", ""), "type": c.get("type"),
                               "status": c["status"], "latest_date": c.get("latest_date"), "window_oldest": c.get("window_oldest"),
                               "post_counting": c.get("post_counting", False), "month_counts": month_counts(c.get("seen_posts"))}
    ml.save_json(os.path.join(ws, "history", "%s.json" % today), snap)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n결과 위치: %s" % run_dir)
    return 2 if aborted["v"] else 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
