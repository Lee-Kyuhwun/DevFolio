# ImpactNote 아키텍처 다이어그램

기준: 2026-11-16 · 코드 `main` (문서 커밋 직전 `dd4d64f`)
대상: `impactnote/`, `devfolio/`, `evals/impact/`

> 다이어그램은 실제 코드 구조를 기준으로 한다. 구현에 없는 컴포넌트는 넣지 않았다.
> 점선은 선택 기능(외부 AI 동의, 수동 평가)을 뜻한다.

## 범례

| 표기 | 의미 |
| --- | --- |
| 실선 | 항상 실행되는 경로 |
| 점선 | 설정·동의·수동 실행이 있어야 하는 경로 |
| `[확인 필요]` | 근거 없는 수치를 대체하는 표시 |
| HYPOTHESIS | 근거가 부족해 확정하지 않은 후보 |

---

## Diagram 1. System Context

```mermaid
flowchart LR
    User["사용자<br/>개발자·실무자"] --> UI["웹 UI<br/>impactnote/web/static"]
    User --> CLI["CLI<br/>impactnote / devfolio"]
    UI --> API["FastAPI<br/>/api"]
    CLI --> Core["ImpactService"]
    API --> Core["ImpactService"]

    Core --> Store["로컬 JSON 저장소<br/>platformdirs · 0600"]
    Core --> Report["보고서 엔진<br/>MD·DOCX·PDF·TXT·CSV"]
    Core --> Intel["프로젝트 분석기<br/>읽기 전용"]
    Intel --> Repo["분석 대상 Git 저장소"]
    Core -. "동의한 경우에만" .-> AI["AI Provider<br/>NVIDIA NIM 등"]
    Eval["평가 하네스<br/>evals/impact"] -. "수동 실행" .-> AI
    Eval --> Dataset["동결 Ground Truth<br/>dataset.json"]
```

- 사용자 데이터는 기본적으로 로컬에만 저장된다.
- 외부 전송은 `Settings.external_ai_consent`가 켜져야 한다.
- 분석 대상 저장소는 `IMPACTNOTE_ANALYZE_ROOTS` allowlist 안에서만 읽는다.

## Diagram 2. Container / Component Architecture

```mermaid
flowchart TB
    subgraph Entry["진입점"]
        Web["impactnote/web/app.py"]
        Api["impactnote/web/api.py"]
        Cli["impactnote/main.py"]
        Legacy["devfolio/ (호환 계층)"]
    end

    subgraph Domain["도메인"]
        Service["core/service.py<br/>ImpactService"]
        Models["core/models.py<br/>Pydantic 모델"]
        Periods["core/periods.py"]
    end

    subgraph Guard["검증·생성"]
        Metrics["core/metrics.py<br/>수치·단위 검증"]
        Claims["core/claims.py<br/>정성 효과 Gate"]
        Report["core/report.py"]
        Ai["core/ai.py"]
    end

    subgraph Intelligence["프로젝트 인텔리전스"]
        Discovery["intel/discovery.py"]
        GitIntel["intel/gitintel.py"]
        Engine["intel/engine.py"]
        AiStage["intel/ai_stage.py"]
    end

    subgraph Platform["기반"]
        Store["core/store.py<br/>JsonStore"]
        AiService["devfolio/core/ai_service.py<br/>LiteLLM·재시도·Fallback"]
        Observability["devfolio/core/ai_observability.py"]
    end

    Web --> Api --> Service
    Cli --> Service
    Legacy --> Service
    Service --> Models
    Service --> Periods
    Service --> Store
    Service --> Report
    Service --> Ai
    Service --> Engine
    Ai --> Metrics --> Claims
    Report --> Metrics
    Report --> Claims
    Engine --> Discovery
    Engine --> GitIntel
    Engine --> AiStage
    AiStage --> Claims
    Ai --> AiService
    AiService --> Observability
```

- `service.py`가 CRUD·상태 계산의 단일 진입점이다.
- `metrics.py`와 `claims.py`는 저장·보고서 양쪽에서 재사용된다.
- `devfolio/`는 삭제하지 않고 Provider·내보내기·레거시 API 호환에 사용한다.

## Diagram 3. Project Intelligence Pipeline

```mermaid
flowchart LR
    Input["프로젝트 경로"] --> Validate["validate_project_path<br/>allowlist · symlink 제외"]
    Validate --> Discover["문서·코드·테스트 탐색"]
    Discover --> Docs["문서 추출<br/>MD·PDF·DOCX·XLSX…"]
    Discover --> Code["코드 심볼·라우트"]
    Validate --> Git["Git log/diff<br/>merge · revert · co-author"]
    Docs --> Engine["engine.py<br/>문서 주장 ↔ 코드 교차"]
    Code --> Engine
    Git --> Engine
    Engine --> Candidates["성과 후보<br/>VERIFIED / SUPPORTED_INFERENCE"]
    Engine --> Gaps["불일치·위험·문서만 존재"]
    Candidates -. "AI 동의 시" .-> AiStage["ai_stage.py<br/>인용 ID·수치·효과 검증"]
    Gaps -. "AI 동의 시" .-> AiStage
    AiStage --> Reviewed["후보 + 근거 ID<br/>부족 시 HYPOTHESIS"]
    Candidates --> Store["ProjectAnalysis 저장"]
    Reviewed --> Store
    Store --> Apply["사용자 확인 후<br/>Activity/Achievement/Evidence"]
```

