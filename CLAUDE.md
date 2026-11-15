# 성과노트 (ImpactNote) — CLAUDE.md

회사 업무 기록·근거 관리·제출용 성과보고서 도구. 제품 본체는 `impactnote/`,
기존 DevFolio 자산은 `devfolio/` 호환 계층으로 유지한다.

**전체 규칙은 `AGENTS.md` 를 따른다.** 아래는 빠른 참조다.

## Ponytail FULL

- 기본은 Ponytail **FULL** 이다. 원문은 `docs/ponytail/` (MIT, commit `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`).
- 요구사항을 완전히 충족하는 가장 작은 변경, 기존 코드 재사용, 불필요한 추상화·의존성 금지를 적용한다.
- 검증·보안·접근성·오류 처리·제품 가드레일은 단순화 대상이 아니다.
- Review/Audit/Debt/Gain은 `AGENTS.md`의 절차로 수동 재현하고, 플러그인 런타임을 실행했다고 주장하지 않는다.

## 워크플로우

- 로컬 `main` 에서 직접 작업하고, 완료 후 `git push origin main`
- 커밋 메시지는 한국어로 "무엇을 왜" 바꿨는지, AI 작성 커밋은 `Co-Authored-By:` 트레일러
- `claude/*` 등 자동 브랜치를 만들지 않는다

## 명령어

```bash
make check                                  # ruff + format + pytest -x
pytest tests/test_impactnote.py -q --no-cov # 성과노트 회귀
impactnote serve                            # http://127.0.0.1:8000
docker compose up -d --build
impactnote migrate                          # DevFolio 이전 (백업·멱등)
```

## 구조

```
impactnote/core/   models, store(JSON 0600), service, periods, metrics, ai, report, migrate
impactnote/web/    FastAPI API + static SPA
impactnote/main.py Typer CLI
devfolio/          레거시 YAML/CLI/API/export_engine/ai_service (읽기·재사용)
```

## 지켜야 할 것

- Pydantic `model_validate()` / `model_dump()` 사용, YAML 은 `ruamel.yaml`
- 무거운 의존성(docxtpl, weasyprint, litellm)은 함수 내 lazy import, 파일 권한 `0600`
- 근거 없는 수치는 `[확인 필요]` 로 치환하고 보고서 본문에는 검증 지표만 사용
- AI 는 설정 동의(`external_ai_consent`)와 허용 Provider 를 통과해야 하며 기본 차단
- AI/Git 후보는 `confirmed=true` 전까지 `verified` 금지, AI 실패 시 원본 불변
- DevFolio 데이터는 읽기 전용, 이전은 ZIP 백업 후 멱등 실행
- 장애·에이전트 실수 수정 시 `docs/agent-incidents.md` 와 `test_incNN_` 회귀 테스트를 같은 커밋에 추가
- API 키 평문 로그·커밋 금지, export 경로 `../` 금지, HTML 사용자 데이터 이스케이프

## 데이터 경로

`~/.local/share/impactnote` (설정 `~/.config/impactnote`), `IMPACTNOTE_DATA_DIR` 로 재정의.
DevFolio 원본은 `IMPACTNOTE_LEGACY_DATA_DIR` 로 읽기 전용 접근.
