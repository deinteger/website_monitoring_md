# 결과 파일 필드 정의

모든 결과는 `workspace/runs/YYYY-MM-DD/`에 저장된다. CSV는 Excel 호환을 위해 UTF-8(BOM)이다.

| 파일 | 생성 | 내용 |
| --- | --- | --- |
| `run-summary.json` | collect.py | 실행 모드, 방문·캐시 수, 판정 집계, 신규·지속·해결 건수, 경고, 요청 정책 |
| `findings.json` | collect.py | 지적 전체(상태 포함), 해결 항목, 게시판별 결과 |
| `recency-status.csv` | collect.py | 게시판별 최신 게시일·판정 |
| `inspection-details.csv` | collect.py | 지적 상세 목록 |
| `ai-review-queue.json` | collect.py | AI가 판단할 항목(마스킹된 발췌 포함) |
| `judgement.json` | judge.py 또는 에이전트 | AI 판단 결과 |
| `inspection-summary.md` | make_summary.py | 9개 구성 요약 보고 |
| `results.jsonl` | collect.py | 게시판별 중간 결과(재개용) |
| `search-index-links.csv`, `search-index-summary.json` | check_index_links.py | 검색엔진 인덱스 URL 점검 결과 |
| `typo-review-queue.json` | collect.py --typo-check | 오타 점검 대상 신규 게시글(본문, 마스킹) |
| `typo-judgement.json` | judge.py --task typo 또는 에이전트 | 게시글 오타 판단(원문 인용 검증됨) |
| `reports/recent/*.md, *.json` | recent_changes.py | 최근 현행화 조회 결과. `latest.*`는 최근 14일 요약(매 실행 후 갱신) |

월간 보고는 `workspace/reports/YYYY-MM/` (`monthly-report.md`, `monthly-metrics.json`, `monthly-boards.csv`)에 저장된다.

## inspection-details.csv

번호, 시스템구분, 분류, 중요도, 메뉴또는영역, 페이지제목, URL, 최신게시일, 기준일, 경과기간, 발견내용, 판단근거, 권고조치, 스크린샷, 상태, 최초발견일

- 상태: 신규 / 지속 (해결 항목은 `findings.json`의 `resolved`)

## recency-status.csv

번호, 시스템구분, 콘텐츠영역, 목록페이지제목, 목록URL, 최신게시물제목, 최신게시일, 기준일, 3개월기준일, 경과기간, 판정, 비고

- 비고에 `캐시(미방문)`이 있으면 이번 실행에서 방문하지 않고 캐시 값으로 재판정한 행이다.

## judgement.json (AI 판단)

```json
{"date": "2026-08-26", "model": "provider/model", "items": [
  {"board_id": "notice", "verdict": "정상|현행화 의심|문구 개선|담당자 확인 필요", "severity": "긴급|높음|보통|낮음",
   "confidence": "high|medium|low", "needs_human": true,
   "issues": [{"type": "...", "quote": "원문 그대로", "reason": "...", "action": "...", "quote_verified": true}],
   "note": "..."}],
 "errors": [], "over_limit_skipped": []}
```

에이전트가 직접 판단할 때도 같은 스키마로 작성한다. `quote`는 입력의 제목·발췌에 있는 구절이어야 한다.

## search-index-links.csv

번호, 시스템구분, 검색엔진, 검색결과제목, 검색결과URL, 실제접속상태, 실제페이지제목, 제목일치여부, 판정, 비고

## 판정값

- 정상
- 게시 최신성 지연
- 게시일 확인 불가
- 담당자 확인 필요
- 제외
- 404오류
- 500오류
- 접속오류 (타임아웃, 연결 실패, 기타 4xx)
- 리다이렉트오류 (허용 도메인 밖으로 이동, 또는 deep link가 메인으로 이동)
- 소프트404 (상태코드 200이나 '페이지 없음' 안내) — 검색 인덱스 점검
- 빈페이지의심, 깨진이미지, 제목불일치 — 검색 인덱스 점검
