#!/usr/bin/env python3
"""검색엔진 인덱스 URL 점검 (표준 라이브러리만 사용).

구글·네이버·다음 등에서 `site:도메인`으로 모은 검색결과 URL을 받아 실제 접속 상태를 점검한다.
  - 404/500/접속 실패, 허용 도메인 밖·메인으로의 리다이렉트
  - 소프트 404(상태코드는 200인데 '페이지를 찾을 수 없음' 안내만 나오는 페이지), 빈 페이지 의심
  - 검색결과 제목과 실제 페이지 제목 불일치
  - 깨진 이미지(--check-images, 같은 도메인 이미지의 404)

URL 수집은 검색엔진 약관·봇 차단 때문에 스크립트가 직접 하지 않는다. 수집 방법은 docs/운영가이드.md 11절
(에이전트 브라우저, 공식 검색 API, 사람이 복사). CSS 깨짐 같은 '화면 렌더링' 오류는 브라우저가 필요하다.

입력 형식: 한 줄에 `URL` 또는 `URL<탭>검색결과제목`. 또는 이 스크립트가 만든 CSV(검색엔진·검색결과제목·검색결과URL 열).

  python scripts/check_index_links.py --workspace workspace \\
      --input google=urls_google.txt --input naver=urls_naver.txt --input daum=urls_daum.txt --check-images
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

COLUMNS = ["번호", "시스템구분", "검색엔진", "검색결과제목", "검색결과URL", "실제접속상태", "실제페이지제목", "제목일치여부", "판정", "비고"]
SOFT404 = ("페이지를 찾을 수 없", "존재하지 않는 페이지", "삭제된 게시", "잘못된 접근", "요청하신 페이지", "Not Found",
           "Page not found", "404 Error", "접근할 수 없는 페이지")
SEVERE = ("404오류", "500오류", "접속오류", "리다이렉트오류", "소프트404", "빈페이지의심")


def _norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def title_match(search_title, real_title):
    a = _norm(re.sub(r"\.{2,}|…", "", search_title or ""))
    b = _norm(real_title)
    if not a or not b:
        return "확인불가"
    if a in b or b in a:
        return "일치"
    return "일치" if difflib.SequenceMatcher(None, a, b).ratio() >= 0.6 else "불일치"


def normalize_url(u):
    return urllib.parse.urldefrag(u.strip())[0]


def read_inputs(specs):
    """[(engine, url, title)] — 같은 URL은 합치고 엔진을 모은다."""
    rows = []
    for spec in specs:
        engine, _, path = spec.partition("=") if "=" in spec and not spec.lower().startswith("http") else ("미상", "", spec)
        with open(path, encoding="utf-8-sig") as f:
            head = f.readline()
            f.seek(0)
            if "검색결과URL" in head:
                for r in csv.DictReader(f):
                    rows.append((r.get("검색엔진") or engine, r["검색결과URL"], r.get("검색결과제목", "")))
            else:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    rows.append((engine, parts[0], parts[1] if len(parts) > 1 else ""))
    merged, order = {}, []
    for engine, url, title in rows:
        key = normalize_url(url)
        if not key.lower().startswith("http"):
            continue
        if key not in merged:
            merged[key] = {"engines": [], "title": title}
            order.append(key)
        if engine not in merged[key]["engines"]:
            merged[key]["engines"].append(engine)
        if title and not merged[key]["title"]:
            merged[key]["title"] = title
    return [(k, merged[k]) for k in order]


def inspect(url, meta, fetcher, check_images, max_images):
    row = {"url": url, "engine": "/".join(meta["engines"]), "search_title": meta["title"], "status": "", "page_title": "",
           "match": "", "verdict": "", "note": ""}
    if not fetcher.host_allowed(url):
        row.update(status="미접속(외부 도메인)", verdict="제외", note="외부 도메인: URL만 기록")
        return row
    r = fetcher.get(url)
    if r.error:
        row.update(status="오류", verdict="접속오류", note=r.error)
        return row
    row["status"] = str(r.status)
    if 300 <= r.status < 400:
        row.update(verdict="리다이렉트오류", note="허용 도메인 밖으로 이동: %s" % urllib.parse.urljoin(url, r.headers.get("Location", "")))
        return row
    if r.status == 404 or r.status == 410:
        row["verdict"] = "404오류"
        return row
    if r.status >= 500:
        row.update(verdict="500오류", note="HTTP %d" % r.status)
        return row
    if r.status >= 400:
        row.update(verdict="담당자 확인 필요", note="HTTP %d (접근 제한 가능성)" % r.status)
        return row
    html = ml.decode_body(r.body, r.headers.get("Content-Type", ""))
    text, _, title = ml.html_parse(html)
    row["page_title"] = title
    row["match"] = title_match(meta["title"], title)
    notes = []
    fin, orig = urllib.parse.urlsplit(r.final_url), urllib.parse.urlsplit(url)
    if fin.path.rstrip("/") != orig.path.rstrip("/"):
        notes.append("리다이렉트: %s" % r.final_url)
        if fin.path.rstrip("/") in ("", "/index.do", "/index.jsp", "/main.do") and orig.path.rstrip("/") not in ("", "/index.do"):
            row["verdict"] = "리다이렉트오류"
            notes.append("메인으로 이동(삭제된 페이지 가능성, 확인 필요)")
    head_text = text[:300]
    if any(p in title for p in SOFT404) or (len(text) < 1500 and any(p in head_text for p in SOFT404)):
        row["verdict"] = "소프트404"
        notes.append("상태코드 200이나 '페이지 없음' 안내로 보임")
    elif len(text) < 80 and not row["verdict"]:
        row["verdict"] = "빈페이지의심"
        notes.append("본문 텍스트가 거의 없음 (스크립트 렌더링 페이지일 수 있어 브라우저 확인 필요)")
    if check_images and not row["verdict"]:
        bad = []
        seen = set()
        for src in re.findall(r"<img[^>]+src=[\"']([^\"']+)", html, re.I):
            u = urllib.parse.urldefrag(urllib.parse.urljoin(r.final_url, src))[0]
            if u in seen or u.startswith("data:") or not fetcher.host_allowed(u):
                continue
            seen.add(u)
            if len(seen) > max_images:
                break
            ir = fetcher.check_url(u)
            if ir.error or ir.status in (404, 410) or (ir.status or 0) >= 500:
                bad.append(u)
        if bad:
            row["verdict"] = "깨진이미지"
            notes.append("깨진 이미지 %d개: %s" % (len(bad), ", ".join(bad[:3])))
    if not row["verdict"]:
        if row["match"] == "불일치":
            row["verdict"] = "제목불일치"
            notes.append("검색결과 제목과 실제 제목이 다름(페이지 개편 또는 콘텐츠 교체 가능성, 확인 필요)")
        else:
            row["verdict"] = "정상"
    row["note"] = " / ".join(notes)
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--input", action="append", required=True, help="엔진=파일 (예: google=urls.txt). 여러 번 지정 가능")
    ap.add_argument("--domain", action="append", default=[], help="허용 도메인(프로필이 없을 때)")
    ap.add_argument("--system", default="")
    ap.add_argument("--check-images", action="store_true")
    ap.add_argument("--max-images", type=int, default=10)
    ap.add_argument("--today", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    settings = ml.load_settings(args.workspace)
    domains = list(args.domain)
    system = args.system
    prof = ml.load_json(os.path.join(args.workspace, "site-profile.json"))
    if prof:
        try:
            p = ml.load_profile(args.workspace)
            domains += p["allowed_domains"]
            system = system or p.get("site_name", "")
        except ml.ProfileError:
            pass
    if not domains:
        print("[오류] 허용 도메인이 없습니다. site-profile.json 또는 --domain 이 필요합니다.", file=sys.stderr)
        return 1
    items = read_inputs(args.input)
    fetcher = ml.Fetcher(settings, domains)
    targets = [u for u, _ in items if fetcher.host_allowed(u)]
    if args.dry_run:
        print(json.dumps({"urls": len(items), "to_request": len(targets), "external_skipped": len(items) - len(targets),
                          "est_minutes_min": round(len(targets) * float(settings["min_interval_sec"]) / 60, 1)}, ensure_ascii=False, indent=2))
        return 0
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    rows, aborted = [], False
    try:
        for url, meta in items:
            rows.append(inspect(url, meta, fetcher, args.check_images, args.max_images))
    except ml.Blocked as e:
        aborted = True
        print("[중단] %s — 보안·운영 부서에 허용 목록 등록을 요청하세요. (이후 URL은 미점검)" % e, file=sys.stderr)
    outdir = os.path.join(args.workspace, "runs", str(today))
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "search-index-links.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(COLUMNS)
        for i, r in enumerate(rows, 1):
            w.writerow([i, system, r["engine"], r["search_title"], r["url"], r["status"], r["page_title"], r["match"], r["verdict"], r["note"]])
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = {"date": str(today), "urls": len(items), "checked": len(rows), "unchecked": len(items) - len(rows), "partial": aborted,
               "verdict_counts": counts, "problems": sum(counts.get(k, 0) for k in SEVERE + ("깨진이미지", "제목불일치", "담당자 확인 필요")),
               "requests": fetcher.request_count}
    ml.save_json(os.path.join(outdir, "search-index-summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if aborted else 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
