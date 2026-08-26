# 홈페이지 점검·모니터링 작업공간

이 폴더는 Antigravity에서 별도 프로그램 없이 에이전트가 홈페이지를 직접 탐색하고 점검하도록 구성한 작업공간입니다.

## 시작 방법

1. Antigravity에서 이 폴더를 작업공간으로 엽니다.
2. `.agents/rules`, `.agents/skills`, `.agents/workflows`가 인식되는지 확인합니다.
3. `references/inspection-targets.md`에 점검 대상 URL과 범위를 입력합니다.
4. 처음에는 최대 20페이지만 시험 점검합니다.
5. 결과는 점검 날짜 폴더를 생성하여 `output` 폴더에 저장합니다. (예: `output/2026-08-26/inspection-details.csv`)

## 폴더 구성

- `.agents/rules/inspection-rules.md` : 항상 지켜야 할 점검 원칙
- `.agents/skills/homepage-inspection/SKILL.md` : 홈페이지 점검 스킬
- `.agents/workflows/homepage-test-inspection.md` : 20페이지 시험 점검
- `.agents/workflows/homepage-full-inspection.md` : 전체 점검
- `.agents/workflows/homepage-recency-inspection.md` : 게시일 최신성 집중 점검
- `references/inspection-targets.md` : 점검 대상과 범위
- `references/recency-rules.md` : 게시일 및 최신 글 기준
- `references/exclusion-rules.md` : 제외 대상
- `references/report-fields.md` : 결과 파일 필드 정의
- `previous` : 이전 점검 결과 보관
- `screenshots` : 오류 화면 저장
- `output` : 날짜별 폴더에 점검 결과 저장

## 권장 첫 명령

다음 명령을 Antigravity 에이전트에 입력합니다.

```text
homepage-inspection 스킬과 작업공간 규칙을 사용하라.
references/inspection-targets.md와 references/recency-rules.md를 읽고,
최대 20페이지만 시험 점검하라.
결과는 output/YYYY-MM-DD/inspection-summary.md와 output/YYYY-MM-DD/inspection-details.csv에 작성하라.
```
