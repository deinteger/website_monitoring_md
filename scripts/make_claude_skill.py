#!/usr/bin/env python3
"""Claude 채팅(claude.ai)에 업로드하는 스킬 zip 빌더 (표준 라이브러리만 사용).

claude.ai 의 스킬은 'SKILL.md 가 든 폴더'를 zip 으로 올린다. 스킬 폴더 안에서 상대경로로 동작해야 하므로
저장소 전체가 아니라 core/ scripts/ config.example/ 와 채팅용 SKILL.md 를 담은 별도 패키지를 만든다.

  python scripts/make_claude_skill.py                 ->  dist/homepage-inspection-claude-skill.zip (claude.ai 채팅용)
  python scripts/make_claude_skill.py --target code   ->  dist/homepage-inspection-claude-code-skill.zip (Claude Code 스킬 폴더용, ~/.claude/skills/ 에 풀기)
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_release  # noqa: E402
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "homepage-inspection"
SKIP_SCRIPTS = {"make_release.py", "make_claude_skill.py", "eval_judge.py"}

SKILL_MD = """---
name: homepage-inspection
description: 공공기관 홈페이지 점검 스킬(채팅용). 게시판 최신 게시일(달력 기준 3개월 지연), 링크·첨부파일·접속 오류, 현행화 의심, 문구 개선, 월간 점검 보고를 파이썬 스크립트와 AI 판단으로 수행한다. 사용자가 site-profile.json 또는 이전 점검 상태 zip 을 올리고 홈페이지 점검, 모니터링, 현행화 확인, 월간 보고를 요청할 때 사용한다.
---

# 홈페이지 점검 (채팅용)

수집·날짜 계산은 이 스킬 폴더의 파이썬 스크립트가, 현행화·문구 같은 추론 판단은 Claude가 한다.
아래 `SKILL_DIR`은 이 SKILL.md가 있는 폴더이며, 스크립트는 `python SKILL_DIR/scripts/...`로 실행한다.

## 이 환경의 제약 (먼저 사용자에게 알린다)

1. 컨테이너는 대화가 끝나면 사라진다. **점검 상태(캐시·이력)는 `state.zip`으로 내려받아 다음 대화에 올려야** 증분 점검과 월간 보고가 이어진다.
2. 대상 사이트에 접속하려면 이 환경의 네트워크에서 해당 도메인이 허용되어야 한다. 막혀 있으면 점검할 수 없다 (우회하지 않는다).
3. 점검 내용이 외부 AI 서비스로 전송된다. 기관 보안 승인 범위를 사용자가 확인했는지 묻는다.
4. 게시판이 수백 개면 대화 한 번의 실행 시간 제한에 걸릴 수 있다 → 처음에는 `--limit 20`으로 시작하고, 대량 점검은 로컬(Claude Code, 스케줄러)을 권한다.

먼저 `core/rules.md`를 읽는다 (읽기 전용, 차단 시 중단, 개인정보 마스킹).

## 절차

1. 사용자가 올린 파일을 확인한다. `site-profile.json`이 필수이고 `settings.json`, 이전 `state.zip`은 선택이다.
   프로필이 없으면 `core/onboarding.md`로 만든다 (`scripts/discover.py`).
   대상 사이트·담당자·AI 연결을 바꿔 달라는 요청은 `scripts/setup.py`(`board add|set|remove`, `set`, `llm`, `show`)로 반영하고 소스·JSON을 직접 고치지 않는다. API 키는 `LLM_API_KEY` 환경변수로만 안내한다.
2. 작업 폴더 `WS=/tmp/ws`를 준비한다.
   - `state.zip`이 있으면 `python SKILL_DIR/scripts/chat_state.py unpack --input <state.zip> --workspace WS`
   - 없으면 올린 `site-profile.json`(과 `settings.json`)을 `WS/`에 복사한다.
3. 요청량 확인 후 점검한다 (처음에는 `--limit 20`).
   ```
   python SKILL_DIR/scripts/collect.py --workspace WS --mode incremental --dry-run
   python SKILL_DIR/scripts/collect.py --workspace WS --mode incremental
   ```
   - 최초·월 1회는 `--mode full`.
   - 대부분이 `접속오류`이고 오류에 `403` 또는 `Tunnel connection failed`가 보이면 **이 환경의 네트워크 허용 설정 문제**다. 점검을 멈추고 사용자에게 해당 도메인을 허용해야 한다고 안내한다. 재시도·우회하지 않는다.
   - 종료코드 2(차단 의심)도 중단하고 보안·운영 부서 협의를 안내한다.
   - 게시판 인식이 이상하면 `--probe <board_id>`로 확인하고 프로필을 보정한다.
4. `WS/runs/<날짜>/ai-review-queue.json`의 항목만 `core/judgement-guide.md` 기준으로 판단해 `judgement.json`을 같은 폴더에 저장한다 (스키마: `core/report-fields.md`). 스크립트가 확정한 날짜·상태·지연 판정은 다시 계산하거나 뒤집지 않는다.
5. 요약을 만든다: `python SKILL_DIR/scripts/make_summary.py --workspace WS`
6. 사용자에게 줄 파일을 파일 다운로드가 가능한 출력 위치에 복사한다: `inspection-summary.md`, `recency-status.csv`, `inspection-details.csv`.
7. **상태를 저장해 내려받게 한다** (반드시):
   `python SKILL_DIR/scripts/chat_state.py pack --workspace WS --output <출력위치>/state.zip`
   그리고 "다음 점검 때 이 state.zip을 올리면 이어서 증분 점검·월간 보고를 할 수 있다"고 안내한다.

