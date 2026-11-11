#!/usr/bin/env python3
"""일괄 실행: collect → (선택) judge → make_summary. 스케줄러(cron, 작업 스케줄러)에 등록하는 용도.

  python scripts/run_all.py --workspace workspace --mode incremental --judge auto

--judge auto : settings.json 의 llm.allowed 가 true 이고 LLM_API_KEY 가 있을 때만 AI 판단 실행
--judge yes  : 항상 실행 시도 / --judge no : 건너뜀(수집 결과만 요약)
종료코드: 0 정상, 2 차단 의심 중단(부분 결과), 1/3/4 설정·AI 오류
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect  # noqa: E402
import judge  # noqa: E402
import make_summary  # noqa: E402
import monlib as ml  # noqa: E402
import recent_changes  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    ap.add_argument("--sample-rate", default="0")
    ap.add_argument("--judge", choices=["auto", "yes", "no"], default="auto")
    ap.add_argument("--today", default="")
    ap.add_argument("--typo-check", action="store_true", help="신규 게시글 본문 오타 점검 포함")
    args = ap.parse_args(argv)
    cargs = ["--workspace", args.workspace, "--mode", args.mode, "--sample-rate", args.sample_rate]
    if args.today:
        cargs += ["--today", args.today]
    if args.typo_check:
        cargs += ["--typo-check"]
    code = collect.main(cargs)
    if code in (1,):
        return code
    settings = ml.load_settings(args.workspace)
    run_judge = args.judge == "yes" or (args.judge == "auto" and settings.get("llm", {}).get("allowed") and os.environ.get("LLM_API_KEY"))
    jcode = 0
    if run_judge:
        jcode = judge.main(["--workspace", args.workspace])
        if args.typo_check or settings.get("typo_check", {}).get("enabled"):
            jcode = jcode or judge.main(["--workspace", args.workspace, "--task", "typo"])
    else:
        print("[안내] AI 판단 건너뜀 (--judge auto: llm.allowed 또는 LLM_API_KEY 없음). 에이전트로 판단하거나 설정 후 judge.py 실행")
    make_summary.main(["--workspace", args.workspace])
    # 채팅형 AI에 올려 "어제 그제 뭐 올라왔어?"에 답할 수 있는 최근 14일 요약 갱신 (오프라인 계산)
    recent_changes.main(["--workspace", args.workspace, "--latest", "--quiet"] + (["--today", args.today] if args.today else []))
    return code or jcode


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main())
