"""테스트용 로컬 가짜 사이트 (실제 기관 사이트에 요청하지 않는다)."""
import http.server
import json
import os
import threading
import zlib


def board(rows, attach=""):
    trs = "".join('<tr><td>%d</td><td><a href="/view/%d">%s</a></td><td>%s</td><td>조회 %d</td></tr>'
                  % (i, zlib.crc32(t.encode("utf-8")), t, d, 100 + i) for i, (t, d) in enumerate(rows, 1))
    return ('<html><head><title>목록 | 테스트</title></head><body><div class="nav"><a href="/about">소개</a></div>'
            '<table class="board"><tr><th>번호</th><th>제목</th><th>등록일</th><th>조회</th></tr>%s%s</table>'
            '</body></html>' % (trs, ('<tr><td colspan="4">%s</td></tr>' % attach) if attach else ""))


class State(object):
    def __init__(self):
        self.pages = {}
        self.hits = {}
        self.lock = threading.Lock()


STATE = State()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _serve(self, head):
        path = self.path.split("?")[0]
        with STATE.lock:
            STATE.hits[path] = STATE.hits.get(path, 0) + 1
        if path == "/blocked":
            self.send_response(429)
            self.end_headers()
            return
        if path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://localhost:%d/elsewhere" % self.server.server_address[1])
            self.end_headers()
            return
        if path == "/files/a.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            if not head:
                self.wfile.write(b"%PDF-1.4")
            return
        if path.startswith("/view/"):
            entry = "<html>ok</html>"
        else:
            entry = STATE.pages.get(path)
        if entry is None:
            self.send_response(404)
            self.end_headers()
            if not head:
                self.wfile.write(b"not found")
            return
        body = entry.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


def start():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def write_workspace(ws, port, boards, settings=None):
    base = "http://127.0.0.1:%d" % port
    prof = {"site_name": "테스트사이트", "base_url": base + "/", "boards": []}
    for b in boards:
        b = dict(b)
        b["url"] = base + b["url"]
        prof["boards"].append(b)
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "site-profile.json"), "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False)
    st = {"min_interval_sec": 0, "retries": 0, "retry_wait_sec": 0, "max_concurrency": 2, "contact": "test"}
    st.update(settings or {})
    with open(os.path.join(ws, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(st, f)
