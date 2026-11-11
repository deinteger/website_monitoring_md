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

## 6. 검색엔진 인덱스 점검 (선택)

구글·네이버·다음의 `site:도메인` 결과에 남은 깨진 링크·소프트 404·깨진 이미지를 점검한다. 절차: `.agents/workflows/search-index-inspection.md`
(URL 수집은 브라우저, 점검은 `scripts/check_index_links.py`). 검색엔진 결과를 스크립트로 직접 긁지 않는다.

## 7. 질문에 답하기 (현황·최근 변경·담당자 연락처)

사용자가 사이트에 일일이 들어가지 않고 물을 때 아래 명령으로 답한다. 기간 표현("어제", "그제", "지난주")은 오늘 날짜 기준으로 `--days`/`--from`/`--to`에 옮길 때만 계산하고, 판정·상태는 계산하지 않는다.

| 사용자 질문 | 명령 | 네트워크 |
| --- | --- | --- |
| "어제 그제 현행화된 게시물이 뭐야?" | `python scripts/recent_changes.py --workspace workspace --days 2` ("어제·그제" = 오늘 제외 2일) | 없음 |
| "최근 일주일에 새로 올라온 거" | `... --days 7 --include-today` | 없음 |
| "점검해서 어제 그제 올라온 거 알려줘" | `... --days 2 --refresh` (증분 점검 후 조회) | 사용 |
| "우리가 처음 확인한 신규 글만" | `... --by seen` | 없음 |
| "보도자료 현황 알려줘" | `python scripts/lookup.py --workspace workspace status 보도자료` | 없음 |
| "전체 홈페이지 현황" | `python scripts/lookup.py --workspace workspace overview` | 없음 |
| "보도자료 담당자 연락처" | `python scripts/lookup.py --workspace workspace contact 보도자료` (특정 글은 `--latest-post` 또는 `--url`) | 해당 페이지 GET 1회 |
| "OO 게시판이 어디 있지?" | `python scripts/lookup.py --workspace workspace find OO` | 없음 |

- 결과의 `주의`(마지막 점검일 이후 미반영, 방문하지 않은 게시판 등)를 **그대로 사용자에게 전달**한다. 데이터가 오래됐으면 `--refresh` 또는 점검을 권한다.
- 질의 명령은 `workspace/cache.json`과 `history/`만 읽으므로 `state.zip`만 있으면 채팅형 환경에서도 사이트 접속 없이 동작한다.
- 후보가 여럿이면(종료코드 3) 추측하지 말고 후보를 사용자에게 보여 주고 고르게 한다.
- 연락처는 **해당 페이지에 공개된 표기만** 전달한다. 근거 원문과 위치(본문/푸터=기관 공통)를 함께 보여 주고, 찾지 못하면 찾지 못했다고 말한다 (추정·생성 금지). 연락처는 저장하거나 다른 곳에 옮기지 않는다.
- 주기 실행 등록은 `python scripts/make_schedule.py --os windows|linux ...`가 명령을 만들어 준다 (출력만 하며 직접 등록하지 않는다).

## 8. 게시글 본문 오타 점검 (선택)

신규 게시글의 본문에서 맞춤법·띄어쓰기·오탈자를 찾는다. 기본은 꺼져 있으며 `--typo-check` 또는 `settings.json`의 `typo_check.enabled`로 켠다.

1. 수집: `python scripts/collect.py --workspace workspace --typo-check` → `typo-review-queue.json` (게시판당 최신 N건, 실행당 상한, 한 번 점검한 글은 재요청 없음, 개인정보 마스킹)
2. 판단: `core/typo-guide.md` 기준으로 판단해 `typo-judgement.json` 작성 (또는 `python scripts/judge.py --workspace workspace --task typo`). `quote`는 본문에 있는 구절만, 고유명사·전문용어는 오류로 보고하지 않는다.
3. 요약: `make_summary.py`가 6절에 오타 표를 넣는다. 본문을 못 찾은 게시판은 프로필에 `body_region`을 지정한다 (`--probe <id> --probe-post`로 미리 확인).

## 9. 점검 범위 선택 (전체 / 게시판 / 오타 / 정책정보 확인주간 / UI/UX / 검색 포털)

사용자가 점검 범위를 말하지 않았으면 **먼저 선택지를 물어본다** (여러 개 선택 가능). 선택 후 `scripts/run_checks.py`로 실행한다.

| 선택 | 내용 | 명령 |
| --- | --- | --- |
| 전체 | 게시판 + 정책정보 확인주간 + UI/UX + 검색 포털 | `python scripts/run_checks.py --workspace workspace --checks all` |
| 게시판 | 접속·링크 오류, 3개월 최신성, 변경 감지 | `--checks board` (모드: `--mode incremental|full`) |
| 오타 | 신규 게시글 본문 맞춤법·오탈자 (AI 판단) | `--checks typo` (게시판 점검과 함께 수집) |
| 정책정보 확인주간 | 체크리스트 22개 항목: 자동 확인·증거 수집, 사람 응답 문항 분리 | `--checks policy` |
| UI/UX | 범정부 UI/UX 가이드라인(공식 배너·식별자·헤더·푸터·건너뛰기 링크) | `--checks uiux` |
| 검색 포털 | 구글·네이버·다음 `site:` 결과의 깨진 링크·소프트404·불법 광고 의심 | `--checks portal` |

- 목록과 비용은 `--list`, 요청량은 `--dry-run`으로 먼저 확인한다 (보안 통보에 쓴다). 터미널 사용자는 `--interactive`로 번호를 고를 수 있다.
- **검색 포털**: 스크립트는 검색 계획(`workspace/index/plan.md`)만 만든다(종료코드 4). 에이전트 브라우저로 `site:도메인 [키워드]`를 검색해 결과를 `workspace/index/<엔진>.txt`(`URL<탭>제목<탭>키워드`)에 저장한 뒤 같은 명령을 다시 실행하면 점검한다. 검색엔진을 스크립트로 직접 긁지 않고, 캡차·차단 시 중단한다.
- **정책정보 확인주간·UI/UX 결과 해석**: 판정 방식이 `auto`인 항목만 자동 판정이고, `assist`는 증거 수집(충족이라고 단정하지 않음), `attest`는 **사람이 네/아니오로 응답**한다. 응답 기록: `python scripts/policy_check.py answer PW-03 --yes --note "..."`, 현황: `policy_check.py status`. 사람 응답을 대신 작성하지 않는다.
- 규칙이 `검수 전(draft)`이거나 규칙팩이 `reviewed=false`이면 결과는 참고용이라고 사용자에게 알린다.
- 가이드라인 개정 반영: `core/guideline-update.md` (규칙 데이터는 `guidelines/`, 근거 인용 검증 포함).

## 하지 말 것

- 스크립트 결과의 날짜·상태를 직접 재계산하거나 뒤집기
- 요청 정책 완화, 차단 우회, 허용 도메인 밖 접속
- 점검하지 않은 항목을 "정상"으로 보고하기
- 개인정보 원문을 결과에 옮겨 적기
