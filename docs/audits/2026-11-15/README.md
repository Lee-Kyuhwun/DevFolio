# 2026-11-15 독립 감사 보고서

이 디렉터리는 6개 역할(A–F)의 **역할 분리 감사** 결과를 보관한다.

| 역할 | 보고서 | 초점 |
| --- | --- | --- |
| A | [A-evaluation.md](A-evaluation.md) | 지표·분모·표본·산술·임계값 |
| B | [B-nvidia.md](B-nvidia.md) | NVIDIA 모델·Endpoint·실호출·키·Rate Limit |
| C | [C-semantic.md](C-semantic.md) | 인용 근거의 Semantic Entailment |
| D | [D-attribution.md](D-attribution.md) | 공동 기여·co-author·merge 귀속 |
| E | [E-portability.md](E-portability.md) | Clean Clone·Docker·CI·OS |
| F | [F-documentation.md](F-documentation.md) | README·문서·명령·링크 일치 |

## 독립성에 대한 정직한 표기

이 감사들은 **동일 세션에서 역할을 분리해 수행한 검증**이다. 서로 다른 인간 감사자나
별도 모델 에이전트가 독립적으로 작성한 보고서가 아니다. 따라서 “외부 독립 감사”라고
부르지 않는다. 각 보고서는 가능한 한 다른 증거(데이터 재계산, 실제 호출, 테스트, Docker,
링크 검사)를 사용했지만, 동일 작업자의 편향 가능성은 남는다.

발견된 결함과 잔여 위험은 [`../../final-report-2026-11-15.md`](../../final-report-2026-11-15.md)
에 통합했다. 수정 후 재검증은 전체 `pytest` 465개와 Docker health로 수행했다.

## 감사 후 남은 주요 위험

- Hallucination 47.6% FAIL, 품질 사실성 2.65/5 FAIL
- 사람 평가자 간 일치도 NOT_MEASURED
- Windows/macOS 실제 GUI NOT_MEASURED
- GitHub 원격 push 후 CI 실행 NOT_MEASURED
- OmniRoute NOT_CONFIGURED
- 비용 NOT_MEASURED
