#!/usr/bin/env python3
"""홈페이지 현황·정보 조회 (표준 라이브러리만 사용). 사람이 일일이 들어가지 않고 물어보는 용도.

  python scripts/lookup.py find 보도자료            # 게시판·페이지 찾기 (이름·주소·담당부서)
  python scripts/lookup.py status 공지사항          # 현황: 판정, 최신 게시일, 최근 게시물, 지적 사항 (오프라인: 저장된 점검 데이터)
  python scripts/lookup.py overview                  # 전체 현황 (오프라인)
  python scripts/lookup.py contact 보도자료          # 그 페이지에 공개된 담당부서·담당자·연락처 (읽기 전용 GET 1회)
  python scripts/lookup.py contact --url https://대상주소/해당페이지   # 프로필에 없는 페이지도 허용 도메인이면 가능

연락처는 **해당 페이지에 공개되어 있는 것만** 추출하며 추정하지 않는다. 근거 원문과 위치(본문/푸터=기관 공통)를 함께 보여준다.
결과를 파일·캐시에 저장하지 않는다. 외부 AI 환경에서 실행하면 출력이 그 서비스에 전달되므로 필요하면 --mask 를 쓴다.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

_BLOCK_END = {"p", "div", "li", "tr", "br", "section", "article", "footer", "header", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table"}
_FOOT = re.compile(r"foot|ft_|_ft|bottom|copyright|addr", re.I)
PHONE = r"(?:0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}|1[5-9]\d{2}[-.\s]?\d{4})"
PHONE_RE = re.compile(r"(?<!\d)" + PHONE + r"(?!\d)")
FAX_RE = re.compile(r"(?:팩스|FAX|Fax|fax)\s*[:：]?\s*(" + PHONE + ")")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KEYWORDS = ("담당부서", "담당자", "담당", "문의", "연락처", "전화", "TEL", "Tel", "tel", "FAX", "팩스", "E-mail", "이메일", "email")
DEPT_RE = re.compile(r"담당\s*부서\s*[:：]?\s*([가-힣A-Za-z0-9·()\s]{2,25}?)(?=\s*(?:담당자|담당|전화|연락처|TEL|Tel|FAX|팩스|이메일|E-mail|문의|\||$))")
PERSON_RE = re.compile(r"담당자\s*[:：]?\s*([가-힣]{2,4})")
ORG_RE = re.compile(r"(?:문의|연락처)\s*[:：]?\s*([가-힣A-Za-z0-9·()]{2,20}?(?:과|팀|실|센터|소|부|담당관|사업단|지원단))(?=\s|\d|$|\()")


class _Lines(HTMLParser):
    """블록 경계마다 줄을 나눈 텍스트와, 각 줄이 푸터 영역인지를 만든다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.skip = [], [], 0
        self.stack = []          # (tag, is_footer)
        self.foot = 0

    def _flush(self):
        t = " ".join("".join(self.cur).split())
        if t:
            self.lines.append((t, self.foot > 0))
        self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
            return
        if tag in ml._VOID:
            if tag == "br":
                self._flush()
            return
        a = dict(attrs)
        is_foot = tag == "footer" or bool(_FOOT.search((a.get("class") or "") + " " + (a.get("id") or "")))
        self.stack.append((tag, is_foot))
        if is_foot:
            self.foot += 1
        if tag in _BLOCK_END:
            self._flush()
        elif tag in ("td", "th", "dt", "dd", "span"):
            self.cur.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if tag in _BLOCK_END:
                    self._flush()
                for _, f in self.stack[i:]:
                    if f:
                        self.foot -= 1
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)


def html_lines(html):
    p = _Lines()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    p._flush()
    return p.lines


def extract_contacts(html):
    """페이지에 공개된 담당부서·담당자·전화·이메일 블록을 찾는다. 추정하지 않고 근거 원문을 함께 반환한다."""
    blocks, seen = [], set()
    for line, in_footer in html_lines(html):
        if len(line) > 400 or not any(k in line for k in KEYWORDS):
            continue
        faxes = [m.group(1) for m in FAX_RE.finditer(line)]
        scrub = FAX_RE.sub(" ", line)
        phones = [p for p in PHONE_RE.findall(scrub)]
        emails = EMAIL_RE.findall(line)
        dept = DEPT_RE.search(line)
        person = PERSON_RE.search(line)
        org = ORG_RE.search(line)
        if not (phones or emails or faxes) and not (dept and person):
            continue
        d = (dept.group(1).strip() if dept else None) or (org.group(1).strip() if org else None)
        b = {"부서": d, "담당자": person.group(1) if person else None, "전화": sorted(set(phones)), "팩스": sorted(set(faxes)),
             "이메일": sorted(set(emails)), "위치": "푸터(기관 공통 가능)" if in_footer else "본문", "원문": line[:200]}
        sig = (b["부서"], b["담당자"], tuple(b["전화"]), tuple(b["이메일"]), b["위치"])
        if sig in seen:
            continue
        seen.add(sig)
        score = (2 if (b["부서"] or b["담당자"]) else 0) + (1 if b["전화"] else 0) + (1 if b["이메일"] else 0)
        b["신뢰도"] = "높음" if (b["부서"] or b["담당자"]) and (b["전화"] or b["이메일"]) else ("중간" if b["전화"] or b["이메일"] else "낮음")
        b["_s"] = (0 if in_footer else 1, score)
        blocks.append(b)
    blocks.sort(key=lambda x: x["_s"], reverse=True)
    for b in blocks:
        b.pop("_s", None)
    return blocks[:8]