## 월간 보고

`state.zip`(이력 포함)을 올린 대화에서: `python SKILL_DIR/scripts/monthly_report.py --workspace WS --month YYYY-MM`
생성된 `monthly-report.md`의 `AI_COMMENT` 자리에 3~5줄 종합 의견을 쓴다 (`core/monthly-report.md` 규칙, 표의 수치만 인용).

## 정책정보 확인주간·UI/UX 점검 (선택)

범위를 말하지 않았으면 먼저 묻는다: 게시판 점검 / 정책정보 확인주간 / UI·UX 가이드라인 / 검색 포털. `python SKILL_DIR/scripts/run_checks.py --workspace WS --checks policy,uiux` (사이트 접속 필요).
`auto`는 자동 판정, `assist`는 증거 수집, `attest`는 **사람이 네/아니오로 응답**하며 대신 작성하지 않는다. 응답은 `python SKILL_DIR/scripts/policy_check.py answer PW-03 --yes --note "..."`로 기록하고 `state.zip`에 담긴다.
검색 포털은 계획(`WS/index/plan.md`)만 만든다(종료코드 4): 브라우저가 없는 환경에서는 사용자가 결과 URL을 직접 모아 올려야 한다.

## 질문에 답하기 (state.zip을 올린 대화)

`state.zip`을 복원한 뒤에는 **사이트 접속 없이** 다음 질문에 답할 수 있다.
- "어제 그제 현행화된 게시물?" → `python SKILL_DIR/scripts/recent_changes.py --workspace WS --days 2` (결과의 `주의`를 그대로 전달. 데이터는 마지막 점검 시점까지)
- "보도자료 현황 / 전체 현황" → `python SKILL_DIR/scripts/lookup.py --workspace WS status 보도자료` / `overview`
- "담당자 연락처" → `python SKILL_DIR/scripts/lookup.py --workspace WS contact 보도자료` (해당 페이지 접속 필요. 공개된 표기만 전달하고 추정하지 않는다)
최신 데이터가 필요하면 점검을 먼저 실행한 뒤 조회한다.

## 사용자에게 보고할 내용

모드, 방문/캐시 수, 신규·지속·해결 건수, 확정 오류, 신규 지연 게시판, 경고, 점검 한계(미점검·AI 판단 미실시 포함)

## 하지 말 것

- 점검하지 않은 항목을 정상으로 보고하기, 개인정보 원문 옮겨 적기
- 요청 정책 완화, 허용 도메인 밖 접속, 차단 우회
"""


SKILL_MD_CODE = """---
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
3. `WS/site-profile.json`이 없으면 `SKILL_DIR/core/onboarding.md`로 만든다 (`SKILL_DIR/config.example/`의 예시를 `WS/`로 복사해 시작, `scripts/discover.py`로 초안 생성). 사용자가 대상 사이트·담당자·AI 연결을 말하면 소스나 JSON을 직접 고치지 말고 `scripts/setup.py`(`board add|set|remove`, `set`, `llm`, `show`)로 반영한다(`core/onboarding.md` 0절). API 키는 파일에 쓰지 않고 `LLM_API_KEY` 환경변수로 안내한다.

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
"""


def main(argv=()):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["chat", "code"], default="chat", help="chat: claude.ai 채팅용(기본), code: Claude Code 개인·프로젝트 스킬용")
    args = ap.parse_args(argv)
    dist = os.path.join(ROOT, "dist")
    stage = dist if args.target == "chat" else os.path.join(dist, "code-skill")
    out = os.path.join(stage, NAME)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(SKILL_MD if args.target == "chat" else SKILL_MD_CODE)
    for d in ("core", "config.example"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(out, d), ignore=shutil.ignore_patterns("__pycache__"))
    def _ign(d, names):   # 가이드라인 원문(source/)은 목차 색인(toc.json)만, 생성된 review-queue.json 은 제외
        drop = [n for n in names if n in ("__pycache__", "review-queue.json")]
        if os.path.basename(d) == "source":
            drop += [n for n in names if n != "toc.json"]
        return drop
    shutil.copytree(os.path.join(ROOT, "guidelines"), os.path.join(out, "guidelines"), ignore=_ign)
    os.makedirs(os.path.join(out, "docs"))                      # 스킬 지침이 가리키는 보안 통보 양식
    shutil.copy2(os.path.join(ROOT, "docs", "보안통보_요청서_양식.md"), os.path.join(out, "docs", "보안통보_요청서_양식.md"))
    os.makedirs(os.path.join(out, "scripts"))
    for f in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
        if f.endswith(".py") and f not in SKIP_SCRIPTS:
            shutil.copy2(os.path.join(ROOT, "scripts", f), os.path.join(out, "scripts", f))
    files = [os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs]
    bad = make_release.scan_hosts(out, files)
    if bad:
        shutil.rmtree(out)
        print("[중단] 허용 목록 밖의 도메인 발견: %s" % ", ".join(sorted(bad)), file=sys.stderr)
        return 1
    zpath = os.path.join(dist, "%s-claude-skill.zip" % NAME if args.target == "chat" else "%s-claude-code-skill.zip" % NAME)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            z.write(os.path.join(out, rel), os.path.join(NAME, rel))
    print("스킬 zip: %s (%d개 파일, %.1f KB)" % (zpath, len(files), os.path.getsize(zpath) / 1024.0))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main(sys.argv[1:]))
