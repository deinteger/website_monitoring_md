#!/usr/bin/env python3
"""채팅형 환경(코드 실행 컨테이너가 대화 후 사라지는 곳)용 상태 보관 도구 (표준 라이브러리만 사용).

점검 상태(프로필·설정·캐시·이력)를 zip 하나로 묶어 내려받고, 다음 대화에서 올려 이어서 쓴다.
증분 점검과 월간 보고는 이 상태가 있어야 이어진다.

  python scripts/chat_state.py pack   --workspace ws --output state.zip
  python scripts/chat_state.py unpack --input state.zip --workspace ws

API 키는 저장하지 않는다(키는 환경변수로만 사용). 결과 폴더(runs/reports)는 용량이 커서 기본 제외한다(--with-reports).
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

TOP_FILES = ("site-profile.json", "settings.json", "cache.json")


def pack(ws, output, with_reports=False):
    n = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name in TOP_FILES:
            p = os.path.join(ws, name)
            if os.path.exists(p):
                z.write(p, name)
                n += 1
        hist = os.path.join(ws, "history")
        if os.path.isdir(hist):
            for f in sorted(os.listdir(hist)):
                if f.endswith(".json"):
                    z.write(os.path.join(hist, f), "history/" + f)
                    n += 1
        if with_reports:
            rep = os.path.join(ws, "reports")
            for d, _, fs in os.walk(rep):
                for f in fs:
                    full = os.path.join(d, f)
                    z.write(full, os.path.relpath(full, ws).replace(os.sep, "/"))
                    n += 1
    return n


def _safe(name):
    if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") or ":" in name:
        return False
    parts = name.replace("\\", "/").split("/")
    if len(parts) == 1:
        return parts[0] in TOP_FILES
    return parts[0] in ("history", "reports") and not name.endswith("/")


def unpack(zip_path, ws):
    n = 0
    os.makedirs(ws, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if not _safe(info.filename):          # 경로 이탈·예상 밖 파일은 거부
                raise SystemExit("[오류] 허용되지 않은 항목: %s" % info.filename)
            dest = os.path.join(ws, *info.filename.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                dst.write(src.read())
            n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("pack")
    a.add_argument("--workspace", default="workspace")
    a.add_argument("--output", required=True)
    a.add_argument("--with-reports", action="store_true")
    b = sub.add_parser("unpack")
    b.add_argument("--input", required=True)
    b.add_argument("--workspace", default="workspace")
    args = ap.parse_args(argv)
    if args.cmd == "pack":
        print("%d개 파일 저장: %s" % (pack(args.workspace, args.output, args.with_reports), args.output))
    else:
        print("%d개 파일 복원: %s" % (unpack(args.input, args.workspace), args.workspace))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
