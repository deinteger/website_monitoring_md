"""선택 모듈: Playwright 브라우저 렌더링 (자바스크립트로 그려지는 페이지, 화면 캡처, 계산된 스타일).

기본 설치에는 필요 없다. 다음 경우에만 쓴다.
  - 게시판 단위: site-profile.json 의 board 에 "render": "playwright"  /  settings.json 의 "js_fallback": "playwright"
  - 정책정보·UI/UX 점검: policy_check.py --render auto|always (빈 껍데기 페이지만 / 전체 페이지를 렌더링한 DOM으로 점검)
  - UI/UX AI 화면 검토: uiux_review.py plan (화면 캡처·계산된 스타일 수집)

설치(사용자만): pip install playwright  후  playwright install chromium
기관 PC에서 설치가 어려우면 쓰지 않는다. 그 경우 AI 에이전트의 브라우저로 같은 확인을 한다(해당 항목은 needs_browser 로 표시).

주의: 브라우저는 페이지 1개당 스크립트·API 등 하위 요청을 추가로 보낸다. 허용 도메인 밖 요청은 차단하고(설정 시) 이미지·글꼴·미디어는
받지 않는다(캡처 때는 이미지·글꼴을 허용한다). Playwright 동기 API는 만든 스레드에서만 쓸 수 있어 전용 스레드 하나에서 순차 처리한다.
"""
from __future__ import annotations

import os
import queue
import threading


class RenderUnavailable(Exception):
    """Playwright 미설치 또는 브라우저 실행 실패."""


STYLE_JS = """() => {
  const sel = ['body','h1','h2','h3','p','a','button','input[type=text],input[type=search]','th','td','label','nav a','footer','header'];
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return [0,0,0,1]; const p = m[1].split(',').map(x => parseFloat(x)); return [p[0],p[1],p[2],p.length>3?p[3]:1]; };
  const bgOf = (el) => { let e = el; while (e) { const c = getComputedStyle(e).backgroundColor; if (parse(c)[3] > 0.5) return c; e = e.parentElement; } return 'rgb(255, 255, 255)'; };
  const out = [];
  for (const s of sel) { const el = document.querySelector(s); if (!el) continue; const cs = getComputedStyle(el);
    out.push({selector: s, text: ((el.innerText || el.value || '') + '').trim().slice(0, 30), color: cs.color, background: bgOf(el),
              fontSize: cs.fontSize, fontWeight: cs.fontWeight, lineHeight: cs.lineHeight, fontFamily: cs.fontFamily.slice(0, 60)}); }
  return out; }"""


def contrast_ratio(c1, c2):
    """WCAG 대비(명도 대비) 비율. c1, c2: 'rgb(r, g, b)' 문자열."""
    import re

    def lum(c):
        m = re.search(r"rgba?\(([^)]+)\)", c or "")
        if not m:
            return 0.0
        r, g, b = [float(x) for x in m.group(1).split(",")[:3]]
        f = lambda v: (v / 255.0 / 12.92) if v / 255.0 <= 0.03928 else (((v / 255.0 + 0.055) / 1.055) ** 2.4)  # noqa: E731
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    a, b = lum(c1), lum(c2)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


