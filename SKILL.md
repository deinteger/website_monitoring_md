---
name: homepage-inspection
description: 공공기관 홈페이지 점검·모니터링·질의 스킬(Claude Code용, 자체 완결형). 점검 범위(전체, 게시판, 오타, 정책정보 확인주간, 범정부 UI/UX 가이드라인, UI/UX 화면 AI 검토, 검색 포털)를 사용자가 고르게 하고 실행한다. 게시판 최신 게시일, 링크·접속 오류, 현행화, 게시글 오타, 월간 보고, 최근 현행화 게시물·현황·담당자 연락처 조회, 정책정보 확인 체크리스트에 사용한다. 홈페이지 점검, 모니터링, 정책정보 확인주간, UI/UX 가이드라인, 검색포털 점검 요청에 사용한다.
---

# 홈페이지 점검 (Claude Code용, 자체 완결형)

수집·날짜 계산은 이 스킬 폴더의 파이썬 스크립트가, 현행화·오타·UI/UX 화면 판단 같은 추론은 Claude가 한다.
`SKILL_DIR`은 이 스킬의 **기본 폴더(Base directory)**이며 스크립트는 `python SKILL_DIR/scripts/...`로 실행한다. Python 3.8 이상이 필요하고 외부 패키지는 필요 없다.
작업 데이터(프로필·설정·캐시·결과)는 스킬 폴더가 아니라 **현재 프로젝트 폴더의 `homepage-workspace/`**(`WS`)에 둔다. 스킬 폴더는 읽기 전용으로 취급한다(갱신 때 덮어써질 수 있다).

## 먼저
1. `SKILL_DIR/core/rules.md`를 읽는다 (읽기 전용, 차단 시 중단, 외부 전송 승인, 개인정보 마스킹, 사람 응답 대행 금지).
2. 처음 쓰는 사용자에게는 데모를 권한다: `python SKILL_DIR/scripts/demo.py --workspace WS/demo` (접속·API 키 없이 모의 사이트로 전체 점검 시연).
3. `WS/site-profile.json`이 없으면 `SKILL_DIR/core/onboarding.md`로 만든다 (`SKILL_DIR/config.example/`의 예시를 `WS/`로 복사해 시작, `scripts/discover.py`로 초안 생성). 사용자가 대상 사이트·담당자·AI 연결을 말하면 소스나 JSON을 직접 고치지 말고 `scripts/setup.py`(`board add|set|remove`, `set`, `llm`, `show`)로 반영한다(`core/onboarding.md` 0절). API 키는 파일에 쓰지 않고 `LLM_API_KEY` 환경변수로 안내한다. 시작 전에 실행 환경(터미널 사용 가능/채팅만/접속 불가)을 `core/skill-body.md`의 '실행 환경 판별'로 먼저 판별하고, 스크립트를 실행하지 못했으면 실행한 것처럼 말하지 않는다.

## 점검 범위 선택 (먼저 물어본다)
사용자가 범위를 말하지 않으면 **전체 / 게시판 / 오타 / 정책정보 확인주간 / UI·UX 가이드라인 / UI·UX 화면 AI 검토 / 검색 포털** 중 무엇을 할지 묻는다(복수 선택 가능).
```
python SKILL_DIR/scripts/run_checks.py --workspace WS --list
python SKILL_DIR/scripts/run_checks.py --workspace WS --checks policy,uiux --dry-run     # 요청량 확인(보안 통보용)
python SKILL_DIR/scripts/run_checks.py --workspace WS --checks all
```
- 보안·운영 부서 통보 전에는 `--limit 20` 시험 점검까지만 한다 (`SKILL_DIR/docs/보안통보_요청서_양식.md`). 종료코드 2(차단 의심)면 재시도·우회 없이 중단한다.
- 정책정보 확인주간·UI/UX: 자동(auto)·증거 수집(assist)·사람 응답(attest) 구분. **네/아니오 응답은 사람이 하며 대신 작성하지 않는다** (`policy_check.py answer`).
- 소스 기준 미충족은 `WS/runs/<날짜>/policy-ai-queue.json`을 브라우저로 확인해 `policy-ai-judgement.json`을 쓰고 `policy_check.py ai-merge`로 병합한다.
- UI/UX 화면 검토는 `SKILL_DIR/core/uiux-review-guide.md`를 따르고 `uiux_review.py merge`로 병합한다 (원문 인용 검증).
- 검색 포털은 계획만 생성(종료코드 4) → 브라우저로 URL 수집 → 재실행. 검색엔진을 스크립트로 긁지 않는다.

## 질문에 답하기
- "어제 그제 현행화된 게시물?" → `python SKILL_DIR/scripts/recent_changes.py --workspace WS --days 2` (결과의 `주의`를 그대로 전달)
- "보도자료 현황 / 전체 현황" → `python SKILL_DIR/scripts/lookup.py --workspace WS status 보도자료` / `overview`
- "담당자 연락처" → `python SKILL_DIR/scripts/lookup.py --workspace WS contact 보도자료` (공개된 표기만, 추정 금지)
- 월간 보고 → `python SKILL_DIR/scripts/monthly_report.py --workspace WS --month YYYY-MM`

## 하지 말 것
- 스크립트가 확정한 날짜·상태·지연 판정을 다시 계산하거나 뒤집기, 점검하지 않은 항목을 정상으로 보고하기
- 요청 정책 완화, 허용 도메인 밖 접속, 차단 우회, 개인정보 원문 옮겨 적기
- `WS`의 내용을 커밋하거나 외부에 전송하기
