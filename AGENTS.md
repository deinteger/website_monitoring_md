# 홈페이지 점검 키트 — 에이전트 지침

공공기관 홈페이지 모니터링·현행화 점검 키트다. 스크립트(수집·날짜 계산)와 AI(추론 판단)가 역할을 나눈다.
pi(Orca 포함), Codex, Antigravity 등 `AGENTS.md`를 읽는 에이전트가 사용한다. Claude Code는 `CLAUDE.md`를 통해 이 파일을 읽는다.

## 작업 시작 전 반드시

1. `core/rules.md` 를 읽고 따른다 (읽기 전용, 차단 시 중단, 외부 전송 승인, 개인정보 마스킹).
2. 점검·월간 보고·온보딩 요청이면 `core/skill-body.md` 의 절차를 따른다. 스킬(`homepage-inspection`)이 인식되면 그것을 사용해도 같다.
3. 판단 단계에서는 `core/judgement-guide.md` 기준을 쓴다.

## 폴더

| 경로 | 내용 |
| --- | --- |
| `core/` | 공통 규칙·판단 기준·절차 (수정 시 전원에게 배포되는 원본) |
| `scripts/` | 표준 라이브러리 전용 파이썬 (`collect.py`, `discover.py`, `judge.py`, `make_summary.py`, `monthly_report.py`, `run_all.py`, `make_release.py`) |
| `config.example/` | 프로필·설정 예시 → 담당자가 `workspace/`로 복사해 수정 |
| `workspace/` | **담당자별 데이터**(프로필, 설정, 캐시, 이력, 결과). 배포·커밋 대상 아님 |
| `docs/` | 운영 가이드, 보안 통보 양식, pi·Orca 사용법 |
| `tests/` | 단위·통합 테스트 (`python -m unittest discover -s tests`) |

## 핵심 명령

```bash
python scripts/collect.py --workspace workspace --mode incremental --dry-run
python scripts/collect.py --workspace workspace --mode incremental     # 일상
python scripts/collect.py --workspace workspace --mode full            # 최초·월 1회
python scripts/collect.py --workspace workspace --probe <board_id>     # 목록 인식 확인
python scripts/make_summary.py --workspace workspace
python scripts/monthly_report.py --workspace workspace --month YYYY-MM
```

## 지켜야 할 것

- 스크립트가 낸 날짜·상태·지연 판정을 다시 계산하거나 뒤집지 않는다. AI는 `ai-review-queue.json` 항목만 판단한다.
- 차단 의심(종료코드 2)이면 재시도·우회 없이 중단하고 사용자에게 보안·운영 부서 협의를 안내한다.
- 점검하지 않은 항목은 "정상"이 아니라 미점검으로 보고한다.
- `workspace/`의 내용을 커밋하거나 외부에 전송하지 않는다.