def _norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def resolve(entries, q):
    """entries: {id: {name,url,owner,...}} → (선택된 id 또는 None, 후보 [id])"""
    qn = _norm(q)
    if q in entries:
        return q, [q]
    exact = [i for i, e in entries.items() if _norm(e.get("name")) == qn]
    if len(exact) == 1:
        return exact[0], exact
    cont = [i for i, e in entries.items() if qn and (qn in _norm(e.get("name")) or qn in _norm(e.get("url")) or qn in _norm(e.get("owner")))]
    if len(cont) == 1:
        return cont[0], cont
    if cont:
        return None, cont[:10]
    scored = sorted(((difflib.SequenceMatcher(None, qn, _norm(e.get("name"))).ratio(), i) for i, e in entries.items()), reverse=True)
    cand = [i for sc, i in scored[:5] if sc >= 0.5]
    return (cand[0], cand) if len(cand) == 1 else (None, cand)


def load_entries(ws):
    cache = ml.load_json(os.path.join(ws, "cache.json")) or {"boards": {}}
    entries = dict((i, dict(b)) for i, b in cache["boards"].items())
    try:
        prof = ml.load_profile(ws)
        for b in prof["boards"]:
            e = entries.setdefault(b["id"], {})
            e.update({"name": b["name"], "url": b["url"], "owner": b.get("owner", ""), "system": b.get("system", ""), "type": b.get("type", "board")})
        return cache, entries, prof
    except ml.ProfileError:
        return cache, entries, None


def fmt_board_status(e):
    L = ["## %s (%s)" % (e.get("name"), e.get("system", ""))]
    L.append("- 주소: %s" % e.get("url"))
    L.append("- 담당부서(프로필): %s" % (e.get("owner") or "미지정"))
    if not e.get("last_checked"):
        L.append("- 점검 이력 없음 (아직 점검하지 않은 게시판)")
        return "\n".join(L)
    L.append("- 판정: **%s** %s" % (e.get("status"), ("(%s)" % e["note"]) if e.get("note") else ""))
    L.append("- 최신 게시일: %s / 최신 글: %s" % (e.get("latest_date") or "확인 불가", e.get("latest_title") or "-"))
    L.append("- 마지막 점검일: %s" % e["last_checked"])
    f = e.get("findings") or []
    L.append("- 지적 사항: %s" % ("없음" if not f else ""))
    for x in f:
        L.append("  - [%s/%s] %s" % (x["category"], x["severity"], x["detail"]))
    rp = (e.get("recent_posts") or [])[:5]
    if rp:
        L.append("- 최근 게시물:")
        for p in rp:
            L.append("  - %s %s" % (p["date"], p["title"]))
    return "\n".join(L)


def overview(cache, entries):
    from collections import Counter
    boards = [e for e in entries.values() if e.get("type") != "static" and e.get("status")]
    sc = Counter(e["status"] for e in boards)
    L = ["# 홈페이지 현황 (마지막 점검일: %s)\n" % (cache.get("last_run") or "없음")]
    L.append("- 점검 대상 게시판 %d개" % len(boards))
    L.append("- 판정별: " + ", ".join("%s %d" % (k, v) for k, v in sc.most_common()))
    stale = sorted([e for e in boards if e["status"] == "게시 최신성 지연"], key=lambda e: e.get("latest_date") or "")
    L.append("- 게시 최신성 지연 %d개:" % len(stale))
    for e in stale[:10]:
        L.append("  - %s (최신 %s, 담당 %s)" % (e["name"], e.get("latest_date"), e.get("owner") or "미지정"))
    fc = Counter(f["category"] for e in boards for f in (e.get("findings") or []))
    L.append("- 지적 사항: " + (", ".join("%s %d건" % (k, v) for k, v in fc.most_common()) or "없음"))
    return "\n".join(L)


