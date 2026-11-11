#!/usr/bin/env python3
"""검색 포털 점검 계획 생성기 (표준 라이브러리만 사용).

구글·네이버·다음에서 `site:도메인`(과 불법 광고 키워드)을 검색해 소관 도메인이 악용되거나 깨진 색인이 남았는지 점검하려면
검색어와 결과 저장 파일 목록이 필요하다. 이 스크립트는 그 **계획만** 만든다 (검색 실행은 에이전트 브라우저 또는 사람이 한다).
검색 페이지를 스크립트로 긁는 것은 약관 위반 소지와 봇 차단 때문에 하지 않는다.

  python scripts/portal_plan.py --workspace workspace --engines google,naver,daum --keywords 1-30
  python scripts/portal_plan.py --workspace workspace --no-keywords        # site:도메인 검색만

키워드는 현재 규칙팩(policy-week)의 붙임2 목록(illegal-ad-keywords.txt)을 쓴다. 수집한 URL은
`workspace/index/<엔진>.txt` (한 줄에 `URL<탭>제목<탭>키워드`)로 저장한 뒤 check_index_links.py 로 점검한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402
import policy_check as pc  # noqa: E402

ENGINES = {
    "google": ("구글", "https://www.google.com/search?q=%s"),
    "naver": ("네이버", "https://search.naver.com/search.naver?query=%s"),
    "daum": ("다음", "https://search.daum.net/search?q=%s"),
}


def load_keywords(gdir, pack="policy-week"):
    meta, _, ver, base = pc.load_pack(gdir, pack)
    path = os.path.join(base, meta.get("keywords_file", "illegal-ad-keywords.txt"))
    out, seen = [], set()
    if not os.path.exists(path):
        return out, ver
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        n, _, kw = line.partition("\t")
        if kw and kw not in seen:       # 원문의 중복 키워드(호빠)는 한 번만
            seen.add(kw)
            out.append((int(n), kw))
    return out, ver


def select(keywords, spec):
    if spec in ("", "all"):
        return keywords
    if os.path.exists(spec):
        want = [l.strip() for l in open(spec, encoding="utf-8") if l.strip() and not l.startswith("#")]
        return [(0, w) for w in want]
    a, _, b = spec.partition("-")
    lo, hi = int(a), int(b or a)
    return [(n, k) for n, k in keywords if lo <= n <= hi]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--guidelines-dir", default="")
    ap.add_argument("--engines", default="google,naver,daum")
    ap.add_argument("--domain", action="append", default=[])
    ap.add_argument("--keywords", default="1-30", help="all | 시작-끝 번호 | 키워드 목록 파일. 기본 1-30(첫 배치)")
    ap.add_argument("--no-keywords", action="store_true")
    ap.add_argument("--print", dest="show", action="store_true", help="계획 요약 출력")
    args = ap.parse_args(argv)

    domains = list(args.domain)
    if not domains:
        try:
            domains = [d for d in ml.load_profile(args.workspace)["allowed_domains"]]
        except ml.ProfileError as e:
            print("[설정 오류] %s (또는 --domain 지정)" % e, file=sys.stderr)
            return 1
    engines = [e for e in args.engines.split(",") if e]
    bad = [e for e in engines if e not in ENGINES]
    if bad:
        print("[오류] 지원하지 않는 엔진: %s (google, naver, daum)" % ", ".join(bad), file=sys.stderr)
        return 1
    gdir = args.guidelines_dir or os.path.join(pc.ROOT, "guidelines")
    kws, ver = ([], "") if args.no_keywords else load_keywords(gdir)
    chosen = [] if args.no_keywords else select(kws, args.keywords)
    queries = []
    for d in domains:
        queries.append({"domain": d, "keyword": "", "q": "site:%s" % d})
        for n, k in chosen:
            queries.append({"domain": d, "keyword": k, "no": n, "q": "site:%s %s" % (d, k)})
    plan = {"domains": domains, "engines": engines, "keywords_pack": ver, "keyword_count": len(chosen), "queries": len(queries),
            "total_searches": len(queries) * len(engines),
            "result_files": dict((e, "workspace/index/%s.txt" % e) for e in engines),
            "line_format": "URL<탭>검색결과제목<탭>키워드(없으면 비움)", "items": []}
    for e in engines:
        for q in queries:
            plan["items"].append({"engine": e, "q": q["q"], "keyword": q["keyword"], "url": ENGINES[e][1] % urllib.parse.quote(q["q"])})
    idx = os.path.join(args.workspace, "index")
    os.makedirs(idx, exist_ok=True)
    ml.save_json(os.path.join(idx, "plan.json"), plan)
    L = ["# 검색 포털 점검 계획\n", "- 도메인: %s" % ", ".join(domains), "- 엔진: %s" % ", ".join(ENGINES[e][0] for e in engines),
         "- 검색어 %d개 × 엔진 %d개 = 검색 %d회 (키워드 %d개, 규칙팩 policy-week %s)" % (len(queries), len(engines), plan["total_searches"], len(chosen), ver or "-"),
         "- 결과 저장: %s (한 줄에 `URL<탭>검색결과제목<탭>키워드`)" % ", ".join(plan["result_files"].values()),
         "- 안전: 검색엔진 로그인·광고 클릭 금지, 캡차·차단 시 그 엔진은 중단하고 기록(우회 금지), 결과 페이지는 읽기만 한다.",
         "- 검색어는 불법 광고 점검용 키워드를 포함한다. 결과 URL을 열어 확인할 때는 업무 목적의 확인에 한정한다.\n", "## 검색 목록\n"]
    for e in engines:
        L.append("### %s\n" % ENGINES[e][0])
        for it in [i for i in plan["items"] if i["engine"] == e]:
            L.append("- `%s` — %s" % (it["q"], it["url"]))
        L.append("")
    open(os.path.join(idx, "plan.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps({k: plan[k] for k in ("domains", "engines", "keyword_count", "queries", "total_searches", "result_files")}, ensure_ascii=False, indent=2))
    print("\n계획 파일: %s, %s" % (os.path.join(idx, "plan.md"), os.path.join(idx, "plan.json")))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
