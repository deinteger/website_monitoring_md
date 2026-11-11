# 가이드라인 개정 반영 절차 (매년)

정책정보 확인 체크리스트와 「디지털 정부서비스 UI/UX 가이드라인」은 매년 개정된다. 규칙은 코드가 아니라 **데이터(`guidelines/`)**이므로,
개정판을 git에 올리고 아래 절차로 규칙팩을 갱신하면 코드 수정 없이 점검 기준이 바뀐다.

```
guidelines/
├─ index.json                    # 팩별 현재 버전 (여기를 바꾸면 점검 기준이 바뀐다)
├─ policy-week/<버전>/           # 정책정보 확인 점검 체크리스트
│   ├─ rules.json  meta.json  illegal-ad-keywords.txt  source/
└─ uiux/<버전>/                  # 디지털 정부 UI/UX 가이드라인
    ├─ rules.json  meta.json  source/(guideline.md, toc.json, [쪽 이미지])
```

## 절차

1. **원문 올리기**: 새 가이드라인(md 변환본: 쪽별 `## p.N` 제목 형식, 쪽 이미지는 선택)을 `guidelines/<팩>/<새버전>/source/`에 넣는다. 목차 색인은 `toc.json`.
   - UI/UX 가이드라인 변환본이 없으면 PDF를 쪽 단위 텍스트로 변환해 같은 형식으로 만든다 (기존 `guideline.md`의 형식 참고).
2. **새 버전 초안 만들기**: `python scripts/guidelines.py new <팩> <새버전> --from <이전버전>` — 이전 규칙을 모두 `draft`/`needs_review`로 복사한다.
3. **규칙 갱신 (에이전트 + 사람)**
   - 에이전트에게: "`guidelines/uiux/<새버전>/source`의 변경된 쪽을 읽고 `rules.json`을 갱신하라. 이전 버전 규칙(`prev_version_ref`)과 비교해 유지/변경/삭제/신규를 판단하라."
   - 원문은 필요한 쪽만 읽는다: `python scripts/guidelines.py pages uiux 220-232`, `--find 키워드`, 쪽 색인 `source/toc.json`.
   - **모든 규칙에는 근거 `source_page`(쪽)와 `source_quote`(원문 그대로의 인용문)를 적는다.** `validate`가 해당 쪽에 인용문이 실제 있는지 검증하므로 근거 없이 만든 규칙은 통과하지 못한다.
   - 점검 방식(`method`): 홈페이지로 확인 가능하고 판정이 명확하면 `auto`, 증거만 모을 수 있으면 `assist`, 계획 수립·화면 판단처럼 사람만 가능하면 `attest`. 근사 판정이면 `hint`에 한계를 쓴다.
   - 지원되는 검사 유형은 `scripts/policy_check.py`의 `CHECK_TYPES`. 새 요건이 기존 유형으로 표현되지 않으면 규칙을 `attest`로 두고 엔진 확장을 별도 과제로 기록한다 (규칙 데이터만으로 새 검사 로직이 생기지는 않는다).
4. **검증**: `python scripts/guidelines.py validate --pack <팩>` — 스키마, 중복 ID, 검사 유형, 원문 인용을 확인한다.
5. **개정 비교**: `python scripts/guidelines.py diff <팩> <이전버전> <새버전>` — 추가·삭제·변경·ID 변경 의심을 사람이 검토하고 보고서(월간·확인주간)의 변경 사항으로 쓴다.
6. **검수 완료 처리**: 사람이 규칙을 검토한 뒤 `needs_review`를 지우고 `status`를 `active`로, `meta.json`의 `reviewed`를 `true`로 바꾼다.
7. **전환**: `python scripts/guidelines.py use <팩> <새버전>` — 검증 오류나 `needs_review`가 남아 있으면 거부한다. 이어서 git에 커밋·배포한다.
8. **응답 재확인**: 사람 응답(`policy_check.py answer`)은 응답 당시의 규칙팩 버전과 함께 저장되며, 버전이 바뀌면 "이전 버전 응답: 재확인 필요"로 표시된다.

## 주의

- 규칙팩이 `reviewed: false`이면 결과 보고서에 주의 문구가 붙는다. 검수 전(`draft`) 규칙의 결과는 "참고"로만 표시되며 점검 결과로 인용하지 않는다.
- 자동 점검은 HTML에서 확인 가능한 요건만 다룬다. 색상·타이포·간격 등 스타일 규칙과 상호작용 요건은 `attest`(사람 확인)로 남긴다.
- 정책정보 확인 체크리스트의 네/아니오 응답은 담당자가 작성한다. 자동 결과는 근거 수집과 참고 판정이다.
- 원문 파일에 기관 내부 정보가 없는지 확인한 뒤 커밋한다. 쪽 이미지는 용량이 커서(약 30MB) 기본 배포에서 제외한다 (`source/` 폴더는 배포 패키지에 포함되지 않는다).
