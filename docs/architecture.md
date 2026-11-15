# ImpactNote 시스템 아키텍처

기준일: 2026-11-16 · 버전: 1.0.0 · 기준 커밋: `dd4d64f` (문서 커밋 직전)

> 다이어그램 10개는 [`architecture/diagrams.md`](architecture/diagrams.md),
> 수치·효과 Claim 검증 상세는 [`architecture/claim-validation.md`](architecture/claim-validation.md).

이 문서는 현재 코드(`impactnote/`, `devfolio/`, `evals/impact/`)를 기준으로 한다. DevFolio 시절의
설계 기록은 [`04-architecture.md`](04-architecture.md) 와 [`superpowers/`](superpowers/) 에
역사 자료로 남아 있다.

## 1. 한 문장 구조

ImpactNote 는 **로컬 JSON 저장소 + FastAPI 웹 UI + Typer CLI + 읽기 전용 프로젝트 분석기 +
선택적 LiteLLM AI 계층**으로 구성된 단일 사용자 로컬 우선 애플리케이션이다.

```text
┌──────────────────────────── 사용자 ────────────────────────────┐
│  웹 UI (바닐라 JS)                  CLI (impactnote / devfolio) │
└───────────────┬──────────────────────────────┬─────────────────┘
                │ HTTP /api                    │ 함수 호출
        ┌───────▼────────┐              ┌──────▼─────────┐
        │ FastAPI router │              │  Typer 명령     │
        │ impactnote/web │              │ impactnote/main│
        └───────┬────────┘              └──────┬─────────┘
                └──────────────┬────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │ ImpactService       │  도메인 유스케이스
                    │ impactnote/core     │
                    └──┬───────┬───────┬──┘
                       │       │       │
          ┌────────────▼─┐ ┌───▼────┐ ┌▼──────────────────┐
          │ JSON Store    │ │ Report │ │ Intel Analyzer     │
          │ 원자적 쓰기    │ │ Engine │ │ 문서·코드·Git diff  │
          └──────────────┘ └────────┘ └─────────┬──────────┘
                                                │ 선택: 동의 시
                                      ┌─────────▼──────────┐
                                      │ AI 계층             │
                                      │ impactnote/core/ai │
                                      │ → devfolio AIService│
                                      │ → LiteLLM Provider  │
                                      └────────────────────┘
```

## 2. 실행 진입점

| 진입점 | 위치 | 역할 |
| --- | --- | --- |
| 웹 UI | `impactnote serve` → `impactnote/web/app.py` | 정적 UI + `/api` 라우터 |
| 신규 CLI | `impactnote` → `impactnote/main.py` | 기록·성과·보고서·프로젝트 분석 |
| 레거시 CLI | `devfolio` → `devfolio/main.py` | 기존 명령·설정 호환 |
| 레거시 API | `devfolio/web/app.py` | 기존 DevFolio 엔드포인트 호환 |
| 평가 하네스 | `python -m evals.impact.run` | Ground Truth 기반 AI 평가 |

`impactnote` 와 `devfolio` 는 같은 설치 패키지에 공존한다. 신규 제품은 `impactnote` 를 사용하고,
`devfolio` 는 마이그레이션·기존 데이터·기존 API 호환을 위해 유지한다.

## 3. 도메인 데이터 흐름

```text
Activity (사실 기록)
   │
   ├─ 수동 성과 생성 ──────────────┐
   ├─ Git 커밋 후보 ───────────────┤
   ├─ AI 분석 (동의 필요) ─────────┤
   └─ 프로젝트 분석 후보 ──────────┤
                                   ▼
                             Achievement
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
                 Evidence        Metric         Report
                 (근거)          (검증 지표)     (기간·템플릿)
```

- **Activity**: 사용자가 입력한 사실. AI 가 실패해도 변경되지 않는다.
- **Achievement**: 해석·요약. 상태는 `user_input`, `needs_review`, `partially_verified`,
  `verified`.
- **Evidence**: PR·티켓·로그·문서·회의록 등. `verified` 는 사람이 확인한 것만.
- **Metric**: 값·단위·기간·산출 기준·근거가 모두 있어야 `verified`.
- **Report**: 기간·템플릿·본문·파일·버전·제출 상태. 재생성 시 버전이 증가한다.

