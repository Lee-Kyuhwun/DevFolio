# 테스트 및 검증 가이드

기준일: 2026-11-15

## 1. 테스트 계층

| 계층 | 위치 | 검증 내용 | 외부 호출 |
| --- | --- | --- | --- |
| 단위·통합 | `tests/` | 도메인·API·저장·보고서·분석기·AI 실패 처리 | 없음 |
| 평가 회귀 | `tests/test_impact_eval.py` | Ground Truth 로더, P/R/F1, 수치 가드레일, fixture | 없음 |
| Offline 평가 | `evals/impact/run.py --offline` | 결정론 기준선·분석기·문서-코드 | 없음 |
| Live 평가 | `evals/impact/run.py --live` | 실제 NVIDIA 생성 3회 + 독립 심사 | 있음 |
| Clean Clone | 새 디렉터리 + 새 venv | 설치·테스트·CLI·Docker·health | 없음 |
| CI | `.github/workflows/ci.yml` | 3.11–3.14, 3 OS, Docker | 없음(키 미사용) |

## 2. 로컬 전체 테스트

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"

pytest -q
```

2026-11-15 기준:

```text
481 passed
```

`pytest` 기본 설정은 `--cov=impactnote --cov=devfolio` 를 포함한다. 커버리지 없이 빠르게:

```bash
pytest -q -p no:cacheprovider --no-cov
```

### 자주 쓰는 타깃

```bash
pytest -q tests/test_impactnote.py
pytest -q tests/test_intel.py
pytest -q tests/test_impact_eval.py tests/test_intel.py tests/test_ai_service.py
pytest -q tests/test_impact_eval.py::test_numeric_guardrail_reaches_nested_statements
```

### 정적 검사

```bash
ruff check impactnote/ devfolio/ tests/ evals/
ruff format --check impactnote/ devfolio/ tests/ evals/
bash scripts/check.sh          # lint + format + pytest -x
```

`scripts/check.sh` 는 `set -e` 이므로 한 단계라도 실패하면 중단한다. 파이프로 출력을
자를 때는 `set -o pipefail` 을 사용해 실제 종료 코드를 보존한다.

## 3. 평가 하네스 테스트

`tests/test_impact_eval.py` 는 다음을 고정한다.

- Ground Truth 파일의 필수 키·라벨·표본 수
- Precision/Recall/F1 계산과 0 분모 처리
- Hallucination combined rate 정의
- Bootstrap CI 결정론(seed)
- `sanitize_ai_result()` 의 **중첩 dict/list** 수치 가드레일
- fixture Git 저장소의 co-author·merge·revert 시나리오
- 임계값 사전 고정 및 판정 문자열

실행:

```bash
pytest -q tests/test_impact_eval.py
```

## 4. Offline 평가 (키 불필요)

```bash
python -m evals.impact.run --offline --no-judge --out /tmp/impact-offline
```

- 결정론 분석기로 성과 후보·귀속·문서-코드를 실행한다.
- Judge 가 없으므로 semantic/quality 는 `NOT_MEASURED` 로 남는다.
- 수치 가드레일·fixture·리포트 생성 경로를 빠르게 확인할 때 쓴다.

저장된 심사 캐시가 있으면 judge 를 재호출하지 않고 재계산할 수 있다.

```bash
python -m evals.impact.run --offline --out /tmp/impact-recheck
```

캐시는 `evals/impact/.cache/judge.json` 이며 gitignore 대상이다. 캐시를 지우면 실제
NVIDIA 호출이 발생한다.

## 5. Live NVIDIA 평가

```bash
export NVIDIA_NIM_API_KEY=...          # 값을 셸 밖으로 출력하지 않는다
export DEVFOLIO_AI_PROVIDER_FALLBACK=0 # 다른 Provider 로 새지 않게 차단
python -m evals.impact.run --live --out /tmp/impact-live
```

특징:

- 생성 모델 `nvidia_nim/openai/gpt-oss-20b`, 심사 `minimaxai/minimax-m3.1-flash`.
- 3개 live 활동을 실제 호출한다. 느리고(수십 초~수 분) 무료 한도·비용이 발생할 수 있다.
- 심사 429/503 은 백오프·대체 모델을 사용한다.
- 결과 JSON/Markdown 에 provider·model·usage·latency·판정이 남는다. 키는 남지 않는다.
- AI 키가 없으면 실행하지 말고 offline 으로 검증한다.

결과 예시와 해석은 [`evaluation-results.md`](evaluation-results.md).

## 6. Clean Clone 검증

새 디렉터리에서 **기존 `.venv`·`.env`·데이터·키체인을 사용하지 않고** 실행한다.

```bash
rsync -a --exclude=.git --exclude=.venv --exclude=.env ./ /tmp/impactnote-clean/
cd /tmp/impactnote-clean
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev,all]"
.venv/bin/pytest -q -p no:cacheprovider --no-cov
```

CLI 핵심 흐름:

```bash
export IMPACTNOTE_DATA_DIR=/tmp/impactnote-clean-data
export IMPACTNOTE_CONFIG_DIR=/tmp/impactnote-clean-config
.venv/bin/impactnote init
.venv/bin/impactnote activity add "clone 검증" --desc "새 환경 확인"
.venv/bin/impactnote report generate --template weekly --period week --format md
```

Docker:

```bash
IMPACTNOTE_PORT=18000 docker compose -p impactnote-clean up -d --build
curl -fsS http://127.0.0.1:18000/api/health
docker compose -p impactnote-clean logs --tail=50 impactnote
docker compose -p impactnote-clean down
```

검증할 것:

- 설치가 네트워크·캐시에 의존해 우연히 성공하지 않는가
- `.env` 없이 health·기록·보고서가 동작하는가
- 데이터 디렉터리가 새 환경에서 생성되는가
- Docker 포트·볼륨·저장소 마운트가 호스트 경로에 고정되지 않았는가

2026-11-15 Clean Clone: 새 venv 설치, **465 passed**.
2026-11-16 전체: **481 passed**. 별도 디렉터리 clean copy 에서도 481 passed.
Docker: `docker build` 성공 후 `serve --host 0.0.0.0` 로 기동, `/api/health` HTTP 200.
상세는 결과 문서에 기록했다. Windows 실제 GUI 는 아직 미검증이다.

## 7. CI

`.github/workflows/ci.yml`:

| Job | 내용 |
| --- | --- |
| `test` | Ubuntu, Python 3.11/3.12/3.13/3.14, 전체 pytest + coverage |
| `portability` | Ubuntu/macOS/Windows, Python 3.12, 전체 pytest |
| `docker` | 이미지 빌드, AI 키 없이 컨테이너 실행, `/api/health` 확인 |
| `lint` | ruff check + format check |

`.github/workflows/ai-eval.yml` 은 **수동 실행**이다. `NVIDIA_NIM_API_KEY` secret 이 없으면
live 평가를 건너뛰고 실패하지 않는다. 키가 있는 경우에만 실제 호출·결과 artifact 업로드.

```text
GitHub → Actions → AI Evaluation (manual) → Run workflow
```

CI 는 GUI 클릭·실제 Windows 앱 창·PDF 렌더링 품질을 검증하지 않는다. 그 범위는 별도 수동
검증이 필요하다.

## 8. 검증하지 않은 것

- 사람 2인 이상의 평가자 간 일치도
- 실제 회사 저장소의 언어·도메인 분포에서의 일반화
- Windows/macOS 실제 GUI 클릭 흐름
- 모든 OS/아키텍처의 PDF 폰트 렌더링
- OmniRoute 경유 NVIDIA 호출
- 정성 효과 주장은 Gate 로 검증하지만, 기능 존재·의미 반대·귀속·용량 주장은 자동 검증하지 못함

이 항목은 통과로 표시하지 않고 [`evaluation-results.md`](evaluation-results.md) 의 한계에
기록한다.
