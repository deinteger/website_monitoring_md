"""홈페이지 점검 키트 공통 라이브러리.

표준 라이브러리만 사용한다 (pip 설치 불필요, Python 3.8 이상).
결정적 작업(날짜 계산, 상태코드, 목록 파싱, 변경 감지, 개인정보 마스킹)을 담당하고,
추론이 필요한 판단은 AI(core/judgement-guide.md)에 넘긴다.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser

VERSION = "1.0.0"

DEFAULT_SETTINGS = {
    "stale_months": 3,              # 게시 최신성 지연 기준(달력 기준 개월)
    "max_concurrency": 2,           # 동시 요청 수 (보수적 기본값)
    "min_interval_sec": 1.0,        # 전체 요청 간 최소 간격(초)
    "timeout_sec": 20,
    "retries": 2,                   # 실패 시 재시도 횟수 (총 시도 = 1 + retries)
    "retry_wait_sec": 3,
    "max_retry_after_sec": 60,
    "abort_after_blocked": 5,       # 403/429가 연속 N회면 차단 의심으로 중단
    "abort_after_failures": 10,     # 응답 없음·접속 실패가 연속 N회면 서버 장애/차단 가능성으로 중단
    "max_total_sec": 45,            # 요청 1회(연결·응답 수신 전체)의 총 시간 상한. 느리게 이어지는 응답·이름 해석 지연 방어
    "user_agent": "WebsiteMonitoringKit/" + VERSION,
    "contact": "",                  # 담당 부서/연락처: User-Agent에 포함되어 허용 목록 등록 및 문의에 활용
    "verify_ssl": True,
    "check_links": True,
    "max_links_per_board": 15,
    "link_check_interval_days": 7,
    "full_every_days": 30,          # 마지막 전체 점검 후 이 기간이 지나면 full 권장 경고
    "js_fallback": "agent",         # 목록을 못 읽은 게시판(js_suspected) 처리: agent(에이전트 브라우저 확인) | playwright(자동 렌더링)
    "render": {"timeout_sec": 30, "block_resources": True, "executable_path": "", "no_sandbox": False, "wait_after_load_ms": 300},
    # 게시글 본문 오타 점검(선택): 신규 게시글의 상세 페이지를 추가로 요청하고 AI가 판단하므로 기본은 꺼 둔다
    "typo_check": {"enabled": False, "max_posts_per_board": 3, "max_posts_per_run": 30, "max_chars": 3000,
                   "checked_cap": 2000},
    "recent_posts_keep_days": 60,   # 최근 게시물 조회용으로 보관하는 기간(일)
    "recent_posts_cap": 100,        # 게시판당 최대 보관 건수
    "excerpt_chars": 1500,
    "seen_posts_cap": 3000,
    "llm": {"allowed": False},
}

CYCLE_ALIASES = {
    "daily": "daily", "매일": "daily",
    "weekly": "weekly", "주1회": "weekly",
    "monthly": "monthly", "월1회": "monthly",
    "quarterly": "quarterly", "분기1회": "quarterly",
}

ATTACHMENT_EXT = (".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                  ".zip", ".csv", ".txt", ".hml")

def setup_stdio():
    """Windows 기본 콘솔(cp949 등)에서 출력 불가 문자로 중단되지 않도록 한다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------- 날짜

_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(20\d{2})\s*[-./]\s*(0?[1-9]|1[0-2])\s*[-./]\s*(0?[1-9]|[12]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})\s*년\s*(0?[1-9]|1[0-2])\s*월\s*(0?[1-9]|[12]\d|3[01])\s*일"),
]


def parse_dates(text, custom_regex=None):
    """텍스트에서 날짜를 등장 순서대로 추출한다. custom_regex는 (연,월,일) 3개 그룹이어야 한다."""
    patterns = [re.compile(custom_regex)] if custom_regex else _DATE_PATTERNS
    found = []
    for pat in patterns:
        for m in pat.finditer(text):
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                found.append((m.start(), dt.date(y, mo, d)))
            except (ValueError, IndexError):
                continue
    found.sort(key=lambda x: x[0])
    return [d for _, d in found]


def add_months(d, n):
    """달력 기준 월 가감. 말일은 해당 월 말일로 보정한다 (예: 5/31 - 3개월 = 2/28)."""
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def is_stale(latest, today, months=3):
    """최신 게시일이 기준일의 달력 기준 N개월 전 날짜와 같거나 이전이면 True (경계값 포함)."""
    return latest <= add_months(today, -months)