def fmt_contacts(title, url, blocks, mask):
    L = ["## 담당자·연락처: %s" % (title or url), "- 확인한 페이지: %s" % url]
    if not blocks:
        L.append("- 이 페이지에서 담당부서·담당자·연락처 표기를 찾지 못했습니다. (JS로 그려지는 영역이거나 표기가 없는 페이지일 수 있습니다 → 조직도·업무안내 페이지 확인 필요)")
        return "\n".join(L)
    for i, b in enumerate(blocks, 1):
        g = (lambda x: ml.mask_pii(x)) if mask else (lambda x: x)
        L.append("\n### %d. [%s] 신뢰도 %s" % (i, b["위치"], b["신뢰도"]))
        L.append("- 담당부서: %s" % (b["부서"] or "-"))
        L.append("- 담당자: %s" % (g(b["담당자"]) if b["담당자"] else "-"))
        L.append("- 전화: %s" % (", ".join(g(p) for p in b["전화"]) or "-"))
        if b["팩스"]:
            L.append("- 팩스: %s" % ", ".join(b["팩스"]))
        L.append("- 이메일: %s" % (", ".join(g(x) for x in b["이메일"]) or "-"))
        L.append("- 근거 원문: `%s`" % g(b["원문"]))
    L.append("\n※ 해당 페이지에 공개된 표기만 추출했으며 최신·정확 여부는 보장하지 않습니다. 푸터 표기는 기관 공통 연락처일 수 있습니다.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("overview")
    for name in ("find", "status", "contact"):
        sp = sub.add_parser(name)
        sp.add_argument("query", nargs="?", default="")
        if name == "contact":
            sp.add_argument("--url", default="")
            sp.add_argument("--mask", action="store_true", help="전화·이메일 일부를 마스킹해 출력")
            sp.add_argument("--latest-post", action="store_true", help="목록 페이지 대신 최신 게시글 페이지에서 찾는다(점검 이력 필요)")
    args = ap.parse_args(argv)
    cache, entries, prof = load_entries(args.workspace)

    if args.cmd == "overview":
        if not cache["boards"]:
            print("[오류] 점검 이력이 없습니다. 점검을 먼저 실행하거나 state.zip을 복원하세요.", file=sys.stderr)
            return 1
        print(overview(cache, entries))
        return 0

    if args.cmd == "contact" and args.url:
        settings = ml.load_settings(args.workspace)
        domains = prof["allowed_domains"] if prof else []
        fetcher = ml.Fetcher(settings, domains)
        if not domains or not fetcher.host_allowed(args.url):
            print("[거부] 허용 도메인 밖의 주소입니다. site-profile.json 의 allowed_domains 에 포함된 사이트만 조회합니다.", file=sys.stderr)
            return 1
        target = {"name": "", "url": args.url}
    else:
        if not args.query:
            print("[오류] 찾을 이름(예: 보도자료)이나 --url 이 필요합니다.", file=sys.stderr)
            return 1
        picked, cands = resolve(entries, args.query)
        if picked is None:
            if not cands:
                print("[없음] '%s'에 해당하는 게시판·페이지가 없습니다. `find` 로 이름을 확인하세요." % args.query)
                return 3
            print("'%s' 후보가 여러 개입니다. 더 구체적으로 지정하세요 (id 또는 이름):" % args.query)
            for i in cands:
                print("  - %s : %s (%s)" % (i, entries[i].get("name"), entries[i].get("url")))
            return 3
        if args.cmd == "find":
            for i in cands:
                print("%s : %s | %s | 담당 %s" % (i, entries[i].get("name"), entries[i].get("url"), entries[i].get("owner") or "미지정"))
            return 0
        target = entries[picked]
        if args.cmd == "status":
            print(json.dumps(target, ensure_ascii=False, indent=2) if args.json else fmt_board_status(target))
            return 0
        if args.latest_post:
            rp = [p for p in (target.get("recent_posts") or []) if p.get("url")]
            if not rp:
                print("[오류] 최신 게시글 주소가 없습니다(점검 이력이 없거나 목록에서 게시글 링크를 인식하지 못함).", file=sys.stderr)
                return 1
            target = dict(target, url=rp[0]["url"], name="%s — 최신 글: %s" % (target.get("name"), rp[0]["title"]))
        settings = ml.load_settings(args.workspace)
        fetcher = ml.Fetcher(settings, prof["allowed_domains"] if prof else [])
        if not fetcher.host_allowed(target["url"]):
            print("[거부] 허용 도메인 밖의 주소입니다.", file=sys.stderr)
            return 1

    try:
        r = fetcher.get(target["url"])
    except ml.Blocked as e:
        print("[중단] %s — 보안·운영 부서 협의 후 다시 시도하세요." % e, file=sys.stderr)
        return 2
    if not r.ok:
        print("[오류] 페이지에 접속하지 못했습니다 (HTTP %s %s)." % (r.status, r.error or ""), file=sys.stderr)
        return 1
    html = ml.decode_body(r.body, r.headers.get("Content-Type", ""))
    blocks = extract_contacts(html)
    title = target.get("name") or ml.html_parse(html)[2]
    if args.json:
        print(json.dumps({"title": title, "url": r.final_url, "owner_in_profile": target.get("owner", ""), "contacts": blocks}, ensure_ascii=False, indent=2))
    else:
        print(fmt_contacts(title, r.final_url, blocks, args.mask))
        if target.get("owner"):
            print("\n- 프로필에 등록된 담당부서: %s" % target["owner"])
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
