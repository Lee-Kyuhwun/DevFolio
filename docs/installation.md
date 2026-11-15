# 설치 및 다른 PC 실행 가이드

기준일: 2026-11-15 · 대상: ImpactNote 1.0.0

## 1. 요구 사항

| 항목 | 최소 | 권장 |
| --- | --- | --- |
| Python | 3.11 | 3.12 또는 3.14 |
| Docker | 선택 | Docker Desktop / Engine + Compose v2 |
| Git | 프로젝트 분석 시 필요 | 최신 |
| OS | macOS·Linux·Windows | CI 는 Ubuntu/macOS/Windows Python 3.12 검증 |
| 메모리 | 1GB | 4GB 이상 (LLM 호출·PDF 변환 시) |

> macOS 기본 `python3` 가 3.9 인 경우가 있다. 이 프로젝트는 `>=3.11` 이므로
> `python3.14` 또는 Homebrew Python 을 명시한다. 2026-11-15 Clean Clone 테스트에서
> 시스템 Python 3.9.6 으로 설치를 시도해 `requires-python` 오류를 확인했다.

## 2. GitHub 에서 새로 Clone

```bash
git clone <저장소 URL> impactnote
cd impactnote
```

현재 저장소 URL 은 GitHub 원격을 사용한다. 회사 내부 저장소라면 접근 권한과 SSH 키를 먼저
설정한다. clone 후에는 기존 PC 의 `.env`, 데이터 디렉터리, 키체인을 복사하지 않는다.

### 2.1 가상환경과 의존성

macOS / Linux:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[all]"
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[all]"
```

개발 도구까지 필요하면 `".[dev,all]"`. `gui`/`docx`/`pdf` 를 개별 설치해도 된다.

### 2.2 초기 실행

```bash
impactnote init
impactnote serve
# http://127.0.0.1:8000
```

`init` 은 데이터 디렉터리를 만들고, 기존 DevFolio 데이터가 있으면 이전 안내를 출력한다.
AI 키가 없어도 기록·성과·근거·보고서·프로젝트 분석(비-AI)은 동작한다.

### 2.3 첫 확인

1. `GET /api/health` 가 `{"status":"ok"}` 를 반환하는지 확인.
2. 업무 기록 1건을 저장.
3. 주간 보고서를 Markdown 으로 생성.
4. 프로젝트 분석에서 읽기 전용 저장소 경로를 지정.
5. AI 를 쓰려면 설정에서 동의를 켜고 `NVIDIA_NIM_API_KEY` 를 주입한 뒤 분석 1건 실행.

## 3. Docker 실행

```bash
cp .env.example .env       # 선택: AI 키를 쓸 때만 값 입력
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/api/health
```

- 기본 바인딩은 `127.0.0.1:8000` 이다. LAN 에 인증 없는 API 를 노출하지 않는다.
- 다른 포트: `IMPACTNOTE_PORT=18000 docker compose up -d`.
- 저장소 마운트: 기본은 현재 디렉터리(`REPOS_DIR=.`)를 `/home/user` 에 읽기 전용 마운트.
  다른 경로는 `REPOS_DIR=/path/to/repos` 로 지정한다.
- 데이터는 named volume `impactnote-data`, 설정은 `impactnote-config` 에 보존된다.
- 기존 DevFolio 볼륨은 `/legacy/...` 에 읽기 전용으로 붙어 마이그레이션 원본으로만 쓰인다.
- AI 키는 `.env` 또는 셸 환경변수로 전달한다. `docker-compose.yml` 에 직접 쓰지 않는다.

중지·재실행:

```bash
docker compose stop
docker compose up -d
# 완전 삭제(데이터 포함)는 사용자가 명시적으로 결정할 때만:
# docker compose down -v
```

## 4. 환경변수

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `IMPACTNOTE_DATA_DIR` | OS 별 platformdirs | JSON 데이터 위치 |
| `IMPACTNOTE_CONFIG_DIR` | OS 별 platformdirs | 설정 위치 |
| `IMPACTNOTE_LEGACY_DATA_DIR` | 기존 devfolio 경로 | DevFolio 데이터 원본 |
| `IMPACTNOTE_LEGACY_CONFIG_DIR` | 기존 devfolio 경로 | DevFolio 설정 원본 |
| `IMPACTNOTE_ANALYZE_ROOTS` | 홈·현재 디렉터리 | 분석 허용 경로(`:` 구분) |
| `NVIDIA_NIM_API_KEY` | 없음 | NVIDIA NIM 키 |
| `GROQ_API_KEY` 등 | 없음 | 다른 Provider 키(선택) |
| `IMPACTNOTE_PORT` | 8000 | Docker 호스트 포트 |
| `REPOS_DIR` | `.` | Docker 저장소 마운트 원본 |
| `DEVFOLIO_AI_PROVIDER_FALLBACK` | 설정값 | 평가 시 `0` 으로 fallback 차단 |

전체 예시는 [`.env.example`](../.env.example) 에 있다. 실제 키가 든 `.env` 는 커밋하지 않는다.

## 5. 데이터 저장 구조

```text
<data_dir>/
  activities.json
  achievements.json
  evidence.json
  metrics.json
  reports.json
  analyses.json
  project_analyses.json
  settings.json
  exports/            # 보고서 내보내기
  migrations/         # DevFolio 백업 ZIP
