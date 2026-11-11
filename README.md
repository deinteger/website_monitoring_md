# 홈페이지 점검·모니터링 키트

> **2026 공공 AI 대전환 챌린지 세션1 출품작.** 구동은 `python scripts/demo.py` 한 줄이면 됩니다(Python 3.8+, 외부 패키지·접속·API 키 불필요).
> - **접속 주소**: 없음(로컬 실행. 데모는 로컬에 모의 기관 사이트를 띄웁니다)
> - **주요 기능**: 게시판 최신성·링크·게시글 오타 점검, 정책정보 확인주간 체크리스트, 범정부 UI/UX 가이드라인 점검, 구글·네이버·다음 검색 포털 점검, 최근 현행화·담당자 연락처 질의
> - **실행·작동 방법**: 아래 "빠른 시작"과 `docs/대회제출/10_구동안내서_초안.md` (제출 안내: `docs/대회제출/00_제출체크리스트_세션1.md`)

공공기관 홈페이지의 **링크·접속 오류, 게시 최신성(달력 기준 3개월), 현행화 의심, 문구, 월간 현황**을 점검하는 키트입니다.
**수집·날짜 계산은 파이썬 스크립트**가, **추론이 필요한 판단은 AI**가 맡습니다. 담당자가 각자 맡은 시스템에 적용하도록 설계했습니다.

## 어떻게 동작하나

```
site-profile.json ─▶ collect.py ─▶ findings.json / recency-status.csv / inspection-details.csv
(게시판 목록·주기)   (HTTP·목록 파싱·3개월 판정·링크·변경 감지·신규/지속/해결)
                          └▶ ai-review-queue.json (신규·변경·이상 건만) ─▶ AI 판단(judgement.json)
                                                                        └▶ make_summary.py ─▶ inspection-summary.md
history/*.json ─▶ monthly_report.py ─▶ 월간 보고(신규 콘텐츠·현행화 수치, 전월 대비)
```

- 방문하지 않은 게시판도 날짜 경과 판정은 매번 다시 계산하고, AI는 **변경·이상 건만** 판단하므로 매일 돌려도 불필요한 점검과 토큰 소모가 적습니다.
- AI 판단은 원문 인용을 요구하고 검증합니다 (원문에 없는 인용은 '담당자 확인 필요'로 하향).

## 할 수 있는 일

| 기능 | 명령/설명 |
|---|---|
| 정기 점검(전체·증분) | `collect.py`, `run_all.py` — 링크·접속 오류, 3개월 최신성, 변경 감지, 신규·지속·해결 |
| AI 판단 | 현행화 의심, 문구, 연락처 형식 이상 (원문 인용 검증) |
| 게시글 본문 오타 점검(선택) | `--typo-check` — 신규 글만, 상한·1회 점검, 마스킹 후 AI 판단 |
| 월간 보고 | `monthly_report.py` — 신규 콘텐츠·현행화 수치 전월 대비 |
| 최근 현행화 조회 | `recent_changes.py --days 2` — "어제 그제 올라온 게시물" (오프라인) |
| 현황·담당자 연락처 조회 | `lookup.py status|overview|contact|find` — 사이트에 들어가지 않고 질의 |
| 검색엔진 인덱스 점검 | `check_index_links.py` — 구글·네이버·다음 `site:` 결과의 깨진 링크·소프트 404 |
| JS 게시판 보완(선택) | Playwright 선택 모듈, 에이전트 브라우저, 서버 렌더링 주소 |
| 점검 범위 선택 | `run_checks.py --list/--checks/--interactive` — 전체·게시판·오타·정책정보 확인주간·UI/UX·검색 포털 |
| 정책정보 확인주간 점검 | `policy_check.py` — 체크리스트 22개 항목: 자동·증거 수집·사람 응답 구분, 응답 기록 |
| 범정부 UI/UX 가이드라인 점검 | 원문 쪽 근거 규칙 24개(공식 배너·식별자·헤더·푸터·건너뛰기 링크), 개정판은 git으로 갱신(`guidelines.py`) |
| 주기 실행 | `make_schedule.py` — Windows/cron 등록 명령 생성 |

## 사용 환경

| 환경 | 가능 범위 |
| --- | --- |
| Claude Code | 전체 (`CLAUDE.md` → `AGENTS.md`, `.claude/skills/`) |
| pi 에이전트 / Orca | 전체 (`AGENTS.md`, `.agents/skills/`) — `docs/pi-orca.md` |
| VS Code Cline | 전체 (`.clinerules/`, 스킬은 `.claude/skills/` 인식) — `docs/cline-vscode.md` |
| Codex, Antigravity | 전체 (`AGENTS.md`, `.agents/`) |
| 스크립트 + 개인 API 키 | 수집·요약·AI 판단·월간 보고, 스케줄 무인 실행 — `docs/운영가이드.md` |
| Claude 채팅(claude.ai) | 조건부 — 스킬 zip 업로드(`make_claude_skill.py`), 코드 실행 켜기, 대상 도메인 허용 필요, 상태는 zip으로 주고받음 — `docs/claude-chat.md` |
| GPT 채팅·기타 일반 채팅 | 파일 실행 불가. 스크립트 결과(`ai-review-queue.json` 등)를 업로드해 판단·보고서 작성만 가능 |

