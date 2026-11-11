# VS Code의 Cline에서 사용하기

## 동작 원리

- **규칙**: Cline은 프로젝트의 `.clinerules/`를 상시 규칙으로 읽는다. 이 키트는 `.clinerules/homepage-inspection.md`(요약)를 제공하며 원본은 `core/rules.md`다.
- **스킬**: Cline 문서는 스킬 폴더(`SKILL.md`)를 `.cline/skills/`, `.clinerules/skills/`, `.claude/skills/`에서 읽는다고 안내한다. 이 키트는 `.claude/skills/homepage-inspection/`이 이미 있어 **별도 복사 없이** 인식되는 것으로 본다 (같은 이름 스킬이 중복 로드되지 않도록 사본을 추가하지 않았다).
- `AGENTS.md`도 읽는 것으로 알려져 있으나 공식 문서가 아닌 2차 자료 기준이다.
- 위 내용은 문서·검색 결과에 근거한 것이며 **설치한 Cline 버전에서 확인 필요**하다. 스킬 기능은 Cline 설정에서 켜야 할 수 있다 (설정 위치는 버전별로 달라 **확인 필요**).

## 사용 순서

1. VS Code에서 이 폴더를 연다 (폴더를 작업 영역 루트로 열어야 상대경로 명령이 동작한다).
2. Cline의 API 공급자를 설정한다. OpenAI 호환 공급자의 Base URL·API 키·모델을 직접 지정할 수 있으므로 timelygpt를 쓰려면 발급 안내의 Base URL·모델명을 입력한다 (**호환 여부는 timelygpt 문서 확인 필요**).
3. 스킬이 보이지 않으면 첫 요청에 "`AGENTS.md`와 `core/skill-body.md`를 읽고 따르라"고 적는다. `.clinerules`가 있어 규칙은 자동 적용된다.
4. 온보딩 / 일상 점검 / 월간 보고 요청 문구는 `docs/pi-orca.md`의 예시를 그대로 쓸 수 있다.

## 권장 설정과 주의

- **명령 승인**: 자동 승인(Auto-approve)은 읽기·`scripts/` 실행까지만 켜고, 파일 삭제·외부 전송·설정 변경은 매번 승인한다. 이 키트의 스크립트는 사이트에 GET/HEAD 요청을 보내므로 처음에는 `--dry-run`과 `--limit 20`부터 승인하며 진행한다.
- **긴 점검**: 게시판이 수백 개면 점검이 수 분~수십 분 걸린다. Cline이 명령 종료를 기다리다 중단될 수 있으므로, **점검(`collect.py`)은 VS Code 터미널에서 직접 실행**하고 Cline에는 결과 파일의 판단·요약을 맡기는 방식을 권장한다.
- **토큰**: Cline은 읽은 파일을 컨텍스트에 싣는다. `ai-review-queue.json`과 `run-summary.json`만 읽게 하고 `cache.json`·`findings.json` 전체는 읽히지 않는다.
- 외부 AI(Cline에 설정한 모델)로 점검 내용이 전송된다. 기관 보안 승인 범위를 확인한다 (`docs/보안통보_요청서_양식.md` 6항).

## 참고 (확인한 출처)

- [Cline 스킬 문서](https://docs.cline.bot/features/skills), [Cline 규칙 안내(2차 자료)](https://fast.io/resources/cline-rules-guide/)
