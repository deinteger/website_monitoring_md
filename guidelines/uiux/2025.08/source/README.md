# 원본 보관 (디지털 정부서비스 UI/UX 가이드라인 2025.08)

- `guideline.md` : 원문 PDF(1,181쪽)를 쪽별 텍스트로 변환한 md (사용자 제공). `## p.N` 제목으로 쪽을 구분한다.
- `toc.json` : 목차 색인(항목·시작쪽·끝쪽). 에이전트는 필요한 쪽만 읽는다 (`python scripts/guidelines.py pages uiux 220-232`).
- 쪽 이미지(`digital_gov_guideline_pages/page_0001.jpg` ... 1,181장, 약 30MB)는 저장소 크기 때문에 포함하지 않았다.
  md의 이미지 링크를 살리려면 이 폴더에 `digital_gov_guideline_pages/`를 두면 된다 (git에 올릴지는 담당자가 결정).
- 개정판이 나오면 새 버전 폴더(`guidelines/uiux/<버전>/source/`)에 같은 방식으로 넣고 `core/guideline-update.md`를 따른다.
