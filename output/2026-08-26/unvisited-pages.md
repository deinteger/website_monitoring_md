# 미방문 페이지 목록

본 문서는 2026-08-26 국립원예특작과학원 대표 홈페이지 시험 점검(20페이지 제한) 과정에서 미방문 또는 점검 제외된 대표 영역을 기록합니다.

## 1. 시험 점검 제한으로 인한 미방문 (Limit Exceeded)
전체 130개 이상의 수집된 URL 중, 시험 점검 설정([inspection-targets.md](file:///c:/dev/homeAuto/homepage-monitor-antigravity/references/inspection-targets.md))의 **최대 20페이지 탐색 한도**에 도달하여 다음 주요 메뉴 및 하위 페이지들은 탐색 대상에서 제외되었습니다.

* **연구성과의 하위 메뉴 일부** (예: 기술지원, 농업기술도서 등)
* **민원/행정의 하위 메뉴 대부분** (예: 정보공개방, 공공데이터개방 등)
* **기관소개 내 하위 상세 안내** (예: 찾아오시는 길, 조직 및 인원 안내 등)

> [!NOTE]
> 이 페이지들의 전체적인 점검을 완료하려면 `homepage-full-inspection.md` 워크플로우를 실행하여 점검 범위를 확장해야 합니다.

## 2. 제외 기준 적용에 따른 미방문 (Excluded Domains & Features)
다음 외부 도메인 및 특정 동적 기능은 제외 규칙([exclusion-rules.md](file:///c:/dev/homeAuto/homepage-monitor-antigravity/references/exclusion-rules.md))에 따라 점검 과정에서 수집만 되고 상세 동작(또는 접속) 점검은 수행하지 않았습니다.

| 대상 URL | 분류/성격 | 미방문 사유 |
| --- | --- | --- |
| `https://www.nongsaro.go.kr/...` | 외부 도메인 연계 | 허용 도메인(`*.nihhs.go.kr`) 외부 링크로 URL 규칙만 기록하고 상세 확인 제외 |
| `https://atis.rda.go.kr/...` | 외부 도메인 연계 | 허용 도메인(`*.nihhs.go.kr`) 외부 링크로 URL 규칙만 기록하고 상세 확인 제외 |
| `https://www.nihhs.go.kr/usr/login/...` | 사용자 로그인 | 로그인 필터 작동 및 제외 가이드라인 적용 |
