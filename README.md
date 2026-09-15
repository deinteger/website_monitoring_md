# 홈페이지 점검·모니터링 작업공간

이 폴더는 Antigravity/Claude Code 에이전트가 홈페이지를 직접 탐색하고 점검하도록 구성한 작업공간입니다.
문구 검토, 현행화 의심 판단처럼 맥락 판단이 필요한 항목은 에이전트가 직접 점검하고,
링크 상태 확인·게시일 판정처럼 기계적으로 계산 가능한 항목은 `mcp-server/`의 MCP 서버가 처리하여
토큰 사용량을 줄입니다.

## 시작 방법

1. `mcp-server/README.md`를 따라 MCP 서버를 설치합니다 (선택 사항이지만 권장).
2. Antigravity 또는 Claude Code에서 이 폴더를 작업공간으로 엽니다.
3. `.agents/rules`, `.agents/skills`, `.agents/workflows`가 인식되는지 확인합니다. (Claude Code는 `.mcp.json`으로 MCP 서버도 함께 인식합니다.)
4. `references/inspection-targets.md`에 점검 대상 URL과 범위를 입력합니다.
5. 처음에는 최대 20페이지만 시험 점검합니다.
6. 결과는 점검 날짜 폴더를 생성하여 `output` 폴더에 저장합니다. (예: `output/2026-08-26/inspection-details.csv`)

## 폴더 구성

- `.agents/rules/inspection-rules.md` : 항상 지켜야 할 점검 원칙
- `.agents/skills/homepage-inspection/SKILL.md` : 홈페이지 점검 스킬
- `.agents/workflows/homepage-test-inspection.md` : 20페이지 시험 점검
- `.agents/workflows/homepage-full-inspection.md` : 전체 점검
- `.agents/workflows/homepage-recency-inspection.md` : 게시일 최신성 집중 점검
- `.agents/workflows/incremental-inspection.md` : 증분 점검 (변화 감지 후 변경된 게시판만 점검)
- `.agents/workflows/search-index-inspection.md` : 검색엔진 인덱스 링크 오류 점검
- `references/inspection-targets.md` : 점검 대상과 범위
- `references/recency-rules.md` : 게시일 및 최신 글 기준
- `references/exclusion-rules.md` : 제외 대상
- `references/report-fields.md` : 결과 파일 필드 정의
- `references/page-cache.md` : 게시판별 최신 게시일 캐시 (증분 점검용, 추출셀렉터 포함)
- `mcp-server/` : [webcheck-mcp](https://github.com/deinteger/webcheck-mcp) 설치 위치. 링크 상태 확인·게시일 판정을 처리하는 범용 MCP 서버 (Claude Code/Antigravity에서 도구로 사용, 다른 기관/업무에도 재사용 가능)
- `previous` : 이전 점검 결과 보관
- `screenshots` : 오류 화면 저장
- `output` : 날짜별 폴더에 점검 결과 저장

## 선택 기능: 정기 자동 실행

매번 사람이 명령어를 입력하지 않아도 되도록, 원할 때 `/schedule` 스킬로
정기 실행을 등록할 수 있습니다 (기본값은 꺼져 있음 — 필요할 때만 켜는 옵션).

```text
/schedule
매일 새벽 3시에 이 저장소에서 incremental-inspection 워크플로우를 실행해줘.
```

증분 점검(`incremental-inspection.md`)은 변화가 감지된 게시판만 상세 점검하므로
정기 실행에 적합합니다. 전체 점검(`homepage-full-inspection.md`)은 자주 돌릴
필요가 없다면 수동으로만 실행하는 것을 권장합니다.

## 권장 첫 명령

다음 명령을 Antigravity 에이전트에 입력합니다.

```text
homepage-inspection 스킬과 작업공간 규칙을 사용하라.
references/inspection-targets.md와 references/recency-rules.md를 읽고,
최대 20페이지만 시험 점검하라.
결과는 output/YYYY-MM-DD/inspection-summary.md와 output/YYYY-MM-DD/inspection-details.csv에 작성하라.
```
