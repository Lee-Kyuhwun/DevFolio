# 성과노트 (ImpactNote)

**회사 업무를 기록하고, 근거로 확인하고, 제출용 성과보고서로 만드는 로컬 우선 도구.**

업무는 매일 쌓이지만 성과평가·승진·이직 서류를 쓸 때는 기억에 의존하게 됩니다. 성과노트는
"기록 → 성과 → 근거 → 보고서" 흐름을 강제해, **말할 수 있는 성과만** 남기고 **숫자는 근거가 있을 때만** 쓰도록 돕습니다.

- 업무 기록은 제목과 설명만으로 3초 안에 저장
- 성과는 문제–행동–결과 구조로 정리하고, 근거(PR·티켓·로그·문서)와 연결
- 수치는 단위·기간·산출 기준·근거가 모두 있어야 "확인됨"으로 인정
- "안정성 향상"·"비용 절감" 같은 정성 효과도 근거가 없으면 저장·보고서에서 제거
- 주간/월간/분기·반기/연간/자유 형식 보고서를 Markdown·DOCX·PDF·TXT·CSV 로 생성
- 모든 데이터는 내 컴퓨터에 JSON 으로 저장(기본 외부 전송 없음)

---

## 빠른 시작

요구 사항: **Python 3.11+** 또는 Docker + Compose v2. macOS 기본 `python3` 가 3.9 이면
`python3.14` 처럼 3.11+ 인터프리터를 명시합니다.

### Docker (권장)

```bash
docker compose up -d --build
# http://localhost:8000
curl -fsS http://127.0.0.1:8000/api/health
```

다른 포트는 `IMPACTNOTE_PORT=18000 docker compose up -d`. 저장소 분석 대상은 기본적으로
현재 디렉터리를 읽기 전용 마운트하며, `REPOS_DIR=/path/to/repos` 로 바꿀 수 있습니다.

기존 DevFolio 데이터 볼륨이 있으면 읽기 전용으로 마운트되어 `설정 → DevFolio 데이터 이전` 에서 가져올 수 있습니다.

