# 성과노트(ImpactNote) 프로젝트 컨텍스트

기준일: 2026-11-15
버전: 1.0.0

## 목적

회사 업무를 빠르게 기록하고, 근거로 확인한 성과만 남기고, 제출용 성과보고서로 재사용한다.
"문서를 잘 쓰는 도구"가 아니라 **기록 → 성과 → 근거 → 보고서**의 흐름을 강제하는 로컬 우선 도구다.

## 핵심 원칙

1. 기록(Activity)과 해석(Achievement)을 분리한다.
2. 근거 없는 수치를 만들지 않는다. 숫자+단위 주장은 기록·근거 텍스트와 대조하고, 확인되지 않으면 `[확인 필요]` 로 바꾼다.
3. 팀 성과를 개인 성과로 부풀리지 않는다. 직접/공동 수행과 의사결정 기여를 분리한다.
4. 외부 AI 전송은 설정에서 동의한 경우에만, 허용 Provider 로만 수행한다(기본 차단).
5. 원본 데이터는 지우지 않는다. DevFolio 이전은 ZIP 백업 후 멱등 실행하며 원본은 읽기만 한다.

## 기술

- Python 3.11+, Typer, Pydantic v2, FastAPI, platformdirs
- 저장: 컬렉션별 JSON(원자적 쓰기, `0600`)
- 문서: Markdown/DOCX/PDF/TXT/CSV (기존 `devfolio/core/export_engine.py` 재사용)
- AI: 기존 `devfolio/core/ai_service.py` + `ai_reliability`/`ai_observability` 재사용, 결과는 별도 저장

## 구조

```
impactnote/            # 현재 제품 본체
├── core/              # models, store, service, periods, metrics, ai, report, migrate
├── web/               # FastAPI API + SPA(static/)
└── main.py            # Typer CLI (impactnote)

devfolio/              # 호환 계층: 기존 CLI/API/데이터/내보내기/AI 신뢰성 자산
tests/                 # 431 tests (impactnote 30 + devfolio 401)
docs/impactnote.md     # 설계·가드레일·API·마이그레이션
```

## 실행

```bash
docker compose up -d --build      # http://localhost:8000
impactnote serve                  # 로컬
impactnote migrate                # DevFolio 데이터 이전
scripts/check.sh                  # ruff + format + pytest -x
```

## 현재 단계

1.0.0 전환 완료: 도메인·API·화면·CLI·Docker·문서·회귀 테스트·브라우저 검증까지 마쳤고
`main` 에 커밋·푸시된 상태다. 다음 개선은 아래 "남은 개선"을 참고한다.

## 제약

로컬 main 직접 작업, 기존 DevFolio 데이터 보존, 유료 AI 호출 전 확인, 회귀 검증이 핵심 제약이다.
세부 작업 규칙은 `AGENTS.md` 에 있다.

## 완료 기준

사용자 문제 재현·수정, `scripts/check.sh` 통과, Docker 기동·주요 흐름 확인, 장애·결정 기록 갱신.

## 남은 개선

- 지표 검증이 "값이 기록·근거 텍스트에 존재"를 요구해, URL 근거만 있는 지표는 확인 절차가 더 필요하다.
- PDF 렌더링은 시스템 폰트/변환 도구 의존성 검증이 남아 있다(컨테이너에서 DOCX 는 확인).
- Git 후보 분류 규칙의 프로젝트별 튜닝, 다중 사용자·클라우드 동기화는 범위 밖이다.
