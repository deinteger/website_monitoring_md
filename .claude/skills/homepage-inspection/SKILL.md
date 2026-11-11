---
name: homepage-inspection
description: 공공기관 홈페이지 점검·모니터링 스킬. 게시판 최신 게시일(달력 기준 3개월 지연), 링크·첨부파일·접속 오류, 현행화 의심, 문구 개선, 월간 점검 보고(신규 콘텐츠·현행화 수치)를 스크립트와 AI 판단으로 수행한다. 홈페이지 점검, 모니터링, 현행화 확인, 게시일 점검, 월간 보고, 사이트 온보딩 요청에 사용한다.
---

# 홈페이지 점검

공공기관 홈페이지의 링크·접속 오류, 게시 최신성(달력 기준 3개월), 현행화 의심, 문구, 월간 현황을 점검한다.
**수집·날짜 계산은 파이썬 스크립트가, 추론이 필요한 판단은 AI가 한다.**

## 먼저 읽을 것 (저장소 루트에서 실행)

1. `core/rules.md` — 안전 원칙(읽기 전용, 차단 시 중단, 외부 전송 승인)과 역할 분담
2. `core/skill-body.md` — 단계별 절차 (이 스킬의 단일 원본)
3. 판단 단계에서만 `core/judgement-guide.md`

## 요약 (자세한 절차는 core/skill-body.md)

```bash
python scripts/collect.py --workspace workspace --mode incremental --dry-run   # 요청량 확인
python scripts/collect.py --workspace workspace --mode incremental             # 점검 (최초·월1회는 --mode full)
# ai-review-queue.json 의 항목만 판단 -> judgement.json 저장
python scripts/make_summary.py --workspace workspace
python scripts/monthly_report.py --workspace workspace --month YYYY-MM         # 월간 보고
```

- `workspace/site-profile.json`이 없으면 점검 전에 `core/onboarding.md`로 프로필을 만든다.
- 스크립트가 확정한 값(상태코드, 최신 게시일, 지연 판정)을 AI가 다시 계산하거나 뒤집지 않는다.
- 차단 의심(종료코드 2)이면 재시도·우회하지 말고 사용자에게 보안·운영 부서 협의를 안내한다.
