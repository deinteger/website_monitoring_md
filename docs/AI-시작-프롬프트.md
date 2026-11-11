# AI 시작 프롬프트 (복사해서 쓰는 문구)

어느 AI 도구에서든 키트 폴더를 열고(또는 스킬/지침을 설치하고) 아래 문구 중 하나를 첫 메시지로 보낸다. 결과 파일은 이 PC의 `workspace/`에만 생성되며 키트 저장소에는 올라가지 않는다.

## 1. 처음 쓸 때 (설정부터)
> 이 폴더의 `AGENTS.md`를 읽고 `core/rules.md`와 `core/onboarding.md` 절차대로 설정을 도와줘. 우리 기관은 [기관명]이고 점검할 사이트는 [주소]야. 담당 부서·연락처는 [부서 이름(연락처)]. 게시판은 자동 발견으로 후보를 찾아 보여주고, 내가 확인한 것만 `scripts/setup.py`로 등록해줘.

## 2. 점검 실행
> `core/skill-body.md` 절차대로 홈페이지 점검을 해줘. 범위는 먼저 물어봐. 처음이면 `--dry-run`으로 요청량부터 보여주고, 내 확인 뒤에 실행해.

## 3. 조회
> 어제·그제 현행화된 게시물이 뭐야? (`scripts/recent_changes.py`)
> [부서/게시판] 담당자 연락처 알려줘. (`scripts/lookup.py contact`)
> 이번 달 월간 보고 만들어줘. (`scripts/monthly_report.py`)

## 4. 설정 변경 (소스·JSON 직접 수정 금지)
> 점검 대상에 [사이트 주소]의 [게시판 이름]을 추가해줘 / 담당을 [부서]로 바꿔줘 / 지연 기준을 2개월로 바꿔줘 / AI 연결을 [anthropic|openai|openai-responses], 모델 [모델명]으로 설정해줘. (API 키는 내가 환경변수 `LLM_API_KEY`로 넣을게)

## 5. 도구별 첫 실행 확인
- 폴더형(Claude Code·Codex·Antigravity·Orca·Cline): 위 문구 1~2번. AI가 `core/rules.md`를 읽었다고 말하는지 확인.
- Claude 채팅: `dist/homepage-inspection-claude-skill.zip` 업로드 후 "홈페이지 점검 스킬로 데모를 돌려줘".
- ChatGPT: `python scripts/make_gpt_bundle.py` 로 만든 `dist/gpt-bundle/`의 `사용법.txt` 순서. 수집은 로컬, 판단·조회는 ChatGPT를 권장(샌드박스 외부 접속은 확인 필요).