### 로컬 실행

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
impactnote init          # 데이터 디렉터리 생성 + 이전 가능 여부 안내
impactnote serve         # http://127.0.0.1:8000
```

AI 키 없이도 기록·성과·근거·보고서·비-AI 프로젝트 분석은 동작합니다. AI 분석은 설정에서
외부 전송에 동의하고 키를 주입했을 때만 실행됩니다.

## 화면

| 메뉴 | 하는 일 |
| --- | --- |
| 대시보드 | 이번 주/월 기록 수, 확인된 성과, 확인 필요 항목, 최근 활동 |
| 업무 기록 | 제목+설명으로 빠르게 저장, 프로젝트·유형·문제/행동/결과 보완 |
| 성과 관리 | 기록을 묶어 성과 후보 생성, 근거 연결, 수치 등록 |
| 근거 자료 | PR·티켓·로그·문서·회의록을 URL/텍스트로 보관, 확인 처리 |
| 프로젝트 분석 | 경로 등록 → 문서·코드·Git 전후 비교 → 근거가 연결된 성과 후보 발굴 |
| AI 성과 분석 | 동의한 경우에만 업무 메모를 성과 구조로 분석(원본 불변) |
| Git 후보 | 커밋 메시지에서 성과 후보를 결정론적으로 추출(확정 아님) |
| 성과보고서 | 기간·템플릿 선택 → 미리보기 → MD/DOCX/PDF/TXT/CSV 다운로드 |
| 제출 이력 | 버전·상태(초안/검토/제출) 관리, 재생성 시 버전 증가 |
| 설정 | 이름·직무, 기본 템플릿, AI 전송 동의·허용 Provider, 데이터 이전 |

## 핵심 원칙

1. **기록과 해석을 분리한다.** 업무 기록(Activity)은 사실, 성과(Achievement)는 해석, AI 분석은 별도 결과물이다. AI 가 실패해도 원본 기록과 수동 편집은 그대로 동작한다.
2. **근거 없는 숫자를 만들지 않는다.** 숫자+단위 주장은 기록/근거 텍스트와 대조하고, 확인되지 않으면 `[확인 필요]` 로 바꾼다. 중첩된 `statements`·`contribution` 필드도 우회하지 못한다. 지표는 단위·기간·산출 기준·근거가 모두 있어야 verified 가 된다.
3. **팀 성과를 개인 성과로 부풀리지 않는다.** AI 프롬프트와 보고서 템플릿은 본인이 수행한 행동과 기여 범위를 분리해 서술한다.
4. **AI 는 동의 후에만, 허용 Provider 로만.** 기본값은 차단이며, 어떤 데이터가 외부로 나가는지 설정 화면에서 확인한 뒤 켠다.
5. **원본은 지우지 않는다.** DevFolio 이전은 ZIP 백업 후 멱등 실행하며, 원본 YAML/JSON 은 읽기만 한다.

## 보고서 템플릿

| 코드 | 용도 | 기본 기간 |
| --- | --- | --- |
| `weekly` | 주간 업무실적 보고 | 주 |
| `monthly` | 월간 업무실적 보고 | 월 |
| `quarterly` | 분기·반기 실적 보고 | 분기/반기 |
| `annual` | 연간 자기평가 | 연 |
| `custom` | 자유 형식(섹션·글자 수 지정) | 사용자 지정 |

기간은 주·월·분기·반기·연·사용자 지정(시작/종료일)을 지원합니다. 보고서 본문에는 **검증된 지표만** 들어가고,
확인되지 않은 수치·상태는 문서 끝 "근거 및 확인 상태" 부록에 모입니다.

## CLI

```bash
impactnote version
impactnote activity add "배포 롤백 자동화" --desc "실패 시 자동 복구" --project 결제
impactnote activity list
impactnote achievement from-activity act_xxx
impactnote achievement list --status verified
impactnote report generate --template monthly --period month --format docx
impactnote report list
impactnote intel analyze /path/to/company-project --author-email me@company.com
impactnote intel list
impactnote migrate           # DevFolio 데이터 이전(백업·멱등)
impactnote serve --host 0.0.0.0 --port 8000
```

기존 `devfolio` 명령과 `/api` 는 호환을 위해 남아 있습니다.

## 데이터 위치

| 항목 | 경로 | 재정의 |
| --- | --- | --- |
| 데이터 | `~/.local/share/impactnote` (macOS: `~/Library/Application Support/impactnote`) | `IMPACTNOTE_DATA_DIR` |
| 설정 | `~/.config/impactnote` | `IMPACTNOTE_CONFIG_DIR` |
| DevFolio 원본 | 기존 `devfolio` 경로 | `IMPACTNOTE_LEGACY_DATA_DIR`, `IMPACTNOTE_LEGACY_CONFIG_DIR` |

컬렉션별 JSON 파일(`activities.json`, `achievements.json`, `evidence.json`, `metrics.json`, `reports.json`, `analyses.json`, `project_analyses.json`, `settings.json`)로 저장되며 파일 권한은 `0600` 입니다.

### 프로젝트 심층 분석

`프로젝트 분석` 화면 또는 `impactnote intel analyze <path>` 는 **읽기 전용**으로 프로젝트를 조사합니다. 분석 경로는 `IMPACTNOTE_ANALYZE_ROOTS`(기본: 홈·현재 디렉터리) 안으로 제한되며, Docker 는 `/app:/home/user` 만 허용하고 호스트 저장소는 기본적으로 현재 디렉터리를 `/home/user` 에 읽기 전용 마운트합니다.

- 문서(MD/TXT/HTML/JSON/YAML/CSV/DOCX/XLSX/PPTX/PDF 등)를 탐색하고 역할을 분류합니다. `.env`·키·자격증명은 읽지 않습니다.
- Git 커밋 메시지 대신 실제 diff·현재 코드·테스트를 근거로 후보를 만들고, 리버트는 제외합니다.
- 문서 주장 ↔ 심볼/라우트를 교차 분석해 `일치 / 문서에만 존재 / 코드에만 존재` 를 구분합니다.
- 전후 수치가 기록된 측정 자료만 개선율을 계산합니다. 측정이 없으면 정성 서술만 합니다.
- PDF 텍스트 추출은 `pypdf` extra 를 사용하며 OCR 은 범위 밖입니다.
- 후보는 `VERIFIED / SUPPORTED_INFERENCE / HYPOTHESIS / INSUFFICIENT_EVIDENCE` 로 표시되고, 적용해도 `needs_review` 상태로 저장됩니다. 확인 전 후보와 연결 업무는 보고서 본문에서 제외됩니다.
- AI 보강은 외부 전송 동의가 있을 때만 실행되며, AI 는 `VERIFIED` 를 만들 수 없고 인용 근거 ID 밖의 내용은 버립니다.

분석 결과는 프로젝트 경로·HEAD·문서 지문이 같으면 재실행 시 이전 결과를 재사용합니다(`incremental`).

## AI 설정

- 설정 화면에서 **외부 AI 전송 동의**를 켜야 분석이 동작합니다(기본 차단).
- `허용 Provider` 를 비우면 설치된 Provider 중 사용 가능한 것을 쓰고, 지정하면 그 Provider 만 사용합니다.
- 키는 환경변수로만 주입합니다: `NVIDIA_NIM_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`. `.env.example` 참고.
- NVIDIA NIM 은 직접 API(`https://integrate.api.nvidia.com/v1`)로 연결되어 있고, 검증된 생성 모델은 `openai/gpt-oss-20b` 입니다. 자세한 설정·모델 확인·한계는 [docs/nvidia-provider.md](docs/nvidia-provider.md).
- OmniRoute 경유 설정은 저장소·설정·로그에서 확인되지 않아 사용하지 않았습니다.
- AI 가 반환한 수치는 원본 기록과 대조해 검증되지 않으면 자동으로 `[확인 필요]` 처리됩니다. 정성 효과 주장은 자동 검증되지 않으므로 사람이 확인해야 합니다.
- 분석 결과는 `analyses.json` 에 별도 저장되며, "성과 후보로 저장"을 눌러야 성과가 됩니다(확정 전 `needs_review`).