def elapsed_text(latest, today):
    days = (today - latest).days
    if days < 0:
        return "미래 날짜"
    if days < 60:
        return "%d일" % days
    return "약 %d개월" % (days // 30)


def due_by_cycle(cycle, last_checked, today):
    """점검 주기에 따라 오늘 방문 대상인지 판단한다. 월·분기는 달력 기준이다."""
    cycle = CYCLE_ALIASES.get(cycle, cycle)
    if last_checked is None or cycle == "daily":
        return True
    if cycle == "weekly":
        return (today - last_checked).days >= 7
    if cycle == "monthly":
        return last_checked <= add_months(today, -1)
    if cycle == "quarterly":
        return last_checked <= add_months(today, -3)
    return True


def iso(d):
    return d.isoformat() if d else None


def from_iso(s):
    return dt.date.fromisoformat(s) if s else None


# ---------------------------------------------------------------- 개인정보 마스킹

_RRN = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<!\d)(0\d{1,2})([-.\s]?)(\d{3,4})([-.\s]?)(\d{4})(?!\d)")


def mask_pii(text):
    """AI 전송·결과 파일 기록 전에 주민번호/이메일/전화번호를 마스킹한다.
    전화번호는 형식 점검이 가능하도록 지역번호와 구분자는 남긴다. 이름·주소는 마스킹하지 못한다."""
    if not text:
        return text
    text = _RRN.sub("******-*******", text)
    text = _EMAIL.sub(lambda m: "***@" + m.group(1), text)
    text = _PHONE.sub(lambda m: m.group(1) + m.group(2) + "*" * len(m.group(3)) + m.group(4) + "****", text)
    return text


# ---------------------------------------------------------------- HTML 처리

_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class _ElementFinder(HTMLParser):
    """tag(+class/id)와 일치하는 요소의 내부 HTML 구간을 찾는다 (중첩 깊이 추적)."""

    def __init__(self, html, tag, cls=None, id_=None, limit=None):
        super().__init__(convert_charrefs=False)
        self.html, self.tag, self.cls, self.id_, self.limit = html, tag.lower(), cls, id_, limit
        self.line_starts = [0]
        for m in re.finditer("\n", html):
            self.line_starts.append(m.end())
        self.depth = 0
        self.start = None
        self.start_attrs = {}
        self.spans = []

    def _offset(self):
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def _match(self, attrs):
        a = dict(attrs)
        if self.id_ and a.get("id") != self.id_:
            return False
        if self.cls and self.cls not in (a.get("class") or "").split():
            return False
        return True

    def handle_starttag(self, tag, attrs):
        if self.limit and len(self.spans) >= self.limit:
            return
        if tag in _VOID:
            return
        if self.depth == 0:
            if tag == self.tag and self._match(attrs):
                self.depth = 1
                self.start_attrs = dict(attrs)
                self.start = self._offset() + len(self.get_starttag_text())
        elif tag == self.tag:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag == self.tag:
            self.depth -= 1
            if self.depth == 0:
                self.spans.append((self.start, self._offset(), self.start_attrs))


def find_elements_attrs(html, tag, cls=None, id_=None, limit=None):
    """[(내부 HTML, 시작 태그 속성 dict)] 반환."""
    finder = _ElementFinder(html, tag, cls, id_, limit)
    try:
        finder.feed(html)
        finder.close()
    except Exception:  # 깨진 HTML도 최대한 처리
        pass
    return [(html[s:e], a) for s, e, a in finder.spans]


def find_elements(html, tag, cls=None, id_=None, limit=None):
    return [inner for inner, _ in find_elements_attrs(html, tag, cls, id_, limit)]


class _TextAndLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.title = [], [], ""
        self._skip = 0
        self._in_title = False
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            self._anchor = {"href": href, "text": []}
        elif tag in ("br", "p", "div", "li", "tr", "td", "th"):
            self.parts.append(" ")
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(" " + alt + " ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join("".join(self._anchor["text"]).split())
            self.links.append(self._anchor)
            self._anchor = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._skip:
            return
        self.parts.append(data)
        if self._anchor is not None:
            self._anchor["text"].append(data)


def html_parse(html):
    """(본문 텍스트, 링크 목록[{href,text}], <title>)을 반환한다."""
    p = _TextAndLinks()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    text = " ".join("".join(p.parts).split())
    return text, p.links, " ".join(p.title.split())


def decode_body(body, content_type=""):
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if not m:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
        enc = m.group(1).decode("ascii", "ignore") if m else None
    else:
        enc = m.group(1)
    for candidate in [enc, "utf-8", "cp949"]:
        if not candidate:
            continue
        try:
            return body.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "replace")


