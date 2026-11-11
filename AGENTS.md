# 홈페이지 점검 키트 — 에이전트 지침

공공기관 홈페이지 모니터링·현행화 점검 키트다. 스크립트(수집·날짜 계산)와 AI(추론 판단)가 역할을 나눈다.
pi(Orca 포함), Codex, Antigravity, Cline 등 `AGENTS.md`를 읽는 에이전트가 사용한다. Claude Code는 `CLAUDE.md`를 통해 이 파일을 읽는다.

## 작업 시작 전 반드시

1. `core/rules.md` 를 읽고 따른다 (읽기 전용, 차단 시 중단, 외부 전송 승인, 개인정보 마스킹).
2. 점검(범위 선택 포함)·월간 보고·온보딩·질의(최근 게시물, 현황, 담당자 연락처) 요청이면 `core/skill-body.md` 의 절차를 따른다. 스킬(`homepage-inspection`)이 인식되면 그것을 사용해도 같다.
3. 판단 단계에서는 `core/judgement-guide.md` 기준을 쓴다.

## 폴더

| 경로 | 내용 |
| --- | --- |
| `core/` | 공통 규칙·판단 기준·절차 (수정 시 전원에게 배포되는 원본) |
| `scripts/` | 표준 라이브러리 전용 파이썬 (`collect.py`, `discover.py`, `judge.py`, `make_summary.py`, `monthly_report.py`, `run_all.py`, `check_index_links.py`, `render.py`(선택), `chat_state.py`, `demo.py`(접속·키 없이 구동하는 데모), `make_release.py`, `make_claude_skill.py`) |
| `guidelines/` | 정책정보 확인 체크리스트·UI/UX 가이드라인 규칙팩(데이터, 매년 개정 시 git으로 갱신). 절차: `core/guideline-update.md` |
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
python scripts/recent_changes.py --workspace workspace --days 2        # 어제·그제 현행화된 게시물 (오프라인)
python scripts/lookup.py --workspace workspace status|overview|find|contact <이름>   # 현황·담당자 연락처
python scripts/collect.py --workspace workspace --typo-check           # 신규 게시글 본문 오타 점검 대상 수집
python scripts/run_checks.py --workspace workspace --list              # 점검 범위 선택지 (전체/게시판/오타/정책정보/UIUX/포털)
python scripts/run_checks.py --workspace workspace --checks policy,uiux
python scripts/uiux_review.py plan --workspace workspace --sample 15   # UI/UX 화면 AI 검토 대기열(일부 페이지, --pages 로 지정)
python scripts/uiux_review.py merge --workspace workspace              # AI 검토 결과 병합(원문 인용 검증)
python scripts/policy_check.py ai-merge --workspace workspace          # 소스 기준 미충족에 대한 AI 화면 확인 병합
python scripts/guidelines.py validate|diff|use|review-queue|review-apply   # 가이드라인 규칙팩 관리(개정 반영, AI 규칙 검수)
```

## 지켜야 할 것

- 스크립트가 낸 날짜·상태·지연 판정을 다시 계산하거나 뒤집지 않는다. AI는 `ai-review-queue.json` 항목만 판단한다.
- 차단 의심(종료코드 2)이면 재시도·우회 없이 중단하고 사용자에게 보안·운영 부서 협의를 안내한다.
- 점검 범위를 말하지 않은 점검 요청에는 먼저 범위를 묻는다. 정책정보 확인 체크리스트의 네/아니오 응답은 사람이 하며 대신 작성하지 않는다.
- 점검하지 않은 항목은 "정상"이 아니라 미점검으로 보고한다.
- `workspace/`의 내용을 커밋하거나 외부에 전송하지 않는다.
