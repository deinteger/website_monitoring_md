# nihhs-inspector MCP 서버

홈페이지 점검 중 순수 계산으로 처리 가능한 작업(링크 상태 확인, 게시일 추출·판정,
캐시 파일 갱신)을 코드로 수행하는 MCP 서버. 에이전트가 페이지 본문을 직접 읽고
판단하는 대신 이 서버의 도구를 호출해 토큰 사용을 줄인다.

특정 도메인에 종속되지 않은 범용 도구이며, `references/page-cache.md` 같은
파이프 테이블 형식의 파일이라면 어디에든 사용할 수 있다.

## 설치

```bash
cd mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 제공 도구

### `check_links(urls, timeout=10, max_workers=10, error_indicators=None)`

URL 목록의 접속 가능 여부를 병렬로 확인한다.

주의: 일부 공공기관 CMS(이 프로젝트의 대표 홈페이지 포함)는 존재하지 않는
경로에도 **HTTP 200**을 반환하고 본문에 커스텀 에러 이미지만 표시한다.
그래서 상태코드만으로는 부족하고, 본문에서 알려진 에러 문구를 함께 검사한다.
기본 문구 목록(`DEFAULT_ERROR_INDICATORS`)에 없는 사이트별 문구는
`error_indicators`로 추가한다.

```
반환: [{url, status_code, ok, error}]
```

### `check_recency(cache_file, timeout=15)`

`page-cache.md` 형식의 파일을 읽어 `추출셀렉터` 컬럼이 채워진 행만 실제로
접속해서 최신 게시일을 뽑고, 달력 기준 3개월 규칙으로 판정한다.

- `추출셀렉터`는 CSS 선택자 문법을 쓴다. 브라우저에서
  `document.querySelector(선택자)`로 검증한 값을 그대로 넣으면 된다.
- 셀렉터가 비어 있으면 실제 접속을 시도하지 않고 `수동확인필요(선택자없음)`을
  반환한다 — 이 경우 에이전트가 브라우저로 한 번 열어 셀렉터를 찾아
  `update_page_cache`로 기록해야 한다.
- 목록이 JS로 렌더링되어 정적 HTML에 날짜가 없는 경우도 마찬가지로
  `수동확인필요`로 반환되므로, 그런 게시판은 여전히 에이전트가 브라우저로
  점검한다.

```
반환: [{콘텐츠영역, URL, 최신게시일, 판정, 경과일, 비고}]
```

### `update_page_cache(cache_file, updates)`

점검 결과를 캐시 파일에 반영한다. `updates`는 `URL`을 반드시 포함해야 하며,
그 외 필드(`최신게시일`, `마지막점검일`, `판정`, `추출셀렉터`, `비고` 등)는
테이블 헤더에 있는 컬럼만 갱신된다.

```
반환: {applied: [...], not_found: [...]}
```

## 동작 확인 (2026-09-15, 실제 사이트 대상 테스트)

- `check_links`: 존재하지 않는 경로(`/no-such-page-xyz-404`)가 HTTP 200으로
  응답하는 것을 확인했고, 본문 에러 문구 검사로 정상 탐지됨.
- `check_recency`: `table.BoardTable tbody tr:first-child td:nth-child(5)`
  셀렉터로 공지사항 최신 게시일 `2026-09-15`를 정확히 추출.
- `update_page_cache`: 대상 행 1건만 갱신되고 나머지 행은 그대로 유지됨을 확인.

## Claude Code에 등록

저장소 루트의 `.mcp.json`에 이미 등록되어 있다. Claude Code가 이 프로젝트를
열면 자동으로 인식한다 (최초 1회 신뢰 여부를 물어볼 수 있다).

수동으로 다른 프로젝트에 등록하려면:

```bash
claude mcp add nihhs-inspector -- /absolute/path/to/mcp-server/.venv/bin/python3 /absolute/path/to/mcp-server/server.py
```

## Antigravity 등 다른 MCP 클라이언트에 등록

Antigravity가 MCP 서버 등록을 지원한다면, 필요한 것은 실행 커맨드뿐이다.

- command: `<repo>/mcp-server/.venv/bin/python3`
- args: `["<repo>/mcp-server/server.py"]`

이 두 값을 Antigravity의 MCP 설정에 그대로 등록하면 된다. 정확한 설정 파일
위치/형식은 Antigravity 버전마다 다를 수 있으니, Antigravity의 MCP 서버 추가
메뉴 또는 문서에서 "command/args로 로컬 서버 등록" 항목을 확인한다.

## 설계 원칙

- 이 서버는 **판단**이 아니라 **계산**만 한다 (HTTP 상태, 날짜 파싱, 3개월 비교,
  파일 텍스트 치환). 문구 개선, 현행화 의심 여부처럼 맥락 판단이 필요한 항목은
  여전히 에이전트가 직접 점검한다.
- `references/` 아래의 md 파일들은 계속 정책·상태 저장소 역할을 한다. 이 서버는
  그 파일들을 읽고 쓸 뿐, 별도의 설정 형식을 새로 만들지 않는다.
