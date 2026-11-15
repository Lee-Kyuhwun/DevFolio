# NVIDIA NIM Provider

기준일: 2026-11-16 · 검증 환경: macOS ARM64, Python 3.14.4, LiteLLM 1.103.2

## 1. 현재 상태

| 항목 | 결과 |
| --- | --- |
| Provider | `nvidia_nim` (LiteLLM) |
| Endpoint | `https://integrate.api.nvidia.com/v1` (직접 호출) |
| 인증 | `NVIDIA_NIM_API_KEY` (`nvapi-` 형식, 값 비노출) |
| 생성 모델 | `openai/gpt-oss-20b` |
| 독립 심사 모델 | `minimaxai/minimax-m3.1-flash` |
| 실제 호출 | **LIVE_VERIFIED** (2026-11-15, 2026-11-16 재확인) |
| OmniRoute | 저장소·설정·로그에서 사용 흔적을 확인하지 못함. **NOT_CONFIGURED** |

> 실제 호출은 최소 횟수로 수행했고, 키 값은 문서·로그·결과 파일에 기록하지 않았다.
> 모델 접근 가능 여부는 계정마다 다르므로 아래 목록은 **2026-11-16 이 계정에서 확인한 값**이다.
>
> 2026-11-16 재확인: `GET /v1/models` HTTP 200, 83개. `openai/gpt-oss-20b`,
> `minimaxai/minimax-m3.1-flash`, `z-ai/glm-5.3-flash` 존재. `meta/llama-3.3-70b-instruct`
> 는 목록에 없다. 실제 생성 3건은 3/3 성공, JSON 3/3, 평균 지연 87.8초
> (37.9–173.6초), prompt 2,275 / completion 3,965 토큰이었다. 비용은 `NOT_MEASURED`.

## 2. 과거 설정 조사 결과

조사 대상: `devfolio/`, `impactnote/`, `evals/`, Docker/Compose, `.env.example`,
Git 이력, 문서, 기존 평가 산출물.

- `nvidia_nim` 문자열과 `NVIDIA_NIM_API_KEY` 매핑은 `devfolio/core/ai_service.py`,
  `devfolio/utils/security.py`, `devfolio/commands/config.py` 에 존재했다.
- 기존 설정 모델 `nvidia_nim/meta/llama-3.3-70b-instruct` 는 **HTTP 410 Gone** 이었다.
- `nvidia/llama-3.1-nemotron-70b-instruct` 는 이 계정에서 **404** 였다.
- **OmniRoute** 설정·프록시 URL·호출 로그는 확인되지 않았다. 따라서 OmniRoute 를 사용했다고
  추정하지 않으며, 이번 검증도 직접 NVIDIA API 로 수행했다.
- 확인되지 않은 과거 호출 기록을 새로 만들지 않았다.

### 왜 OmniRoute 를 연결하지 않았나

- 재사용할 기존 OmniRoute 설정이 없었다.
- 현재 코드는 `nvidia_nim` 의 LiteLLM 기본 endpoint 를 사용하며, 별도 proxy base URL
  환경변수를 지원하지 않는다.
- 검증되지 않은 proxy 경로를 추가하면 키 전달·로깅·장애 분석 지점이 늘어난다.
- 따라서 **직접 API 경로만** 연결했고, OmniRoute 는 향후 별도 요구가 있을 때
  endpoint·인증·감사 로그를 먼저 검증한 뒤 추가해야 한다.

## 3. 확인된 모델

`GET /v1/models` 는 HTTP 200, 83개 모델을 반환했다. 그중 이 계정에서 실제 호출까지 확인한 것은
다음과 같다.

