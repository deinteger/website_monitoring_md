#!/usr/bin/env python3
"""월간 보고 집계기 (표준 라이브러리만 사용).

workspace/history/*.json 스냅샷으로 월별 신규 콘텐츠 등록 현황, 현행화 현황, 오류 신규·지속·해결을
전월 대비 수치로 계산해 monthly-report.md / monthly-metrics.json / monthly-boards.csv 를 만든다.

예) python scripts/monthly_report.py --workspace workspace --month 2026-09
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

RECENCY_STATUSES = ("정상", "게시 최신성 지연", "게시일 확인 불가", "담당자 확인 필요")
STALE = ("게시 최신성 지연",)


def month_bounds(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    start = dt.date(y, m, 1)
    return start, ml.add_months(start, 1) - dt.timedelta(days=1)


def prev_month(ym):
    s, _ = month_bounds(ym)
    p = ml.add_months(s, -1)
    return "%04d-%02d" % (p.year, p.month)


def load_snapshots(ws):
    d = os.path.join(ws, "history")
    if not os.path.isdir(d):
        return []
    return [ml.load_json(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".json")]


def delta(cur, prev, pct=False):
    if prev is None:
        return "비교 기준 없음"
    diff = cur - prev
    s = "%+.1f%%p" % diff if pct else "%+d" % diff
    return s


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def fmt_pct(v):
    return "-" if v is None else "%.1f%%" % v


def compute(snaps, ym):
    start, end = month_bounds(ym)
    s_m_list = [s for s in snaps if start <= ml.from_iso(s["date"]) <= end]
    if not s_m_list:
        raise SystemExit("[오류] %s 에 해당하는 점검 이력(history)이 없습니다." % ym)
    s_m = s_m_list[-1]
    earlier = [s for s in snaps if ml.from_iso(s["date"]) < start]
    s_prev = earlier[-1] if earlier else None
    pm = prev_month(ym)
    pstart, _ = month_bounds(pm)

    def board_set(s):
        return dict((bid, b) for bid, b in s["boards"].items() if b.get("type") == "board" and b["status"] != "제외")

    cur = board_set(s_m)
    prv = board_set(s_prev) if s_prev else None

    def recency_block(bs):
        if bs is None:
            return None
        c = Counter(b["status"] for b in bs.values())
        denom = sum(c[k] for k in RECENCY_STATUSES)
        return {"counts": dict(c), "denominator": denom, "normal_rate": pct(c["정상"], denom)}

    rc, rp = recency_block(cur), recency_block(prv)
    updated = [bid for bid, b in cur.items() if b.get("latest_date") and ml.from_iso(b["latest_date"]) >= start]
    updated_prev = None
    if prv is not None and s_prev:
        ps, pe = pstart, start - dt.timedelta(days=1)
        updated_prev = [bid for bid, b in prv.items() if b.get("latest_date") and ps <= ml.from_iso(b["latest_date"]) <= pe]
    transitions = {"improved": [], "newly_stale": []}
    if prv is not None:
        for bid, b in cur.items():
            p = prv.get(bid)
            if not p:
                continue
            if p["status"] in STALE and b["status"] == "정상":
                transitions["improved"].append(bid)
            if p["status"] == "정상" and b["status"] in STALE:
                transitions["newly_stale"].append(bid)

    # 신규 콘텐츠(게시일 기준 월별 건수)
    content, tot_c, tot_p, partial = [], 0, 0, []
    for bid, b in cur.items():
        if not b.get("post_counting"):
            continue
        mc = b.get("month_counts", {})
        n_c, n_p = mc.get(ym, 0), mc.get(pm, 0)
        wo = ml.from_iso(b.get("window_oldest")) if b.get("window_oldest") else None
        cov_c = bool(wo and wo <= start)
        cov_p = bool(wo and wo <= pstart)
        content.append({"board_id": bid, "name": b["name"], "system": b["system"], "owner": b.get("owner", ""),
                        "cur": n_c, "prev": n_p, "cur_complete": cov_c, "prev_complete": cov_p})
        tot_c += n_c
        tot_p += n_p
        if not cov_c:
            partial.append(b["name"])

    # 오류·지적 신규/지속/해결
    key_cat = {}
    for s in snaps:
        for f in s["findings"]:
            key_cat[f["key"]] = f["category"]
    in_month = set()
    for s in s_m_list:
        in_month |= set(f["key"] for f in s["findings"])
    keys_m = set(f["key"] for f in s_m["findings"])
    keys_p = set(f["key"] for f in s_prev["findings"]) if s_prev else None
    if keys_p is not None:
        f_new = in_month - keys_p
        f_cont = keys_m & keys_p
        f_res = (keys_p | in_month) - keys_m
    else:
        f_new, f_cont, f_res = None, None, None

    def cat_count(keys):
        c = Counter(key_cat[k] for k in (keys or []))
        return dict(c)

    return {"month": ym, "prev_month": pm, "snapshot_date": s_m["date"], "prev_snapshot_date": s_prev["date"] if s_prev else None,
            "runs_in_month": len(s_m_list), "modes": dict(Counter(s["mode"] for s in s_m_list)),
            "recency": rc, "recency_prev": rp, "updated": updated, "updated_prev": updated_prev, "transitions": transitions,
            "content": content, "content_total": tot_c, "content_total_prev": tot_p, "partial_boards": partial,
            "findings": {"open_now": len(keys_m), "new": None if f_new is None else len(f_new), "continuing": None if f_cont is None else len(f_cont),
                         "resolved": None if f_res is None else len(f_res), "open_by_category": cat_count(keys_m),
                         "new_by_category": cat_count(f_new) if f_new is not None else None},
            "boards_cur": cur, "boards_prev": prv}


def render(m):
    ym, pm = m["month"], m["prev_month"]
    rc, rp = m["recency"], m["recency_prev"]
    has_prev = rp is not None
    L = ["# %s 홈페이지 점검 월간 보고\n" % ym]
    L.append("## 1. 점검 개요\n")
    L.append("- 집계 기준: %s 월말 마지막 점검(%s)%s" % (ym, m["snapshot_date"], (" / 비교 기준: " + m["prev_snapshot_date"] + " 점검") if has_prev else " / 전월 점검 이력 없음(비교 기준 없음)"))
    L.append("- 월 중 점검 횟수: %d회 (%s)" % (m["runs_in_month"], ", ".join("%s %d회" % (k, v) for k, v in m["modes"].items())))
    L.append("- 게시일 판정 대상 게시판: %d개\n" % rc["denominator"])

    L.append("## 2. 핵심 지표 (전월 대비)\n")
    rows = [["게시 최신성 정상률", fmt_pct(rc["normal_rate"]), fmt_pct(rp["normal_rate"]) if has_prev else "-",
             delta(rc["normal_rate"], rp["normal_rate"], True) if has_prev and rc["normal_rate"] is not None and rp["normal_rate"] is not None else "비교 기준 없음"]]
    rows.append(["게시 최신성 지연 게시판 수", rc["counts"].get("게시 최신성 지연", 0), rp["counts"].get("게시 최신성 지연", 0) if has_prev else "-",
                 delta(rc["counts"].get("게시 최신성 지연", 0), rp["counts"].get("게시 최신성 지연", 0) if has_prev else None)])
    up_rate = pct(len(m["updated"]), rc["denominator"])
    up_prev = pct(len(m["updated_prev"]), rp["denominator"]) if has_prev and m["updated_prev"] is not None else None
    rows.append(["월 중 신규 게시가 있었던 게시판 수", "%d (%s)" % (len(m["updated"]), fmt_pct(up_rate)),
                 ("%d (%s)" % (len(m["updated_prev"]), fmt_pct(up_prev))) if m["updated_prev"] is not None else "-",
                 delta(len(m["updated"]), len(m["updated_prev"]) if m["updated_prev"] is not None else None)])
    rows.append(["신규 등록 콘텐츠(게시글) 건수", m["content_total"], m["content_total_prev"], delta(m["content_total"], m["content_total_prev"])])
    f = m["findings"]
    rows.append(["미해결 지적 건수(월말)", f["open_now"], "-", "-"])
    L.append(_table(["지표", ym, pm, "증감"], rows))

    L.append("## 3. 신규 콘텐츠 등록 현황\n")
    cs = sorted(m["content"], key=lambda x: -x["cur"])
    L.append(_table(["시스템", "게시판", "담당부서", ym + " 등록", pm + " 등록", "증감", "집계범위"],
                    [[c["system"], c["name"], c["owner"], c["cur"], c["prev"], delta(c["cur"], c["prev"]),
                      "전체" if c["cur_complete"] else "부분(하한값)"] for c in cs]))
    if m["partial_boards"]:
        L.append("※ 목록 수집 범위(첫 N쪽)가 해당 월 초까지 닿지 않은 게시판은 실제보다 적게 집계될 수 있습니다(하한값): %s\n" % ", ".join(m["partial_boards"]))
    L.append("※ 건수는 목록에 표시된 게시일 기준이며, 삭제된 게시글과 수집 이전에 삭제·비공개된 글은 반영되지 않습니다.\n")

    L.append("## 4. 현행화 현황\n")
    L.append(_table(["판정", ym + " (게시판 수)", pm + " (게시판 수)"],
                    [[k, rc["counts"].get(k, 0), rp["counts"].get(k, 0) if has_prev else "-"] for k in RECENCY_STATUSES]))
    if has_prev:
        names = lambda ids: ", ".join(m["boards_cur"][i]["name"] for i in ids) or "없음"  # noqa: E731
        L.append("- 지연 → 정상 전환(현행화 개선): %d개 — %s" % (len(m["transitions"]["improved"]), names(m["transitions"]["improved"])))
        L.append("- 정상 → 지연 전환(신규 지연): %d개 — %s\n" % (len(m["transitions"]["newly_stale"]), names(m["transitions"]["newly_stale"])))
    stale = [(b["name"], b.get("owner", ""), b.get("latest_date")) for b in m["boards_cur"].values() if b["status"] in STALE]
    L.append("### 현재 게시 최신성 지연 게시판\n")
    L.append(_table(["게시판", "담당부서", "최신 게시일"], sorted(stale, key=lambda x: x[2] or "")))

    L.append("## 5. 오류·지적 현황\n")
    if f["new"] is None:
        L.append("전월 점검 이력이 없어 신규·지속·해결 구분은 다음 달부터 제공됩니다. (월말 미해결 %d건)\n" % f["open_now"])
    else:
        L.append(_table(["구분", "건수"], [["월 중 신규 발생", f["new"]], ["지속(전월말부터 미해결)", f["continuing"]], ["해결", f["resolved"]], ["월말 미해결", f["open_now"]]]))
    if f["open_by_category"]:
        L.append("월말 미해결 분류별: " + ", ".join("%s %d건" % (k, v) for k, v in f["open_by_category"].items()) + "\n")

    L.append("## 6. 담당부서별 현황\n")
    by_owner = defaultdict(lambda: {"boards": 0, "stale": 0, "content": 0})
    for b in m["boards_cur"].values():
        o = b.get("owner") or "(미지정)"
        by_owner[o]["boards"] += 1
        by_owner[o]["stale"] += 1 if b["status"] in STALE else 0
    for c in m["content"]:
        by_owner[c["owner"] or "(미지정)"]["content"] += c["cur"]
    L.append(_table(["담당부서", "게시판 수", "지연 게시판", ym + " 신규 등록"],
                    [[o, v["boards"], v["stale"], v["content"]] for o, v in sorted(by_owner.items())]))

    L.append("## 7. 집계 한계\n")
    L.append("- 증분 점검 시 방문하지 않은 게시판은 마지막 방문 시점의 데이터를 사용합니다.")
    L.append("- 최신성 정상률의 분모는 게시일 판정 대상 게시판(정상·지연·확인불가·담당자확인필요)이며 접속 오류·제외 게시판은 제외합니다.")
    L.append("- 신규 발생·해결은 월 중 점검 시점에 관측된 지적 기준입니다(점검 사이에 발생·해결된 건은 누락 가능).\n")
    L.append("## 8. AI 종합 의견\n\n<!-- AI_COMMENT: 위 수치와 judgement.json(현행화 의심·문구 개선)을 근거로 3~5줄 요약. 수치는 위 표 값만 인용. -->\n")
    return "\n".join(L) + "\n"


def _table(headers, rows):
    if not rows:
        return "해당 없음\n"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--month", default="", help="YYYY-MM (기본: 지난달)")
    ap.add_argument("--today", default="")
    args = ap.parse_args(argv)
    today = ml.from_iso(args.today) if args.today else dt.date.today()
    ym = args.month or prev_month("%04d-%02d" % (today.year, today.month))
    snaps = load_snapshots(args.workspace)
    m = compute(snaps, ym)
    pm = m["prev_month"]
    outdir = os.path.join(args.workspace, "reports", ym)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "monthly-report.md"), "w", encoding="utf-8") as fh:
        fh.write(render(m))
    metrics = {k: v for k, v in m.items() if k not in ("boards_cur", "boards_prev", "content")}
    metrics["content"] = m["content"]
    ml.save_json(os.path.join(outdir, "monthly-metrics.json"), metrics)
    with open(os.path.join(outdir, "monthly-boards.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(["시스템구분", "게시판", "담당부서", "판정(월말)", "최신게시일", ym + " 등록", pm + " 등록", "증감", "집계범위"])
        cmap = dict((c["board_id"], c) for c in m["content"])
        for bid, b in m["boards_cur"].items():
            c = cmap.get(bid)
            w.writerow([b["system"], b["name"], b.get("owner", ""), b["status"], b.get("latest_date") or "",
                        c["cur"] if c else "", c["prev"] if c else "", (c["cur"] - c["prev"]) if c else "",
                        ("전체" if c["cur_complete"] else "부분") if c else "집계불가"])
    print(os.path.join(outdir, "monthly-report.md"))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