- AI는 `VERIFIED`를 만들 수 없다. 최대 `SUPPORTED_INFERENCE`다.
- 인용 ID가 근거 목록에 없으면 후보에서 제외한다.
- 커밋 메시지의 `+N/-N`은 개선 효과의 측정 근거로 쓰지 않는다.

## Diagram 4. Evidence Graph / Data Model

```mermaid
erDiagram
    ACTIVITY ||--o{ ACHIEVEMENT : "activity_ids"
    ACTIVITY }o--o{ EVIDENCE : "evidence_ids"
    ACHIEVEMENT }o--o{ EVIDENCE : "evidence_ids"
    ACHIEVEMENT ||--o{ METRIC : "achievement_id"
    EVIDENCE ||--o{ METRIC : "evidence_id"
    ACHIEVEMENT }o--o{ REPORT : "achievement_ids"
    ACTIVITY }o--o{ REPORT : "activity_ids"
    AIANALYSIS ||--o| ACHIEVEMENT : "applied_achievement_id"
    PROJECTANALYSIS ||--o{ CANDIDATE : "candidates"
    CANDIDATE }o--o{ EVIDENCEREF : "evidence_ids"
    CANDIDATE ||--o| MEASUREMENT : "measurement_id"

    ACTIVITY {
        string id
        string title
        date date
        string description
        string problem
        string action
        string result
        list evidence_ids
    }
    ACHIEVEMENT {
        string id
        string title
        string problem
        string action
        string result
        string source
        bool confirmed
        string status
    }
    EVIDENCE {
        string id
        string type
        string reference
        bool verified
    }
    METRIC {
        string id
        string value
        string unit
        string basis
        bool verified
    }
    AIANALYSIS {
        string id
        string activity_id
        string status
        dict result
    }
    EVIDENCEREF {
        string id
        string kind
        string path
        string locator
        bool verified
    }
```

현재 구현에는 별도 `Claim` 테이블이 없다. Claim 검증 결과는
`AIAnalysis.result.unverified_effects`와 `ProjectAnalysis` 후보의 품질 라벨로 남는다.
그래프 DB가 아니라 **ID 참조 집합**이다.

## Diagram 5. AI Generation Sequence

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as API/CLI
    participant S as ImpactService
    participant A as core/ai.py
    participant P as AIService
    participant N as NVIDIA NIM
    participant G as Guardrails
    participant D as JsonStore

    C->>API: analyze(activity_id)
    API->>S: activity + settings
    S->>A: analyze_activity()
    A->>A: external_ai_consent 확인
    alt 동의 없음
        A-->>C: ConsentRequired
    end
    A->>A: Activity + Evidence 프롬프트 구성
    A->>P: _call(json_mode=True)
    P->>N: /chat/completions
    alt 429/5xx/timeout
        P->>P: 재시도·백오프·Circuit Breaker
        P-->>A: 분류된 오류
        A->>D: AIAnalysis(status=failed)
        A-->>C: 원본 Activity 유지
    else 정상
        N-->>P: JSON text
        P-->>A: content + telemetry
        A->>A: _parse_json
        A->>G: sanitize_ai_result (수치+단위)
        A->>G: gate_result (정성 효과)
        G-->>A: cleaned + unverified_*
        A->>D: AIAnalysis(status=completed)
        A-->>C: 후보(needs_review)
    end
```

## Diagram 6. Hallucination Prevention Flow

```mermaid
flowchart TB
    Text["AI 생성 문장"] --> Split["문장 단위 분리"]
    Split --> Numeric{"숫자+단위<br/>주장인가?"}
    Numeric -- 예 --> Unit["근거의 (값, 단위)와 대조"]
    Unit -- 불일치 --> Replace["[확인 필요]로 대체"]
    Unit -- 일치 --> Effect{"효과 주장인가?"}
    Numeric -- 아니오 --> Effect
    Effect -- 아니오 --> Keep["그대로 저장"]
    Effect -- 예 --> Neg{"근거 문장에<br/>부정 표현이 있는가?"}
    Neg -- 예 --> Reject["문장 삭제 + 사유 기록"]
    Neg -- 아니오 --> Match{"같은 대상+효과<br/>또는 수치 일치?"}
    Match -- 예 --> Keep
    Match -- 아니오 --> Reject
    Replace --> Save["저장 결과"]
    Keep --> Save
    Reject --> Save
    Save --> Report{"기계 생성 성과인가?"}
    Report -- 예 --> Revalidate["보고서 생성 시<br/>외부 근거로 재검증"]
    Report -- 아니오 --> Body["본문 유지<br/>(사용자 직접 작성)"]
    Revalidate --> Final["보고서 본문"]
    Body --> Final
