"""선택 모듈: Playwright 브라우저 렌더링 (자바스크립트로 그려지는 목록용).

기본 설치에는 필요 없다. 아래를 지정한 게시판만 사용한다.
  - 게시판 단위: site-profile.json 의 board 에 "render": "playwright"
  - 자동 보완:   settings.json 에 "js_fallback": "playwright" (목록을 못 읽은 게시판만 렌더링)

설치(사용자만): pip install playwright  후  playwright install chromium
기관 PC에서 설치가 어려우면 쓰지 말고 에이전트 브라우저 보완(js_fallback=agent, 기본값)을 사용한다.

주의: 브라우저는 페이지 1개당 스크립트·API 등 하위 요청을 추가로 보낸다. 허용 도메인 밖 요청과(설정 시) 이미지·글꼴·미디어는 차단한다.
Playwright 동기 API는 만든 스레드에서만 쓸 수 있어 전용 스레드 하나에서 순차 처리한다.
"""
from __future__ import annotations

import os
import queue
import threading
import urllib.parse


class RenderUnavailable(Exception):
    """Playwright 미설치 또는 브라우저 실행 실패."""


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

    def fetch(self, url, wait_selector=None):
        """렌더링된 HTML을 반환한다: {status, html, final_url, error}"""
        self.start()
        reply = queue.Queue()
        self._q.put((url, wait_selector, reply))
        return reply.get()

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
                    url, wait_selector, reply = item
                    reply.put(self._render_one(browser, url, wait_selector))
                browser.close()
        except Exception as e:
            if not self._ready.is_set():
                self._error = "Playwright 시작 실패: %s" % str(e)[:200]
                self._ready.set()

    def _render_one(self, browser, url, wait_selector):
        timeout_ms = int(float(self.cfg.get("timeout_sec", 30)) * 1000)
        block = bool(self.cfg.get("block_resources", True))
        ctx = browser.new_context(user_agent=self.ua, locale="ko-KR")
        try:
            page = ctx.new_page()
            blocked = {"n": 0}

            def route(r):
                req = r.request
                host_ok = self.host_allowed(req.url) or req.url.startswith(("data:", "about:", "blob:"))
                if (not host_ok) or (block and req.resource_type in ("image", "media", "font")):
                    blocked["n"] += 1
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
            return {"status": resp.status if resp else None, "html": page.content(), "final_url": page.url, "error": None}
        except Exception as e:
            return {"status": None, "html": "", "final_url": url, "error": "렌더링 실패: %s" % str(e).splitlines()[0][:200]}
        finally:
            ctx.close()
