# Agent D — Attribution Auditor

감사일: 2026-11-15 · 대상: `impactnote/core/intel/gitintel.py`,
`impactnote/core/intel/engine.py`, `evals/impact/fixture.py`

## 범위

- Git author/committer/co-author/merge를 구분하는가
- 공동 기여를 단독 기여로 표시하지 않는가
- 여러 개발자 저장소에서 개인 귀속이 정확한가
- 근거 없는 귀속을 UNKNOWN으로 두는가

## 확인한 증거

- `gitintel.py`가 `%(trailers:key=Co-authored-by)`를 파싱하고 `co_authors`에 저장.
- merge 판정은 `%P` parent 수를 사용.
- `engine.py`가 작성자와 co-author에게 contribution credit을 분배.
- `fixture.py`에 Alice/Bob/Carol/Manager, 공동 수정, merge, co-author trailer,
  revert, 비성과 변경이 포함됨.
- `pytest` 타깃:
  - `test_fixture_extracts_achievements_and_coauthor_attribution`
  - `test_other_developer_contribution_is_not_attributed`
  - `test_ai_sanitizes_problem_and_unattributed_numbers`
  → **3 passed**
- 전체 평가: exact attribution 8/8 = **100%**, coverage 100%, wrong-solo 0%.

## 발견 사항

1. **UNKNOWN 처리**: 리뷰만 한 경우, 대리 커밋, 이슈 담당자 기여는 정답에서 제외했다.
   100%는 “모든 협업 유형을 맞혔다”는 뜻이 아니다.
2. **합성 저장소**: 8개 단위는 실제 회사 저장소의 복잡한 권한·PR·리뷰 기록을 대표하지 않는다.
3. **committer != author**: 현재 fixture는 author/committer가 같은 경우가 많다. 다른 사람이
   커밋을 대신 작성한 경우는 정답에서 UNKNOWN으로 제외됐다.
4. **merge commit**: merge parent 판정은 테스트됐지만, GitHub squash merge의 PR 메타데이터는
   로컬 Git만으로 알 수 없다.

## 결론

현재 8개 단위에서 **PASS**이며, co-author와 공동 기여를 단독으로 표시하는 오류는 발견되지
않았다. 리뷰·설계·대리 커밋·PR 메타데이터는 미검증 범위다.
