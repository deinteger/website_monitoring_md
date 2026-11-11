# 전체 점검 (최초·월 1회)

1. `core/rules.md`, `core/skill-body.md`를 읽는다.
2. 시험 점검: `python scripts/collect.py --workspace workspace --mode full --limit 20` 결과를 화면과 대조한다.
3. 전체: `python scripts/collect.py --workspace workspace --mode full` (먼저 `--dry-run`으로 요청량 확인).
4. AI 판단 대상이 많으면 우선순위(확정 오류 근거·신규 지연·변경)대로 판단하고, 남은 항목은 요약의 점검 한계에 기록한다.
5. `make_summary.py` 실행 후 보고한다.
