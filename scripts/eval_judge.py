#!/usr/bin/env python3
"""AI 판단 정확도 평가 (표준 라이브러리만 사용).

tests/eval/judgement-cases.json(합성 정답 세트)을 judge.py 와 같은 프롬프트·검증으로 LLM에 돌려
판정 정확도와 오답을 출력한다. 모델을 바꾸거나 core/judgement-guide.md 를 고친 뒤 실행해 편차를 확인한다.

  LLM_API_KEY=... LLM_MODEL=... LLM_BASE_URL=... python scripts/eval_judge.py --min-accuracy 0.8

비용: 케이스 수만큼 호출한다(배치 없음). 외부 AI로 전송되는 것은 합성 데이터뿐이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge  # noqa: E402
import monlib as ml  # noqa: E402


def score(cases, ask):
    """ask(case) -> validate_item 결과 dict. 반환: (정확도, 오답 목록, 전체 결과)"""
    rows, wrong = [], []
    for c in cases:
        got = ask(c)
        ok = got["verdict"] == c["expected"]
        rows.append({"id": c["id"], "title": c["title"], "expected": c["expected"], "got": got["verdict"], "ok": ok, "note": got.get("note", "")})
        if not ok:
            wrong.append(rows[-1])
    return (sum(r["ok"] for r in rows) / float(len(rows)) if rows else 0.0), wrong, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=os.path.join(judge.ROOT, "tests", "eval", "judgement-cases.json"))
    ap.add_argument("--min-accuracy", type=float, default=0.8)
    args = ap.parse_args(argv)
    cfg = {"provider": os.environ.get("LLM_PROVIDER", "openai"), "base_url": os.environ.get("LLM_BASE_URL", ""),
           "api_key": os.environ.get("LLM_API_KEY", ""), "model": os.environ.get("LLM_MODEL", "")}
    if not cfg["api_key"] or not cfg["model"]:
        print("[오류] LLM_API_KEY, LLM_MODEL 환경변수가 필요합니다.", file=sys.stderr)
        return 1
    cases = json.load(open(args.cases, encoding="utf-8"))["cases"]
    system = judge.read_text(os.path.join(judge.ROOT, "core", "judgement-guide.md")) + "\n" + judge.OUTPUT_SPEC

    def ask(c):
        try:
            raw = judge.extract_json(judge.call_llm(system, judge.build_user_payload([c["item"]], c["today"]), cfg))
            r = next((x for x in raw.get("items", []) if x.get("board_id") == c["item"]["board_id"]), {})
        except Exception as e:
            return {"verdict": "호출실패", "note": str(e)}
        return judge.validate_item(r, c["item"]) if r else {"verdict": "누락", "note": ""}

    acc, wrong, rows = score(cases, ask)
    print("모델: %s/%s  정확도: %.1f%% (%d/%d)" % (cfg["provider"], cfg["model"], acc * 100, sum(r["ok"] for r in rows), len(rows)))
    for w in wrong:
        print("  [오답] %s %s: 기대 %s / 응답 %s %s" % (w["id"], w["title"], w["expected"], w["got"], w["note"]))
    return 0 if acc >= args.min_accuracy else 5


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