```

- 파일 권한은 `0600`, 쓰기는 임시 파일 + `os.replace` 로 원자적이다.
- 백업은 데이터 디렉터리 전체를 복사하면 된다. 복원은 같은 경로에 되돌린 뒤 재실행.
- 다른 PC 로 옮길 때 JSON 만 복사해도 되지만, 키·키체인은 복사하지 않는다.

## 6. OS·아키텍처 고려사항

| 환경 | 확인된 내용 | 남은 위험 |
| --- | --- | --- |
| macOS ARM64 | 2026-11-15 Clean Clone 설치·465 테스트·CLI·Docker health 통과 | GUI 브라우저 수동 클릭은 미검증 |
| Linux AMD64 | Dockerfile `python:3.12-slim` 기반. CI Ubuntu 예정 | 실제 배포 이미지 E2E 는 CI 에서 확인 필요 |
| Windows AMD64 | CI matrix 예정, 경로 구분자·PowerShell 안내 제공 | 로컬 Windows GUI 실행은 미검증 |
| Python 3.9 | 설치 실패(`requires-python >=3.11`) | 3.11+ 사용 |

- 경로는 `pathlib.Path` 를 사용하고, Docker 내부 경로(`/app`, `/home/user`)와 호스트 경로를
  분리한다.
- PDF 는 시스템 폰트·Pango/Cairo 에 의존한다. Docker 이미지에는 CJK 폰트가 포함된다.
- Windows 에서 Docker Desktop 의 파일 공유가 막혀 있으면 `REPOS_DIR` 마운트가 실패할 수 있다.
- Git 줄바꿈 설정은 저장소에 강제하지 않는다. Windows에서 스크립트 실행 오류가 나면
  `git config core.autocrlf input` 후 다시 clone 한다(선택).
- ARM64/AMD64 이미지는 빌드 플랫폼에 맞춰 생성된다. 다른 아키텍처 배포 시
  `docker buildx build --platform` 으로 별도 빌드해야 한다.

## 7. Clean Clone 검증 절차

```bash
# 1) 작업 트리를 네트워크 없는 새 디렉터리로 스냅샷 (또는 GitHub clone)
rsync -a --exclude=.git --exclude=.venv --exclude=.env ./ /tmp/impactnote-clean/
cd /tmp/impactnote-clean

# 2) 새 가상환경
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev,all]"

# 3) 테스트
.venv/bin/pytest -q -p no:cacheprovider --no-cov

# 4) 키 없이 CLI 핵심 흐름
IMPACTNOTE_DATA_DIR=/tmp/impactnote-clean-data \
IMPACTNOTE_CONFIG_DIR=/tmp/impactnote-clean-config \
.venv/bin/impactnote init
IMPACTNOTE_DATA_DIR=/tmp/impactnote-clean-data \
IMPACTNOTE_CONFIG_DIR=/tmp/impactnote-clean-config \
.venv/bin/impactnote activity add "clone 검증" --desc "새 환경 확인"
IMPACTNOTE_DATA_DIR=/tmp/impactnote-clean-data \
IMPACTNOTE_CONFIG_DIR=/tmp/impactnote-clean-config \
.venv/bin/impactnote report generate --template weekly --period week --format md

# 5) Docker
IMPACTNOTE_PORT=18000 docker compose -p impactnote-clean up -d --build
curl -fsS http://127.0.0.1:18000/api/health
```

2026-11-15 실제 결과:

- 새 Git 스냅샷 clone, 새 venv, `pip install -e ".[dev,all]"` 성공
- `465 passed`
- AI 키 없이 `init` → 기록 → 주간 보고서 → 목록 조회 성공
- Docker 이미지 빌드·health check 성공 (상세 결과는 [`evaluation-results.md`](evaluation-results.md))

## 8. 문제 해결

| 증상 | 확인 |
| --- | --- |
| `No module named impactnote` | venv 활성화, `pip install -e .` |
| `requires-python >=3.11` | Python 3.9 이하. 3.11+ 인터프리터로 venv 재생성 |
| 포트 8000 사용 중 | `IMPACTNOTE_PORT` 또는 `impactnote serve --port 8001` |
| Docker health 실패 | `docker compose logs impactnote`, 포트·볼륨 권한 확인 |
| AI 401 | 키 주입 확인. 키를 문서·로그에 붙이지 않는다 |
| AI 410/404 | 모델 ID 폐기/접근 불가. [`nvidia-provider.md`](nvidia-provider.md) |
| 분석 경로 거부 | `IMPACTNOTE_ANALYZE_ROOTS` 에 경로 포함, Docker 는 `/home/user` 하위 |
| PDF 실패 | Pango/Cairo·CJK 폰트 설치. Docker 이미지 사용 권장 |
| 보고서에 숫자가 `[확인 필요]` | 의도된 가드레일. 근거·지표를 먼저 등록 |

## 9. 설치 후 AI 를 쓰지 않는 경우

AI 키가 없어도 다음은 정상 동작한다.

- 업무 기록 CRUD, 성과·근거·지표 관리
- Git 커밋 후보 추출(규칙 기반, AI 미사용)
- 문서·코드·Git 프로젝트 분석의 결정론 부분
- Markdown/DOCX/PDF/TXT/CSV 보고서 생성
- DevFolio 데이터 이전

AI 분석만 `EXTERNAL_AI_NOT_ALLOWED` 또는 인증 오류로 실패하며, 원본 기록은 바뀌지 않는다.

정성 효과 Gate 는 새 패키지·서비스를 요구하지 않는다. AI를 쓰지 않아도 보고서 생성 시
기계 생성 성과의 효과 문장을 근거와 대조하며, 차단 사유는 "확인 필요 항목"에 표시된다.
