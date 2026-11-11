---
name: homepage-inspection
description: 공공기관 홈페이지 점검·모니터링·질의 스킬. 게시판 최신 게시일(달력 기준 3개월 지연), 링크·첨부·접속 오류, 현행화 의심, 문구·게시글 본문 오타, 월간 점검 보고, 검색엔진 인덱스 깨진 링크를 점검하고, 어제·최근 현행화된 게시물 조회, 게시판 현황, 특정 페이지 담당자·연락처 찾기에 답한다. 홈페이지 점검, 모니터링, 현행화, 게시일, 오타, 월간 보고, 담당자 연락처, 최근 등록 게시물, 사이트 온보딩 요청에 사용한다.
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

## 질문에 답하기 (사이트에 들어가지 않고 물을 때)

- "어제 그제 현행화된 게시물?" → `python scripts/recent_changes.py --workspace workspace --days 2` (점검 후 조회는 `--refresh`)
- "보도자료 현황 / 전체 현황" → `python scripts/lookup.py --workspace workspace status 보도자료` / `overview`
- "보도자료 담당자 연락처" → `python scripts/lookup.py --workspace workspace contact 보도자료` (공개된 표기만, 근거 원문 제공, 추정 금지)
- 게시글 본문 오타 점검(선택): `collect.py --typo-check` → `core/typo-guide.md` 기준 판단
- 상세는 `core/skill-body.md` 7~8절
