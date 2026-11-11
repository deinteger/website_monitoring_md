# 홈페이지 점검 절차 (단일 원본)

모든 어댑터(Claude 스킬, pi·Codex·Antigravity용 스킬, `AGENTS.md`)는 이 문서를 가리킨다. 저장소 루트를 작업 디렉터리로 실행한다.
먼저 `core/rules.md`(안전·역할 분담)를 읽는다.

## 0. 준비 확인

1. `workspace/site-profile.json`이 있는가?
   - 없으면 **온보딩**(`core/onboarding.md`)부터 한다. 점검을 시작하지 않는다.
2. `workspace/settings.json`의 `contact`(담당 부서·연락처)와 요청 정책이 설정되어 있는가? 없으면 사용자에게 알리고 `config.example/settings.example.json`을 복사하도록 안내한다.
3. 정보보안 담당 통보·허용 목록 등록이 끝났는지 사용자에게 확인한다 (`docs/보안통보_요청서_양식.md`). 확인 전에는 **시험 점검(`--limit 20`)까지만** 한다.

## 1. 모드 결정

| 상황 | 모드 |
| --- | --- |
| 최초, 월 1회, 규칙·프로필을 크게 바꾼 뒤 | `full` |
| 일상 점검(매일·매주) | `incremental` (기본) |
| 시험 점검 | `--limit 20` (full 또는 incremental과 함께) |

사용자가 모드를 말하지 않으면 `incremental`로 하되, 요약의 `warnings`에 "전체 점검 권장"이 있으면 사용자에게 알린다.

## 2. 실행

```bash
# 요청량·예상 시간 확인 (요청하지 않음). 결과를 사용자에게 알린다
python scripts/collect.py --workspace workspace --mode incremental --dry-run
# 실행
python scripts/collect.py --workspace workspace --mode incremental
```

- 종료코드 2 = 차단 의심으로 중단. **재시도·우회하지 말고** 사용자에게 보안·운영 부서의 허용 목록 등록을 안내한다. 이후 `--resume`으로 이어서 실행할 수 있다.
- 한 게시판의 파싱이 이상하면 `--probe <board_id>`로 목록·날짜 인식 결과를 확인하고 `site-profile.json`을 보정한다.

산출물은 `workspace/runs/YYYY-MM-DD/`에 생성된다 (`core/report-fields.md`).

## 3. AI 판단

1. `run-summary.json`과 `ai-review-queue.json`**만** 읽는다. 전체 캐시·전체 게시판을 읽지 않는다 (토큰 절약).
2. 각 항목을 `core/judgement-guide.md` 기준으로 판단한다. 브라우저가 있고 `no_date`/`region_not_found`/`js_suspected` 항목이면 해당 URL을 읽기 전용으로 열어 확인한다.
3. `judgement.json`을 `core/report-fields.md`의 스키마로 `workspace/runs/YYYY-MM-DD/`에 저장한다. `quote`는 입력에 있는 구절만 쓴다.
4. 에이전트 없이 API로 돌리려면 `python scripts/judge.py --workspace workspace` (사전 조건: `llm.allowed`, 환경변수 — `docs/운영가이드.md`).

## 4. 요약 작성

```bash
python scripts/make_summary.py --workspace workspace
```

생성된 `inspection-summary.md`를 읽고 **종합 의견**(우선 조치 순서, 반복 이슈, 담당부서별 요청 사항)만 보완한다. 스크립트가 만든 수치·표는 고치지 않는다.

사용자에게는 다음을 보고한다: 모드, 방문/캐시 수, 신규·지속·해결 건수, 확정 오류 목록, 신규 지연 게시판, 경고, 점검 한계.

## 5. 월간 보고 (월말·월초)

```bash
python scripts/monthly_report.py --workspace workspace --month YYYY-MM
```

`monthly-report.md`의 `AI_COMMENT` 자리에 3~5줄 종합 의견을 쓴다. 수치는 표의 값만 인용하고 새로 계산하지 않는다. 지표 정의는 `core/monthly-report.md`.

## 하지 말 것

- 스크립트 결과의 날짜·상태를 직접 재계산하거나 뒤집기
- 요청 정책 완화, 차단 우회, 허용 도메인 밖 접속
- 점검하지 않은 항목을 "정상"으로 보고하기
- 개인정보 원문을 결과에 옮겨 적기