```

- 수치 검증은 `normalize_unit`으로 `10m`와 `10분`을 같게 본다.
- `80%`는 `80ms`로 통과하지 않는다.
- 효과 주장이 아니면 Gate는 문장을 건드리지 않는다.

## Diagram 7. AI Provider Fallback

```mermaid
flowchart LR
    Req["AI 요청"] --> Model["모델 후보 목록"]
    Model --> Call["LiteLLM completion"]
    Call --> Ok{"성공?"}
    Ok -- 예 --> Telemetry["provider/model/usage 기록"]
    Ok -- 아니오 --> Classify["오류 분류<br/>429·timeout·5xx·인증"]
    Classify --> Retry{"재시도 가능?"}
    Retry -- 예 --> Backoff["백오프 후 재시도"]
    Backoff --> Call
    Retry -- 아니오 --> Next{"다음 모델/Provider?"}
    Next -- 예 --> Call
    Next -- 아니오 --> Fail["AIAnalysis failed<br/>원본 불변"]
    Classify --> Breaker["Circuit Breaker<br/>cooldown 기록"]
    Breaker --> Next
```

현재 `nvidia_nim`은 `openai/gpt-oss-20b`만 허용한다. 계정별 접근 모델이 달라
모델 목록을 넓게 두지 않는다.

## Diagram 8. Git Evolution Timeline

```mermaid
timeline
    title ImpactNote 개발 흐름 (Git 근거)
    2026-10 : DevFolio 문서 생성 도구
             : YAML·프로젝트 문서·내보내기
    2026-10 : AI 신뢰성 계층
             : 모델 전환·Circuit Breaker·관측
    2026-11-15 : ImpactNote 전환
               : Activity·Achievement·Evidence·Report
    2026-11-15 : 프로젝트 인텔리전스
               : 문서·코드·Git 교차 분석·기여 귀속
    2026-11-16 : Ground Truth 평가
               : 42 claim·문서-코드·귀속·live
    2026-11-16 : 정성 효과 Hard Gate
               : 수치+단위·효과 문장·보고서 재검증
    2026-11-16 : 포트폴리오 문서화
               : ADR·다이어그램·증거 매트릭스
```

`timeline`은 GitHub Mermaid에서 지원되지만, 렌더러 버전에 따라 표시가 다를 수 있다.
Git 이력 원문은 `git log --oneline --graph`로 확인한다.

## Diagram 9. CI/CD & Deployment

```mermaid
flowchart TB
    Dev["로컬 main"] --> Hook["pre-commit<br/>ruff·format·pytest"]
    Hook --> Push["git push origin main"]
    Push --> CI["GitHub Actions CI"]
    CI --> T1["test: Python 3.11–3.14"]
    CI --> T2["portability: Ubuntu/macOS/Windows"]
    CI --> T3["docker: build + /api/health"]
    CI --> T4["lint: ruff check + format"]
    T1 --> Green{"모두 통과?"}
    T2 --> Green
    T3 --> Green
    T4 --> Green
    Green -- 예 --> Main["origin/main"]
    Green -- 아니오 --> Fix["수정 후 재실행"]
    Manual["수동 AI Evaluation"] -. "NVIDIA_NIM_API_KEY 있을 때" .-> Eval["evals/impact/run --live"]
    Manual -. "키 없음" .-> Skip["skip (실패 아님)"]
```

Docker는 `127.0.0.1`에만 바인딩하고, 컨테이너에서는 `serve --host 0.0.0.0`으로
내부 포트를 연다. 인증이 없는 API를 LAN에 노출하지 않기 위한 설정이다.

## Diagram 10. Commit / Merge History (이번 작업)

```mermaid
gitGraph
    commit id: "6e6ce68" tag: "before"
    commit id: "adfe892"
    commit id: "f05691d"
    commit id: "e728935"
    commit id: "e2dd608"
    commit id: "3ec1010"
    commit id: "dd4d64f"
    commit id: "docs"
```

| 순서 | Commit | 목적 |
| ---: | --- | --- |
| 0 | `6e6ce68` | 작업 시작 HEAD (origin/main과 동기화) |
| 1 | `adfe892` | NVIDIA NIM Provider·응답 안정성 |
| 2 | `f05691d` | 수치·정성 효과 Guardrail |
| 3 | `e728935` | 프로젝트 인텔리전스·기여 귀속 |
| 4 | `e2dd608` | Ground Truth 평가·A/B 하네스 |
| 5 | `3ec1010` | Docker·CI·이식성 |
| 6 | `dd4d64f` | NVIDIA gpt-oss 토큰 하한 회귀 테스트 |
| 7 | `docs` | 아키텍처·개발사·포트폴리오 문서 |

실제 문서 커밋 SHA는 `git log -1 --oneline`으로 확인한다. 이 저장소는 별도
Integration Branch를 만들지 않고 `main`에 순차 커밋했다(AGENTS.md 규칙).

## 렌더링 검증

- Mermaid CLI(`mmdc`)는 이 환경에 설치되어 있지 않아 **로컬 렌더링을 수행하지 않았다**.
- 대신 코드 펜스·다이어그램 선언·노드 참조를 스크립트로 검사했다.
- GitHub Markdown 렌더링은 실제 push 후 저장소 화면에서 확인해야 한다.