## 빠른 시작

```bash
python scripts/demo.py        # 모의 사이트로 전체 점검 시연 (접속·키 불필요)
```

실제 사이트에 적용할 때:

```bash
# 1) 설정: config.example/settings.example.json 을 workspace/settings.json 으로 복사하고 contact 입력
# 2) 정보보안 담당 통보 (docs/보안통보_요청서_양식.md) — 요청량은 dry-run 으로 산출
# 3) 프로필 초안 생성 후 검수 (core/onboarding.md, 에이전트에 맡겨도 됨)
python scripts/discover.py --workspace workspace --base-url https://대상주소/ --site-name "시스템명"
python scripts/collect.py --workspace workspace --probe <board_id>      # 게시판별 목록 인식 확인
# 4) 시험 점검 → 전체 점검 → 일상(증분) 점검
python scripts/collect.py --workspace workspace --mode full --limit 20
python scripts/collect.py --workspace workspace --mode full --dry-run
python scripts/collect.py --workspace workspace --mode incremental
# 5) 요약, 월간 보고
python scripts/make_summary.py --workspace workspace
python scripts/monthly_report.py --workspace workspace --month 2026-09
```

에이전트로 쓸 때는 "homepage-inspection 스킬로 증분 점검하라"처럼 요청하면 됩니다.

## 결과

`workspace/runs/YYYY-MM-DD/`: `inspection-summary.md`, `inspection-details.csv`, `recency-status.csv`, `findings.json`, `ai-review-queue.json`, `judgement.json`, `run-summary.json`
`workspace/reports/YYYY-MM/`: `monthly-report.md`, `monthly-metrics.json`, `monthly-boards.csv`
검색엔진 인덱스 점검(구글·네이버·다음 `site:`)은 `search-index-links.csv`로 별도 출력됩니다. 필드 정의는 `core/report-fields.md`, 월간 지표 정의는 `core/monthly-report.md` 입니다.

## 보안·운영 주의

- **읽기 전용**(GET/HEAD)이며 로그인·입력·업로드를 하지 않습니다. 허용 도메인 밖은 접속하지 않습니다.
- 기본 요청 정책은 보수적입니다(동시 2, 간격 1초). **실행 전 보안·운영 부서에 통보**하고, 차단되면 우회하지 말고 허용 목록 등록을 요청하세요. 403/429가 연속되면 자동 중단합니다.
- 외부 AI로 점검 내용을 보내려면 기관 보안 승인 후 `llm.allowed`를 켜야 합니다. 전송 전 주민번호·전화·이메일은 마스킹됩니다(이름·주소는 마스킹되지 않음).
- `workspace/`(프로필·캐시·결과)는 커밋·배포하지 않습니다.

## 한계 (알고 쓰세요)

- 스크립트는 기본적으로 자바스크립트로 그려지는 목록을 읽지 못합니다 → `js_suspected`로 표시되며 (A) 에이전트 브라우저 확인, (B) 서버 렌더링 주소 사용, (C) Playwright 선택 모듈 중 고를 수 있습니다 (`docs/운영가이드.md` 9절).
- 게시일은 목록의 첫 날짜를 기본으로 인식합니다. 사이트마다 `--probe`로 검증하고 프로필을 보정해야 합니다.
- 월별 신규 콘텐츠 건수는 수집한 목록 범위 내 집계입니다(부분 집계는 표시됨).
- AI 판단은 모델마다 편차가 있습니다. 모델을 바꾸면 `scripts/eval_judge.py`로 비교하세요.
- timelygpt API의 호환 여부와 pi의 스킬 인식 경로는 설치 버전·제공 사양에 따라 **확인이 필요**합니다.

## 폴더

| 경로 | 내용 |
| --- | --- |
| `core/` | 공통 규칙·판단 기준·절차 (단일 원본) |
| `scripts/` | 표준 라이브러리 전용 파이썬 |
| `guidelines/` | 정책정보 확인 체크리스트·UI/UX 가이드라인 규칙팩(데이터). 개정 절차 `core/guideline-update.md` |
| `config.example/` | 프로필·설정 예시 |
| `.agents/`, `.claude/`, `.clinerules/` | 에이전트별 얇은 어댑터(스킬·워크플로·규칙 요약) |
| `docs/` | 운영 가이드, 보안 통보 양식, pi·Orca 사용법 |
| `tests/` | 테스트와 AI 판단 평가 세트 |
| `workspace/` | 담당자별 데이터 (커밋 대상 아님). `workspace/legacy/`는 이전 점검 원본(내부용) |

## 개발·배포

```bash
python -m unittest discover -s tests          # 테스트 (로컬 가짜 사이트 사용, 외부 요청 없음)
python scripts/make_claude_skill.py           # claude.ai 채팅용 스킬 zip
python scripts/make_release.py                # 배포 zip (허용 목록 방식, 실제 기관 도메인 혼입 검사)
```

버전: `VERSION` 참고. 규칙·판단 기준 개선은 `core/`만 고치면 모든 어댑터에 반영됩니다.
