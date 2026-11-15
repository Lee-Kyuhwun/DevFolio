# Agent B — NVIDIA Integration Auditor

감사일: 2026-11-15 · 대상: `devfolio/core/ai_service.py`, `devfolio/utils/security.py`,
`evals/impact/judge.py`

## 범위

- 실제 Provider·모델 ID·Endpoint·인증이 코드와 일치하는가
- 실제 호출 성공·JSON·토큰·지연이 기록되었는가
- 키가 저장소·결과·로그에 노출되지 않았는가
- Rate Limit·fallback·폐기 모델 처리가 문서와 일치하는가

## 확인한 증거

1. 키 상태: `get_api_key("nvidia_nim")`가 값을 반환했고 `nvapi-` 형식이었다.
   **키 값은 출력하지 않았다.**
2. `GET https://integrate.api.nvidia.com/v1/models` → **HTTP 200, 83개**.
   `openai/gpt-oss-20b`, `minimaxai/minimax-m3.1-flash`, `z-ai/glm-5.3-flash` 목록 확인.
3. 실제 생성 3회: 3/3 `LIVE_VERIFIED`, JSON 3/3, prompt 1,966 / completion 2,795,
   평균 145,844ms, 최대 307,546ms.
4. 실제 심사: `minimaxai/minimax-m3.1-flash` HTTP 200. 429/503 백오프·fallback 코드 확인.
5. 폐기/접근 불가: 기존 `meta/llama-3.3-70b-instruct` HTTP 410, `nvidia/llama-3.1-nemotron-70b-instruct` HTTP 404.
6. 키 노출 스캔: `nvapi-...`/`sk-...` 패턴 파일 없음, `.env`·`api_keys.json`·judge 캐시 tracked 없음.
7. CI workflow YAML parse OK. AI eval은 키가 없으면 skip하고 실패하지 않음.

## 판정

**직접 NVIDIA NIM 연결: PASS (LIVE_VERIFIED).**

## 발견 사항

- **OmniRoute는 NOT_CONFIGURED**: 저장소·설정·로그에서 흔적이 없어 사용하지 않았다.
  현재 코드는 proxy base URL을 지원하지 않으므로 “OmniRoute 경유 가능”이라고 주장하지 않는다.
- **비용은 NOT_MEASURED**: 실제 청구 금액을 확인하지 않았다. 토큰 사용량만 기록했다.
- **Rate Limit의 정확한 한도는 NOT_MEASURED**: 429/503 발생과 대응만 확인했다.
- `gpt-oss-20b`는 reasoning 토큰과 긴 지연이 있어 평가 비용·시간이 크다.
- 생성 모델과 심사 모델이 같은 NVIDIA 호스팅이므로 완전 독립은 아니다.

## 결론

키·모델·Endpoint·JSON·오류 대응은 실제 호출로 검증됐다. 다만 비용·한도·OmniRoute는
검증 범위 밖이며, 문서에 그대로 표기했다.
