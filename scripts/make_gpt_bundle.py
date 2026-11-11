#!/usr/bin/env python3
"""ChatGPT(맞춤 GPT·프로젝트)용 자료 묶음 생성기 (표준 라이브러리만 사용).

dist/gpt-bundle/ 에 다음을 만든다.
  instructions.txt   맞춤 GPT '지침'(8,000자 이내로 작성; 한도는 변경될 수 있어 업로드 시 확인)
  knowledge/*.md     '지식' 파일(core 절차·판단 기준·연락처 조회 등)
  kit.zip            코드 인터프리터(파이썬)로 풀어 실행할 키트 전체(배포본)
  사용법.txt          설정 순서

ChatGPT 샌드박스는 외부 사이트 접속이 막힐 수 있다(확인 필요). 그래서 역할을 나눈다:
  수집(접속) = 로컬 PC(Codex·Claude Code 등), 판단·조회·보고·설정 = ChatGPT(결과 파일 업로드 후).
"""
from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monlib as ml  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 8000
KNOWLEDGE = ["core/rules.md", "core/skill-body.md", "core/judgement-guide.md", "core/typo-guide.md", "core/uiux-review-guide.md",
             "core/onboarding.md", "core/monthly-report.md", "core/report-fields.md", "core/recency-rules.md", "core/exclusion-rules.md"]

INSTRUCTIONS = """당신은 공공기관 홈페이지 점검 보조자다. 실무체·개조식으로 결론부터 답한다.

[역할 분담] 날짜·상태·지연 판정과 접속·링크 점검은 스크립트(scripts/)가 한다. 당신은 스크립트가 만든 ai-review-queue.json 항목만 판단하고, 스크립트가 낸 값은 다시 계산하거나 뒤집지 않는다. 점검하지 않은 항목은 '정상'이 아니라 '미점검'으로 보고한다.

[필수 규칙] 지식 파일 rules.md를 먼저 따른다: 읽기 전용 점검, 차단 의심(종료코드 2)이면 재시도·우회 없이 중단하고 보안·운영 부서 협의를 안내, 외부 AI 전송은 기관 승인 후에만, 개인정보 마스킹. 정책정보 확인 체크리스트의 네/아니오는 사람이 답하며 대신 작성하지 않는다. 점검 범위를 말하지 않은 점검 요청에는 먼저 범위(전체/게시판/오타/정책정보/UIUX/포털)를 묻는다.

[환경 구분] ChatGPT 샌드박스는 외부 사이트에 접속하지 못할 수 있다. 접속 가능 여부를 먼저 시험(대상 주소 1건)하고, 안 되면 수집은 사용자의 PC(Codex·Claude Code 등)에서 하도록 안내한 뒤 결과 파일(workspace/runs/날짜/ 의 csv·json)을 받아 판단·보고만 한다. 결과 파일은 세션이 끝나면 사라지므로 마지막에 내려받게 안내한다.

[설치] 코드 인터프리터로 kit.zip을 풀고 그 폴더에서 python scripts/... 를 실행한다(파이썬 3.8 이상, 외부 라이브러리 불필요).

[설정 변경] 사용자가 대상 사이트·게시판·담당자·점검 주기·AI 연결을 바꿔 달라고 하면 파일을 직접 고치지 말고 python scripts/setup.py 로 한다: init, board add|set|remove|list, site, set <키> <값>, llm, show. API 키는 파일·채팅에 쓰지 않고 환경변수 LLM_API_KEY로만 지정하게 안내한다. 외부 AI 전송 허용(llm --allow yes)은 사용자가 승인했다고 말한 경우에만 한다.

[자주 쓰는 명령] (작업 폴더 workspace)
- 범위 목록: python scripts/run_checks.py --workspace workspace --list
- 점검: python scripts/run_checks.py --workspace workspace --checks board,policy,uiux (모드 --mode incremental|full, 먼저 --dry-run)
- 최근 현행화 게시물: python scripts/recent_changes.py --workspace workspace --days 2
- 현황·담당자: python scripts/lookup.py --workspace workspace status|overview|find|contact <이름>
- 월간 보고: python scripts/monthly_report.py --workspace workspace --month YYYY-MM
- 데모(접속·키 불필요): python scripts/demo.py

[판단 기준] judgement-guide.md, typo-guide.md, uiux-review-guide.md를 따른다. AI 판단에는 원문 인용(quote)을 반드시 붙이고, 입력에 없는 인용이면 '확인불가/담당자 확인 필요'로 낮춘다. 근거가 부족하면 단정하지 말고 '확인 필요'로 표시하며 대안 시나리오를 2개 이상 제시한다.

[안내] 절차 상세는 지식 파일 skill-body.md. 처음 질문에는 점검 범위를 묻고, 대상 사이트가 없으면 setup.py init 부터 안내한다. 결과 폴더는 사용자 PC(또는 이 세션)에만 생성되며 키트 원본 저장소에는 올라가지 않는다.
"""

HOWTO = """ChatGPT 사용법 (맞춤 GPT)
1. ChatGPT > GPT 만들기 > 구성 > 지침에 instructions.txt 내용을 붙여 넣는다 (글자 수 한도는 화면에서 확인).
2. 지식에 knowledge/ 폴더의 파일을 올리고, 코드 인터프리터(데이터 분석)를 켠다.
3. 대화 첫머리에 kit.zip 을 첨부하고 "kit.zip 을 풀고 데모를 돌려줘" 라고 한다. (샌드박스에 외부 접속이 되는지 확인 필요)
4. 실제 점검은 사용자 PC에서 수집한 결과 폴더(workspace/runs/날짜/)를 압축해 올린 뒤 "판단·보고해줘"라고 한다.
5. 작업이 끝나면 만들어진 결과 파일을 내려받는다 (세션 종료 시 삭제).
※ GPT 웹은 대상 사이트 접속이 막힐 수 있다. 확인 전에는 수집을 로컬(Codex 등)에서 하는 방식을 기본으로 한다.
※ 민감한 점검 결과를 외부 서비스에 올리는 것은 기관 보안 승인 후에만 한다.
"""


def main(argv=()):
    import subprocess
    out = os.path.join(ROOT, "dist", "gpt-bundle")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "knowledge"))
    if len(INSTRUCTIONS) > LIMIT:
        print("[오류] 지침이 %d자로 한도(%d)를 넘습니다" % (len(INSTRUCTIONS), LIMIT), file=sys.stderr)
        return 1
    with open(os.path.join(out, "instructions.txt"), "w", encoding="utf-8") as f:
        f.write(INSTRUCTIONS)
    with open(os.path.join(out, "사용법.txt"), "w", encoding="utf-8") as f:
        f.write(HOWTO)
    for rel in KNOWLEDGE:
        src = os.path.join(ROOT, rel)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(out, "knowledge", os.path.basename(rel)))
    import make_release
    if make_release.main(()) != 0:
        return 1
    zname = "website-monitoring-kit-v%s.zip" % ml.VERSION
    shutil.copyfile(os.path.join(ROOT, "dist", zname), os.path.join(out, "kit.zip"))
    print("GPT 묶음: %s (지침 %d자, 지식 %d개, kit.zip)" % (out, len(INSTRUCTIONS), len(os.listdir(os.path.join(out, "knowledge")))))
    return 0


if __name__ == "__main__":
    ml.setup_stdio()
    sys.exit(main(sys.argv[1:]))
