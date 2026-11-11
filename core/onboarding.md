# 사이트 온보딩 (프로필 작성)

신규 시스템을 점검 대상으로 등록하는 절차. **AI는 최초 1회 사이트 구조를 파악하고, 이후 일상 점검은 스크립트가 프로필로 수행한다.**
사이트 구조(게시판 위치, 날짜 표기, 목록 영역)가 시스템마다 달라 확산의 가장 큰 장벽이므로, 이 단계를 정확히 하는 것이 중요하다.

## 0. 채팅으로 설정하기 (소스·JSON 직접 수정 불필요)

사용자가 "우리 기관 사이트 점검 대상으로 추가해줘", "담당자 연락처 바꿔줘", "AI 연결 설정해줘"처럼 말하면 에이전트는 **`scripts/setup.py`로 설정을 바꾼다.** 필요한 값(사이트 이름·주소·담당 부서·주기·AI 종류·모델명)이 빠졌으면 먼저 묻는다.

```bash
python scripts/setup.py init --site-name "OO 홈페이지" --base-url https://대상주소/ --contact "부서 이름(연락처)"
python scripts/setup.py board add --id notice --name 공지사항 --url https://대상주소/board/notice.do --owner 총무과 --cycle daily
python scripts/setup.py board add --id biz --name 공지 --system "다른시스템" --url https://다른주소/n   # 한 프로필에 여러 시스템·도메인 가능
python scripts/setup.py board set notice cycle=weekly owner=기획과     # 수정 (exclude=true, irregular=true 등)
python scripts/setup.py board remove notice
python scripts/setup.py set stale_months 2                              # 일반 설정 (잘못된 키·값은 거부)
python scripts/setup.py llm --provider anthropic --model <모델명> --allow yes   # 외부 AI 전송 허용은 기관 보안 승인 후에만
python scripts/setup.py show                                            # 현재 설정·대상 표로 확인
```

- 저장 전 검증하며 오류면 파일을 바꾸지 않는다. 대상 도메인은 `allowed_domains`에 자동 반영된다.
- **API 키는 파일에 저장하지 않는다.** 사용자가 터미널에서 `LLM_API_KEY` 환경변수로 지정하도록 안내하고, 채팅에 키를 붙여 넣지 않게 한다.
- `llm --allow yes`는 사용자가 명시적으로 요청·확인한 경우에만 실행한다(`core/rules.md`의 외부 전송 승인 규칙).
- 게시판 자동 발견은 아래 2절의 `discover.py` 후 `python scripts/setup.py board import-draft`로 프로필에 합친다.

## 1. 사전 준비

1. `workspace/` 폴더에 `settings.json`을 만든다 (`config.example/settings.example.json` 복사). `contact`에 담당 부서·연락처를 입력한다.
2. 정보보안 담당·운영 부서에 통보하고 필요 시 허용 목록 등록을 요청한다 (`docs/보안통보_요청서_양식.md`).

## 2. 초안 생성

```bash
python scripts/discover.py --workspace workspace --base-url https://대상주소/ --site-name "시스템명"
```

`workspace/site-profile.draft.json`이 생성된다. 게시판 후보(`type: board`)와 정적 페이지(`type: static`)가 구분되고,
목록 영역(`region`)·행 태그(`row_tag`)·점검 주기가 추정된다. **추정값은 틀릴 수 있다.**

## 3. 검수·보정 (AI + 사람)

초안을 열어 항목별로 확인·수정한다.

1. **불필요 항목 삭제**: 로그인·관리자·검색 결과·동일 게시판의 중복 URL
2. **이름**: 메뉴명과 일치하게 수정 (`name`)
3. **담당부서**: `owner` 입력 (월간 보고의 부서별 현황에 사용)
4. **주기**: 게시가 잦은 곳 `daily`, 보통 `weekly`, 정적·드문 곳 `monthly`/`quarterly`
5. **예외 지정**
   - 비정기 게시 영역 → `"irregular": true` (3개월 경과 시 오류가 아니라 '담당자 확인 필요')
   - 연례 간행물·아카이브 → `"recency_exempt": true`
   - 점검 제외 → `"exclude": true, "exclude_reason": "..."`
6. **목록 인식 확인**: 게시판마다 아래를 실행해 결과를 본다.

   ```bash
   python scripts/collect.py --workspace workspace --probe <board_id>
   ```

   - `latest_date`가 화면의 최신 글 게시일과 같은지
   - `titles`에 실제 글 제목이 나오는지
   - `region_found`가 `false`이면 `region`(`{"tag":"table","class":"..."}` 또는 `{"tag":"div","id":"..."}`)을 보정
   - 날짜가 다른 열(예: 행사일)을 잡으면 `date_regex`(연·월·일 3그룹 정규식) 또는 `"date_source": "any"` 사용
   - 목록 항목이 `tr`/`li`가 아니면 `row_tag`/`row_class` 지정
   - 게시판이 JS로 그려져 소스에 글이 없으면(`js_suspected`) 스크립트가 못 읽는다. 선택: (A) 그대로 두어 에이전트 브라우저로 확인(기본), (B) 같은 목록을 HTML로 주는 서버 렌더링 URL을 찾아 `url`에 입력, (C) 해당 게시판에 `"render": "playwright"` 지정(별도 설치 필요). 자세한 비교는 `docs/운영가이드.md` 9절.
   - 월별 신규 콘텐츠 집계가 필요한 게시판은 최근 글이 첫 쪽에 충분히 담기는지 확인하고, 부족하면 `pages`와 `page_url_template`(`{page}` 포함)를 지정한다.
7. 저장: 검수한 파일을 `workspace/site-profile.json`으로 저장한다 (`draft`는 삭제).

## 4. 시험 점검

```bash
python scripts/collect.py --workspace workspace --mode full --limit 20 --dry-run
python scripts/collect.py --workspace workspace --mode full --limit 20
```

결과의 `recency-status.csv`를 화면과 대조해 5~10개 게시판의 최신 게시일이 맞는지 확인한 뒤 전체 점검으로 넘어간다.
