#!/usr/bin/env python3
"""사이트 프로필 초안 생성기 (표준 라이브러리만 사용).

시작 URL에서 같은 도메인 내 링크를 얕게 따라가며 게시판 후보(날짜 목록이 있는 페이지)와
정적 페이지를 구분해 workspace/site-profile.draft.json 을 만든다.
초안은 반드시 사람이 또는 AI(core/onboarding.md)가 검수·보정한 뒤 site-profile.json 으로 저장한다.

요청은 collect.py 와 동일한 보수적 정책(간격·재시도·차단 시 중단)을 따른다.

예) python scripts/discover.py --workspace workspace --base-url https://www.example.go.kr/ --site-name "OO 홈페이지"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

SKIP_URL = re.compile(r"(login|logout|logon|admin|download|filedown|fileDown|print|rss|sitemap\.xml|member|join|mypage)", re.I)
SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|ico|css|js|zip|pdf|hwp|hwpx|docx?|xlsx?|pptx?|mp4|mp3)$", re.I)
IGNORE_PARAMS = {"page", "pageindex", "pageno", "currentpage", "pageunit", "cpage", "pg"}


def normalize(url):
    p = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.lower() not in IGNORE_PARAMS]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", urllib.parse.urlencode(q), ""))


def guess_region(html):
    """날짜가 가장 많은 table/ul 요소를 목록 영역으로 추정하고 (region, row_tag, 날짜 수)를 반환한다."""
    best = (0, None, None)
    for tag, row in (("table", "tr"), ("ul", "li"), ("ol", "li")):
        for inner, attrs in ml.find_elements_attrs(html, tag):
            n = len(ml.parse_dates(ml.html_parse(inner)[0]))
            if n > best[0]:
                spec = {"tag": tag}
                if attrs.get("id"):
                    spec["id"] = attrs["id"]
                elif attrs.get("class"):
                    spec["class"] = attrs["class"].split()[0]
                best = (n, spec, row)
    return best[1], best[2], best[0]


def guess_cycle(latest, today, is_board):
    if not is_board or latest is None:
        return "monthly"
    days = (today - latest).days
    return "daily" if days <= 10 else ("weekly" if days <= 45 else "monthly")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--site-name", default="")
    ap.add_argument("--allow-domain", action="append", default=[])
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--today", default="")
    args = ap.parse_args(argv)

    import datetime as dt
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    settings = ml.load_settings(args.workspace)
    host = (urllib.parse.urlsplit(args.base_url).hostname or "").lower()
    allowed = sorted(set([host] + [d.lower() for d in args.allow_domain]))
    fetcher = ml.Fetcher(settings, allowed)

    seen, queue, boards = set(), deque([(normalize(args.base_url), 0)]), []
    seen.add(queue[0][0])
    fetched = 0
    try:
        while queue and fetched < args.max_pages:
            url, depth = queue.popleft()
            r = fetcher.get(url)
            fetched += 1
            if not r.ok:
                continue
            html = ml.decode_body(r.body, r.headers.get("Content-Type", ""))
            region, row_tag, ndates = guess_region(html)
            text, links, title = ml.html_parse(html)
            board = {"id": "", "name": (title or url)[:60], "url": url, "type": "static",
                     "cycle": "monthly", "owner": "", "irregular": False}
            if ndates >= 3 and region:
                probe = {"region": region, "row_tag": row_tag}
                parsed = ml.parse_list_page(html, url, probe)
                if len(parsed["rows"]) >= 3:
                    latest = max([r_["date"] for r_ in parsed["rows"] if r_["date"] <= today] or [None]) if parsed["rows"] else None
                    board.update({"type": "board", "region": region, "row_tag": row_tag,
                                  "cycle": guess_cycle(latest, today, True),
                                  "_discover": {"rows": len(parsed["rows"]), "latest": ml.iso(latest)}})
            skip_hrefs = set()
            if board["type"] == "board":
                skip_hrefs = set(l_.get("href") for l_ in parsed["links"])  # 게시글 상세 링크는 따라가지 않는다
            if board["type"] == "board" or depth <= 1:  # 정적 페이지는 메뉴 수준(깊이 1 이하)만 후보로 기록
                board["id"] = "b%03d" % (len(boards) + 1)
                boards.append(board)
            if depth >= args.depth:
                continue
            for l in links:
                href = (l.get("href") or "").strip()
                if not href or href in skip_hrefs or href.startswith("#") or href.lower().startswith(("javascript", "mailto:", "tel:")):
                    continue
                u = normalize(urllib.parse.urljoin(r.final_url, href))
                if (urllib.parse.urlsplit(u).hostname or "").lower() not in allowed:
                    continue
                if u in seen or SKIP_URL.search(u) or SKIP_EXT.search(urllib.parse.urlsplit(u).path):
                    continue
                seen.add(u)
                queue.append((u, depth + 1))
    except ml.Blocked as e:
        print("[중단] %s — 허용 목록 등록 후 다시 실행하세요." % e, file=sys.stderr)

    profile = {"site_name": args.site_name or host, "base_url": args.base_url, "allowed_domains": allowed, "boards": boards,
               "_note": "초안입니다. 게시판 이름·주기·담당부서·비정기 여부를 검수하고, 불필요한 정적 페이지는 삭제하세요. "
                        "검수 후 site-profile.json 으로 저장."}
    out = os.path.join(args.workspace, "site-profile.draft.json")
    ml.save_json(out, profile)
    n_board = sum(1 for b in boards if b["type"] == "board")
    print(json.dumps({"fetched_pages": fetched, "boards": n_board, "static": len(boards) - n_board, "output": out,
                      "requests": fetcher.request_count}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
