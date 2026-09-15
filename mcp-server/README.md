# MCP 서버 설치 (webcheck-mcp)

이 프로젝트에서 쓰는 MCP 서버(링크 상태 확인, 게시일 판정, 캐시 갱신)는
범용 도구로 일반화되어 별도 저장소로 분리되었습니다.

- 코드 저장소: https://github.com/deinteger/webcheck-mcp
- 다른 기관/업무에서도 그대로 재사용할 수 있습니다. 이 폴더는 그 패키지를
  이 프로젝트의 로컬 가상환경에 설치해두는 위치일 뿐, 도구 코드 자체는
  여기에 없습니다.

## 설치

```bash
cd mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

설치가 끝나면 `.venv/bin/webcheck-mcp` 실행 파일이 생기고, 저장소 루트의
`.mcp.json`이 이를 참조합니다.

## 제공 도구

- `check_links` : URL 목록의 접속 가능 여부 확인 (본문 에러 문구 검사 포함)
- `check_recency` : `references/page-cache.md`의 `추출셀렉터`로 최신 게시일을
  뽑아 최신성 판정
- `update_page_cache` : 점검 결과를 `references/page-cache.md`에 반영

각 도구의 파라미터와 반환값 상세는
[webcheck-mcp README](https://github.com/deinteger/webcheck-mcp#제공-도구)를
참고합니다.

## 판정 값 매핑 (webcheck-mcp → 이 프로젝트의 분류)

`webcheck-mcp`는 범용 도구라 판정 명칭이 짧습니다. 보고서
(`output/*/inspection-summary.md`, `*.csv`)를 작성할 때는 아래처럼
`.agents/rules/inspection-rules.md`의 6개 분류로 치환해서 기록합니다.

| webcheck-mcp `판정` | 이 프로젝트의 분류 |
| --- | --- |
| `정상` | 정상 |
| `최신성 지연` | 게시 최신성 지연 |
| `날짜 확인 불가` | 게시일 확인 불가 |
| `수동확인필요(선택자없음)` / `수동확인필요(선택자로날짜못찾음)` | 브라우저로 직접 확인 후 담당자 확인 필요 또는 확정 오류로 재분류 |
| `접속오류` | 확정 오류 (재확인 원칙에 따라 최소 2회 재시도 후 확정) |

## 동작 확인 (2026-09-15, 실제 사이트 대상 테스트)

- `check_links`: 존재하지 않는 경로(`/no-such-page-xyz-404`)가 HTTP 200으로
  응답하는 것을 확인했고, 본문 에러 문구 검사로 정상 탐지됨.
- `check_recency`: `table.BoardTable tbody tr:first-child td:nth-child(5)`
  셀렉터로 공지사항 최신 게시일 `2026-09-15`를 정확히 추출.
- `update_page_cache`: 대상 행 1건만 갱신되고 나머지 행은 그대로 유지됨을 확인.