# ---------------------------------------------------------------- 목록 파싱

def _slug_key(href, title, date):
    if href and not href.lower().startswith("javascript"):
        p = urllib.parse.urlsplit(href)
        return (p.path + ("?" + p.query if p.query else "")).strip()
    if href:
        m = re.search(r"\(\s*['\"]?([\w-]+)['\"]?", href)
        if m:
            return "js:" + m.group(1)
    return "h:" + hashlib.sha1(("%s|%s" % (title, date)).encode("utf-8")).hexdigest()[:12]


def parse_list_page(html, url, board):
    """게시판 목록 페이지에서 게시일·제목·링크를 추출한다."""
    region_spec = board.get("region") or None
    region_html, region_found = html, True
    if region_spec:
        found = find_elements(html, region_spec.get("tag", "div"), region_spec.get("class"), region_spec.get("id"), limit=1)
        if found:
            region_html = found[0]
        else:
            region_found = False
    text, links, title = html_parse(region_html)
    custom = board.get("date_regex")

    row_tag = board.get("row_tag")
    if not row_tag:
        row_tag = "tr" if region_html.lower().count("<tr") >= 2 else ("li" if region_html.lower().count("<li") >= 2 else None)
    rows = []
    if row_tag:
        for rhtml in find_elements(region_html, row_tag, board.get("row_class")):
            rtext, rlinks, _ = html_parse(rhtml)
            dates = parse_dates(rtext, custom)
            if not dates:
                continue
            first = next((l for l in rlinks if l.get("href")), None)
            rtitle = (first["text"] if first and first["text"] else rtext)[:120]
            href = first["href"] if first else None
            d = dates[0] if board.get("date_source", "first_per_row") == "first_per_row" else max(dates)
            rows.append({"date": d, "title": rtitle, "href": urllib.parse.urljoin(url, href) if href and not href.lower().startswith("javascript") else href,
                         "key": _slug_key(href, rtitle, d)})
    all_dates = parse_dates(text, custom)
    raw_lower = html.lower()
    js_suspected = (not all_dates) and raw_lower.count("<script") >= 3 and len(text) < 400
    return {
        "page_title": title or html_parse(html)[2],
        "region_found": region_found,
        "rows": rows,
        "dates": all_dates,
        "text": text,
        "links": links,
        "js_suspected": js_suspected,
    }


_BODY_HINT = re.compile(r"view|cont|article|body|txt|text|detail|conts", re.I)


def extract_post_body(html, board):
    """게시글 상세 페이지에서 본문 텍스트를 추출한다.
    우선순위: 프로필의 body_region({tag,class|id}) > 휴리스틱(본문 후보 클래스/ID 중 텍스트가 가장 긴 요소, 페이지 전체의 90% 미만).
    반환: (본문 텍스트, 방법). 본문을 못 찾으면 ("", "not_found")."""
    spec = board.get("body_region")
    if spec:
        found = find_elements(html, spec.get("tag", "div"), spec.get("class"), spec.get("id"), limit=1)
        if found:
            return html_parse(found[0])[0], "body_region"
        return "", "body_region_not_found"
    page_len = max(len(html_parse(html)[0]), 1)
    best, best_len = None, 0
    for tag in ("div", "article", "section", "td", "dd"):
        for inner, attrs in find_elements_attrs(html, tag):
            if not _BODY_HINT.search((attrs.get("class") or "") + " " + (attrs.get("id") or "")):
                continue
            t = html_parse(inner)[0]
            if best_len < len(t) < 0.9 * page_len:
                best, best_len = t, len(t)
    if best:
        return best, "heuristic"
    return "", "not_found"


_CLIENT_REDIRECTS = [
    re.compile(r"<meta[^>]+http-equiv\s*=\s*[\"']?refresh[\"']?[^>]*content\s*=\s*[\"']?\s*\d+\s*;\s*url\s*=\s*['\"]?([^\"'>\s]+)", re.I),
    re.compile(r"(?:document\.location|window\.location|\blocation)(?:\.href)?\s*=\s*[\"']([^\"']+)[\"']"),
    re.compile(r"location\.(?:replace|assign)\(\s*[\"']([^\"']+)[\"']\s*\)"),
]