| 모델 ID | 용도 | 확인 |
| --- | --- | --- |
| `openai/gpt-oss-20b` | 성과 문장 생성, 평가 생성 | HTTP 200, JSON structured output |
| `minimaxai/minimax-m3.1-flash` | 독립 심사(claim/doc/quality) | HTTP 200 |
| `z-ai/glm-5.3-flash` | 심사 fallback | HTTP 200 |
| `meta/llama-3.3-70b-instruct` | 과거 설정 | HTTP 410 Gone — 사용 안 함 |
| `nvidia/llama-3.1-nemotron-70b-instruct` | 후보 | HTTP 404 — 사용 안 함 |

모델 목록은 영구적이지 않다. 새 환경에서는 먼저 `/v1/models` 와 짧은 호출로 확인한다.

```bash
test -n "$NVIDIA_NIM_API_KEY" || { echo "NVIDIA_NIM_API_KEY not set"; exit 1; }
curl -sS https://integrate.api.nvidia.com/v1/models \
  -H "Authorization: Bearer $NVIDIA_NIM_API_KEY" \
  | python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("data",[])))'
```

## 4. 코드 연결 지점

| 파일 | 역할 |
| --- | --- |
| `devfolio/core/ai_service.py` | LiteLLM 호출, 모델 정규화, JSON mode, telemetry, 재시도 |
| `devfolio/utils/security.py` | keyring → env → 파일 순 API 키 조회 |
| `devfolio/commands/config.py` | Provider 선택 UI/CLI |
| `impactnote/core/ai.py` | 동의 확인, 프롬프트, 근거 가드레일 |
| `evals/impact/judge.py` | 독립 심사 직접 호출, 캐시·재시도·fallback |

### 모델 이름 정규화

기존 설정에 `nvidia_nim/openai/gpt-oss-20b` 처럼 LiteLLM prefix 가 이미 붙어 있을 수 있다.
이때 다시 `nvidia_nim/` 를 붙이면 `nvidia_nim/nvidia_nim/...` 이 되어 실패한다.
`normalize_provider_model_name()` 이 prefix 를 한 번만 붙이도록 정규화한다.

### JSON 출력

NVIDIA NIM `/chat/completions` 는 `response_format={"type":"json_object"}` 를 지원한다.
코드는 `nvidia_nim` 을 JSON mode 지원 Provider 로 등록하고, 응답에서 JSON 객체를 추출·검증한다.

### 토큰·reasoning

`gpt-oss-20b` 는 reasoning 토큰을 사용한다. LiteLLM 1.103.2 의 `nvidia_nim` 은
`reasoning_effort` 파라미터를 지원하지 않으므로 전달하지 않고, `max_tokens` 를 최소 2048로
보정한다. 너무 낮은 한도는 JSON이 잘려 실패할 수 있다.

### Telemetry

호출 결과에는 provider, model, latency, usage(prompt/completion/total tokens)가 남는다.
API 키와 원문 프롬프트는 결과 파일에 남기지 않는다.

## 5. 설정 방법

### 5.1 키 주입

가장 단순한 방법은 환경변수다. `.env.example` 을 복사해 `.env` 를 만들고 값을 채운다.
`.env` 는 `.gitignore` 대상이며 Docker 이미지에도 복사하지 않는다.

```bash
cp .env.example .env
# .env 편집: NVIDIA_NIM_API_KEY=nvapi-...
```

또는 실행 셸에서만:

```bash
export NVIDIA_NIM_API_KEY="$(cat /path/to/private/keyfile)"
```

키를 채팅·이슈·커밋·스크린샷에 붙이지 않는다. 이 저장소의 문서와 평가 결과에는 키가 없다.

### 5.2 앱 설정

1. `impactnote serve` 로 UI 를 연다.
2. **설정 → 외부 AI 전송 동의**를 켠다.
3. 허용 Provider 에 `nvidia_nim` 을 지정하거나 비워 둔다.
4. 기본 Provider 를 `nvidia_nim` 으로 선택한다.
5. 짧은 업무 기록 1건으로 AI 분석을 실행해 결과와 오류를 확인한다.

키가 없으면 AI 분석은 실패하지만 기록·성과·근거·보고서·프로젝트 분석의 비-AI 기능은
그대로 동작한다.

