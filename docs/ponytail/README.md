# Ponytail 운영 지침 (vendored)

기준일: 2026-11-15

ImpactNote에서 사용하는 Ponytail 방식의 원문과 적용 범위를 기록한다. 이것은 플러그인 설치가
아니라 **공개 지침을 읽고 Freebuff 기본 도구로 재현하는 운영 규칙**이다.

## 원문 출처

- 저장소: https://github.com/DietrichGebert/ponytail
- 기준 commit: `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`
- commit 날짜: 2026-10-29
- 라이선스: **MIT** (Copyright (c) 2026 DietrichGebert)
- 원문 다운로드: `raw.githubusercontent.com`의 위 commit 고정 URL

| 파일 | 원문 |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | 공통 규칙 |
| [`SKILL.md`](SKILL.md) | 핵심 Ponytail 스킬 |
| [`review.md`](review.md) | Ponytail Review |
| [`audit.md`](audit.md) | Ponytail Audit |
| [`debt.md`](debt.md) | Ponytail Debt |
| [`gain.md`](gain.md) | Ponytail Gain |
| [`LICENSE`](LICENSE) | MIT 라이선스 전문 |

위 파일은 다운로드한 원문을 그대로 보존한다. 프로젝트별 충돌 해소와 실행 규칙은 이 문서와
루트 `AGENTS.md`·`CLAUDE.md`에만 추가하며, 원문 파일은 수정하지 않는다.

## SHA-256

```text
fb1bc6909ac3ef82d5c22106e32ef682b0cff66788fa915fb9b53b15c9d2f3ab  LICENSE
9badd22a32e19cb884e46dfa8d3aae82bb81dfa5484105b8b4f0262df823a509  SKILL.md
b98b15e1d683ee205e124b52b8d330128593f4a87b545cf8185e2712cd1bb25f  AGENTS.md
33fe4ebe22a460924e5d4a261e223df22e409cc94ab76182bee9fb91a3ef022e  review.md
2b3223a02c386d1263e1b08343cb8eb3a53e444cdafb1d79e26c8ec2a8fcad28  audit.md
b5ec2762f6ba8c4af9ea7173aa6c9f91b88655a25e43f9de0264f6ce8722b25f  debt.md
231034a896d6762e4b5c8468287083422c56b499119976ec9f76821f7d083090  gain.md
```

## 적용 방식

- 기본 강도: **FULL**.
- 사용자가 `Ponytail lite`, `Ponytail full`, `Ponytail ultra`, `Ponytail off`라고 말하면
  강도를 바꾼다.
- `Ponytail Review`/`코드 검토`: 미커밋 변경 → 없으면 최근 커밋을 검토한다. 기본은 수정 없이
  보고서만 작성한다.
- `Ponytail Audit`: 전체 저장소를 조사하고 중요도순 보고서를 작성한다. 요청 없이 전체를
  재작성하지 않는다.
- `Ponytail Debt`: `shortcut:`/`ponytail:` 주석을 세어 파일·제한·업그레이드 시점을 기록한다.
- `Ponytail Gain`: 공식 벤치마크 수치를 표시할 뿐, 이 저장소의 절감량을 만들어내지 않는다.
- Freebuff에는 Ponytail 플러그인 런타임·슬래시 명령·자동 훅이 없다. 위 동작은 파일 읽기,
  Git diff, 테스트 실행, 코드 검색으로 수동 재현한다.

## 충돌 해소

ImpactNote의 기존 규칙이 Ponytail보다 우선한다.

1. **안전·가드레일 우선**: 근거 없는 수치 금지, AI 동의, `verified` 확인, DevFolio 원본 보호,
   키 비노출, path traversal/XSS 방지는 단순화 대상이 아니다.
2. **호환 계층 보존**: `devfolio/`는 삭제하지 않는다. “dead code”로 보여도 레거시 CLI/API/YAML
   호환을 위해 유지한다.
3. **검증 우선**: FULL의 “가장 작은 변경”은 테스트·호출자·fixture·문서까지 완료한다는 뜻이다.
   테스트 삭제나 검증 약화로 diff를 줄이지 않는다.
4. **Ponytail은 기능 추가 명령이 아니다**: 요청하지 않은 기능, 추상화, 의존성, 마이크로서비스,
   큐, 별도 DB를 추가하지 않는다.
5. **원문과 프로젝트 규칙이 충돌하면** 제품 안전 규칙을 적용하고, 그 사실을 최종 보고에 적는다.

## Freebuff 지원 범위

| Ponytail 기능 | Freebuff 재현 |
| --- | --- |
| 지침 로드 | 저장소의 `AGENTS.md`/`CLAUDE.md`와 이 디렉터리의 원문을 파일로 읽음 |
| FULL/LITE/ULTRA/OFF | 사용자 문구로 세션 내 전환 |
| Review | `git diff`, 호출자 검색, 테스트 실행, 보고서 작성 |
| Audit | 저장소 탐색·의존성·테스트·실행 경로 조사 |
| Debt | `shortcut:`/`ponytail:`/TODO/FIXME 검색 |
| Gain | 공식 벤치마크 표시 또는 실제 전후 측정값만 사용 |
| 플러그인 훅/슬래시 명령 | **미지원**. 실행한 척하지 않음 |

## 적용하지 않는 것

- Ponytail 플러그인 설치, 자동 훅, 세션 상태 저장, 슬래시 명령 실행
- 공식 벤치마크 수치를 이 저장소의 절감량으로 변환
- “lazy”를 이유로 한 입력 검증·보안·접근성·오류 처리·요구사항 생략
