# 원본 보관 (디지털 정부서비스 UI/UX 가이드라인 2025.08)

- `guideline.md` : 원문 PDF(1,181쪽)를 쪽별 텍스트로 변환한 md (사용자 제공). `## p.N` 제목으로 쪽을 구분하고 각 쪽 이미지를 연결한다.
- `digital_gov_guideline_pages/page_0001.jpg` ... `page_1181.jpg` : 쪽 이미지(1,181장, 약 34MB). md의 이미지 링크가 이 폴더로 연결된다.
  AI가 화면 비교·시각 규칙(색상·간격·아이콘 등)을 검토할 때 해당 쪽 이미지를 직접 열어 본다.
- `toc.json` : 목차 색인(항목·시작쪽·끝쪽). 에이전트는 필요한 쪽만 읽는다 (`python scripts/guidelines.py pages uiux 220-232`).
- 이 `source/` 폴더는 용량이 커서 **배포 패키지(make_release, 채팅용 스킬 zip)에는 포함되지 않는다.** 저장소에서만 쓴다.
- 개정판이 나오면 새 버전 폴더(`guidelines/uiux/<버전>/source/`)에 같은 방식으로 넣고 `core/guideline-update.md`를 따른다.