## 4. 프로젝트 분석과 Evidence Graph

`impactnote/core/intel/` 는 프로젝트 경로를 **읽기 전용**으로 조사한다.

1. `discovery.py` — 경로 allowlist 검증, 문서·코드·테스트 파일 탐색, `.env`·키 파일 제외.
2. `gitintel.py` — `git log`/diff, merge parent, co-author trailer, 리버트 판정.
3. `docextract.py` — MD/TXT/HTML/JSON/YAML/CSV/DOCX/XLSX/PPTX/PDF 텍스트 추출.
4. `engine.py` — 코드 심볼·라우트·문서 주장 교차 분석, 성과 후보 생성, 근거 연결.
5. `models.py` — 후보·근거·품질 라벨(`VERIFIED`, `SUPPORTED_INFERENCE`, `HYPOTHESIS`,
   `INSUFFICIENT_EVIDENCE`)과 co-author 필드.

Evidence Graph 는 별도 그래프 DB가 아니라 **후보 ID → 근거 ID/파일 경로/커밋 SHA/문서 인용**의
참조 집합이다. 보고서·AI 프롬프트·평가 하네스가 같은 참조를 사용한다.

핵심 원칙:

- 카테고리 매칭은 단어 경계를 사용한다. 예: `ci` 가 `asyncio` 에 매칭되지 않는다.
- 커밋 메시지의 키워드만으로 성과를 확정하지 않는다. 실제 diff·현재 코드·테스트를 본다.
- 리버트된 변경, 측정 근거 없는 개선율은 후보에서 제외하거나 `HYPOTHESIS` 로 낮춘다.
- 분석 결과는 `needs_review` 로 저장되고, 사람이 확인해야 보고서 본문에 들어간다.

## 5. 수치·근거 가드레일

`impactnote/core/metrics.py`:

- `40%`, `3.5시간`, `12건`, `2배` 같은 **숫자+단위**를 claim 으로 추출한다.
- 원본 기록·근거 텍스트에 같은 숫자가 없으면 `[확인 필요]` 로 치환한다.
- `sanitize_ai_result()` 는 문자열뿐 아니라 **중첩 dict/list** (`statements.monthly`,
  `contribution.decisions` 등)까지 재귀적으로 검사한다. 2026-11-15 평가에서 중첩 필드가
  가드레일을 우회한 결함을 수정한 뒤 추가된 동작이다.
- 보고서 본문에는 `Metric.verified == True` 인 지표만 사용하고, 나머지는 부록으로 보낸다.

`impactnote/core/claims.py`:

- “안정성 향상”, “비용 절감”, “응답 시간 단축” 같은 **정성 효과 주장**을 문장 단위로 추출한다.
- 근거 문장에 같은 대상+효과 표현이 있거나, 수치+단위가 일치할 때만 통과시킨다.
- “측정되지 않음/기록 없음”은 명시적 미지원으로 처리한다.
- 차단된 문장은 삭제하고 `unverified_effects` 에 사유를 남긴다(보류·감사 가능).
- AI 저장(`ai.py`), 프로젝트 분석(`intel/ai_stage.py`), 보고서(`report.py`)에 연결된다.
- 보고서는 AI·분석·Git 이 만든 성과에만 적용하고, 사용자가 직접 쓴 성과는 보존한다.
- 수치 비교는 `(값, 정규화 단위)` 쌍으로 한다. `80%`는 `80ms`로 통과하지 않는다.

이 Gate 는 효과 주장만 대상으로 한다. 기능 존재·의미 반대·기여 귀속·용량 주장은
여전히 별도 검증이 필요하며, [`research/hallucination-root-cause.md`](research/hallucination-root-cause.md)
와 [`evaluation/hallucination-experiments.md`](evaluation/hallucination-experiments.md) 에
미해결 범위를 기록했다.

## 6. AI Provider 계층

