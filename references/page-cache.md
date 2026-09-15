# 게시판 점검 캐시

에이전트가 점검 후 이 파일을 자동으로 업데이트한다.
다음 점검 시 이 파일의 `최신게시일`과 오늘 게시판 목록 첫 줄 날짜를 비교하여 변화가 없으면 상세 점검을 스킵한다.

## 캐시 갱신 규칙

- 점검 완료 후 반드시 이 파일의 해당 행을 업데이트한다.
- `최신게시일`이 변경된 경우에만 해당 게시판을 상세 점검 대상으로 포함한다.
- `마지막점검일`은 실제로 목록에 접속한 날짜를 기록한다.
- `추출셀렉터`는 최신 게시일을 뽑아내는 데 사용한 CSS 선택자(또는 스크립트 표현식)를 기록한다. 값이 있으면 재탐색 없이 그대로 사용하고, 비어 있으면 점검 중 찾은 값을 채워 넣는다.

## 대표홈페이지 (www.nihhs.go.kr)

| 점검주기 | 콘텐츠영역 | URL | 최신게시일 | 마지막점검일 | 판정 | 추출셀렉터 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 매일 | 공지사항 | https://www.nihhs.go.kr/usr/nihhs/news_Notice_list.do?mc=MN0000000135 | 2026-08-24 | 2026-08-26 | 정상 | | |
| 매일 | 보도자료 | https://www.nihhs.go.kr/usr/nihhs/news_Press_list.do?mc=MN0000000136 | 2026-08-23 | 2026-08-26 | 정상 | | |
| 주1회 | 행사앨범 | https://www.nihhs.go.kr/usr/nihhs/news_Album_list.do?mc=MN0000000138 | 2026-08-13 | 2026-08-26 | 정상 | | |
| 주1회 | 주간농사정보 | https://www.nihhs.go.kr/farmer/techInfo/weekFarmerInfo.do?mc=MN0000000030 | 2026-08-19 | 2026-08-26 | 정상 | | |
| 주1회 | 기술정보 | https://www.nihhs.go.kr/usr/nihhs/news_Public_list.do?mc=MN0000000025 | 2026-08-04 | 2026-08-26 | 정상 | | |
| 주1회 | 연구동향 월간리포트 | https://www.nihhs.go.kr/farmer/techInfo/rctAgriTechList.do?mc=MN0000000024 | 2026-07-28 | 2026-08-26 | 정상 | | |
| 주1회 | 일반자료실 | https://www.nihhs.go.kr/usr/persnal/Pds_list.do?mc=MN0000000140 | 2025-11-04 | 2026-08-26 | 게시 최신성 지연 | | |
| 분기1회 | 주요연구성과(연보) | https://www.nihhs.go.kr/farmer/rdRslt/rdMajorRsltList.do?mc=MN0000000039 | 2025 | 2026-08-26 | 게시 최신성 지연 | | 연례 간행물 |
| 분기1회 | 품종정보 | https://www.nihhs.go.kr/farmer/rdRslt/newBreedInfo.do?mc=MN0000000040 | 2025 | 2026-08-26 | 게시 최신성 지연 | | 비정기 등록 |
| 분기1회 | 영농활용 | https://www.nihhs.go.kr/farmer/rdRslt/rdFarmingApplyList.do?mc=MN0000000041 | 2025 | 2026-08-26 | 게시 최신성 지연 | | 비정기 등록 |
| 분기1회 | 시험연구보고서 | https://www.nihhs.go.kr/usr/farmer/examResearchReportList.do?mc=MN0000000046 | 2026 | 2026-08-26 | 담당자 확인 필요 | | 연도만 표기됨 |

## 과수생육시스템 (fruit.nihhs.go.kr)

| 점검주기 | 콘텐츠영역 | URL | 최신게시일 | 마지막점검일 | 판정 | 추출셀렉터 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 매일 | 보도자료 | https://fruit.nihhs.go.kr/openapi/selectPartApiBoardList.do?frtgrdCode=com | 2026-08-17 | 2026-08-26 | 정상 | | |
| 매일 | 주간농사정보(메인) | https://fruit.nihhs.go.kr/ | 2026-08-19 | 2026-08-26 | 정상 | | |
| 주1회 | 공지사항 | https://fruit.nihhs.go.kr/com/useeInfo/main_noticeListMain.do | 2026-01-16 | 2026-08-26 | 게시 최신성 지연 | | |
| 주1회 | 사과 생육정보 | https://fruit.nihhs.go.kr/apple/grwhInfo_eclnBlpr.do | 2026-04-26 | 2026-08-26 | 정상 | | 계절성 데이터 |
| 주1회 | 배 생육정보 | https://fruit.nihhs.go.kr/pear/grwhInfo_eclnBlpr.do | 2026-04-10 | 2026-08-26 | 정상 | | 계절성 데이터 |
| 주1회 | 복숭아 생육정보 | https://fruit.nihhs.go.kr/peach/grwhInfo_eclnBlpr.do | 2026-04-15 | 2026-08-26 | 정상 | | 계절성 데이터 |
| 주1회 | 포도 생육정보 | https://fruit.nihhs.go.kr/grape/grwhInfo_eclnBlpr.do | 2026-07-15 | 2026-08-26 | 정상 | | 계절성 데이터 |
| 주1회 | 감귤 생육정보 | https://fruit.nihhs.go.kr/citrus/grwhInfo_eclnBlpr.do | No data | 2026-08-26 | 담당자 확인 필요 | | 2026년 데이터 누락 |
| 분기1회 | 사용자매뉴얼 | https://fruit.nihhs.go.kr/com/useeInfo/main_manualList.do | 2021-12-24 | 2026-08-26 | 게시 최신성 지연 | | 매뉴얼 성격 |
