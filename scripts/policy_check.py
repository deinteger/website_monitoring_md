#!/usr/bin/env python3
"""정책정보 확인주간·UI/UX 가이드라인 점검 엔진 (표준 라이브러리만 사용).

guidelines/<팩>/<버전>/rules.json 의 규칙을 읽어 홈페이지를 점검하고 체크리스트(CSV·MD·JSON)를 만든다.
규칙 데이터와 엔진을 분리해 개정판은 guidelines/ 만 갱신하면 된다 (core/guideline-update.md).

규칙의 판정 방식(method)
  auto    스크립트가 판정한다(충족/미충족). 근사 측정이면 규칙 hint에 한계를 적는다.
  assist  스크립트는 증거만 수집하고 '확인 필요(증거 첨부)'로 둔다. 충족이라고 단정하지 않는다.
  attest  사람이 네/아니오로 응답한다(계획 수립 여부 등 홈페이지로 확인할 수 없는 문항).
status=draft 규칙(검수 전)의 결과는 '참고'로만 표시된다.

  python scripts/policy_check.py --workspace workspace --pack policy-week          # 점검
  python scripts/policy_check.py --workspace workspace --pack all --dry-run        # 요청량 확인
  python scripts/policy_check.py answer PW-03 --yes --note "관리계획 수립(2026.3.)"  # 사람 응답 기록
  python scripts/policy_check.py status                                            # 응답 현황
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_TYPES = {"viewport_meta", "doctype_html5", "charset_meta", "lang_attr", "title_tag", "img_alt", "skip_nav", "deprecated_tags",
               "ie_legacy", "text_contains", "link_text_contains", "region_exists", "page_weight", "load_time",
               "external_links_dead", "map_embed", "page_dates", "phone_format", "portal_search",
               "text_matches", "link_text_matches", "order", "region_img_alt", "skip_link_present", "skip_link_first",
               "skip_link_count", "skip_main_first", "skip_target_exists", "link_check"}
METHODS = ("auto", "assist", "attest")
STATUSES = ("active", "draft")
MAP_RE = re.compile(r"dapi\.kakao\.com/v2/maps|map\.kakao\.com|openapi\.map\.naver\.com|naveropenapi|maps\.googleapis\.com|"
                    r"maps\.google\.com/maps|google\.com/maps/embed|map\.vworld\.kr|api\.vworld\.kr|map\.ngii\.go\.kr", re.I)
DEPRECATED_RE = re.compile(r"<(font|center|marquee|blink|frameset|frame|acronym|big|tt|strike|basefont|applet)\b", re.I)
IE_RE = re.compile(r"activex|classid\s*=|x-ua-compatible[^>]*content\s*=\s*[\"']?[^>\"']*ie=(?!edge)", re.I)
LABEL_RE = re.compile(r"(최종\s*수정일|수정일|갱신일|최종\s*업데이트|업데이트|기준일)\s*[:：]?\s*(.{0,30})")
_REGION_HINT = {"header": re.compile(r"header|gnb|masthead|top-?bar", re.I), "footer": re.compile(r"footer|foot", re.I)}


# ------------------------------------------------------------------ 규칙팩

def guidelines_dir(arg=""):
    return arg or os.path.join(ROOT, "guidelines")


def load_index(gdir):
    return ml.load_json(os.path.join(gdir, "index.json"), {"packs": {}})


def load_pack(gdir, pack, version=None):
    idx = load_index(gdir)
    ver = version or (idx["packs"].get(pack) or {}).get("current")
    if not ver:
        raise SystemExit("[오류] 규칙팩 '%s'의 현재 버전이 index.json에 없습니다." % pack)
    base = os.path.join(gdir, pack, ver)
    rules = ml.load_json(os.path.join(base, "rules.json"))
    if rules is None:
        raise SystemExit("[오류] %s 가 없습니다." % os.path.join(base, "rules.json"))
    meta = ml.load_json(os.path.join(base, "meta.json"), {})
    return meta, rules["rules"], ver, base


# ------------------------------------------------------------------ 페이지 수집

def gather_pages(profile, fetcher, max_pages):
    pol = profile.get("policy") or {}
    home = pol.get("home_url") or profile.get("base_url") or profile["boards"][0]["url"]
    names = [("home", home)] + list((pol.get("pages") or {}).items()) + [("sample_%d" % i, u) for i, u in enumerate(pol.get("sample_pages") or [], 1)]
    for b in profile["boards"]:
        if b.get("type") == "static" and not b.get("exclude"):
            names.append((b["id"], b["url"]))
    seen, plan = set(), []
    for name, url in names:
        if url in seen:
            continue
        seen.add(url)
        plan.append((name, url))
    return plan[: max(1, max_pages)]


def _load_page(name, url, r):
    p = {"name": name, "url": url, "status": r.status, "error": r.error, "elapsed": r.elapsed, "ok": False, "html": "", "text": "", "links": [],
         "title": "", "bytes": len(r.body or b""), "final_url": r.final_url, "headers": r.headers or {}, "thin": False, "client_redirect": None}
    if r.ok and 200 <= r.status < 300:
        p["html"] = ml.decode_body(r.body, (r.headers or {}).get("Content-Type", ""))
        p["text"], p["links"], p["title"] = ml.html_parse(p["html"])
        p["ok"] = True
    return p


def fetch_pages(plan, fetcher):
    """페이지를 수집한다. 자바스크립트·메타 새로고침으로 이동하는 빈 껍데기 페이지는 같은 도메인 안에서 최대 2번 따라간다.
    그래도 본문이 비어 있으면 thin=True 로 표시해 점검에서 제외(미충족이 아니라 수집 한계)한다."""
    pages = {}
    for name, url in plan:
        p = _load_page(name, url, fetcher.get(url))
        chain, seen = [], {p["final_url"]}
        while p["ok"] and len(p["text"]) < 200 and not p["links"] and len(chain) < 2:
            nxt = ml.find_client_redirect(p["html"], p["final_url"])
            if not nxt or nxt in seen or not fetcher.host_allowed(nxt):
                break
            seen.add(nxt)
            chain.append(nxt)
            p = _load_page(name, url, fetcher.get(nxt))
        p["client_redirect"] = chain or None
        p["thin"] = bool(p["ok"] and len(p["text"]) < 200 and not p["links"])
        pages[name] = p
    return pages


def region_html(html, scope):
    f = ml.find_elements(html, scope, limit=1)
    if f:
        return f[0]
    for t in ("div", "section", "nav", "ul"):
        for inner, attrs in ml.find_elements_attrs(html, t):
            if _REGION_HINT[scope].search((attrs.get("class") or "") + " " + (attrs.get("id") or "")):
                return inner
    return ""


# ------------------------------------------------------------------ 검사 구현

def _agg(per_page, evidence_only=False, label_ok="", label_ng=""):
    """per_page: [(name, ok, note)] → {status, evidence}"""
    if not per_page:
        return {"status": "unknown", "evidence": ["점검할 페이지를 수집하지 못함"]}
    bad = [(n, note) for n, ok, note in per_page if not ok]
    ev = ["%s: %s" % (n, note) for n, ok, note in per_page if note][:12]
    if evidence_only:
        return {"status": "info", "evidence": ev or [label_ok]}
    return {"status": "fail" if bad else "pass", "evidence": ev or ([label_ng] if bad else [label_ok])}


def _ok_pages(ctx, names=None):
    return [p for n, p in ctx["pages"].items() if p["ok"] and not p.get("thin") and (names is None or n in names)]


def _thin_msg(ctx):
    thin = [n for n, p in ctx["pages"].items() if p.get("thin")]
    return ("수집한 페이지(%s)의 본문이 비어 있습니다(스크립트로 그려지는 페이지로 추정): 브라우저 렌더링(Playwright 선택 모듈) 또는 사람 확인이 필요합니다" % ", ".join(thin)) if thin else ""



SKIP_RE = re.compile(r"바로\s*가기|건너뛰기|skip", re.I)


def _is_skip(a):
    return (a.get("href") or "").strip().startswith("#") and bool(SKIP_RE.search(a.get("text") or ""))


def _target_pages(ctx, chk):
    ok = _ok_pages(ctx)
    if chk.get("all_pages"):
        return ok
    home = ctx["pages"].get("home")
    return [home] if home and home["ok"] and not home.get("thin") else []


def _home_or_none(ctx):
    h = ctx["pages"].get("home")
    return h if h and h["ok"] and not h.get("thin") else None


def _region_text(p, scope):
    if scope == "html":
        return p["html"]
    if scope in ("header", "footer"):
        return ml.html_parse(region_html(p["html"], scope))[0]
    return p["text"]


def _agg3(pp, chk, empty_note):
    """pp: [(page, ok(True/False/None), note)] → 상태. None 은 판정 불가(info)."""
    if not pp:
        return {"status": "unknown", "evidence": [empty_note]}
    ev = ["%s: %s" % (n, note) for n, ok, note in pp if note][:12] or ["확인됨"]
    if any(ok is False for _, ok, _ in pp):
        return {"status": "fail", "evidence": ev}
    if any(ok is None for _, ok, _ in pp):
        return {"status": "info", "evidence": ev}
    if chk.get("evidence_only"):
        return {"status": "info", "evidence": ev}
    return {"status": "pass", "evidence": ev}


V2_TYPES = {"text_matches", "link_text_matches", "order", "region_img_alt", "skip_link_present", "skip_link_first", "skip_link_count",
            "skip_main_first", "skip_target_exists", "link_check", "region_exists"}


def run_check_v2(chk, ctx):
    """UI/UX 규칙팩용 확장 검사. 처리하지 않는 유형이면 None."""
    t = chk["type"]
    if t in V2_TYPES and not _ok_pages(ctx) and _thin_msg(ctx):
        return {"status": "unknown", "evidence": [_thin_msg(ctx)]}
    if t == "text_contains" and (chk.get("scope") == "each_page_top" or chk.get("variants")):
        keys = chk["any"]
        pages = _ok_pages(ctx) if chk.get("scope") == "each_page_top" else _target_pages(ctx, {})
        if not pages:
            return {"status": "unknown", "evidence": [_thin_msg(ctx) or "페이지를 수집하지 못함"]}
        pp = []
        for p in pages:
            src = p["text"][:1500] if chk.get("scope") == "each_page_top" else p["text"]
            if any(k in src for k in keys):
                pp.append((p["name"], True, ""))
            else:
                var = [v for v in chk.get("variants", []) if v in p["text"]]
                pp.append((p["name"], False, ("변형 문구 발견: '%s' (원문 문구와 다름)" % var[0]) if var else "배너 문구를 찾지 못함"))
        return _agg3(pp, chk, "페이지를 수집하지 못함")
    if t in ("skip_link_present", "skip_link_first", "skip_link_count", "skip_main_first", "skip_target_exists"):
        pp = []
        for p in _ok_pages(ctx):
            links = [a for a in p["links"] if a.get("href") is not None]
            skips = [a for a in links[:20] if _is_skip(a)]
            if t == "skip_link_present":
                pp.append((p["name"], bool(skips), "" if skips else "건너뛰기 링크를 찾지 못함"))
            elif t == "skip_link_first":
                ok = bool(links) and _is_skip(links[0])
                pp.append((p["name"], ok, "" if ok else "문서의 첫 링크가 건너뛰기 링크가 아님(첫 링크: %s)" % ((links[0]["text"] or links[0]["href"])[:30] if links else "없음")))
            elif t == "skip_link_count":
                n = len([a for a in links[:15] if _is_skip(a)])
                pp.append((p["name"], None if n == 0 else n <= int(chk.get("max", 3)), "건너뛰기 링크 %d개%s" % (n, " (없음: UX-S1에서 판정)" if n == 0 else "")))
            elif t == "skip_main_first":
                if not skips:
                    pp.append((p["name"], None, "건너뛰기 링크 없음"))
                else:
                    a = skips[0]
                    tid = a["href"].strip()[1:].lower()
                    ok = bool(re.search(r"본문|콘텐츠|content|main", a["text"] or "", re.I) or re.search(r"main|content|container|contents", tid))
                    pp.append((p["name"], ok, "첫 건너뛰기 링크: '%s' → #%s" % ((a["text"] or "")[:20], tid)))
            else:
                if not skips:
                    pp.append((p["name"], None, "건너뛰기 링크 없음"))
                    continue
                miss = []
                for a in skips:
                    tid = a["href"].strip()[1:]
                    if not tid or not re.search(r"\b(?:id|name)\s*=\s*[\"']%s[\"']" % re.escape(tid), p["html"]):
                        miss.append("#%s" % tid)
                pp.append((p["name"], not miss, ("목적지 없음: %s" % ", ".join(miss)) if miss else ""))
        return _agg3(pp, chk, "페이지를 수집하지 못함")
    if t in ("text_matches", "link_text_matches", "order", "region_img_alt", "link_check", "region_exists") and (t != "region_exists" or chk.get("tag_only") or chk.get("all_pages")):
        pages = _target_pages(ctx, chk)
        if not pages:
            return {"status": "unknown", "evidence": [_thin_msg(ctx) or "홈페이지를 수집하지 못함"]}
        scope = chk.get("scope", "html")
        pp = []
        for p in pages:
            if t == "region_exists":
                ok = bool(ml.find_elements(p["html"], scope, limit=1)) if chk.get("tag_only") else bool(region_html(p["html"], scope).strip())
                pp.append((p["name"], ok, "" if ok else "<%s> 요소를 찾지 못함" % scope))
            elif t == "text_matches":
                pats = [x.replace("{agency_name}", re.escape((ctx["profile"].get("policy") or {}).get("agency_name", ""))) for x in chk["patterns"]]
                src = _region_text(p, scope)
                m = next((re.search(x, src, re.I) for x in pats if re.search(x, src, re.I)), None)
                if chk.get("evidence_only"):
                    pp.append((p["name"], None, ("표기 확인: '%s'" % m.group(0)[:40]) if m else "표기를 찾지 못함"))
                else:
                    pp.append((p["name"], bool(m), ("확인: '%s'" % m.group(0)[:50]) if m else "%s 영역에서 해당 문구를 찾지 못함" % scope))
            elif t == "link_text_matches":
                rg = region_html(p["html"], scope) if scope in ("header", "footer") else p["html"]
                links = ml.html_parse(rg)[1]
                hit = next((a for a in links if any(re.search(x, a.get("text") or "", re.I) for x in chk["patterns"])), None)
                pp.append((p["name"], bool(hit), ("링크 확인: '%s'" % hit["text"][:30]) if hit else "%s 영역에서 해당 링크 문구를 찾지 못함" % scope))
            elif t == "order":
                src = _region_text(p, scope)
                pos = []
                for it in chk["items"]:
                    m = re.search(it["regex"], src, re.I | re.S)
                    pos.append((it["name"], m.start() if m else None))
                found = [(n, i) for n, i in pos if i is not None]
                missing = [n for n, i in pos if i is None]
                if chk.get("require_all") and missing:
                    pp.append((p["name"], False, "누락: %s" % ", ".join(missing)))
                elif len(found) < 2:
                    pp.append((p["name"], None, "비교할 항목이 2개 미만(찾음: %s)" % ", ".join(n for n, _ in found) or "없음"))
                else:
                    ok = [i for _, i in found] == sorted(i for _, i in found)
                    pp.append((p["name"], ok, "순서 %s: %s%s" % ("일치" if ok else "불일치", " → ".join("%s(%d)" % (n, i) for n, i in found), (" / 누락: " + ", ".join(missing)) if missing else "")))
            elif t == "region_img_alt":
                rg = region_html(p["html"], scope)
                if not rg.strip():
                    pp.append((p["name"], None, "%s 영역을 찾지 못함" % scope))
                    continue
                bad, skipped = [], 0
                imgs = []
                for im in re.findall(r"<img\b[^>]*>", rg, re.I):
                    sm = re.search(r"src\s*=\s*[\"']([^\"']+)", im, re.I)
                    absu = urllib.parse.urljoin(p["final_url"], sm.group(1)) if sm else ""
                    tiny = re.search(r"\b(?:width|height)\s*=\s*[\"']?[01][\"'\s>px]", im, re.I)
                    hidden = re.search(r"display\s*:\s*none|aria-hidden\s*=\s*[\"']true|visibility\s*:\s*hidden", im, re.I)
                    third = absu.startswith("http") and not ctx["fetcher"].host_allowed(absu)
                    if tiny or hidden or third:       # 추적 픽셀·숨김·외부 도메인 이미지는 로고 점검 대상이 아니다
                        skipped += 1
                        continue
                    imgs.append(im)
                for im in imgs:
                    am = re.search(r"\balt\s*=\s*[\"']([^\"']*)[\"']", im, re.I)
                    if chk.get("require_alt") and (not am or not am.group(1).strip()):
                        bad.append("alt 없음/빈 값: %s" % (re.search(r"src\s*=\s*[\"']([^\"']{0,40})", im, re.I) or [None, "?"])[1])
                    for w in chk.get("forbid_words", []):
                        if am and w in am.group(1):
                            bad.append("alt에 '%s' 포함: '%s'" % (w, am.group(1)[:30]))
                pp.append((p["name"], not bad, "; ".join(bad[:3]) if bad else "이미지 %d개 확인%s" % (len(imgs), (" (추적 픽셀·숨김·외부 이미지 %d개 제외)" % skipped) if skipped else "")))
            else:  # link_check
                rg = region_html(p["html"], scope)
                if not rg.strip():
                    pp.append((p["name"], None, "%s 영역을 찾지 못함" % scope))
                    continue
                seen, bad, ext, checked = set(), [], 0, 0
                for a in ml.html_parse(rg)[1]:
                    href = (a.get("href") or "").strip()
                    if not href or href.startswith(("#", "javascript", "mailto:", "tel:")):
                        continue
                    u = urllib.parse.urldefrag(urllib.parse.urljoin(p["final_url"], href))[0]
                    if not u.startswith("http") or u in seen:
                        continue
                    seen.add(u)
                    if not ctx["fetcher"].host_allowed(u):
                        ext += 1
                        continue
                    if checked >= int(chk.get("max_links", 30)):
                        break
                    checked += 1
                    r = ctx["fetcher"].check_url(u)
                    if r.error or r.status in (404, 410) or (r.status or 0) >= 500:
                        bad.append("%s (%s)" % (u, r.status or r.error))
                pp.append((p["name"], not bad, ("깨진 링크 %d개: %s" % (len(bad), "; ".join(bad[:3]))) if bad else "같은 도메인 링크 %d개 점검, 외부 %d개는 미점검" % (checked, ext)))
        res = _agg3(pp, chk, "페이지를 수집하지 못함")
        if chk.get("evidence_only") and res["status"] == "fail":
            res["status"] = "info"
        return res
    return None


def run_check(chk, ctx):
    """검사를 실행하되, 본문이 비어 점검에서 제외된 페이지가 있으면 '통과'를 '일부 미측정'으로 낮춘다(거짓 충족 방지)."""
    res = _run_check_inner(chk, ctx)
    thin = [n for n, p in ctx["pages"].items() if p.get("thin")]
    if thin and res["status"] == "pass":
        res = dict(res, status="info", evidence=list(res["evidence"]) + ["수집 한계로 점검에서 제외된 페이지: %s (본문이 비어 있음)" % ", ".join(thin)])
    return res


def _run_check_inner(chk, ctx):
    t = chk["type"]
    r2 = run_check_v2(chk, ctx)
    if r2 is not None:
        return r2
    pages = _ok_pages(ctx, chk.get("pages")) if chk.get("pages") else _ok_pages(ctx)
    if not pages and _thin_msg(ctx):
        return {"status": "unknown", "evidence": [_thin_msg(ctx)]}
    if chk.get("pages") and not pages:
        miss = [n for n in chk["pages"] if n not in ctx["pages"]]
        return {"status": "unknown", "evidence": ["프로필 policy.pages에 %s 주소가 지정되지 않았거나 접속하지 못함" % ", ".join(miss or chk["pages"])]}
    if not pages and t not in ("portal_search", "external_links_dead"):
        return {"status": "unknown", "evidence": ["페이지를 수집하지 못함"]}
    pp = []
    if t == "viewport_meta":
        pp = [(p["name"], bool(re.search(r"<meta[^>]+name\s*=\s*[\"']viewport[\"']", p["html"], re.I)), "") for p in pages]
        pp = [(n, ok, "" if ok else "viewport 설정 없음") for n, ok, _ in pp]
    elif t == "doctype_html5":
        pp = [(p["name"], bool(re.match(r"\s*(?:<!--.*?-->\s*)*<!doctype\s+html\s*>", p["html"][:600], re.I | re.S)), "") for p in pages]
        pp = [(n, ok, "" if ok else "HTML5 doctype(<!DOCTYPE html>) 아님") for n, ok, _ in pp]
    elif t == "charset_meta":
        pp = [(p["name"], bool(re.search(r"<meta[^>]+charset\s*=", p["html"], re.I) or "charset=" in str(p["headers"].get("Content-Type", "")).lower()), "") for p in pages]
        pp = [(n, ok, "" if ok else "문자셋 선언 없음") for n, ok, _ in pp]
    elif t == "lang_attr":
        pp = [(p["name"], bool(re.search(r"<html[^>]+\blang\s*=", p["html"], re.I)), "") for p in pages]
        pp = [(n, ok, "" if ok else "html lang 속성 없음") for n, ok, _ in pp]
    elif t == "title_tag":
        pp = [(p["name"], bool(p["title"].strip()), "" if p["title"].strip() else "페이지 제목(title) 없음") for p in pages]
    elif t == "img_alt":
        for p in pages:
            imgs = re.findall(r"<img\b[^>]*>", p["html"], re.I)
            miss = [i for i in imgs if not re.search(r"\balt\s*=", i, re.I)]
            pp.append((p["name"], not miss, "이미지 %d개 중 대체텍스트(alt) 속성 없음 %d개" % (len(imgs), len(miss)) if miss else ""))
    elif t == "skip_nav":
        for p in pages:
            texts = [a["text"] for a in p["links"][:20]]
            ok = any(k in tx for tx in texts for k in ("본문 바로가기", "본문바로가기", "건너뛰기", "바로가기", "Skip"))
            pp.append((p["name"], ok, "" if ok else "상단에 본문 바로가기(건너뛰기) 링크를 찾지 못함"))
    elif t == "deprecated_tags":
        for p in pages:
            found = DEPRECATED_RE.findall(p["html"])
            pp.append((p["name"], not found, "폐기된 태그 %d개(%s)" % (len(found), ", ".join(sorted(set(x.lower() for x in found)))) if found else ""))
    elif t == "ie_legacy":
        for p in pages:
            m = IE_RE.search(p["html"])
            pp.append((p["name"], not m, "IE 전용 흔적: %s" % m.group(0)[:40] if m else ""))
    elif t == "text_contains":
        keys = []
        for k in chk["any"]:
            if "{agency_name}" in k:
                an = (ctx["profile"].get("policy") or {}).get("agency_name")
                if not an:
                    return {"status": "unknown", "evidence": ["site-profile의 policy.agency_name이 필요함"]}
                k = k.replace("{agency_name}", an)
            keys.append(k)
        scope = chk.get("scope", "any_page")
        home = ctx["pages"].get("home")
        hit = None
        if scope == "any_page":
            for p in pages:
                for k in keys:
                    if k in p["text"]:
                        hit = "%s: '%s' 표기 확인" % (p["name"], k)
                        break
                if hit:
                    break
        else:
            home = _home_or_none(ctx)
            if not home:
                return {"status": "unknown", "evidence": [_thin_msg(ctx) or "홈페이지를 수집하지 못함"]}
            if scope == "home":
                src = home["text"]
            elif scope == "home_top":
                src = home["text"][:1500]
            else:
                src = ml.html_parse(region_html(home["html"], scope))[0] if scope in ("header", "footer") else ""
            for k in keys:
                if k in src:
                    hit = "%s 영역: '%s' 표기 확인" % (scope, k)
                    break
        if chk.get("evidence_only"):
            return {"status": "info", "evidence": [hit or "표기를 찾지 못함: %s" % " / ".join(keys)]}
        return {"status": "pass" if hit else "fail", "evidence": [hit or "'%s' 표기를 %s에서 찾지 못함" % (" / ".join(keys), scope)]}
    elif t == "link_text_contains":
        found = []
        for p in pages:
            for a in p["links"]:
                if any(k in a["text"] for k in chk["any"]):
                    found.append("%s: '%s' → %s" % (p["name"], a["text"][:30], urllib.parse.urljoin(p["final_url"], a.get("href") or "")))
        found = found[:5]
        if chk.get("evidence_only"):
            return {"status": "info", "evidence": found or ["해당 링크 텍스트를 찾지 못함: %s" % " / ".join(chk["any"])]}
        return {"status": "pass" if found else "fail", "evidence": found or ["해당 링크를 찾지 못함"]}
    elif t == "region_exists":
        home = _home_or_none(ctx)
        if not home:
            return {"status": "unknown", "evidence": [_thin_msg(ctx) or "홈페이지를 수집하지 못함"]}
        ok = bool(region_html(home["html"], chk["scope"]).strip())
        return {"status": "pass" if ok else "fail", "evidence": ["%s 영역 %s (요소 또는 class/id 흔적 기준 근사)" % (chk["scope"], "확인" if ok else "찾지 못함")]}
    elif t == "page_weight":
        limit = float(chk.get("max_mb", 3)) * 1024 * 1024
        for p in pages:
            base = urllib.parse.urlsplit(p["final_url"])
            urls = []
            for src in re.findall(r"<img[^>]+src=[\"']([^\"']+)", p["html"], re.I) + re.findall(r"<script[^>]+src=[\"']([^\"']+)", p["html"], re.I):
                urls.append(src)
            for tag in re.findall(r"<link\b[^>]*>", p["html"], re.I):
                if re.search(r"rel\s*=\s*[\"']stylesheet", tag, re.I):
                    m = re.search(r"href\s*=\s*[\"']([^\"']+)", tag, re.I)
                    if m:
                        urls.append(m.group(1))
            uniq, seen = [], set()
            for u in urls:
                a = urllib.parse.urldefrag(urllib.parse.urljoin(p["final_url"], u))[0]
                if a.startswith("http") and a not in seen and ctx["fetcher"].host_allowed(a):
                    seen.add(a)
                    uniq.append(a)
            cap = int(chk.get("asset_limit", 40))
            total, unknown = p["bytes"], 0
            for a in uniq[:cap]:
                r = ctx["fetcher"].check_url(a)
                cl = (r.headers or {}).get("Content-Length")
                if cl and str(cl).isdigit():
                    total += int(cl)
                else:
                    unknown += 1
            truncated = max(0, len(uniq) - cap)
            mb = total / 1048576.0
            note = "HTML+자원 합계 %.2fMB (자원 %d개 중 크기 미확인 %d, 미측정 %d)" % (mb, min(len(uniq), cap), unknown, truncated)
            pp.append((p["name"], total <= limit, note))
            if total <= limit and (unknown or truncated):
                pp[-1] = (p["name"], None, note + " — 일부 미측정")
        bad = [x for x in pp if x[1] is False]
        part = [x for x in pp if x[1] is None]
        ev = ["%s: %s" % (n, note) for n, ok, note in pp]
        return {"status": "fail" if bad else ("info" if part else "pass"), "evidence": ev[:12]}
    elif t == "load_time":
        mx = float(chk.get("max_sec", 3))
        pp = [(p["name"], p["elapsed"] <= mx, "HTML 응답 %.2f초 (전체 렌더링 시간이 아닌 근사치)" % p["elapsed"]) for p in pages]
        res = _agg(pp)
        res["evidence"] = ["%s: %s" % (n, note) for n, ok, note in pp][:12]
        return res
    elif t == "external_links_dead":
        pol = (ctx["settings"].get("policy") or {})
        if not pol.get("check_external_links"):
            return {"status": "skipped", "evidence": ["외부 링크 점검은 옵트인입니다 (settings.json의 policy.check_external_links=true). 외부 사이트에 HEAD 요청이 나갑니다."]}
        ext, seen = [], set()
        for p in pages:
            for a in p["links"]:
                href = (a.get("href") or "").strip()
                if not href or href.startswith(("#", "javascript", "mailto:", "tel:")):
                    continue
                u = urllib.parse.urldefrag(urllib.parse.urljoin(p["final_url"], href))[0]
                if u.startswith("http") and u not in seen and not ctx["fetcher"].host_allowed(u):
                    seen.add(u)
                    ext.append((p["name"], u))
        cap = int(pol.get("max_external_links", 100))
        broken = []
        for name, u in ext[:cap]:
            r = ctx["ext_fetcher"].check_url(u)
            if r.error or r.status in (404, 410) or (r.status or 0) >= 500:
                broken.append("%s: %s (%s)" % (name, u, r.status or r.error))
        ev = ["외부 링크 %d개 중 %d개 점검(상한 %d)" % (len(ext), min(len(ext), cap), cap)] + broken[:10]
        return {"status": "fail" if broken else ("info" if len(ext) > cap else "pass"), "evidence": ev}
    elif t == "map_embed":
        found = []
        for p in pages:
            m = MAP_RE.search(p["html"])
            if m:
                found.append("%s: 지도 사용 흔적(%s) %s" % (p["name"], m.group(0)[:30], p["final_url"]))
        return {"status": "info", "evidence": found or ["수집한 페이지에서 지도 사용 흔적을 찾지 못함 (수집 범위 밖 페이지는 확인 못 함)"]}
    elif t == "page_dates":
        ev = []
        for p in pages:
            labels = []
            for m in LABEL_RE.finditer(p["text"]):
                ds = ml.parse_dates(m.group(2))
                if ds:
                    labels.append((m.group(1), ds[0]))
            if labels:
                lab, d = max(labels, key=lambda x: x[1])
                ev.append("%s: %s %s (%s)" % (p["name"], lab, d, ml.elapsed_text(d, ctx["today"])))
            else:
                ev.append("%s: 갱신일 표기를 찾지 못함 (%s)" % (p["name"], p["final_url"]))
        return {"status": "info", "evidence": ev}
    elif t == "phone_format":
        ev = []
        for p in pages:
            full = re.findall(r"(?<!\d)0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}(?!\d)", p["text"])
            scrub = re.sub(r"0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}", " ", p["text"])
            local = re.findall(r"(?<![\d-])\d{3,4}-\d{4}(?!\d)", scrub)
            fax = bool(re.search(r"팩스|FAX|Fax", p["text"]))
            ev.append("%s: 지역번호 포함 전화 %d건, 지역번호 없는 번호 의심 %d건, 팩스 표기 %s" % (p["name"], len(full), len(local), "있음" if fax else "없음"))
        return {"status": "info", "evidence": ev}
    elif t == "portal_search":
        runs = os.path.join(ctx["ws"], "runs")
        files = sorted(os.path.join(runs, d, "search-index-links.csv") for d in (os.listdir(runs) if os.path.isdir(runs) else [])
                       if os.path.exists(os.path.join(runs, d, "search-index-links.csv")))
        if not files:
            return {"status": "unknown", "evidence": ["검색 포털 점검 미실시 (--checks portal)"]}
        with open(files[-1], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        from collections import Counter
        c = Counter(r["판정"] for r in rows)
        return {"status": "info", "evidence": ["최근 포털 점검(%s): URL %d건, %s" % (os.path.basename(os.path.dirname(files[-1])), len(rows), ", ".join("%s %d" % kv for kv in c.most_common()))]}
    return _agg(pp)


# ------------------------------------------------------------------ 규칙 평가

def evaluate_rule(rule, ctx, answers, version, pack_results):
    res = {"id": rule["id"], "category": rule["category"], "text": rule["text"], "method": rule["method"], "status": rule.get("status", "active"),
           "source_ref": rule.get("source_ref", ""), "hint": rule.get("hint", ""), "checks": [], "auto": "", "suggest": "", "answer": "", "note": ""}
    statuses = []
    for chk in rule.get("checks") or []:
        r = run_check(chk, ctx)
        r["type"] = chk["type"]
        res["checks"].append(r)
        if not chk.get("evidence_only") or r["status"] in ("unknown", "skipped"):
            statuses.append(r["status"])
    if rule.get("pack_ref"):
        pr = pack_results.get(rule["pack_ref"])
        if pr is None:
            res["checks"].append({"type": "pack_ref", "status": "unknown", "evidence": ["규칙팩 '%s'을 이번에 점검하지 않았습니다 (--checks %s)" % (rule["pack_ref"], rule["pack_ref"])]})
        else:
            from collections import Counter
            c = Counter(x["auto"] for x in pr)
            res["checks"].append({"type": "pack_ref", "status": "info", "evidence": ["규칙팩 %s 결과: %s" % (rule["pack_ref"], ", ".join("%s %d" % kv for kv in c.most_common()))]})
    m = rule["method"]
    if m == "attest":
        res["auto"] = "사람 응답 필요"
    elif m == "assist":
        res["auto"] = "확인 필요(미충족 징후)" if "fail" in statuses else "확인 필요(증거 첨부)"
    else:
        if "fail" in statuses:
            res["auto"] = "미충족(자동)"
            res["suggest"] = "아니오(제안)"
        elif not statuses or any(s in ("unknown", "skipped", "info", "error") for s in statuses):
            res["auto"] = "확인 필요(일부 미측정)"
        else:
            res["auto"] = "충족(자동)"
            res["suggest"] = "네(제안)"
    if res["status"] == "draft":
        res["auto"] = "참고(검수 전 규칙): " + res["auto"]
        res["suggest"] = ""
        res["note"] = "검수 전(draft) 규칙: 결과를 점검 결과로 인용하지 말 것. "
    a = answers.get(rule["id"])
    if a:
        stale = a.get("pack_version") != version
        res["answer"] = "%s (%s%s)" % (a["answer"], a.get("date", ""), ", 이전 버전 응답: 재확인 필요" if stale else "")
        if a.get("note"):
            res["note"] += "응답 메모: %s" % a["note"]
    return res


COLUMNS = ["구분", "점검 항목", "규칙ID", "판정 방식", "자동 판정", "제안 응답", "사람 응답", "근거(증거)", "비고"]


def write_outputs(outdir, pack, version, meta, results, pages_meta, warnings, today):
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, "policy-%s" % pack)
    ml.save_json(base + ".json", {"pack": pack, "version": version, "date": str(today), "meta": meta, "warnings": warnings, "pages": pages_meta, "results": results})
    with open(base + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(COLUMNS)
        for r in results:
            ev = " / ".join(e for c in r["checks"] for e in c["evidence"])[:600]
            w.writerow([r["category"], r["text"], r["id"], {"auto": "자동", "assist": "증거 수집", "attest": "사람 확인"}[r["method"]], r["auto"],
                        r["suggest"], r["answer"], ev, (r["note"] + r["hint"])[:400]])
    from collections import Counter
    c = Counter(r["auto"].split(":")[-1].strip() for r in results)
    L = ["# %s 점검 결과 (규칙팩 %s %s, %s)\n" % (meta.get("title") or pack, pack, version, today)]
    L.append("- 점검 페이지 %d개 (수집 성공 %d개)" % (len(pages_meta), sum(1 for p in pages_meta if p["ok"])))
    L.append("- 판정: " + ", ".join("%s %d" % kv for kv in c.most_common()))
    if not meta.get("reviewed"):
        L.append("- **주의**: 이 규칙팩은 검수 완료로 표시되지 않았습니다(meta.reviewed=false). 자동 판정은 참고용입니다.")
    for w_ in warnings:
        L.append("- **주의**: " + w_)
    L.append("\n※ 제출용 체크리스트의 네/아니오는 담당자가 확인해 작성합니다. 이 결과는 근거 수집과 참고 판정이며 응답을 대신하지 않습니다.\n")
    cat = None
    for r in results:
        if r["category"] != cat:
            cat = r["category"]
            L.append("\n## %s\n" % cat)
        L.append("### %s %s\n- 판정 방식: %s / 자동 판정: **%s**%s%s" % (r["id"], r["text"], {"auto": "자동", "assist": "증거 수집", "attest": "사람 확인"}[r["method"]], r["auto"],
                 (" / 제안: " + r["suggest"]) if r["suggest"] else "", (" / 사람 응답: " + r["answer"]) if r["answer"] else ""))
        for c_ in r["checks"]:
            for e in c_["evidence"][:6]:
                L.append("  - [%s] %s" % (c_["type"], e))
        if r["hint"]:
            L.append("  - 참고: " + r["hint"])
        L.append("")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return base


# ------------------------------------------------------------------ 응답 기록

def answers_path(ws):
    return os.path.join(ws, "policy-answers.json")


def cmd_answer(args):
    gdir = guidelines_dir(args.guidelines_dir)
    found = None
    for pack in load_index(gdir)["packs"]:
        _, rules, ver, _ = load_pack(gdir, pack)
        for r in rules:
            if r["id"] == args.rule_id:
                found = (pack, ver, r)
    if not found:
        print("[오류] 규칙 ID '%s' 를 현재 규칙팩에서 찾지 못했습니다." % args.rule_id, file=sys.stderr)
        return 1
    if args.yes == args.no:
        print("[오류] --yes 또는 --no 중 하나를 지정하세요.", file=sys.stderr)
        return 1
    ans = ml.load_json(answers_path(args.workspace), {}) or {}
    ans[args.rule_id] = {"answer": "네" if args.yes else "아니오", "date": args.today or str(dt.date.today()), "note": args.note, "by": args.by,
                         "pack": found[0], "pack_version": found[1]}
    ml.save_json(answers_path(args.workspace), ans)
    print("기록: %s = %s (%s %s) — %s" % (args.rule_id, ans[args.rule_id]["answer"], found[0], found[1], found[2]["text"][:50]))
    return 0


def cmd_status(args):
    gdir = guidelines_dir(args.guidelines_dir)
    ans = ml.load_json(answers_path(args.workspace), {}) or {}
    for pack in load_index(gdir)["packs"]:
        meta, rules, ver, _ = load_pack(gdir, pack)
        att = [r for r in rules if r["method"] == "attest"]
        done = [r for r in att if r["id"] in ans]
        stale = [r for r in done if ans[r["id"]].get("pack_version") != ver]
        print("%s %s: 사람 확인 문항 %d개 중 응답 %d개 (이전 버전 응답 %d개)" % (pack, ver, len(att), len(done), len(stale)))
        for r in att:
            a = ans.get(r["id"])
            print("  %s %s : %s" % (r["id"], r["text"][:40], ("%s(%s)" % (a["answer"], a["date"]) if a else "미응답")))
    return 0


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="run", choices=["run", "answer", "status"])
    ap.add_argument("rule_id", nargs="?", default="")
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--pack", default="all", help="policy-week | uiux | all")
    ap.add_argument("--guidelines-dir", default="")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", default="")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--by", default="")
    args = ap.parse_args(argv)
    if args.action == "answer":
        return cmd_answer(args)
    if args.action == "status":
        return cmd_status(args)

    ws = args.workspace
    gdir = guidelines_dir(args.guidelines_dir)
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    packs = list(load_index(gdir)["packs"]) if args.pack == "all" else [args.pack]
    settings = ml.load_settings(ws)
    try:
        profile = ml.load_profile(ws)
    except ml.ProfileError as e:
        print("[설정 오류] %s" % e, file=sys.stderr)
        return 1
    fetcher = ml.Fetcher(settings, profile["allowed_domains"])
    plan = gather_pages(profile, fetcher, args.max_pages)
    loaded = {p: load_pack(gdir, p) for p in packs}
    est_assets = sum(int(c.get("asset_limit", 40)) for _, rules, _, _ in loaded.values() for r in rules for c in (r.get("checks") or []) if c["type"] == "page_weight")
    ext_on = bool((settings.get("policy") or {}).get("check_external_links"))
    if args.dry_run:
        print(json.dumps({"packs": dict((p, loaded[p][2]) for p in packs), "pages": [{"name": n, "url": u} for n, u in plan],
                          "page_requests": len(plan), "asset_requests_upper_bound": est_assets * len(plan) if est_assets else 0,
                          "external_link_check": ext_on, "external_requests_upper_bound": int((settings.get("policy") or {}).get("max_external_links", 100)) if ext_on else 0,
                          "request_policy": {"max_concurrency": settings["max_concurrency"], "min_interval_sec": settings["min_interval_sec"], "user_agent": fetcher.ua}},
                         ensure_ascii=False, indent=2))
        return 0
    warnings, aborted = [], False
    try:
        pages = fetch_pages(plan, fetcher)
    except ml.Blocked as e:
        print("[중단] %s" % e, file=sys.stderr)
        return 2
    ext_settings = dict(settings)
    ext_fetcher = ml.Fetcher(ext_settings, [])      # 외부 링크 점검 전용(허용 도메인 제한 없음, 옵트인일 때만 사용)
    ctx = {"pages": pages, "fetcher": fetcher, "ext_fetcher": ext_fetcher, "settings": settings, "profile": profile, "ws": ws, "today": today}
    for n, p in pages.items():
        if p.get("client_redirect"):
            warnings.append("%s: 주소가 스크립트로 이동하는 껍데기 페이지라 이동 후 주소를 점검했습니다 (%s)" % (n, " → ".join(p["client_redirect"])))
        if p.get("thin"):
            warnings.append("%s: 본문이 비어 있어 점검에서 제외했습니다(수집 한계, 스크립트 렌더링 페이지 추정)" % n)
    failed = [n for n, p in pages.items() if not p["ok"]]
    if failed:
        warnings.append("수집하지 못한 페이지: %s" % ", ".join("%s(%s)" % (n, pages[n]["status"] or pages[n]["error"]) for n in failed))
    answers = ml.load_json(answers_path(ws), {}) or {}
    outdir = os.path.join(ws, "runs", str(today))
    pack_results, summary = {}, {}
    order = sorted(packs, key=lambda p: any(r.get("pack_ref") for r in loaded[p][1]))   # pack_ref 를 가진 팩은 나중에
    try:
        for pack in order:
            meta, rules, ver, _ = loaded[pack]
            results = [evaluate_rule(r, ctx, answers, ver, pack_results) for r in rules]
            pack_results[pack] = results
            base = write_outputs(outdir, pack, ver, meta, results, [{"name": p["name"], "url": p["url"], "final_url": p["final_url"], "ok": p["ok"], "status": p["status"], "thin": p.get("thin", False)} for p in pages.values()], warnings, today)
            summary[pack] = {"version": ver, "rules": len(results), "files": base}
    except ml.Blocked as e:
        aborted = True
        print("[중단] %s — 부분 결과" % e, file=sys.stderr)
    print(json.dumps({"date": str(today), "packs": summary, "pages": len(pages), "requests": fetcher.request_count + ext_fetcher.request_count,
                      "warnings": warnings, "output_dir": outdir}, ensure_ascii=False, indent=2))
    return 2 if aborted else 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
