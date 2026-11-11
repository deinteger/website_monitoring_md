#!/usr/bin/env python3
"""배포용 키트 빌더 (표준 라이브러리만 사용).

허용 목록(ALLOW)에 있는 파일만 dist/ 로 복사하고 zip 으로 묶는다. workspace/ 의 실제 설정·캐시·결과·이전 데이터는
절대 포함되지 않는다. 복사 후 모든 텍스트 파일의 URL 호스트를 검사해 허용 호스트 밖의 도메인
(예: 실제 기관 도메인)이 발견되면 릴리스를 중단한다.

  python scripts/make_release.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = ["AGENTS.md", "CLAUDE.md", "README.md", ".gitignore", "core", "docs", "scripts", "config.example", "tests",
         ".agents/skills", ".agents/rules", ".agents/workflows", ".claude/skills"]
ALLOWED_HOSTS = {"example.go.kr", "www.example.go.kr", "example.com", "www.example.com", "127.0.0.1", "localhost",
                 "api.openai.com", "api.anthropic.com", "claude.ai", "github.com", "pi.dev", "onorca.dev", "www.onorca.dev",
                 "code.claude.com", "cdn.jsdelivr.net"}
TEXT_EXT = (".md", ".py", ".json", ".txt", ".csv", ".html", ".gitignore", "")


def collect_files():
    for item in ALLOW:
        p = os.path.join(ROOT, item)
        if os.path.isfile(p):
            yield item
        elif os.path.isdir(p):
            for d, dirs, files in os.walk(p):
                dirs[:] = [x for x in dirs if x not in ("__pycache__", ".pytest_cache")]
                for f in files:
                    if not f.endswith((".pyc", ".tmp")):
                        yield os.path.relpath(os.path.join(d, f), ROOT)


def scan_hosts(base, files):
    bad = {}
    pat = re.compile(r"https?://([A-Za-z0-9.-]+)")
    for rel in files:
        if not rel.endswith(TEXT_EXT):
            continue
        try:
            text = open(os.path.join(base, rel), encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for h in pat.findall(text):
            h = h.lower().rstrip(".")
            if h not in ALLOWED_HOSTS:
                bad.setdefault(h, set()).add(rel)
    return bad


def main():
    name = "website-monitoring-kit-v%s" % ml.VERSION
    dist = os.path.join(ROOT, "dist")
    out = os.path.join(dist, name)
    if os.path.exists(out):
        shutil.rmtree(out)
    files = sorted(set(collect_files()))
    for rel in files:
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), dst)
    os.makedirs(os.path.join(out, "workspace"), exist_ok=True)
    open(os.path.join(out, "workspace", ".gitkeep"), "w").close()
    with open(os.path.join(out, "VERSION"), "w", encoding="utf-8") as f:
        f.write(ml.VERSION + "\n")
    bad = scan_hosts(out, files)
    if bad:
        shutil.rmtree(out)
        print("[릴리스 중단] 허용 목록 밖의 도메인이 발견되었습니다. 실제 기관 정보가 섞였는지 확인하세요:", file=sys.stderr)
        for h, fs in sorted(bad.items()):
            print("  %s  <- %s" % (h, ", ".join(sorted(fs))), file=sys.stderr)
        print("의도한 도메인이면 scripts/make_release.py 의 ALLOWED_HOSTS 에 추가하세요.", file=sys.stderr)
        return 1
    zpath = os.path.join(dist, name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(out):
            for f in fs:
                full = os.path.join(d, f)
                z.write(full, os.path.join(name, os.path.relpath(full, out)))
    print("릴리스 폴더: %s\nzip: %s\n파일 %d개" % (out, zpath, len(files) + 2))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