def find_client_redirect(html, base_url):
    """HTTP 리다이렉트가 아닌 자바스크립트·메타 새로고침 이동 주소를 찾는다(주석 처리된 스크립트는 무시).
    메인 주소가 빈 껍데기 페이지로 실제 홈에 이동시키는 사이트에서 점검 대상 페이지를 바로잡는 용도."""
    clean = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    for pat in _CLIENT_REDIRECTS:
        m = pat.search(clean)
        if m and m.group(1).strip() and not m.group(1).strip().startswith(("#", "javascript:")):
            return urllib.parse.urljoin(base_url, m.group(1).strip())
    return None


def fingerprint(parsed):
    """변경 감지용 지문. 조회수 같은 변동 숫자의 영향을 줄이기 위해 제목·날짜 중심으로 계산한다."""
    if parsed["rows"]:
        basis = "|".join("%s:%s" % (r["date"], r["title"]) for r in parsed["rows"][:50])
    else:
        basis = ",".join(str(d) for d in parsed["dates"][:50]) + "|" + re.sub(r"\d+", "#", parsed["text"])[:5000]
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- 요청 제어

class Blocked(Exception):
    """차단 의심(403/429 연속). 즉시 중단하여 대상 서버·보안장비에 부담을 주지 않는다."""


class FetchResult(object):
    def __init__(self, url):
        self.url, self.final_url, self.status = url, url, None
        self.headers, self.body, self.error, self.elapsed = {}, b"", None, 0.0

    @property
    def ok(self):
        return self.status is not None and 200 <= self.status < 400


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """허용 도메인 밖으로 가는 리다이렉트는 따라가지 않는다(외부 사이트 접속 금지, URL만 기록)."""

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.fetcher.host_allowed(urllib.parse.urljoin(req.full_url, newurl)):
            return None
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


