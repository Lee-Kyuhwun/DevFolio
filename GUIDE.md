# DevFolio 시작 가이드

처음 설치부터 AI 키 발급, 등록, 첫 포트폴리오 생성까지 단계별로 안내합니다.

---

## 목차

1. [설치](#1-설치)
2. [초기 설정 (init)](#2-초기-설정-init)
3. [AI 키 발급](#3-ai-키-발급)
4. [AI 키 등록](#4-ai-키-등록)
5. [웹 UI 사용법](#5-웹-ui-사용법)
6. [CLI 사용법 (선택)](#6-cli-사용법-선택)
7. [Git 저장소 자동 분석](#7-git-저장소-자동-분석)
8. [문서 내보내기](#8-문서-내보내기)
9. [FAQ](#9-faq)

---

## 1. 설치

### 방법 A — pip 설치 (권장)

Python 3.11 이상이 필요합니다.

```bash
# 저장소 클론
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio

# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 전체 기능 설치 (AI + 내보내기 + 웹 UI)
pip install -e ".[all]"

# 설치 확인
devfolio --help
```

> **기능별 선택 설치**
> | 옵션 | 포함 기능 |
> |---|---|
> | `pip install -e .` | 기본 CLI만 |
> | `pip install -e ".[ai]"` | AI 초안 생성 추가 |
> | `pip install -e ".[gui]"` | 웹 UI 추가 |
> | `pip install -e ".[all]"` | 모든 기능 (권장) |

---

### 방법 B — Docker (웹 UI만 사용할 경우)

Python 설치 없이 웹 UI만 바로 사용할 수 있습니다.

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio

docker compose up --build
```

브라우저에서 `http://localhost:8000` 접속.

> **제한:** Docker 환경에서는 `devfolio scan`(Git 분석)을 사용할 수 없습니다.  
> 로컬 pip 설치 방식을 권장합니다.

---

## 2. 초기 설정 (init)

설치 후 한 번만 실행합니다. 이름, 이메일, AI 설정을 대화형으로 입력합니다.

```bash
devfolio init
```

순서대로 입력합니다:

```
이름: 홍길동
이메일: hong@example.com
GitHub URL (선택): https://github.com/honggildong
블로그 URL (선택): https://blog.example.com

AI Provider를 지금 설정하시겠습니까? (y/n): y
→ 아래 3단계에서 키를 발급한 뒤 다시 입력하거나, 나중에 등록해도 됩니다.
```

> **나중에 이름/이메일을 바꾸려면:**
> ```bash
> devfolio config user set --name "홍길동" --email "hong@example.com"
> ```

---

## 3. AI 키 발급

AI 기능(초안 자동 생성, 문구 개선 등)을 사용하려면 API 키가 필요합니다.  
**키가 없어도 수동 입력과 문서 내보내기는 가능합니다.**

아래 4개 제공자 중 하나를 선택하세요.

---

### Anthropic (Claude) — 권장

1. [console.anthropic.com](https://console.anthropic.com) 접속 → 회원가입 또는 로그인
2. 좌측 메뉴 **API Keys** → **Create Key**
3. 키 이름 입력 (예: `devfolio`) → **Create Key** 클릭
4. 표시된 `sk-ant-...` 값을 복사 (이 창을 닫으면 다시 볼 수 없음)

> 무료 크레딧으로 시작 가능합니다.  
> 권장 모델: `claude-sonnet-4-20250514`

---

### OpenAI (GPT)

1. [platform.openai.com](https://platform.openai.com) 접속 → 회원가입 또는 로그인
2. 우측 상단 프로필 → **API keys** → **Create new secret key**
3. 키 이름 입력 → **Create secret key** 클릭
4. 표시된 `sk-...` 값을 복사

> 권장 모델: `gpt-4o`

---

### Google Gemini

1. [aistudio.google.com](https://aistudio.google.com) 접속 → Google 계정 로그인
2. 좌측 **Get API key** → **Create API key**
3. 프로젝트 선택 또는 새 프로젝트 생성 → **Create API key in existing project**
4. 표시된 `AIza...` 값을 복사

> 권장 모델: `gemini-1.5-flash` (무료 구간 있음)

---

### Ollama (로컬, 무료)

인터넷 연결 없이 로컬에서 실행됩니다. API 키가 필요 없습니다.

```bash
# Ollama 설치 (macOS)
brew install ollama

# 모델 다운로드 (약 2~4GB)
ollama pull llama3.2

# 서버 실행
ollama serve
```

기본 주소: `http://localhost:11434`  
모델 설정 시 Base URL은 위 주소를 입력합니다.

---

## 4. AI 키 등록

### 방법 A — 웹 UI에서 등록 (권장)

1. `devfolio serve` 실행 → 브라우저에서 `http://127.0.0.1:8000` 접속
2. 우측 상단 또는 사이드바에서 **Settings** 탭 클릭
3. **AI 모델 설정** 섹션으로 이동
4. **제공자** 선택 (Anthropic / OpenAI / Gemini / Ollama)
5. **모델** 입력 (예: `claude-sonnet-4-20250514`)
6. **API 키** 입력 → **저장** 클릭

키는 OS 키체인(macOS Keychain / Windows Credential Manager / Linux Secret Service)에 안전하게 저장됩니다.

---

### 방법 B — CLI에서 등록

```bash
devfolio config ai set
```

프롬프트에 따라 입력합니다:

```
Provider 이름 [anthropic/openai/gemini/ollama]: anthropic
모델: claude-sonnet-4-20250514
API 키: sk-ant-xxxxxxxx...
```

등록 확인:

```bash
devfolio config ai list
# anthropic  claude-sonnet-4-20250514  sk-an...****
```

연결 테스트:

```bash
devfolio config ai test
# ✓ 연결 성공
```

---

### 방법 C — 환경 변수로 설정 (CI/서버 환경)

키를 파일에 저장하지 않고 환경 변수로만 사용할 수 있습니다.

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Gemini
export GEMINI_API_KEY="AIza..."
```

`.env` 파일에 저장하고 싶다면 (Docker 사용 시):

```
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## 5. 웹 UI 사용법

```bash
devfolio serve
# → http://127.0.0.1:8000 자동 열림
```

### 기본 흐름

```
입력 → AI 초안 → 검토·수정 → 내보내기
```

| 탭 | 역할 |
|---|---|
| **입력** | 프로젝트 경험을 자유롭게 붙여넣기 |
| **Git Scan** | 로컬 Git 저장소를 분석해 자동 생성 |
| **Projects** | 저장된 프로젝트 관리 |
| **미리보기** | 이력서·포트폴리오 미리보기 및 내보내기 |
| **Settings** | 프로필·AI·내보내기 설정 |

### 첫 번째 초안 만들기

1. **입력** 탭으로 이동
2. 텍스트 영역에 프로젝트 경험을 자유롭게 붙여넣기  
   (노션 내용, 깃허브 PR 설명, 회의록, 업무 메모 무엇이든)
3. AI 모델 선택 → **AI로 초안 만들기** 클릭
4. 오른쪽 패널에 초안이 생성되면 내용 검토 및 수정
5. **초안 저장** 클릭

---

## 6. CLI 사용법 (선택)

웹 UI 없이 터미널에서만 사용하는 방법입니다.

```bash
# 프로젝트 추가 (대화형)
devfolio project add

# 작업 추가
devfolio task add --project PROJECT_ID

# AI로 작업 bullet 생성
devfolio ai generate task --project PROJECT_ID

# 전체 이력서 AI 생성
devfolio ai generate resume

# 이력서 내보내기
devfolio export resume --format pdf

# 포트폴리오 내보내기
devfolio export portfolio --format html
```

---

## 7. Git 저장소 자동 분석

본인이 작업한 Git 저장소를 분석해 포트폴리오 프로젝트를 자동으로 생성합니다.

### 웹 UI에서

1. **Git Scan** 탭으로 이동
2. **저장소 경로** 입력 (예: `/Users/me/projects/my-app` 또는 `.`)
3. **Author Email** 입력 (생략 시 Git 설정 이메일 사용)
4. 소스 코드까지 분석하려면 **AI 상세 분석** 체크 (API 키 필요)
5. **분석 시작** 클릭
6. 결과 확인 후 **초안으로 불러오기** 클릭

### CLI에서

```bash
# 기본 스캔 (커밋 통계만)
devfolio scan /path/to/your/repo

# AI 상세 분석 (README + 소스 코드 분석)
devfolio scan /path/to/your/repo --analyze

# 언어 지정
devfolio scan . --analyze --lang ko

# 현재 디렉터리 스캔
devfolio scan .
```

---

## 8. 문서 내보내기

### 웹 UI

1. **미리보기 및 내보내기** 탭으로 이동
2. **문서 종류** 선택: 이력서 / 포트폴리오
3. **소스** 선택: 현재 초안 / 저장된 프로젝트
4. **내보내기 포맷** 선택
5. **문서 내보내기** 클릭 → 파일 경로 확인

### CLI

```bash
# Markdown
devfolio export resume --format md

# PDF
devfolio export resume --format pdf

# Word (.docx)
devfolio export resume --format docx

# HTML
devfolio export portfolio --format html
```

출력 파일은 OS 데이터 디렉터리 아래 `exports/` 폴더에 저장됩니다.

| OS | 경로 |
|---|---|
| macOS | `~/Library/Application Support/devfolio/exports/` |
| Linux | `~/.local/share/devfolio/exports/` |
| Windows | `%LOCALAPPDATA%\devfolio\devfolio\exports\` |

---

## 9. FAQ

**Q. AI 키 없이도 사용할 수 있나요?**  
네. 수동으로 프로젝트와 작업 내용을 입력하고 저장한 뒤 이력서·포트폴리오로 내보낼 수 있습니다. AI 기능(초안 자동 생성, 문구 개선)만 비활성화됩니다.

---

**Q. API 키가 어디에 저장되나요? 안전한가요?**  
키는 OS 키체인에 저장됩니다 (macOS Keychain, Windows Credential Manager, Linux Secret Service). 설정 파일이나 코드에는 저장되지 않습니다. 환경 변수로 주입하는 경우에도 평문 로그에는 절대 출력되지 않습니다.

---

**Q. 어떤 AI 제공자를 선택해야 하나요?**

| 상황 | 추천 |
|---|---|
| 처음 시작, 무료 크레딧 사용 | Anthropic 또는 Gemini |
| 인터넷 없이 오프라인 사용 | Ollama (로컬) |
| GPT 계열 선호 | OpenAI |

---

**Q. `devfolio init`을 이미 실행했는데 AI 설정을 나중에 추가할 수 있나요?**  
```bash
devfolio config ai set
# 또는 웹 UI Settings 탭에서 언제든 추가/수정 가능
```

---

**Q. 기존 프로젝트 데이터를 백업하거나 이전하려면?**  
```bash
# 백업
devfolio data backup

# JSON으로 내보내기
devfolio data export-json

# 복원
devfolio data restore backup_file.zip
```

---

**Q. 웹 UI 포트를 바꾸고 싶어요.**  
```bash
devfolio serve --port 9000
```

---

**Q. 로그를 자세히 보려면?**  
```bash
DEVFOLIO_LOG_LEVEL=DEBUG devfolio serve
```
