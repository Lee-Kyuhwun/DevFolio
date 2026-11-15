# 성과노트 (ImpactNote)

**회사 업무를 기록하고, 근거로 확인하고, 제출용 성과보고서로 만드는 로컬 우선 도구.**

업무는 매일 쌓이지만 성과평가·승진·이직 서류를 쓸 때는 기억에 의존하게 됩니다. 성과노트는
"기록 → 성과 → 근거 → 보고서" 흐름을 강제해, **말할 수 있는 성과만** 남기고 **숫자는 근거가 있을 때만** 쓰도록 돕습니다.

- 업무 기록은 제목과 설명만으로 3초 안에 저장
- 성과는 문제–행동–결과 구조로 정리하고, 근거(PR·티켓·로그·문서)와 연결
- 수치는 단위·기간·산출 기준·근거가 모두 있어야 "확인됨"으로 인정
- 주간/월간/분기·반기/연간/자유 형식 보고서를 Markdown·DOCX·PDF·TXT·CSV 로 생성
- 모든 데이터는 내 컴퓨터에 JSON 으로 저장(기본 외부 전송 없음)

---

## 빠른 시작

### Docker (권장)

```bash
docker compose up -d --build
# http://localhost:8000
```

기존 DevFolio 데이터 볼륨이 있으면 읽기 전용으로 마운트되어 `설정 → DevFolio 데이터 이전` 에서 가져올 수 있습니다.

### 로컬 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
impactnote init          # 데이터 디렉터리 생성 + 이전 가능 여부 안내
impactnote serve         # http://127.0.0.1:8000
```

## 화면

| 메뉴 | 하는 일 |
| --- | --- |
| 대시보드 | 이번 주/월 기록 수, 확인된 성과, 확인 필요 항목, 최근 활동 |
| 업무 기록 | 제목+설명으로 빠르게 저장, 프로젝트·유형·문제/행동/결과 보완 |
| 성과 관리 | 기록을 묶어 성과 후보 생성, 근거 연결, 수치 등록 |
| 근거 자료 | PR·티켓·로그·문서·회의록을 URL/텍스트로 보관, 확인 처리 |
| AI 성과 분석 | 동의한 경우에만 업무 메모를 성과 구조로 분석(원본 불변) |
| Git 후보 | 커밋 메시지에서 성과 후보를 결정론적으로 추출(확정 아님) |
| 성과보고서 | 기간·템플릿 선택 → 미리보기 → MD/DOCX/PDF/TXT/CSV 다운로드 |
| 제출 이력 | 버전·상태(초안/검토/제출) 관리, 재생성 시 버전 증가 |
| 설정 | 이름·직무, 기본 템플릿, AI 전송 동의·허용 Provider, 데이터 이전 |

## 핵심 원칙

1. **기록과 해석을 분리한다.** 업무 기록(Activity)은 사실, 성과(Achievement)는 해석, AI 분석은 별도 결과물이다. AI 가 실패해도 원본 기록과 수동 편집은 그대로 동작한다.
2. **근거 없는 숫자를 만들지 않는다.** 숫자+단위 주장은 기록/근거 텍스트와 대조하고, 확인되지 않으면 `[확인 필요]` 로 바꾼다. 지표는 단위·기간·산출 기준·근거가 모두 있어야 verified 가 된다.
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

컬렉션별 JSON 파일(`activities.json`, `achievements.json`, `evidence.json`, `metrics.json`, `reports.json`, `analyses.json`, `settings.json`)로 저장되며 파일 권한은 `0600` 입니다.

## AI 설정

- 설정 화면에서 **외부 AI 전송 동의**를 켜야 분석이 동작합니다(기본 차단).
- `허용 Provider` 를 비우면 설치된 Provider 중 사용 가능한 것을 쓰고, 지정하면 그 Provider 만 사용합니다.
- 키는 환경변수로만 주입합니다: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
- AI 가 반환한 수치는 원본 기록과 대조해 검증되지 않으면 자동으로 `[확인 필요]` 처리됩니다.
- 분석 결과는 `analyses.json` 에 별도 저장되며, "성과 후보로 저장"을 눌러야 성과가 됩니다(확정 전 `needs_review`).

## 개발

```bash
pytest -q                       # 전체 테스트
ruff check impactnote tests
ruff format impactnote tests
node --check impactnote/web/static/app.js
```

처음 사용하는 경우 [GUIDE.md](GUIDE.md), 구조와 설계 결정은 [docs/impactnote.md](docs/impactnote.md) 와 [docs/04-architecture.md](docs/04-architecture.md) 를 참고하세요.

## 라이선스

MIT — [LICENSE](LICENSE)

---

**English.** ImpactNote is a local-first tool for recording company work, verifying it with evidence,
and generating submission-ready performance reports. It deliberately refuses unsupported numbers:
every metric needs a unit, period, measurement basis and linked evidence, and AI-suggested achievements
stay as review candidates until a human confirms them. Data lives in local JSON files; external AI is
opt-in and gated by an explicit consent setting.
