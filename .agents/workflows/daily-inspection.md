# 일상 점검 (증분)

1. `core/rules.md`, `core/skill-body.md`를 읽는다.
2. `python scripts/collect.py --workspace workspace --mode incremental --dry-run`으로 요청량을 확인해 사용자에게 알린다.
3. `python scripts/collect.py --workspace workspace --mode incremental`을 실행한다. 종료코드 2면 중단하고 보안·운영 부서 협의를 안내한다.
4. `ai-review-queue.json` 항목만 `core/judgement-guide.md` 기준으로 판단해 `judgement.json`을 저장한다.
5. `python scripts/make_summary.py --workspace workspace` 후 종합 의견을 보완하고 사용자에게 보고한다.