## 개발

```bash
pytest -q                       # 전체 테스트 (2026-11-16: 481 passed)
ruff check impactnote devfolio tests evals
ruff format --check impactnote devfolio tests evals
node --check impactnote/web/static/app.js
bash scripts/check.sh
```

### AI 성능 평가

```bash
# 키 없이 결정론 분석기만
python -m evals.impact.run --offline --no-judge --out /tmp/impact-offline

# 실제 NVIDIA 생성 3회 + 독립 심사 (비용·시간 발생)
export NVIDIA_NIM_API_KEY=...
export DEVFOLIO_AI_PROVIDER_FALLBACK=0
python -m evals.impact.run --live --out /tmp/impact-live
```

2026-11-15 실제 결과 요약: 성과 P/R/F1 1.00, 귀속 100%, 문서-코드 83.3%,
Semantic 83.3%, **Hallucination 47.6% FAIL**, **품질 사실성 2.65/5 FAIL**. 전체 판정은
`CONDITIONAL PASS` 이며 AI 품질은 통과가 아닙니다. 자세한 정의·표본·한계는
[docs/evaluation-results.md](docs/evaluation-results.md) 와
[docs/ai-evaluation.md](docs/ai-evaluation.md) 를 참고하세요.

### 문서

| 문서 | 내용 |
| --- | --- |
| [docs/installation.md](docs/installation.md) | 새 PC 설치, Docker, OS별 주의, Clean Clone |
| [docs/architecture.md](docs/architecture.md) | 현재 시스템 구조, Evidence Graph, AI 계층 |
| [docs/architecture/diagrams.md](docs/architecture/diagrams.md) | 시스템·데이터·AI·검증·CI 다이어그램 10개 |
| [docs/architecture/claim-validation.md](docs/architecture/claim-validation.md) | 수치·단위·정성 효과 검증 상세 |
| [docs/ai-evaluation.md](docs/ai-evaluation.md) | 평가 지표 정의, Ground Truth, 실행 방법 |
| [docs/nvidia-provider.md](docs/nvidia-provider.md) | NVIDIA NIM 설정·검증·제한 |
| [docs/testing.md](docs/testing.md) | 단위·통합·Live·CI 검증 |
| [docs/evaluation-results.md](docs/evaluation-results.md) | 실제 측정 결과·실패·한계 |
| [docs/final-report-2026-11-15.md](docs/final-report-2026-11-15.md) | Phase 16 최종 보고·판정 |
| [docs/audits/2026-11-15/](docs/audits/2026-11-15/) | 6개 역할별 감사 보고서 |
| [docs/impactnote.md](docs/impactnote.md) | 제품 개념·도메인·API |
| [docs/engineering/development-history.md](docs/engineering/development-history.md) | Workstream별 개발 히스토리 |
| [docs/portfolio/README.md](docs/portfolio/README.md) | 포트폴리오·면접·트레이드오프 |
| [docs/portfolio/evidence-index.md](docs/portfolio/evidence-index.md) | 주장별 증거·검증 상태 |
| [docs/README.md](docs/README.md) | 전체 문서 지도 |

처음 사용하는 경우 [GUIDE.md](GUIDE.md), DevFolio 시절 구조는
[docs/04-architecture.md](docs/04-architecture.md) 에 역사 자료로 남아 있습니다.

## 라이선스

MIT — [LICENSE](LICENSE)

---

**English.** ImpactNote is a local-first tool for recording company work, verifying it with evidence,
and generating submission-ready performance reports. It deliberately refuses unsupported numbers:
every metric needs a unit, period, measurement basis and linked evidence, and AI-suggested achievements
stay as review candidates until a human confirms them. Data lives in local JSON files; external AI is
opt-in and gated by an explicit consent setting.
