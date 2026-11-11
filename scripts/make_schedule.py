#!/usr/bin/env python3
"""주기 실행 등록 명령 생성기 (표준 라이브러리만 사용). 명령을 출력만 하고 시스템을 직접 바꾸지 않는다.

  python scripts/make_schedule.py --os windows --time 07:10 --schedule weekdays
  python scripts/make_schedule.py --os linux   --time 07:10 --schedule weekdays
  python scripts/make_schedule.py --os windows --time 07:30 --schedule monthly --day 1 --mode full

출력된 명령을 복사해 실행하면 등록된다. 삭제 방법도 함께 출력한다.
"""
from __future__ import annotations

import argparse
import ntpath
import os
import posixpath
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_WIN_ABS = re.compile(r"^([A-Za-z]:[\\/]|\\\\)")


def _paths(args):
    """대상 OS 기준으로 경로를 만든다 (리눅스에서 윈도우용 명령을 만들어도 경로가 깨지지 않게)."""
    join = ntpath.join if args.os == "windows" else posixpath.join
    root = args.root or ROOT
    ws = args.workspace or join(root, "workspace")
    if not (args.os == "windows" and _WIN_ABS.match(ws)) and not (args.os == "linux" and ws.startswith("/")):
        ws = os.path.abspath(ws)
    return join(root, "scripts", "run_all.py"), ws


def build(args):
    script, ws = _paths(args)
    hh, mm = args.time.split(":")
    py = args.python
    run = [py, script, "--workspace", ws, "--mode", args.mode, "--judge", args.judge]
    if args.typo_check:
        run.append("--typo-check")
    name = args.name
    out = []
    if args.os == "windows":
        cmd = " ".join('"%s"' % x if (" " in x or "\\" in x) else x for x in run)
        sc = {"daily": "/SC DAILY", "weekdays": "/SC WEEKLY /D MON,TUE,WED,THU,FRI",
              "weekly": "/SC WEEKLY /D MON", "monthly": "/SC MONTHLY /D %d" % args.day}[args.schedule]
        out.append('schtasks /Create %s /ST %s:%s /TN "%s" /TR "%s"' % (sc, hh, mm, name, cmd.replace('"', '\\"')))
        out.append('# 삭제: schtasks /Delete /TN "%s" /F' % name)
        out.append('# 확인: schtasks /Query /TN "%s"' % name)
    else:
        cmd = " ".join(shlex.quote(x) for x in run)
        dow = {"daily": "*", "weekdays": "1-5", "weekly": "1", "monthly": "*"}[args.schedule]
        dom = str(args.day) if args.schedule == "monthly" else "*"
        out.append("(crontab -l 2>/dev/null; echo '%d %d %s * %s %s') | crontab -" % (int(mm), int(hh), dom, dow, cmd.replace("'", "'\\''")))
        out.append("# 삭제: crontab -e 에서 해당 줄 삭제")
        out.append("# 확인: crontab -l")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--os", choices=["windows", "linux"], required=True)
    ap.add_argument("--time", default="07:10")
    ap.add_argument("--schedule", choices=["daily", "weekdays", "weekly", "monthly"], default="weekdays")
    ap.add_argument("--day", type=int, default=1, help="monthly 일 때 실행일(1~28)")
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    ap.add_argument("--judge", choices=["auto", "yes", "no"], default="no")
    ap.add_argument("--typo-check", action="store_true")
    ap.add_argument("--workspace", default="", help="기본: <키트 폴더>/workspace")
    ap.add_argument("--root", default="", help="키트 폴더 경로(다른 OS용 명령을 만들 때 지정)")
    ap.add_argument("--python", default="python")
    ap.add_argument("--name", default="")
    args = ap.parse_args(argv)
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", args.time):
        print("[오류] --time 은 HH:MM 형식", file=sys.stderr)
        return 1
    if not 1 <= args.day <= 28:
        print("[오류] --day 는 1~28", file=sys.stderr)
        return 1
    args.name = args.name or ("홈페이지점검-%s" % args.mode)
    print("\n".join(build(args)))
    sep = "\\" if args.os == "windows" else "/"
    print("\n# 실행 결과: %s%sruns%s<날짜>%sinspection-summary.md, reports%srecent%slatest.md" % ((_paths(args)[1], sep, sep, sep, sep, sep)))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
