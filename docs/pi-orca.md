# pi 에이전트와 Orca에서 사용하기

## 동작 원리

- **pi**는 프로젝트의 `AGENTS.md`를 시작 시 읽고, 프로젝트의 `.agents/skills/` 또는 `.pi/skills/`에 있는 Agent Skills(`SKILL.md`)를 자동으로 인식한다 (pi 문서 기준. 버전에 따라 경로가 바뀔 수 있어 **설치한 pi 버전의 문서로 확인 필요**).
- **Orca**는 Claude Code·Codex·pi 등 CLI 에이전트를 워크트리별로 실행하는 데스크톱 앱이다. 모델 접근을 자체 제공하지 않고 각 에이전트에 설정한 계정·키를 쓴다. pi를 Orca에서 실행하면 pi와 동일하게 이 저장소의 `AGENTS.md`와 스킬을 읽는다.
- 이 키트는 이미 `AGENTS.md`와 `.agents/skills/homepage-inspection/SKILL.md`를 갖추고 있어 **별도 변환 없이** 위 경로로 인식된다.

## 사용 순서

1. 키트 폴더를 Orca의 프로젝트(저장소)로 추가한다 (git 저장소여야 워크트리 기능을 쓸 수 있다. 아니면 `git init` 후 첫 커밋).
2. pi 에이전트를 새 세션으로 연다. pi에서 사용할 모델·API 키는 pi 설정에서 지정한다 (timelygpt 등 OpenAI 호환 엔드포인트 사용 가능 여부는 pi의 커스텀 공급자 설정과 **timelygpt 문서 확인 필요**).
3. 스킬 인식 확인: pi에서 스킬 목록에 `homepage-inspection`이 보이는지 확인한다. 보이지 않으면 첫 프롬프트에 "`AGENTS.md`와 `core/skill-body.md`를 읽고 따르라"고 적으면 동일하게 동작한다.
4. 첫 사용(온보딩):

   ```text
   homepage-inspection 스킬로 이 사이트를 온보딩하라. 시작 주소는 https://대상주소/ 이고 시스템명은 "OO"이다.
   core/onboarding.md 절차대로 workspace/site-profile.json을 만들고, 각 게시판은 --probe로 검증한 결과를 요약해 보여달라.
   ```

5. 일상 점검:

   ```text
   homepage-inspection 스킬로 증분 점검을 하라. 먼저 --dry-run 요청량을 알려주고, 이후 점검을 실행해 ai-review-queue 항목을 판단한 뒤 요약을 작성하라.
   ```

6. 월간 보고:

   ```text
   homepage-inspection 스킬로 지난달 월간 보고를 작성하라 (monthly_report.py 실행 후 AI 종합 의견 작성).
   ```

## 주의

- 에이전트가 직접 판단하면 모델 호출 비용이 pi에 설정한 키/구독에서 소모된다. 항목 수가 많으면(전체 점검) `ai-review-queue` 상위 항목부터 판단하고 나머지는 점검 한계에 기록하게 한다.
- 에이전트 대신 스크립트가 API로 직접 판단하게 하려면 `docs/운영가이드.md`의 `judge.py`/`run_all.py`를 쓴다 (Orca 없이도 가능).
- 외부 AI 서비스 전송은 기관 보안 승인 후에만 한다. 에이전트에게 `workspace/`의 내용을 외부로 보내는 작업을 시키지 않는다.
- 워크트리를 여러 개 쓰면 `workspace/`가 워크트리마다 따로 생긴다(커밋되지 않음). 캐시·이력이 이어지도록 점검은 **한 워크트리(또는 저장소 루트)에서만** 실행한다.

## 참고 (확인한 출처)

- [pi 코딩 에이전트 문서(미러)](https://cdn.jsdelivr.net/npm/@mariozechner/pi-coding-agent@0.64.0/docs/skills.md), [Orca 소개](https://www.onorca.dev/docs) — 위 설명은 이 자료와 검색 결과에 근거하며, 설치 버전과 다를 수 있다.
