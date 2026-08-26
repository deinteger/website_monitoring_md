# 홈페이지 시험 점검

1. `homepage-inspection` 스킬을 사용한다.
2. 작업공간 규칙과 `references` 폴더의 기준 문서를 읽는다.
3. 점검 대상 홈페이지 메인 URL에 접속한다.
4. 메인 페이지와 상단 메뉴를 기준으로 최대 20페이지만 탐색한다.
5. 외부 사이트는 접속하지 않고 URL만 기록한다.
6. 동일 URL은 한 번만 점검한다.
7. 게시일이 표시되는 게시판·썸네일·카드 목록의 최신 글 날짜를 확인한다.
8. 최신 게시일이 기준일보다 달력 기준 3개월 이상 오래된 경우 `게시 최신성 지연`으로 분류한다.
9. 명확한 오류는 다시 접속하여 재현 여부를 확인한다.
10. 결과를 `output/YYYY-MM-DD/inspection-summary.md`, `output/YYYY-MM-DD/inspection-details.csv`, `output/YYYY-MM-DD/recency-status.csv`에 작성한다.
11. 점검하지 못한 페이지와 이유를 `output/YYYY-MM-DD/unvisited-pages.md`에 기록한다.
