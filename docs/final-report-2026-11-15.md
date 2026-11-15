# Phase 16 — 최종 결과 보고 (2026-11-15)

대상: ImpactNote 1.0.0 · 기준 커밋 `48e35fc` + 이번 작업 트리 변경
평가 데이터: `impactnote-ai-eval-1.0.0`

## A. 미측정 지표 해결 현황

| 평가 항목 | 기존 | 이번 측정 | 표본 수 | 결과 |
| --- | --- | --- | ---: | --- |
| Hallucination Rate (combined) | 미측정 | **47.6%** (95% CI 33.3–61.9%) | 42 claims | **FAIL** |
| 성과 발굴 Precision / Recall / F1 | 미측정 | **1.00 / 1.00 / 1.00** | 12 TP + 8 negative | **PASS** |
| 성과 문장 품질 | 미측정 | 평균 **3.68/5**, 사실성 **2.65/5**, 저사실성 **55%** | 20 | **FAIL** |
| 개인 기여 귀속 | 미측정 | exact **100%**, coverage **100%**, wrong-solo **0%** | 8 | **PASS** |
| 문서·코드 의미 일치 | 미측정 | accuracy **83.3%**, macro F1 **0.839**, false MATCH **0%** | 12 | **PASS** |
| Semantic Entailment | 미측정 | accuracy **83.3%**, macro F1 **0.710**, unsupported citation **0%**, contradiction recall **100%** | 42 | **PASS** |

정의:

- Hallucination combined = (NEUTRAL + INSUFFICIENT_EVIDENCE + CONTRADICTION) / N.
- 품질 FAIL은 평균이 아니라 **사실성 하한** 때문이다. 평균 3.68은 3.5를 넘지만,
  factual 2.65 < 3.0, 저사실성 55% > 25%다.
- 미측정: 사람 평가자 간 일치도, 정성 효과 자동 검증, 비용, Windows GUI, PDF 시각 품질.

## B. NVIDIA 실제 검증

| 항목 | 결과 |
| --- | --- |
| Provider | `nvidia_nim` (LiteLLM 1.103.2) |
| Endpoint | `https://integrate.api.nvidia.com/v1` 직접 |
| 생성 모델 | `openai/gpt-oss-20b` |
| 심사 모델 | `minimaxai/minimax-m3.1-flash` |
| 모델 목록 | HTTP 200, 83개 |
| 기존 설정 모델 | `meta/llama-3.3-70b-instruct` HTTP 410 → 제거 |
| 실제 생성 | 3/3 `LIVE_VERIFIED`, JSON 3/3 |
| 토큰·지연 | prompt 1,966 / completion 2,795, 평균 145,844ms, 최대 307,546ms |
| 가드레일 | raw unsupported number 7.1% → 저장 0.0%, 1건 `[확인 필요]` 대체 |
| 금지 주장 | 0 |
| OmniRoute | **NOT_CONFIGURED** — 설정·로그 흔적 없음, 미사용 |
| 비용 | **NOT_MEASURED** — 청구서 미확인 |

수정한 결함:

- `nvidia_nim/` prefix 중복 방지 및 모델명 정규화
- 폐기 모델 대신 `openai/gpt-oss-20b` 등록
- JSON mode 지원 목록에 NVIDIA 추가
- `gpt-oss` reasoning 대응 `max_tokens >= 2048`
- `NVIDIA_NIM_API_KEY` 매핑·Provider 선택
- telemetry usage 기록

## C. 다른 PC 실행 가능성

| 항목 | 결과 |
| --- | --- |
| 새 디렉터리 Clone | PASS (로컬 새 Git 저장소) |
| 새 venv 설치 | PASS (`Python 3.14.4`, `pip install -e ".[dev,all]"`) |
| 테스트 | **465 passed** |
| AI 키 없이 CLI | PASS: init → 기록 → 주간 보고서 → 조회 |
| Docker | PASS: build + `127.0.0.1:18001` `/api/health` |
| Docker core API | PASS: 기록 생성, 보고서 생성, AI 동의 없음 409 |
| GitHub 원격 Clean Clone | **NOT_MEASURED** — push하지 않음 |
| Windows/macOS GUI | **NOT_MEASURED** |
| Linux 실제 배포 | **NOT_MEASURED** — CI/Docker health로 대체 |

이번에 고친 이식성 결함:

- macOS 기본 Python 3.9.6에서 설치 실패 → 3.11+ 안내
- Docker 포트 `IMPACTNOTE_PORT`로 변경 가능
- `REPOS_DIR` 기본값을 현재 디렉터리로 변경
- `.env`·키 파일 gitignore/dockerignore
- 선택적 AI 키 환경변수 문서화

