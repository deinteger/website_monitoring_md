#!/usr/bin/env python3
"""최근 현행화(신규 게시) 조회 (표준 라이브러리만 사용).

"어제·그제 현행화된 게시물이 뭐야?" 같은 질문에 답한다. 저장된 점검 데이터(cache.json, history/)만 읽으므로
**네트워크 없이** 동작하며, 어느 환경(Claude, GPT, 제미나이, 로컬)에서든 state.zip/workspace만 있으면 된다.

기간 지정
  --days N        오늘을 뺀 최근 N일 (어제부터 N일 전까지). "어제·그제" = --days 2
  --from/--to     YYYY-MM-DD 직접 지정
  --include-today 오늘 포함
기준
  --by posted(기본) 목록에 표시된 게시일이 기간 안인 글   |  --by seen  이 키트가 기간 중 처음 확인한 글
최신화
  --refresh       조회 전에 증분 점검을 실행(네트워크 사용). 없으면 마지막 점검 시점까지의 데이터만 반영
  --latest        최근 14일(오늘 포함) 요약을 reports/recent/latest.{md,json}에 저장 (스케줄 실행 뒤 자동 호출용.
                  이 파일만 채팅형 AI에 올려도 "어제 그제 뭐 올라왔어?"에 답할 수 있다)
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

MAX_ROWS_PRINT = 200


def window(args, today):
    if args.latest:
        return today - dt.timedelta(days=13), today
    if args.date_from or args.date_to:
        f = ml.from_iso(args.date_from) if args.date_from else None
        t = ml.from_iso(args.date_to) if args.date_to else (today if args.include_today else today - dt.timedelta(days=1))
        return (f or t), t
    n = max(1, args.days)
    to = today if args.include_today else today - dt.timedelta(days=1)
    return to - dt.timedelta(days=n - 1), to


def query(cache, snaps, d_from, d_to, by, today):
    f_s, t_s = str(d_from), str(d_to)
    posts, boards_no_detail, board_rows = [], [], []
    stale_boards = []
    for bid, b in cache["boards"].items():
        if b.get("type") != "board" or b.get("status") == "제외":
            continue
        lc = b.get("last_checked")
        if lc and lc < t_s and b.get("fetch_status"):
            stale_boards.append({"board_id": bid, "name": b["name"], "last_checked": lc})
        rp = b.get("recent_posts")
        hits = []
        if rp:
            for p in rp:
                v = p["date"] if by == "posted" else p.get("first_seen")
                if v and f_s <= v <= t_s:
                    hits.append(p)
        elif by == "posted" and b.get("latest_date") and f_s <= b["latest_date"] <= t_s:
            boards_no_detail.append({"board_id": bid, "system": b["system"], "name": b["name"], "owner": b.get("owner", ""), "latest_date": b["latest_date"]})
        for p in hits:
            posts.append({"board_id": bid, "system": b["system"], "board": b["name"], "owner": b.get("owner", ""), "date": p["date"],
                          "title": p["title"], "url": p.get("url") or b["url"], "first_seen": p.get("first_seen")})
        if hits:
            board_rows.append({"board_id": bid, "system": b["system"], "board": b["name"], "owner": b.get("owner", ""),
                               "count": len(hits), "latest_date": max(p["date"] for p in hits)})
    posts.sort(key=lambda p: (p["date"], p["board"]), reverse=True)
    board_rows.sort(key=lambda r: (-r["count"], r["board"]))

    # 판정 변화(지연 -> 정상 등): 기간 시작 전 마지막 스냅샷과 기간 끝 이전 마지막 스냅샷 비교
    transitions = {"improved": [], "newly_stale": [], "note": None}
    before = [s for s in snaps if s["date"] <= f_s]     # 기간 시작일 포함 이전의 마지막 점검
    after = [s for s in snaps if s["date"] <= str(today)]
    if before and after and before[-1]["date"] < after[-1]["date"]:
        sb, sa = before[-1], after[-1]
        for bid, b in sa["boards"].items():
            p = sb["boards"].get(bid)
            if not p or b.get("type") != "board":
                continue
            if p["status"] == "게시 최신성 지연" and b["status"] == "정상":
                transitions["improved"].append({"board": b["name"], "owner": b.get("owner", ""), "latest_date": b.get("latest_date")})
            if p["status"] == "정상" and b["status"] == "게시 최신성 지연":
                transitions["newly_stale"].append({"board": b["name"], "owner": b.get("owner", ""), "latest_date": b.get("latest_date")})
        transitions["note"] = "비교: %s → %s 점검" % (sb["date"], sa["date"])
    else:
        transitions["note"] = "비교할 이력이 부족함(기간 시작일 이전 점검 이력이 없거나 이후 점검이 없음)"
    warnings = []
    last_run = cache.get("last_run")
    if not last_run:
        warnings.append("점검 이력이 없습니다. 먼저 점검을 실행하세요.")
    elif last_run < t_s:
        warnings.append("마지막 점검일은 %s 입니다. 이후(%s~%s)에 등록된 게시물은 반영되지 않았습니다 → --refresh 또는 점검 실행" % (last_run, last_run, t_s))
    if stale_boards:
        warnings.append("게시판 %d개는 기간 종료일(%s) 이후 방문하지 않아(증분 점검 주기) 이후 등록분이 빠졌을 수 있습니다." % (len(stale_boards), t_s))
    if boards_no_detail:
        warnings.append("게시판 %d개는 건별 목록 없이 최신 게시일만 알 수 있습니다(목록 행 인식 불가)." % len(boards_no_detail))
    if by == "seen":
        warnings.append("'처음 확인한 날짜' 기준: 게시판 최초 수집 때 보인 글은 확인일을 알 수 없어 제외됩니다.")
    return {"from": f_s, "to": t_s, "by": by, "posts": posts, "boards": board_rows, "boards_without_detail": boards_no_detail,
            "transitions": transitions, "warnings": warnings, "last_run": last_run, "stale_boards": stale_boards}


def render(r):
    basis = "게시일 기준" if r["by"] == "posted" else "처음 확인한 날짜 기준"
    L = ["# 최근 현행화 조회 (%s ~ %s, %s)\n" % (r["from"], r["to"], basis)]
    L.append("- 게시물 **%d건** / 게시판 **%d개** (마지막 점검일: %s)" % (len(r["posts"]), len(r["boards"]), r["last_run"] or "없음"))
    for w in r["warnings"]:
        L.append("- **주의**: " + w)
    L.append("")
    L.append("## 게시판별\n")
    if r["boards"]:
        L.append("| 시스템 | 게시판 | 담당부서 | 건수 | 최신 게시일 |\n| --- | --- | --- | --- | --- |")
        L += ["| %s | %s | %s | %d | %s |" % (b["system"], b["board"], b["owner"], b["count"], b["latest_date"]) for b in r["boards"]]
    else:
        L.append("해당 기간에 확인된 신규 게시물이 없습니다.")
    if r["boards_without_detail"]:
        L.append("\n건별 목록 없이 최신 게시일만 확인된 게시판:\n")
        L += ["- %s / %s (최신 게시일 %s)" % (b["system"], b["name"], b["latest_date"]) for b in r["boards_without_detail"]]
    L.append("\n## 게시물 목록\n")
    if r["posts"]:
        L.append("| 게시일 | 시스템 | 게시판 | 제목 | 최초 확인일 |\n| --- | --- | --- | --- | --- |")
        for p in r["posts"][:MAX_ROWS_PRINT]:
            L.append("| %s | %s | %s | [%s](%s) | %s |" % (p["date"], p["system"], p["board"], p["title"].replace("|", "\\|"), p["url"], p["first_seen"] or "기준선"))
        if len(r["posts"]) > MAX_ROWS_PRINT:
            L.append("\n(상위 %d건만 표시. 전체는 JSON 파일 참조)" % MAX_ROWS_PRINT)
    else:
        L.append("없음")
    t = r["transitions"]
    L.append("\n## 현행화 상태 변화 (%s)\n" % t["note"])
    L.append("- 지연 → 정상(현행화 개선): %s" % (", ".join("%s(%s)" % (x["board"], x["latest_date"]) for x in t["improved"]) or "없음"))
    L.append("- 정상 → 지연(신규 지연): %s" % (", ".join("%s(%s)" % (x["board"], x["latest_date"]) for x in t["newly_stale"]) or "없음"))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--from", dest="date_from", default="")
    ap.add_argument("--to", dest="date_to", default="")
    ap.add_argument("--include-today", action="store_true")
    ap.add_argument("--by", choices=["posted", "seen"], default="posted")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--today", default="")
    ap.add_argument("--json", action="store_true", help="표 대신 JSON 출력")
    ap.add_argument("--quiet", action="store_true", help="화면 출력 없이 파일만 저장")
    args = ap.parse_args(argv)

    today = ml.from_iso(args.today) if args.today else dt.date.today()
    ws = args.workspace
    if args.refresh:
        import collect
        buf = io.StringIO()
        cargs = ["--workspace", ws, "--mode", "incremental"] + (["--today", args.today] if args.today else [])
        with contextlib.redirect_stdout(buf):
            code = collect.main(cargs)
        sys.stderr.write("[최신화] 증분 점검 종료코드 %s\n" % code)
    cache = ml.load_json(os.path.join(ws, "cache.json"))
    if not cache:
        print("[오류] 점검 이력(cache.json)이 없습니다. 점검을 먼저 실행하거나 state.zip을 복원하세요.", file=sys.stderr)
        return 1
    snaps = []
    hd = os.path.join(ws, "history")
    if os.path.isdir(hd):
        snaps = [ml.load_json(os.path.join(hd, f)) for f in sorted(os.listdir(hd)) if f.endswith(".json")]
    d_from, d_to = window(args, today)
    res = query(cache, snaps, d_from, d_to, args.by, today)
    md = render(res)
    outdir = os.path.join(ws, "reports", "recent")
    os.makedirs(outdir, exist_ok=True)
    stem = "latest" if args.latest else "%s_%s_%s" % (res["from"], res["to"], args.by)
    with open(os.path.join(outdir, stem + ".md"), "w", encoding="utf-8") as f:
        f.write(md)
    ml.save_json(os.path.join(outdir, stem + ".json"), res)
    if not args.quiet:
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else md)
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