### 5.3 Docker

```bash
NVIDIA_NIM_API_KEY=... docker compose up -d --build
```

Compose 는 키를 컨테이너 환경변수로 전달한다. 키를 `docker-compose.yml` 에 직접 쓰지 않는다.
Docker 에서 keyring 을 쓸 수 없으므로 환경변수 주입을 권장한다.

## 6. 실제 검증 기록

| 검증 | 결과 |
| --- | --- |
| `/v1/models` | HTTP 200, 83개 |
| 직접 `gpt-oss-20b` 호출 | HTTP 200, JSON, prompt 100 / completion 364, reasoning 241 |
| LiteLLM `nvidia_nim/openai/gpt-oss-20b` | 성공, 17.9초, JSON, usage 95 / 224 |
| 평가 생성 3회 | 3/3 `LIVE_VERIFIED`, 평균 145,844ms, prompt 1,966 / completion 2,795 |
| JSON schema | 3/3 통과 |
| 수치 가드레일 | raw unsupported number 7.1% → 저장 0.0%, 1건 대체 |
| 금지 주장 hit | 0 |

평가 결과 전체는 [`evaluation-results.md`](evaluation-results.md).

## 7. Rate Limit·비용·오류

- 무료 NIM 계정은 분당 요청 한도가 있다. 평가 중 `429` 와 `503`(safety screening)이 발생했고,
  `judge.py` 는 429/503 에 백오프 후 재시도하며 503 은 `z-ai/glm-5.3-flash` 로 fallback 한다.
- 이번 실행의 실제 청구 금액은 확인하지 않았다. **비용은 `NOT_MEASURED`** 이며, 토큰 사용량만
  기록했다. 무료 크레딧·계정 정책은 NVIDIA 콘솔에서 확인해야 한다.
- 긴 응답(최대 307초)이 관찰됐다. 애플리케이션 호출에는 시간 예산과 재시도 제한이 있다.

자주 보는 오류:

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| 401 | 키 없음/오타 | `NVIDIA_NIM_API_KEY` 확인, 키 재발급 |
| 404 | 모델 ID 오류/접근 불가 | `/v1/models` 로 실제 ID 확인 |
| 410 | 모델 서비스 종료 | 목록에서 제거, 대체 모델 사용 |
| 429 | 요청 한도 | 백오프, 호출량 축소 |
| 503 | safety screening/일시 장애 | 재시도 또는 심사 fallback |
| JSON 파싱 실패 | 출력 잘림/형식 위반 | `max_tokens` 상향, JSON mode 확인 |

## 8. 보안·감사

- 키 조회 우선순위: OS keyring → 환경변수 → `api_keys.json`(0600). Docker 는 환경변수 권장.
- `api_keys.json`, `.env`, `*.pem`, `*.key` 는 gitignore 대상이다.
- 평가 결과에는 키·원문 프롬프트·회사 식별 정보를 저장하지 않는다.
- 외부 AI 전송은 앱 설정의 명시적 동의가 있어야 한다.
- 프록시(OmniRoute 등)를 추가할 경우 키 전달 경로와 로그 마스킹을 별도로 감사해야 한다.

## 9. 알려진 제한

- 계정별 모델 접근 권한이 달라 문서의 목록만 믿으면 안 된다.
- `gpt-oss-20b` 는 reasoning 토큰 때문에 지연·비용이 커질 수 있다.
- 생성 모델과 심사 모델이 같은 NVIDIA 호스팅에 있어 완전 독립 평가가 아니다.
- 정성 효과 주장은 결정론 Gate 가 검증하지만, 효과 주장이 아닌 기능 존재·의미 반대·귀속·용량 주장은 검증하지 못한다.
- 모델 간 품질 A/B는 이번 라운드에서 수행하지 않았다(`NOT_MEASURED`).
- OmniRoute 경유는 현재 코드에서 지원·검증되지 않았다.
