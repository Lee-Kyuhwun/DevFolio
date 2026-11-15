# Agent E — Portability Auditor

감사일: 2026-11-15 · 대상: 새 Clone, Docker, 데이터 경로, CI

## 범위

- 다른 PC에서 새로 clone해 설치·실행되는가
- 기존 `.venv`·`.env`·데이터·키체인 없이 동작하는가
- Docker 빌드·health·핵심 API가 동작하는가
- 경로·포트·OS 의존성이 하드코딩되지 않았는가
- CI가 이 검증을 자동화하는가

## 확인한 증거

1. 작업 트리를 `.git`·`.venv`·`.env` 없이 새 디렉터리에 스냅샷하고 새 Git 저장소로 clone.
2. 새 venv(`Python 3.14.4`)에서 `pip install -e ".[dev,all]"` 성공.
3. **465 passed** (28.95s).
4. AI 키 없이:
   - `impactnote init` → 데이터 디렉터리 생성
   - `activity add` → 기록 생성
   - `report generate --template weekly` → 424자 Markdown 본문
   - `activity list` → 기록 조회
5. Docker:
   - `docker compose -p impactnote-clone2 up -d --build` 성공
   - `127.0.0.1:18001`에서 `/api/health` HTTP 200
   - `/api/meta`에서 `external_ai_enabled: false`
   - 테스트 후 컨테이너·볼륨 정리
6. 경로/포트:
   - `IMPACTNOTE_PORT`로 호스트 포트 변경
   - `REPOS_DIR` 기본값을 현재 디렉터리로 변경
   - 데이터·설정은 named volume/`IMPACTNOTE_*`로 분리
7. `docker compose config` 성공. CI YAML parse 성공.
8. CI에 Ubuntu/macOS/Windows Python 3.12 job, Python 3.11–3.14 job, Docker health job 추가.

## 발견 사항

1. **macOS 기본 Python 3.9.6 실패를 재현**했다. `requires-python >=3.11`이므로 3.11+
   인터프리터를 명시해야 한다. 설치 문서에 반영했다.
2. **GitHub 원격 Clean Clone은 수행하지 못했다.** 현재 변경을 push하지 않았기 때문이다.
   대신 동일 파일 집합을 새 Git 저장소로 clone해 검증했다. CI는 push 후 원격 clone을
   자동 검증하도록 설계했다.
3. **Windows/macOS 실제 GUI 클릭은 미검증**이다. CI의 테스트는 GUI 창을 띄우지 않는다.
4. Docker Compose는 여전히 현재 디렉터리를 `/app`에 바인드 마운트한다. 개발용으로는
   편리하지만, 운영 이미지처럼 immutable하게 쓰려면 별도 compose override가 필요하다.
5. PDF 렌더링의 OS별 폰트 차이는 미검증이다.

## 판정

**Clean Clone + Docker 핵심 경로: PASS (macOS ARM64).**
**전체 OS/아키텍처 호환 보장: CONDITIONAL** — CI와 Windows 수동 검증이 남았다.