class Fetcher(object):
    def __init__(self, settings, allowed_domains=None):
        self.s = settings
        self.allowed = set(d.lower() for d in (allowed_domains or []))
        ua = settings["user_agent"]
        if settings.get("contact"):
            ua += " (+%s)" % settings["contact"]
        # HTTP 헤더는 ASCII만 허용한다. 한글 담당 부서·연락처는 퍼센트 인코딩해 보낸다(서버 관리자가 로그에서 식별 가능).
        self.ua = urllib.parse.quote(ua, safe=" ()+@.,:/;=-_&?*")
        self._lock = threading.Lock()
        self._next = 0.0
        self._blocked = 0
        self._fail = 0
        self.abort_reason = ""
        self.aborted = False
        self.request_count = 0
        self.head_unsupported = set()
        ctx = None
        if not settings.get("verify_ssl", True):
            ctx = ssl._create_unverified_context()
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _SafeRedirect(self))

    def host_allowed(self, url):
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        return (not self.allowed) or host in self.allowed

    def throttle(self):
        """외부(브라우저 렌더링 등)에서도 같은 요청 간격을 지키기 위해 호출한다."""
        self._wait()

    def _wait(self):
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next)
            self._next = t + float(self.s["min_interval_sec"])
        if t > now:
            time.sleep(t - now)

    def _note(self, status, error=None):
        with self._lock:
            if status in (403, 429):
                self._blocked += 1
                if self._blocked >= int(self.s["abort_after_blocked"]):
                    self.aborted = True
                    self.abort_reason = "403/429가 연속 %d회 발생하여 차단 의심으로 중단" % self._blocked
            else:
                self._blocked = 0
            if status is None and error:
                self._fail += 1
                if self._fail >= int(self.s["abort_after_failures"]):
                    self.aborted = True
                    self.abort_reason = "응답 없음·접속 실패가 연속 %d회 발생(서버 장애 또는 차단 가능성)하여 중단" % self._fail
            else:
                self._fail = 0

    def _do(self, url, method, max_bytes, out):
        try:
            req = urllib.request.Request(url, method=method, headers={
                "User-Agent": self.ua, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9"})
            with self.opener.open(req, timeout=float(self.s["timeout_sec"])) as r:
                out["status"], out["final_url"], out["headers"] = r.status, r.geturl(), dict(r.headers)
                out["body"] = r.read(max_bytes) if method == "GET" else b""
        except urllib.error.HTTPError as e:
            out["status"], out["final_url"], out["headers"] = e.code, e.geturl() or url, dict(e.headers or {})
            try:
                out["body"] = e.read(20000)
            except Exception:
                out["body"] = b""
        except (urllib.error.URLError, socket.timeout, ConnectionError, ssl.SSLError, OSError) as e:
            out["error"] = "%s: %s" % (type(e).__name__, getattr(e, "reason", e))
        except Exception as e:  # 예기치 않은 예외도 한 요청의 실패로 처리한다
            out["error"] = "%s: %s" % (type(e).__name__, e)
        finally:
            out["done"] = True

    def get(self, url, method="GET", max_bytes=2000000):
        res = FetchResult(url)
        attempts = 1 + int(self.s["retries"])
        for attempt in range(attempts):
            if self.aborted:
                raise Blocked(self.abort_reason or "차단·장애 의심으로 중단")
            self._wait()
            self.request_count += 1
            t0 = time.monotonic()
            res.error, res.status, retry_after = None, None, None
            out = {}
            th = threading.Thread(target=self._do, args=(url, method, max_bytes, out), daemon=True)
            th.start()
            th.join(float(self.s["max_total_sec"]))
            if not out.get("done"):   # 느린 응답·이름 해석 지연으로 총 시간을 넘긴 요청은 포기한다(스레드는 버림)
                res.error = "시간 초과: %d초 안에 응답을 끝내지 못함" % int(self.s["max_total_sec"])
            else:
                res.status, res.final_url = out.get("status"), out.get("final_url", url)
                res.headers, res.body, res.error = out.get("headers", {}), out.get("body", b""), out.get("error")
                retry_after = (res.headers or {}).get("Retry-After")
            res.elapsed = time.monotonic() - t0
            self._note(res.status, res.error)
            if res.error is None and res.status is not None and res.status < 500 and res.status != 429:
                break
            if attempt < attempts - 1:
                wait = float(self.s["retry_wait_sec"]) * (attempt + 1)
                if retry_after and str(retry_after).isdigit():
                    wait = min(float(retry_after), float(self.s["max_retry_after_sec"]))
                time.sleep(wait)
        return res

    def check_url(self, url):
        """링크·첨부 점검: HEAD 우선, 미지원 서버는 GET(최소 읽기)으로 재확인한다."""
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host not in self.head_unsupported:
            r = self.get(url, method="HEAD")
            if r.status in (405, 501):      # HEAD 미지원 서버: 같은 호스트에는 다시 HEAD 를 보내지 않는다(요청 절반, 일부 서버의 HEAD 연결 끊김 회피)
                self.head_unsupported.add(host)
            if not (r.error or r.status in (400, 403, 405, 501)):
                return r
        return self.get(url, method="GET", max_bytes=1024)


# ---------------------------------------------------------------- 설정·프로필

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
    os.replace(tmp, path)


def load_settings(workspace):
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    user = load_json(os.path.join(workspace, "settings.json"), {}) or {}
    for k, v in user.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    return s


class ProfileError(Exception):
    pass


def load_profile(workspace):
    path = os.path.join(workspace, "site-profile.json")
    prof = load_json(path)
    if prof is None:
        raise ProfileError("사이트 프로필이 없습니다: %s (config.example/site-profile.example.json 참고 또는 discover.py 실행)" % path)
    if not isinstance(prof.get("boards"), list) or not prof["boards"]:
        raise ProfileError("site-profile.json에 boards 목록이 없습니다")
    seen, hosts = set(), set()
    base = prof.get("base_url")
    if base:
        hosts.add((urllib.parse.urlsplit(base).hostname or "").lower())
    for b in prof["boards"]:
        for req in ("id", "name", "url"):
            if not b.get(req):
                raise ProfileError("boards 항목에 %s 누락: %r" % (req, b))
        if not re.match(r"^[A-Za-z0-9_-]+$", b["id"]):
            raise ProfileError("board id는 영문·숫자·_-만 허용: %s" % b["id"])
        if b["id"] in seen:
            raise ProfileError("board id 중복: %s" % b["id"])
        seen.add(b["id"])
        b.setdefault("system", prof.get("site_name", ""))
        b.setdefault("type", "board")
        b.setdefault("owner", "")
        if b.get("render") not in (None, "", "playwright"):
            raise ProfileError("render 값 오류(%s): %s (playwright 만 허용)" % (b["id"], b["render"]))
        b["cycle"] = CYCLE_ALIASES.get(b.get("cycle", "weekly"), b.get("cycle", "weekly"))
        if b["cycle"] not in ("daily", "weekly", "monthly", "quarterly"):
            raise ProfileError("cycle 값 오류(%s): %s" % (b["id"], b["cycle"]))
        b.setdefault("pages", 1)
        hosts.add((urllib.parse.urlsplit(b["url"]).hostname or "").lower())
    prof["allowed_domains"] = sorted(set(d.lower() for d in prof.get("allowed_domains", [])) | hosts)
    return prof
