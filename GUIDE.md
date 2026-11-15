# 성과노트(ImpactNote) 시작 가이드

처음 설치부터 첫 업무 기록, 근거 연결, 제출용 보고서 생성, DevFolio 데이터 이전까지 순서대로 안내합니다.

---

## 목차

1. [설치와 실행](#1-설치와-실행)
2. [첫 업무 기록](#2-첫-업무-기록)
3. [성과로 묶기](#3-성과로-묶기)
4. [근거 연결](#4-근거-연결)
5. [수치(지표) 등록](#5-수치지표-등록)
6. [AI 성과 분석](#6-ai-성과-분석)
7. [Git 후보 수집](#7-git-후보-수집)
8. [성과보고서 생성](#8-성과보고서-생성)
9. [제출 이력·버전](#9-제출-이력버전)
10. [설정](#10-설정)
11. [DevFolio 데이터 이전](#11-devfolio-데이터-이전)
12. [CLI 사용법](#12-cli-사용법)
13. [문제 해결](#13-문제-해결)

---

## 1. 설치와 실행

### 방법 A — Docker (권장)

```bash
docker compose up -d --build
# 브라우저에서 http://localhost:8000
```

- 새 데이터는 `impactnote-data` 볼륨에 저장됩니다.
- 기존 DevFolio 볼륨은 읽기 전용으로 마운트되어 `설정 → DevFolio 데이터 이전`에서만 사용됩니다.
- 중지: `docker compose down` (볼륨은 유지)

### 방법 B — 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,all]"
impactnote init                    # 데이터 디렉터리 생성
impactnote serve                   # http://127.0.0.1:8000
```

### 데이터 위치

| 항목 | 기본 경로 | 재정의 |
| --- | --- | --- |
| 데이터 | `~/.local/share/impactnote` (macOS: `~/Library/Application Support/impactnote`) | `IMPACTNOTE_DATA_DIR` |
| 설정 | `~/.config/impactnote` (macOS: `~/Library/Preferences/impactnote`) | `IMPACTNOTE_CONFIG_DIR` |
| DevFolio 원본 | 기존 `devfolio` 경로 | `IMPACTNOTE_LEGACY_DATA_DIR`, `IMPACTNOTE_LEGACY_CONFIG_DIR` |

컬렉션별 JSON 파일로 저장되며 권한은 `0600` 입니다.

---

## 2. 첫 업무 기록

1. 좌측 메뉴에서 **업무 기록**을 엽니다.
2. **빠른 기록**에 제목과 한 줄 설명만 입력하고 **기록 추가**를 누릅니다.
3. 나중에 **수정**에서 프로젝트, 업무 유형, 문제/행동/결과, 기간, 협업 대상을 보완합니다.

기록 단계에서는 사실만 적는 것이 좋습니다. 해석과 성과 문장은 다음 단계에서 만듭니다.
진행 중인 일은 상태를 `진행 중`으로 두면 대시보드의 "진행 중인 업무"에 나타납니다.

---

## 3. 성과로 묶기

1. **업무 기록**에서 관련 기록을 체크합니다.
2. **성과 관리**로 이동해 **선택한 업무 N건으로 성과 만들기**를 누릅니다.
3. 제목·문제·수행 내용을 다듬고 **저장**합니다.

성과 상태는 다음처럼 계산됩니다.

| 상태 | 의미 |
| --- | --- |
| `사용자 입력 기반` | 아직 연결된 근거가 없음 |
| `추가 확인 필요` | 근거가 확인되지 않았거나 AI/Git 후보를 검토해야 함 |
| `일부 근거 확인됨` | 확인된 근거와 미확인 근거가 섞여 있음 |
| `근거 확인됨` | 연결된 근거가 모두 확인됨 |

AI·Git 이 만든 후보는 **"확인했습니다"** 를 체크하기 전까지 `근거 확인됨`으로 올라가지 않습니다.

---

## 4. 근거 연결

**근거 자료** 화면에서 PR, 티켓, 로그, 문서, 회의록 등을 등록합니다.

- 유형: `git_commit`, `pull_request`, `jira`, `confluence`, `test_result`, `deployment`, `incident`, `report`, `file`, `url`, `note`
- 참조: URL, 티켓 번호, 파일 경로 등
- **확인됨** 체크: 본인이 실제로 확인한 근거만 체크합니다.

등록한 근거는 **성과 관리 → 수정·근거 연결**에서 여러 개를 선택해 연결합니다.
미확인 근거만 연결하면 상태는 `추가 확인 필요`로 유지됩니다.

---

## 5. 수치(지표) 등록

성과 수정 화면 아래 **지표 추가**에서 입력합니다.

- 이름, 값, 단위, 기간, 측정 기준/산출 방식, 근거
- **근거 확인됨**은 값이 기록·근거 텍스트에 그대로 있을 때만 인정됩니다(예: 기록에 "12분"이 있어야 "12분" 지표가 확인됨).
- 확인되지 않은 지표는 삭제되지 않고 보고서의 **확인 필요 항목** 부록에 모입니다.

보고서 본문에는 확인된 지표만 들어갑니다.

---

## 6. AI 성과 분석

AI 는 **선택 기능**이며 기본값은 차단입니다.

1. **설정**에서 **외부 AI 전송에 동의합니다**를 켭니다.
2. 필요하면 **허용 Provider** 를 지정합니다(비우면 사용 가능한 Provider 중 선택).
3. API 키를 환경변수로 주입합니다: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
4. **AI 성과 분석**에서 기록을 선택해 분석을 실행합니다.

동작 원칙:

- 분석 결과는 원본 기록과 별도로 저장됩니다.
- AI 가 만든 숫자가 기록·근거에 없으면 `[확인 필요]` 로 치환됩니다.
- 실패(레이트리밋·타임아웃·파싱 오류)해도 원본 기록과 수동 편집은 그대로 동작합니다.
- 결과는 **성과 후보로 저장**을 눌러야 성과가 되며, 검토 전에는 `추가 확인 필요` 상태입니다.

---

## 7. Git 후보 수집

**AI 성과 분석 → Git 후보**에서 저장소 경로와 작성자 이메일을 입력합니다.

- 커밋 메시지·변경량을 규칙 기반으로 분석해 업무 기록과 성과 후보를 만듭니다(AI 미사용).
- 후보는 항상 `추가 확인 필요` 이며, 자동으로 확정되지 않습니다.
- Docker 에서는 `REPOS_DIR`(기본 `~`)이 `/home/user` 에 읽기 전용으로 마운트됩니다.

---

## 8. 성과보고서 생성

**성과보고서** 화면에서 선택합니다.

| 항목 | 값 |
| --- | --- |
| 제출 목적 | 주간 / 월간 / 분기 / 반기 / 연간 자기평가 / 자유 형식 |
| 기간 | 주간 / 월간 / 분기 / 반기 / 연간 / 사용자 지정 |
| 파일 형식 | Markdown / DOCX / PDF / TXT / CSV |
| 추가 옵션 | 제목, 글자 수 제한, 자유 형식 섹션 |

생성 후 미리보기가 표시되고, 상단의 형식 버튼으로 다운로드할 수 있습니다.
본문에는 검증된 지표만 들어가고, 확인되지 않은 수치·상태는 문서 끝 "근거 및 확인 상태"에 모입니다.

---

## 9. 제출 이력·버전

**제출 이력**에서 생성한 보고서를 확인하고 상태를 `초안`/`제출`로 바꿉니다.
같은 기간·템플릿으로 다시 생성하면 버전이 `v1 → v2`로 증가하며 이전 버전도 남습니다.

---

## 10. 설정

- 이름·직무·기본 템플릿
- 외부 AI 전송 동의, 허용 Provider
- DevFolio 데이터 이전

AI 동의를 끄면 분석 API 는 `EXTERNAL_AI_NOT_ALLOWED` 로 거부합니다.

---

## 11. DevFolio 데이터 이전

1. 기존 DevFolio 데이터가 있는 환경이면 **설정 → DevFolio 데이터 이전**을 누릅니다.
2. 실행 전 ZIP 백업이 만들어지고, 프로젝트의 각 작업이 업무 기록으로 변환됩니다.
3. 문제/해결/결과가 있는 작업은 성과 후보(`추가 확인 필요`)로 생성됩니다.
4. 다시 실행해도 중복 생성되지 않습니다(`migration.json` 지문).

CLI:

```bash
impactnote migrate            # 이미 이전했으면 already_migrated
impactnote migrate --force    # 강제 재실행
```

원본 YAML/JSON 은 수정·삭제하지 않습니다.

---

## 12. CLI 사용법

```bash
impactnote version
impactnote init
impactnote serve [--host 0.0.0.0] [--port 8000] [--reload]

impactnote activity add "배포 롤백 자동화" --desc "실패 시 자동 복구" --project 결제
impactnote activity list
impactnote achievement from-activity act_xxx
impactnote achievement list --status verified

impactnote report generate --template monthly --period month --format docx
impactnote report list

impactnote migrate
```

기존 `devfolio` 명령과 `/api` 는 호환을 위해 유지됩니다.

---

## 13. 문제 해결

| 증상 | 확인 |
| --- | --- |
| 화면이 예전 모습 | 브라우저 캐시 — `?v=` 쿼리를 붙여 새로고침 |
| AI 분석이 409 | 설정의 외부 AI 전송 동의가 꺼져 있음 |
| AI 분석이 실패 | Provider 키·쿼터·모델 상태 확인, 원본 기록은 그대로 유지됨 |
| 보고서에 숫자가 `[확인 필요]` | 값이 기록·근거 텍스트에 없거나 지표가 미확인 |
| 이전 후 데이터가 안 보임 | `IMPACTNOTE_LEGACY_DATA_DIR` 경로와 원본 존재 여부 확인 |
| Docker 포트 충돌 | `docker compose down` 후 재기동, 8000 포트 사용 프로세스 확인 |

추가 설계 설명은 [docs/impactnote.md](docs/impactnote.md), 제품 소개는 [README.md](README.md) 를 참고하세요.
