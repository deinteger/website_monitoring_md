---
name: homepage-inspection
description: 공공기관 홈페이지 점검·모니터링·질의 스킬. 점검 범위(전체, 게시판, 오타, 정책정보 확인주간, 범정부 UI/UX 가이드라인, 검색 포털)를 사용자가 고르게 하고 실행한다. 게시판 최신 게시일, 링크·접속 오류, 현행화, 게시글 오타, 월간 보고, 구글·네이버·다음 site: 점검, 정책정보 확인 체크리스트, 최근 현행화 게시물·현황·담당자 연락처 조회에 사용한다. 홈페이지 점검, 모니터링, 정책정보 확인주간, UI/UX 가이드라인, 검색포털 점검 요청에 사용한다.
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
- 대상 사이트·담당자·AI 연결 변경 요청은 소스·JSON을 직접 고치지 말고 `python scripts/setup.py`(`board add|set|remove`, `set`, `llm`, `show`)로 반영한다(`core/onboarding.md` 0절). API 키는 `LLM_API_KEY` 환경변수로만 안내한다.
- 스크립트가 확정한 값(상태코드, 최신 게시일, 지연 판정)을 AI가 다시 계산하거나 뒤집지 않는다.
- 차단 의심(종료코드 2)이면 재시도·우회하지 말고 사용자에게 보안·운영 부서 협의를 안내한다.

## 질문에 답하기 (사이트에 들어가지 않고 물을 때)

- "어제 그제 현행화된 게시물?" → `python scripts/recent_changes.py --workspace workspace --days 2` (점검 후 조회는 `--refresh`)
- "보도자료 현황 / 전체 현황" → `python scripts/lookup.py --workspace workspace status 보도자료` / `overview`
- "보도자료 담당자 연락처" → `python scripts/lookup.py --workspace workspace contact 보도자료` (공개된 표기만, 근거 원문 제공, 추정 금지)
- 게시글 본문 오타 점검(선택): `collect.py --typo-check` → `core/typo-guide.md` 기준 판단
- 상세는 `core/skill-body.md` 7~8절

## 점검 범위 선택 (먼저 물어본다)

사용자가 범위를 말하지 않으면 **전체 / 게시판 / 오타 / 정책정보 확인주간 / UI·UX 가이드라인 / UI·UX 화면 AI 검토 / 검색 포털** 중 무엇을 할지 먼저 묻는다 (복수 선택 가능).

- `python scripts/run_checks.py --workspace workspace --list` (선택지·비용) / `--checks all|board,typo,policy,uiux,portal` / `--dry-run` (요청량)
- UI/UX 화면 AI 검토(`--checks uiux-ai`): 일부 페이지(기본 15, `--ui-pages`로 지정)를 `core/uiux-review-guide.md`로 검토 → `uiux_review.py merge`(원문 인용 검증). 소스 기준 미충족은 `policy-ai-queue.json`을 화면에서 확인해 `policy_check.py ai-merge`
- 정책정보 확인주간·UI/UX: 자동(auto)·증거 수집(assist)·사람 응답(attest) 구분. **네/아니오 응답은 사람이 하며 대신 작성하지 않는다** (`policy_check.py answer`)
- 검색 포털: 계획 생성(종료코드 4) → 브라우저로 URL 수집 → 재실행. 스크립트로 검색엔진을 긁지 않는다
- 가이드라인 개정 반영: `core/guideline-update.md`, `python scripts/guidelines.py validate|diff|use`
