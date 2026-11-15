# AI Reliability 운영 가이드

DevFolio의 AI 딥 분석은 모델이 폐기되거나 Provider 장애가 나도 **품질 하한선을 지키며** 끝까지 갈 수 있게 설계되어 있다.
이 문서는 그 구조와 운영 방법을 정리한다.

## 1. 호출 구조

```
scan/git API
  └─ AIService.analyze_project_with_report()   ← 단계 상태 + 품질 리포트
       ├─ [scan]      git_scanner (결정론적, AI 미사용)
       ├─ [analysis]  _call() ─┬─ _call_messages()        ← Provider 순회
       │                       │    └─ _call_single_provider()  ← 모델 순회 · 재시도 · 차단
       │                       └─ _extract_json (validator)
       ├─ [cases]     _extract_problem_solving_cases()
       └─ [quality]   ai_quality.validate_analysis()      ← Level 1·2
```

**재시도 제어 지점은 `_call_single_provider` 하나뿐이다.** litellm 내부 재시도는 `max_retries=0`으로 꺼서
애플리케이션 재시도와 중첩되지 않게 한다.

## 2. 오류 분류와 정책

| 분류 | 판단 근거 | 같은 모델 재시도 | 모델 차단 | 다음 동작 |
|---|---|---|---|---|
| `model_gone` | `model_decommissioned`, 404, "does not exist" | ✗ | 영구 | 다음 모델 후보 |
| `auth` | 401/403, invalid api key | ✗ | 영구 | 다음 Provider |
| `bad_request` | 400, unsupported parameter, `limit: 0` | ✗ | 영구 | 다음 모델 후보 |
| `context` | context length/too many tokens | ✗ | 영구 | 다음 모델 후보 |
| `content_policy` | policy/safety | ✗ | 영구 | 다음 모델 후보(우회 목적 아님) |
| `rate_limit` | 429 | 1회 (백오프) | Cooldown | 소진 시 다음 Provider |
| `timeout` | timeout/408 | 1회 (백오프) | Cooldown | 다음 모델 후보 |
| `server` | 5xx, connection error | 1회 (백오프) | Cooldown | 다음 모델 후보 |
| `truncated` | `finish_reason=length` | ✗ | ✗ | 다음 모델 후보 |
| `json_invalid` | 스키마·파싱 실패 | ✗ | ✗ | 다음 모델 후보 |

- 백오프는 지수 + 지터이며 `Retry-After`가 있으면 그 값을 존중한다(상한 `DEVFOLIO_AI_MAX_BACKOFF`).
- 모든 대기는 **전체 시간 예산** 안에서만 허용된다. 예산을 넘기면 남은 후보를 건너뛴다.
- 일 단위 quota 소진(`quota` + `day`)은 기다려도 회복되지 않으므로 즉시 다음 Provider로 넘어간다.

## 3. Circuit Breaker (모델 상태)

- 저장 위치: 데이터 디렉터리의 `ai_model_health.json`
- 키 형식: `provider::model` (예: `groq::gemma2-9b-it`)
- 상태: 정상(CLOSED) / 차단(OPEN). Cooldown이 지나면 자동으로 다시 후보에 들어간다(HALF_OPEN).
- **영구 차단**은 프로세스를 재시작해도 유지된다(폐기 모델을 매번 다시 두드리지 않기 위함).
- 수동 해제:

```bash
# 컨테이너 안에서 저장 파일을 지우면 다음 호출부터 모두 재시도 대상이 된다
docker compose exec devfolio rm -f /root/.local/share/devfolio/ai_model_health.json
```

## 4. 품질 하한선

AI 호출이 성공해도 아래를 통과하지 못하면 **완료로 처리하지 않는다**(`analyzed: false`).

| Level | 검사 | 실패 시 |
|---|---|---|
| 1 | 필수 필드 존재·타입·비어 있지 않음, `tasks` 구조 | Hard Gate |
| 2 | `tech_stack`이 저장소 근거(README·의존성·언어·경로)에 존재 | 다수가 근거 없음 → Hard Gate, 소수는 경고 |
| 2 | 문장 속 수치(`42%`, `3배` 등)가 저장소에서 확인되는가 | Hard Gate (`unverified_metric`) |
| 2 | 중복된 task 이름 | 경고 |
| 3 | 기존 `ReviewResult` 심사(생성 경로) | 연결 시 Hard Gate |

- 점수는 보조 지표다. 근거 불일치·허위 수치는 점수와 무관하게 막는다.
- 판정은 AI가 아니라 코드가 한다 → 같은 입력이면 항상 같은 결과(테스트 가능).

## 5. 단계 상태와 열화 동작

단계 상태는 `pending / running / completed / partial / failed / skipped` 중 하나이며 API의 `ai_report.stages`로 노출된다.

| 상황 | 결과 |
|---|---|
| AI 성공 + 품질 통과 | `analyzed: true`, `ai_report.completed: true` |
| AI 성공 + 품질 실패 | `analyzed: false`, `ai_error`에 사유, 기본 스캔 결과만 사용 |
| AI 전부 실패 | `analyzed: false`, `stages.analysis: failed`, 스캔 단계는 `completed` 유지 |
| 사례 추출만 실패 | 나머지 결과는 유지, `stages.cases: skipped` |

