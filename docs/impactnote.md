# 성과노트(ImpactNote) 설계 문서

## 1. 왜 DevFolio 를 성과노트로 바꿨나

DevFolio 는 "개발자 포트폴리오/이력서 생성기"였습니다. 하지만 회사 업무에서 실제로 반복되는 문제는
문서 양식이 아니라 **기록의 소실과 근거의 부재**였습니다.

- 성과평가 시즌에 "무슨 일을 했는지" 기억나지 않는다.
- 숫자를 쓰고 싶지만 출처를 댈 수 없다.
- 팀 성과와 개인 기여가 섞여 과장처럼 보인다.
- 매번 같은 내용을 다른 양식으로 다시 쓴다.

성과노트는 이 네 가지를 제품 구조로 해결합니다: **빠른 기록 → 구조화된 성과 → 근거 연결 → 기간별 보고서**.

## 2. 제품 흐름

```
업무 기록(Activity) ──┐
                      ├─→ 성과(Achievement) ─→ 근거(Evidence) ─→ 지표(Metric)
Git 커밋 / AI 분석 ───┘                                   │
                                                          ▼
                                   기간 선택 → 템플릿 → 보고서(Report) → MD/DOCX/PDF/TXT/CSV
                                                          │
                                                          ▼
                                                  제출 이력(버전·상태)
```

- **Activity**: 제목·설명·날짜·프로젝트·유형·문제/행동/결과. 제목+설명만으로 저장 가능.
- **Achievement**: 기록을 묶어 만든 성과. 상태는 `user_input`, `needs_review`, `partially_verified`, `verified`.
- **Evidence**: PR·티켓·로그·문서·회의록·대시보드·기타. `verified` 는 사람이 확인한 근거만.
- **Metric**: 이름·값·단위·기간·산출 기준·근거. 네 요소가 모두 있어야 `verified`.
- **Report**: 기간·템플릿·본문·파일·버전·제출 상태. 같은 기간/템플릿 재생성 시 버전이 증가한다.
- **AIAnalysis**: 원본 기록을 건드리지 않는 별도 분석 결과. 적용은 사용자가 명시적으로 선택한다.

## 3. 수치 가드레일

`impactnote/core/metrics.py`

1. 본문에서 `40%`, `3.5시간`, `12건`, `2배` 같은 숫자+단위 주장을 찾는다.
2. 해당 주장의 숫자가 원본 텍스트(기록·근거·지표)에 존재하는지 대조한다.
3. 없으면 `[확인 필요]` 로 치환하고 `unverified_metrics` 에 남긴다.
4. 보고서 본문에는 `Metric.verified == True` 인 지표만 쓴다. 나머지는 "확인 필요 항목" 부록으로 보낸다.

즉, AI 가 그럴듯한 숫자를 만들어도 문서에 그대로 들어갈 수 없습니다.

## 4. AI 안전장치

`impactnote/core/ai.py`

- `Settings.external_ai_consent` 가 `False` 면 `EXTERNAL_AI_NOT_ALLOWED` 로 거부한다(기본값).
- `allowed_providers` 가 비어 있지 않으면 해당 Provider 만 사용한다.
- 프롬프트는 회사 내부 보고 문체를 요구하고, 마케팅·자기소개서 말투와 근거 없는 수치를 금지한다.
- `AIService._call` 실패(레이트리밋·타임아웃·파싱 오류)는 `AIAnalysis.status = "failed"` 로 저장하고 원본 기록은 그대로 둔다.
- Git 수집은 AI 없이 커밋 메시지·변경량으로 결정론적 후보를 만들고 `needs_review` 로 둔다.
- AI/Git 후보는 사용자가 "확인했습니다"를 체크(`confirmed=true`)하기 전까지 `verified` 로 올라가지 않는다.

## 5. 저장소

`impactnote/core/store.py`

- `platformdirs` 기반 데이터/설정 경로, `IMPACTNOTE_*` 환경변수로 재정의.
- 컬렉션별 JSON, 임시 파일 + `os.replace` 원자적 쓰기, 파일 권한 `0600`.
- 모델 변경은 Pydantic 기본값으로 흡수되므로 기존 JSON 과 호환된다.
- 레거시 DevFolio 경로는 읽기 전용으로만 접근한다(마이그레이션 원본).

## 6. DevFolio 마이그레이션

`impactnote/core/migrate.py`

1. 레거시 데이터 디렉터리를 ZIP 으로 백업한다.
2. 레거시 프로젝트의 각 작업(Task)을 업무 기록으로 만든다. `source_ref = legacy:<project>:<task>` 로 멱등.
3. 문제/해결/결과가 있는 작업은 성과 후보로 만들고 `source="migration"`, `needs_review=True` 로 둔다.
4. `migration.json` 에 지문을 남겨 재실행 시 `already_migrated` 를 반환한다. `--force` 로 재실행 가능.
5. 원본 YAML/JSON 은 수정·삭제하지 않는다.

## 7. API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/health`, `/api/meta` | 상태·브랜드·선택지 |
| GET | `/api/dashboard` | 기간별 집계·확인 필요 항목 |
| CRUD | `/api/activities` | 업무 기록 |
| CRUD | `/api/achievements` | 성과, `/from-activities` 로 기록 묶기 |
| POST | `/api/achievements/{id}/evidence`, `/metrics` | 근거·지표 연결 |
| CRUD | `/api/evidence`, `/api/metrics` | 근거·지표 |
| POST | `/api/ai/analyze`, `/api/ai/analyses/{id}/apply` | AI 분석·후보 저장 |
| POST | `/api/git/import` | 커밋 → 기록·후보 |
| GET/POST/PATCH | `/api/reports`, `/api/reports/{id}/download` | 보고서 생성·이력·다운로드 |
| GET/PUT | `/api/settings` | 설정·AI 동의 |
| POST | `/api/migrate` | DevFolio 이전 |

## 8. 검증

- `tests/test_impactnote.py`: 기록 CRUD, 성과·근거 상태, 지표 검증, Git 후보, AI 동의/실패/수치 세탁, 기간 집계,
  템플릿·버전, 다운로드, 마이그레이션 멱등·원본 보존, 파일 권한, 브랜드 문자열.
- 기존 `tests/` 401개는 레거시 호환 계층(`devfolio`) 검증으로 유지한다(전체 431개).
- `scripts/check.sh`, CI(`.github/workflows/ci.yml`), `tox.ini` 가 `impactnote/` 를 lint·커버리지 대상에 포함한다.
- Docker: `docker compose up -d --build` 후 `http://localhost:8000` (서비스명 `impactnote`, 컨테이너 `devfolio-impactnote-1`).
- 검증 완료: 컨테이너 내 E2E(기록→성과→근거→지표→DOCX/MD 보고서), 마이그레이션 멱등·백업·원본 불변, 브라우저 흐름.

## 9. 범위 밖 / 남은 개선

- 다중 사용자·권한·클라우드 동기화는 없다(로컬 단일 사용자 전제).
- PDF 는 기존 ExportEngine 의 변환 경로를 재사용하므로 시스템 폰트/변환 도구에 의존한다.
- Git 후보 분류는 커밋 메시지 기반 규칙이라 프로젝트별 튜닝 여지가 있다.
- DOCX 표 스타일·회사별 양식 커스터마이징은 템플릿 확장 지점으로 남겨 두었다.