class Renderer(object):
    def __init__(self, settings, host_allowed, user_agent):
        self.cfg = settings.get("render", {}) or {}
        self.host_allowed = host_allowed
        self.ua = user_agent
        self._q = queue.Queue()
        self._thread = None
        self._ready = threading.Event()
        self._error = None
        self.pages = 0
        self._start_lock = threading.Lock()

    # -- 공개 API --------------------------------------------------------
    def start(self):
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        self._ready.wait(60)
        if self._error:
            raise RenderUnavailable(self._error)

    def _call(self, cmd):
        self.start()
        reply = queue.Queue()
        self._q.put((cmd, reply))
        return reply.get()

    def fetch(self, url, wait_selector=None):
        """렌더링된 HTML을 반환한다: {status, html, final_url, error}"""
        return self._call({"op": "html", "url": url, "wait": wait_selector})

    def capture(self, url, shots, wait_selector=None, want_styles=True):
        """화면 캡처와 계산된 스타일을 수집한다.
        shots: [{"name": "desktop", "path": "...png", "width": 1280, "height": 900, "full_page": True}, ...]
        반환: {status, html, final_url, shots: {name: path}, styles: [...], error}"""
        return self._call({"op": "capture", "url": url, "shots": shots, "wait": wait_selector, "styles": want_styles})

    def close(self):
        if self._thread is not None:
            self._q.put(None)
            self._thread.join(10)

    # -- 전용 스레드 -------------------------------------------------------
    def _run(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._error = "Playwright 미설치 (pip install playwright, playwright install chromium)"
            self._ready.set()
            return
        try:
            with sync_playwright() as p:
                kw = {"headless": True}
                exe = self.cfg.get("executable_path") or os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
                if exe:
                    kw["executable_path"] = exe
                if self.cfg.get("no_sandbox"):
                    kw["args"] = ["--no-sandbox"]
                try:
                    browser = p.chromium.launch(**kw)
                except Exception as e:  # 브라우저 미설치 등
                    self._error = "브라우저 실행 실패: %s" % str(e).splitlines()[0][:200]
                    self._ready.set()
                    return
                self._ready.set()
                while True:
                    item = self._q.get()
                    if item is None:
                        break
                    cmd, reply = item
                    try:
                        reply.put(self._capture(browser, cmd) if cmd["op"] == "capture" else self._render_one(browser, cmd["url"], cmd.get("wait")))
                    except Exception as e:
                        reply.put({"status": None, "html": "", "final_url": cmd.get("url"), "shots": {}, "styles": [],
                                   "error": "렌더링 실패: %s" % str(e).splitlines()[0][:200]})
                browser.close()
        except Exception as e:
            if not self._ready.is_set():
                self._error = "Playwright 시작 실패: %s" % str(e)[:200]
                self._ready.set()

    def _open(self, browser, url, wait_selector, viewport=None, block=True):
        timeout_ms = int(float(self.cfg.get("timeout_sec", 30)) * 1000)
        kw = {"user_agent": self.ua, "locale": "ko-KR"}
        if viewport:
            kw["viewport"] = viewport
        ctx = browser.new_context(**kw)
        page = ctx.new_page()

        def route(r):
            req = r.request
            host_ok = self.host_allowed(req.url) or req.url.startswith(("data:", "about:", "blob:"))
            if (not host_ok) or (block and req.resource_type in ("image", "media", "font")):
                r.abort()
            else:
                r.continue_()
        page.route("**/*", route)
        resp = page.goto(url, wait_until="load", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
        except Exception:
            pass  # 폴링 사이트는 networkidle 이 오지 않을 수 있다
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout_ms)
        page.wait_for_timeout(int(self.cfg.get("wait_after_load_ms", 300)))
        self.pages += 1
        return ctx, page, resp

    def _render_one(self, browser, url, wait_selector):
        ctx = None
        try:
            ctx, page, resp = self._open(browser, url, wait_selector, block=bool(self.cfg.get("block_resources", True)))
            return {"status": resp.status if resp else None, "html": page.content(), "final_url": page.url, "error": None}
        except Exception as e:
            return {"status": None, "html": "", "final_url": url, "error": "렌더링 실패: %s" % str(e).splitlines()[0][:200]}
        finally:
            if ctx:
                ctx.close()

    def _capture(self, browser, cmd):
        out = {"status": None, "html": "", "final_url": cmd["url"], "shots": {}, "styles": [], "error": None}
        first = True
        for spec in cmd["shots"]:
            ctx = None
            try:
                ctx, page, resp = self._open(browser, cmd["url"], cmd.get("wait"), {"width": int(spec["width"]), "height": int(spec.get("height", 900))}, block=False)
                if first:
                    out.update(status=resp.status if resp else None, html=page.content(), final_url=page.url)
                    if cmd.get("styles"):
                        out["styles"] = page.evaluate(STYLE_JS)
                    first = False
                os.makedirs(os.path.dirname(spec["path"]) or ".", exist_ok=True)
                page.screenshot(path=spec["path"], full_page=bool(spec.get("full_page")))
                out["shots"][spec["name"]] = spec["path"]
            except Exception as e:
                out["error"] = "캡처 실패(%s): %s" % (spec.get("name"), str(e).splitlines()[0][:160])
            finally:
                if ctx:
                    ctx.close()
        return out