**기본 스캔 결과를 AI 분석 결과처럼 표시하지 않는다.** 실패 시 `payload`는 비우고 화면에는 미완료로 표시한다.

## 6. 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DEVFOLIO_AI_TIME_BUDGET` | `90` | AI 호출 전체 시간 예산(초) |
| `DEVFOLIO_AI_MODEL_RETRIES` | `1` | 같은 모델에서의 추가 재시도 횟수 (0 = 재시도 없음) |
| `DEVFOLIO_AI_MAX_MODELS` | `3` | Provider당 후보 모델 수 상한 |
| `DEVFOLIO_AI_COOLDOWN` | `300` | 일시 장애 모델 차단 시간(초) |
| `DEVFOLIO_AI_MAX_BACKOFF` | `8` | 백오프 상한(초) |
| `DEVFOLIO_AI_PROVIDER_FALLBACK` | `1` | `0`이면 첫 Provider만 사용(자동 전환 OFF) |
| `DEVFOLIO_AI_ALLOW_THIRD_PARTY` | `1` | `0`이면 pollinations(외부 무료 서비스)로 데이터를 보내지 않음 |

## 7. 운영 절차

### 모델이 폐기되었을 때

1. 로그에서 `kind=model_gone` 또는 `400 model_decommissioned`를 확인한다.
2. 사용 가능한 모델 목록을 확인한다.

```bash
docker compose exec devfolio python -c "
import json, urllib.request
from devfolio.core.ai_service import get_api_key
req = urllib.request.Request('https://api.groq.com/openai/v1/models',
    headers={'Authorization': 'Bearer ' + get_api_key('groq'),
             'User-Agent': 'DevFolio/1.0'})
print(', '.join(sorted(m['id'] for m in json.load(urllib.request.urlopen(req, timeout=20))['data'])))
"
```

3. `devfolio/core/ai_service.py`의 `_GENERATION_SAFE_MODEL_REGISTRY`에서 해당 Provider 항목을 갱신한다.
4. 상태 파일을 지워 이전 차단 기록을 정리한다(위 3절).

### Fallback 후보 바꾸기

- 모델 후보: 위 레지스트리 튜플의 순서가 우선순위다. 앞에 둘수록 먼저 시도한다.
- Provider 순서: `_provider_fallback_chain()` — 명시 지정 → 기본 Provider → 설정된 나머지 → 내장 pollinations.

### 품질 기준 조정

- 필수 필드: `devfolio/core/ai_quality.py`의 `_REQUIRED_TEXT_FIELDS`, `_REQUIRED_LIST_FIELDS`
- 수치 검증: `_METRIC_PATTERN`
- 기술 스택 허용 기준: `_validate_tech_stack`의 "절반 이상" 규칙

### 장애 로그 확인

```bash
docker compose logs devfolio | grep -E "모델 차단|다음 후보|다음 Provider|미완료|시간 예산"
# AI 호출 이력(프롬프트 400자 미리보기 포함)
docker compose exec devfolio tail -20 /root/.local/share/devfolio/ai_logs.jsonl
```

운영 로그에는 프롬프트 전문을 남기지 않는다(DEBUG에서만 300/600자 미리보기).

## 8. 측정 결과 (2026-11-15, Docker / Groq 무료 등급)

| 항목 | 값 |
|---|---|
| E2E `/api/scan/git` (analyze=true) | 9.3초, `analyzed: true` |
| 사용 모델 | `groq/openai/gpt-oss-120b` (fallback 없음) |
| 품질 검증 | `passed`, 기술 스택 12/14 근거 확인 |
| 단일 분석 호출 | 4.0초 / 2,028자 (INC-21 측정) |
| 전 Provider 실패 시 | `completed: false`, 스캔 단계만 유지 |

측정하지 못한 항목: P95 지연, 요청당 비용(무료 등급), 장기 성공률, 동시 요청 부하.

## 9. 알려진 한계

- **pollinations는 클라이언트 `max_tokens`를 무시하고 1500 토큰에서 자른다.** 키 없는 기본 Provider로 긴 스키마를 요청하면
  잘림이 발생하고, 이제는 `truncated`로 감지되어 다른 후보로 넘어간다(조용히 깨진 JSON이 되지 않는다).
- 모델 목록은 정적 레지스트리 + 수동 갱신이다. Provider `/v1/models` 자동 동기화는 아직 없다.
- LiteLLM `Router`로 교체하지 않았다 — 기존 단일 제어 지점이 이미 테스트로 고정되어 있고, Router 도입은
  Provider 설정·키 주입 경로를 전면 교체해야 해서 이득보다 위험이 컸다. Router의 정책 시맨틱(재시도 금지 목록,
  `allowed_fails`/`cooldown_time`, `max_retries=0`)은 동일하게 구현했다.
- Level 3(심사)는 생성 경로(`generate_with_review`)에만 연결되어 있고, 코드 분석 경로는 Level 1·2로 판정한다.
