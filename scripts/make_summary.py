#!/usr/bin/env python3
"""inspection-summary.md 생성기 (표준 라이브러리만 사용).

findings.json(+ 있으면 judgement.json)으로 core/rules.md 의 9개 구성 요약을 만든다.
AI 판단이 없으면 해당 항목을 '미실시'로 명시해 점검 완료로 오해되지 않게 한다.
에이전트는 이 파일을 바탕으로 종합 의견만 보완하면 된다.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402


def esc(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    if not rows:
        return "해당 없음\n"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def typo_block(typo):
    """게시글 본문 오타 점검 결과(6절에 덧붙임). typo = {"queue":..., "judgement":...} 또는 None"""
    if not typo or typo.get("queue") is None:
        return []
    q, j = typo["queue"], typo.get("judgement")
    L = ["### 게시글 본문 오타 점검\n"]
    L.append("대상 게시글 %d건 수집 (본문 확인 불가·상한 초과 등 제외 %d건)\n" % (len(q["items"]), len(q.get("skipped", []))))
    if j is None:
        L.append("AI 판단 미실시: 수집한 게시글 본문의 오타는 점검되지 않았습니다.\n")
        return L
    rows = []
    for it in j["items"]:
        for x in it["issues"]:
            rows.append([it.get("name"), "[%s](%s) (%s)" % (it.get("title") or "-", it.get("url") or "", it.get("date") or ""), x["type"],
                         x["quote"], x["suggestion"], x["reason"]])
    L.append(table(["게시판", "게시글", "유형", "오류 구절(원문)", "수정안", "사유"], rows))
    judged = len(j["items"])
    clean = sum(1 for it in j["items"] if not it["issues"])
    L.append("점검 %d건 중 오류 없음 %d건, 지적 %d건 (원문 인용 검증에 실패해 버려진 AI 지적 %d건)\n" % (judged, clean, len(rows), j.get("dropped_unverified", 0)))
    return L


def build(findings, judgement, today, months, typo=None):
    meta = findings["meta"]
    fl = findings["findings"]
    boards = findings["boards"]
    cutoff = ml.add_months(ml.from_iso(str(today)), -months)
    by_cat = lambda c: [f for f in fl if f["category"] == c]  # noqa: E731
    L = []
    L.append("# 홈페이지 점검 결과 요약\n")
    L.append("## 1. 점검 개요\n")
    L.append("- 기준일: %s (%d개월 기준일: %s)" % (today, months, cutoff))
    L.append("- 점검 모드: %s%s" % ("전체 점검(full)" if meta["mode"] == "full" else "증분 점검(incremental)", " — **중단된 부분 결과**" if meta.get("partial") else ""))
    L.append("- 대상 게시판·페이지: %d개 (방문 %d, 캐시 재판정 %d, 제외 %d)" % (meta["boards_total"], meta["visited"], meta["from_cache"], meta["excluded"]))
    L.append("- HTTP 요청 수: %d (동시 %s, 최소 간격 %ss)" % (meta["requests"], meta["request_policy"]["max_concurrency"], meta["request_policy"]["min_interval_sec"]))
    for w in meta.get("warnings", []):
        L.append("- **경고**: " + w)
    L.append("")
    L.append("## 2. 종합 결과\n")
    sc = meta["status_counts"]
    L.append(table(["판정", "게시판 수"], [[k, v] for k, v in sorted(sc.items(), key=lambda kv: -kv[1])]))
    L.append("지적 사항: 총 %d건 (신규 %d / 지속 %d / 이번에 해결 %d)\n" % (meta["findings"], meta["findings_new"], meta["findings_continuing"], meta["findings_resolved"]))
    cols = ["상태", "중요도", "시스템", "영역", "발견내용", "URL"]
    row = lambda f: [f["state"], f["severity"], f["system"], f["area"], f["detail"], f["url"]]  # noqa: E731
    L.append("## 3. 확정 오류\n")
    L.append(table(cols, [row(f) for f in by_cat("확정 오류")]))
    L.append("## 4. 게시 최신성 지연\n")
    L.append(table(["상태", "시스템", "영역", "최신 게시일", "경과", "담당부서", "URL"],
                   [[f["state"], f["system"], f["area"], f.get("latest_date"), f["elapsed"], f.get("owner"), f["url"]] for f in by_cat("게시 최신성 지연")]))

    items = (judgement or {}).get("items", [])
    L.append("## 5. 현행화 의심\n")
    if judgement is None:
        L.append("AI 판단 미실시: 현행화·문구 항목은 점검되지 않았습니다 (collect 결과만 반영).\n")
    else:
        rows = [[i["verdict"], i["severity"], i.get("name"), x["type"], x["quote"], x["reason"], x["action"], "O" if x["quote_verified"] else "X"]
                for i in items if i["verdict"] == "현행화 의심" for x in i["issues"]]
        L.append(table(["판정", "중요도", "영역", "유형", "원문 인용", "사유", "권고", "인용검증"], rows))
        L.append("## 6. 문구 개선사항\n")
        rows = [[i.get("name"), x["quote"], x["reason"], x["action"]] for i in items if i["verdict"] == "문구 개선" for x in i["issues"]]
        L.append(table(["영역", "원문 인용", "사유", "개선안"], rows))
    if judgement is None:
        L.append("## 6. 문구 개선사항\n\nAI 판단 미실시\n")
    L.extend(typo_block(typo))
    L.append("## 7. 담당자 확인 필요사항\n")
    rows = [[f["system"], f["area"], f["detail"], f["evidence"], f.get("owner"), f["url"]] for f in by_cat("담당자 확인 필요")]
    rows += [[i.get("name"), "-", i["note"], "AI 판단(신뢰도 %s)" % i["confidence"], "", i.get("url")] for i in items if i["verdict"] == "담당자 확인 필요"]
    L.append(table(["시스템/영역", "영역", "내용", "근거", "담당부서", "URL"], rows))
    L.append("## 8. 점검 한계\n")
    lim = []
    if meta["mode"] == "incremental":
        lim.append("증분 점검: 주기가 도래하지 않은 %d개 게시판은 방문하지 않고 캐시 기준으로 판정함" % meta["from_cache"])
    if meta.get("unvisited_no_cache"):
        lim.append("방문하지 못했고 캐시도 없는 게시판 %d개: %s" % (len(meta["unvisited_no_cache"]), ", ".join(meta["unvisited_no_cache"])))
    unparsed = [b["name"] for b in boards if b.get("fetched") and any(r in ("no_date", "region_not_found", "js_suspected") for r in b.get("reasons", []))]
    if unparsed:
        lim.append("목록·게시일을 자동 인식하지 못한 게시판(프로필 보정 또는 브라우저 확인 필요): " + ", ".join(unparsed))
    if judgement is None:
        lim.append("AI 판단 미실시")
    elif judgement.get("errors"):
        lim.append("AI 판단 실패 배치 %d건 (해당 항목은 '담당자 확인 필요'로 표기)" % len(judgement["errors"]))
    if judgement and judgement.get("over_limit_skipped"):
        lim.append("AI 판단 건수 상한 초과로 제외된 게시판 %d개" % len(judgement["over_limit_skipped"]))
    if typo and typo.get("queue") is not None and typo["queue"].get("skipped"):
        lim.append("오타 점검에서 제외된 게시글 %d건: %s" % (len(typo["queue"]["skipped"]), "; ".join(sorted(set(x["reason"] for x in typo["queue"]["skipped"])))[:300]))
    lim.append("개인정보 노출 점검은 마스킹된 텍스트 기준이며 이름·주소는 자동 마스킹되지 않음")
    L.extend("- " + x for x in lim)
    L.append("")
    L.append("## 9. 후속 조치 제안\n")
    acts = []
    if by_cat("확정 오류"):
        acts.append("확정 오류 %d건: 담당부서에 수정 요청 (중요도 높음 우선)" % len(by_cat("확정 오류")))
    if by_cat("게시 최신성 지연"):
        acts.append("게시 최신성 지연 %d건: 신규 게시 또는 폐지·아카이브 여부 확인" % len(by_cat("게시 최신성 지연")))
    if meta["findings_resolved"]:
        acts.append("해결 %d건: 확인 후 종결 처리" % meta["findings_resolved"])
    if not acts:
        acts.append("조치 필요 항목 없음")
    L.extend("- " + x for x in acts)
    resolved = findings.get("resolved", [])
    if resolved:
        L.append("\n### 이번에 해결된 항목\n")
        L.append(table(["영역", "분류", "내용", "최초 발견일"], [[f["area"], f["category"], f["detail"], f.get("first_seen")] for f in resolved]))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    runs = os.path.join(args.workspace, "runs")
    date = args.date or (sorted(os.listdir(runs))[-1] if os.path.isdir(runs) and os.listdir(runs) else "")
    if not date:
        print("[오류] runs 폴더가 비어 있습니다.", file=sys.stderr)
        return 1
    findings = ml.load_json(os.path.join(runs, date, "findings.json"))
    if findings is None:
        print("[오류] findings.json 없음", file=sys.stderr)
        return 1
    judgement = ml.load_json(os.path.join(runs, date, "judgement.json"))
    months = int(ml.load_settings(args.workspace)["stale_months"])
    typo = {"queue": ml.load_json(os.path.join(runs, date, "typo-review-queue.json")),
            "judgement": ml.load_json(os.path.join(runs, date, "typo-judgement.json"))}
    md = build(findings, judgement, date, months, typo)
    path = os.path.join(runs, date, "inspection-summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(path)
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
