# 검색엔진 인덱스 링크 점검 (구글·네이버·다음)

검색엔진에 남은 오래된 URL(삭제 페이지, 404, 소프트 404, 메인으로 튕김, 깨진 이미지)을 찾는다.
**URL 수집은 에이전트 브라우저(또는 공식 API, 사람이 복사)가, 접속 점검은 스크립트가 한다.** 안전 원칙은 `core/rules.md`와 같다.

1. `workspace/site-profile.json`의 `allowed_domains`를 읽는다.
2. 브라우저로 각 엔진에서 `site:<도메인>`을 검색해 결과 URL(과 검색결과 제목)을 엔진별 파일로 저장한다 (로그인 금지, 광고 링크 제외, 도메인당 최대 30~50개).
   - 구글 `https://www.google.com/search?q=site:<도메인>`, 네이버 `https://search.naver.com/search.naver?query=site:<도메인>`, 다음 `https://search.daum.net/search?q=site:<도메인>`
   - 파일 형식: 한 줄에 `URL<탭>검색결과제목` (예: `workspace/index/google.txt`)
   - 캡차·차단이 뜨면 그 엔진은 중단하고 사유를 기록한다. 우회하지 않는다.
3. 스크립트로 점검한다.

   ```bash
   python scripts/check_index_links.py --workspace workspace --dry-run --input google=workspace/index/google.txt --input naver=workspace/index/naver.txt --input daum=workspace/index/daum.txt
   python scripts/check_index_links.py --workspace workspace --check-images --input google=workspace/index/google.txt --input naver=workspace/index/naver.txt --input daum=workspace/index/daum.txt
   ```

4. 결과 `workspace/runs/YYYY-MM-DD/search-index-links.csv`(판정: 정상, 404오류, 소프트404, 리다이렉트오류, 빈페이지의심, 깨진이미지, 제목불일치 등)와 `search-index-summary.json`을 읽고, `빈페이지의심`·`제목불일치`·`리다이렉트오류` 항목은 브라우저로 열어 실제 화면을 확인한다 (읽기 전용).
5. 브라우저 화면 확인 중 CSS 깨짐 등 렌더링 오류를 발견하면 비고에 사실만 적는다 (스크립트는 렌더링을 보지 못한다).
6. 검색엔진이 `site:` 결과를 제한하면 수집한 범위만 점검하고 제한 사유를 요약에 기록한다. 이 점검은 게시판 점검의 신규·지속·해결 이력과 별도 파일로 관리한다.