```text
impactnote.core.ai.analyze_activity()
  ├─ Settings.external_ai_consent 확인 (기본 차단)
  ├─ allowed_providers / default_provider 확인
  ├─ 프롬프트 구성 (Activity + 연결된 Evidence)
  └─ devfolio.core.ai_service.AIService._call()
       ├─ LiteLLM provider/model 선택
       ├─ 재시도·백오프·Rate Limit·cooldown
       ├─ JSON mode·출력 완결성·언어 필터
       ├─ telemetry (provider, model, usage, latency)
       └─ 실패 시 AIAnalysis.status = failed (원본 불변)
```

- Provider 키는 `devfolio/utils/security.py` 의 3단계 폴백(OS 키체인 → 환경변수 →
  설정 디렉터리 파일)으로 읽는다. 값은 로그·결과·문서에 남기지 않는다.
- NVIDIA NIM 은 `nvidia_nim` provider 로 연결되어 있다. 상세 설정은
  [`nvidia-provider.md`](nvidia-provider.md).
- AI 분석은 별도 `analyses.json` 에 저장되며, 사용자가 “성과 후보로 저장”을 눌러야 성과가 된다.

## 7. 저장소와 보안 경계

- 데이터·설정 경로는 `platformdirs` 기반이며 `IMPACTNOTE_DATA_DIR`,
  `IMPACTNOTE_CONFIG_DIR` 로 재정의한다.
- 컬렉션별 JSON 파일, 임시 파일 + `os.replace` 원자적 쓰기, 파일 권한 `0600`.
- 분석 경로는 `IMPACTNOTE_ANALYZE_ROOTS` allowlist 안으로 제한한다. Docker 기본값은
  `/app:/home/user`.
- `.env`, `api_keys.json`, 키 파일은 `.gitignore`·`.dockerignore` 대상이다.
- 외부 AI 전송은 설정의 명시적 동의가 있어야 하며, 평가 하네스도 Provider fallback 을 끈다.

## 8. 배포·CI

- **로컬**: Python 3.11+ 가상환경, `pip install -e ".[all]"`, `impactnote serve`.
- **Docker**: `Dockerfile` (python:3.12-slim, WeasyPrint·CJK 폰트·git 포함),
  `docker-compose.yml` (127.0.0.1 바인딩, 데이터 볼륨, 선택적 저장소 마운트).
- **CI**: `.github/workflows/ci.yml`
  - Python 3.11–3.14 테스트 + lint/format
  - Ubuntu/macOS/Windows Python 3.12 테스트
  - AI 키 없이 Docker 이미지 빌드·health check
- **수동 AI 평가**: `.github/workflows/ai-eval.yml` — `NVIDIA_NIM_API_KEY` 가 없으면
  live 평가를 건너뛰고 CI 를 실패시키지 않는다.

## 9. 평가 계층

`evals/impact/` 는 제품 코드와 분리된 평가 하네스다.

- `dataset.json` — 동결된 Ground Truth (claim 42, doc-code 12, 성과 12 + 비성과 8,
  귀속 8, live 3).
- `fixture.py` — 통제 Git 저장소를 매 실행마다 임시 생성.
- `metrics.py` — P/R/F1, hallucination, bootstrap CI.
- `judge.py` — 생성 모델과 다른 NVIDIA 심사 모델, 캐시·재시도·fallback.
- `run.py` — 오케스트레이터, 사전 고정 임계값, Markdown/JSON 보고서.
- `results/latest.json` — 민감한 원문을 제외한 최신 집계 결과.

평가 구조와 지표 정의는 [`ai-evaluation.md`](ai-evaluation.md), 실제 결과는
[`evaluation-results.md`](evaluation-results.md) 에 있다.

## 10. 알려진 경계

- 단일 사용자·로컬 파일 저장. 다중 사용자 권한·클라우드 동기화는 없다.
- PDF 는 시스템 폰트·변환 도구에 의존한다.
- 문서-코드 판정은 심볼/라우트 기반이라 한국어 서술형 문서를 보수적으로 분류할 수 있다.
- 대형 저장소는 코드 500개·문서 160개 상한으로 일부만 분석한다.
- AI 의 정성 효과 주장과 다중 평가자 일치도는 아직 자동 검증 범위 밖이다.
