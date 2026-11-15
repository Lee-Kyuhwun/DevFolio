# Agent F — Documentation Auditor

감사일: 2026-11-15 · 대상: README, `docs/architecture.md`, `docs/ai-evaluation.md`,
`docs/nvidia-provider.md`, `docs/installation.md`, `docs/testing.md`,
`docs/evaluation-results.md`

## 범위

- 문서가 현재 코드·테스트·실행 방법과 일치하는가
- 존재하지 않는 명령·기능을 안내하지 않는가
- 상대 링크가 깨지지 않았는가
- 평가 수치·표본 수·판정이 결과 JSON과 일치하는가
- 비밀키·회사 자료가 문서에 없는가

## 확인한 증거

1. 9개 문서의 로컬 Markdown 링크 검사 → **깨진 링크 0**.
2. `python -m evals.impact.run --help`:
   `--live`, `--offline`, `--no-judge`, `--out` 확인.
3. 새 venv의 `impactnote --help`:
   `version`, `init`, `serve`, `migrate`, `activity`, `achievement`, `report`, `intel` 확인.
4. `docker compose config`:
   `127.0.0.1:${IMPACTNOTE_PORT}:8000`, 데이터/설정/legacy/repo 마운트 확인.
5. `.env.example`에 실제 키 패턴 없음. `.env`·`api_keys.json`은 gitignore.
6. 문서 수치가 `latest.json`과 일치:
   - 42 claims, 47.6%, 20 quality, 3.68/2.65, 12 doc, 8 attribution, 3 live.
7. 테스트 수 465가 README·testing·impactnote·evaluation-results에서 일치.
8. CI workflow YAML parse OK.

## 발견 사항

1. **현재 개발 venv에는 `impactnote` console script가 없다.**
   저장소 루트의 `.venv`는 프로젝트를 editable 설치하지 않은 상태였다. Clean Clone의 새 venv에는
   entry point가 정상 생성되어 `impactnote --help`가 동작했다. README의 설치 절차를 따른
   사용자에게는 문제가 없지만, 이 개발 venv에서 명령을 바로 실행하면 실패한다.
   문서는 “설치 후 실행”을 전제로 하며, 이 사실을 감사 결과에 남긴다.
2. **OmniRoute**: 문서는 “확인되지 않음/미지원”으로만 쓰고, 사용했다고 주장하지 않는다.
3. **비용**: 문서는 `NOT_MEASURED`로 표기하며 0원이라고 하지 않는다.
4. **Windows GUI**: 문서는 미검증을 명시한다.
5. `docs/04-architecture.md`는 역사 자료로 남아 있고, 현재 문서는 `architecture.md`로
   연결된다. 오래된 문서를 삭제하지 않았다.

## 판정

**문서 일치성: PASS (검증된 범위).** 존재하지 않는 명령을 안내하는 사례는 발견하지 못했다.
다만 개발 venv의 entry point 부재는 사용자 환경별로 다를 수 있으므로 설치 문서의 전제를
따라야 한다.