## D. 코드 수정 결과

| 영역 | 파일 | 수정 |
| --- | --- | --- |
| NVIDIA | `devfolio/core/ai_service.py` | 모델 정규화·JSON·토큰·telemetry |
| 키 | `devfolio/utils/security.py` | `NVIDIA_NIM_API_KEY` |
| 설정 | `devfolio/commands/config.py` | NVIDIA Provider |
| 분석기 | `impactnote/core/intel/engine.py` | 카테고리 경계, 후보 상한 14, co-author 귀속 |
| Git | `impactnote/core/intel/gitintel.py` | trailer 파싱, merge `%P` |
| 모델 | `impactnote/core/intel/models.py` | `co_authors` |
| 가드레일 | `impactnote/core/metrics.py` | **중첩 dict/list 수치 검사** |
| 평가 | `evals/impact/*` | dataset·fixture·metrics·judge·run·archive·results |
| 테스트 | `tests/test_impact_eval.py`, `tests/test_intel.py` | 평가·가드레일·귀속 회귀 |
| 배포 | `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`, CI | 이식성·보안 |

기존 미커밋 변경(`report.py`, `main.py`, `api.py`, `discovery.py`, `ai_stage.py`,
`pyproject.toml`, `Dockerfile` 등)은 보존했으며 이번 작업의 성과로 새로 주장하지 않는다.

## E. 문서 최신화

새로 작성:

- [`architecture.md`](architecture.md)
- [`ai-evaluation.md`](ai-evaluation.md)
- [`nvidia-provider.md`](nvidia-provider.md)
- [`installation.md`](installation.md)
- [`testing.md`](testing.md)
- [`evaluation-results.md`](evaluation-results.md)
- [`audits/2026-11-15/`](audits/2026-11-15/)
- 이 최종 보고서

수정:

- `README.md` — NVIDIA, 평가, Clean Clone, 465 테스트, 문서 지도
- `docs/README.md` — 현재 문서 인덱스
- `docs/impactnote.md` — 중첩 가드레일, 465 테스트, 평가 링크
- `.env.example` — 실제 키 없는 환경 템플릿

오래된 DevFolio 문서(`04-architecture.md` 등)는 삭제하지 않고 역사 자료로 보존했다.

## F. 최종 품질 판단

**CONDITIONAL PASS — AI 품질은 FAIL.**

- 엔지니어링: 평가 하네스, 실제 NVIDIA 호출, 결함 수정, Clean Clone, Docker, 문서, 465 테스트는
  검증됐다.
- AI 신뢰성: Hallucination 47.6%와 품질 사실성 2.65/5는 회사 내부 성과보고에 그대로 쓰기
  어렵다. 수치 가드레일이 저장 단계에서 숫자를 막지만, 정성 효과 주장은 여전히 사람이
  확인해야 한다.
- 전체 판정이 `CONDITIONAL PASS`인 이유는 실패 지표가 2개이기 때문이며, **통과**를 뜻하지
  않는다.

### 다음 우선순위

1. 정성 효과 주장(“향상/절감/보장”)에 대한 근거 요구 또는 `[확인 필요]` 표시
2. 현재 프롬프트로 품질 표본을 늘려 Historical 20개와 분리 평가
3. 사람 평가자 2인 이상의 품질·의미 일치 일치도 측정
4. GitHub push 후 CI(3 OS·Docker·Python 3.11–3.14) 실제 실행
5. Windows/macOS GUI 및 PDF 렌더링 수동 검증
6. Semantic 결과에 claim별 예측·이유 저장

## G. 검증 명령·증거

```bash
bash scripts/check.sh                 # lint + format + 465 passed
pytest -q tests/test_impact_eval.py   # 평가 회귀
python -m evals.impact.run --live     # 실제 NVIDIA 평가
docker compose -p impactnote-clone2 up -d --build
curl -fsS http://127.0.0.1:18001/api/health
```

- 전체 테스트: **465 passed**
- 실제 평가: `/tmp/impact-eval-live6/impact-results.json` (원문 포함, 커밋하지 않음)
- 집계: [`../evals/impact/results/latest.json`](../evals/impact/results/latest.json)
- 6개 감사: [`audits/2026-11-15/`](audits/2026-11-15/)

## H. 명시적 한계

- 이 감사는 동일 세션의 역할 분리 감사이며, 별도 인간/모델 에이전트의 외부 감사가 아니다.
- GitHub 원격 push·CI 실행은 하지 않았다.
- 커밋·푸시도 하지 않았다.
- 측정하지 않은 값을 0이나 100%로 바꾸지 않았다.
