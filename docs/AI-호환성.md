# AI 도구별 사용 방법 (호환성 표)

원칙: **입구 파일만 도구마다 다르고, 절차·판단 기준(`core/`)과 스크립트(`scripts/`)는 하나**다. 어떤 AI든 "파일을 읽고 터미널 명령을 실행할 수 있으면" 같은 방식으로 쓴다.

| 도구 | 입구 | 설치 위치 | 확인 수준 |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`(→`AGENTS.md`), `.claude/skills/` | 저장소 폴더에서 실행 / 개인용은 `~/.claude/skills/` | 공식 문서 기준 (실기 미검증) |
| Codex (CLI·IDE·앱) | `AGENTS.md`, `.agents/skills/` | 저장소 폴더에서 실행 / 개인용은 `~/.agents/skills/` | 공식 문서 기준 (실기 미검증) |
| Antigravity | `AGENTS.md`, `GEMINI.md`, `.agents/` | 저장소 폴더 열기 | 공식 문서 기준 (실기 미검증) |
| Orca (pi·Claude·Codex 에이전트) | `AGENTS.md` | Orca가 실행하는 에이전트가 해당 파일을 읽음 | 문서 기준 (실기 미검증) |
| Cline (VS Code) | `.clinerules/` | 저장소 폴더 열기 | 문서 기준 (실기 미검증) |
| Claude 채팅 | 스킬 zip 업로드 | `dist/homepage-inspection-claude-skill.zip` | 코드 실행 가능 요금제 필요, 외부 접속 허용 범위 확인 필요 |
| ChatGPT | 대화에 시작 프롬프트 + 결과 파일 첨부 | 수집은 로컬(Codex 등)에서, 판단·조회·보고는 ChatGPT에서 | 수집은 ChatGPT 샌드박스에서 불가할 수 있음(확인 필요) |

## 공통 시작 문구 (어느 도구에서나)
더 많은 문구(설정·점검·조회·설정 변경)는 `docs/AI-시작-프롬프트.md`. ChatGPT용 묶음은 `python scripts/make_gpt_bundle.py` (`dist/gpt-bundle/`).

> 이 폴더의 `AGENTS.md`를 읽고 `core/rules.md`와 `core/skill-body.md` 절차대로 홈페이지 점검을 도와줘. 점검 범위부터 물어봐.

## 결과 파일은 각자 PC에 생성된다
- 결과는 **실행한 사람의 로컬 `workspace/`**(스킬 설치형은 `homepage-workspace/`)에만 만들어진다. `.gitignore`가 `workspace/*`를 제외하므로 커밋·푸시되지 않는다.
- 점검 종료 시 결과 폴더의 절대 경로를 출력한다. 키트 원본 저장소에는 아무것도 올라가지 않는다.
- 외부 전송은 설정한 AI API 호출(`llm.allowed`로 허용한 경우)과 점검 대상 사이트 접속뿐이다 (`scripts/judge.py`, `scripts/monlib.py` 외 네트워크 코드 없음).
- Claude 채팅·ChatGPT 샌드박스는 세션이 끝나면 파일이 사라지므로, 종료 전 결과 파일(또는 `workspace` 압축본)을 내려받아 보관한다.

## AI API 연결 (`workspace/settings.json`의 `llm.provider`)
`openai`(호환 서버 포함) · `openai-responses`(Responses API 모델) · `anthropic`. 키는 환경변수로 넣고 파일에 쓰지 않는다.

## 미검증 사항
도구별 폴더 인식 경로는 공식 문서 기준이며 도구 버전에 따라 다를 수 있다. 처음 쓸 때 시작 문구로 `core/rules.md`를 읽는지 확인한다.
