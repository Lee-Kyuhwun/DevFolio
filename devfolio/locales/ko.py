"""한국어 문자열 카탈로그."""

STRINGS: dict[str, str] = {
    # 공통
    "not_initialized": "DevFolio가 초기화되지 않았습니다.",
    "not_initialized_hint": "`devfolio init`을 먼저 실행하세요.",
    "cancelled": "취소되었습니다.",
    "success": "완료!",

    # 프로젝트
    "project.not_found": "프로젝트를 찾을 수 없습니다: {name}",
    "project.not_found_hint": "`devfolio project list`로 프로젝트 목록을 확인하세요.",
    "project.duplicate": "이미 같은 이름의 프로젝트가 있습니다: '{name}'",
    "project.duplicate_hint": "`devfolio project list`로 기존 프로젝트를 확인하세요.",
    "project.created": "프로젝트 등록 완료! ID: {id}",
    "project.deleted": "'{name}' 삭제되었습니다.",
    "project.updated": "수정되었습니다.",
    "project.none": "등록된 프로젝트가 없습니다.",
    "project.none_hint": "`devfolio project add`로 첫 프로젝트를 등록하세요.",

    # 작업
    "task.not_found": "작업을 찾을 수 없습니다: {name} (프로젝트: {project})",
    "task.not_found_hint": "`devfolio task list <프로젝트명>`으로 작업 목록을 확인하세요.",
    "task.created": "작업 내역 등록 완료! ID: {id}",
    "task.deleted": "'{name}' 삭제되었습니다.",
    "task.updated": "수정되었습니다.",
    "task.none": "등록된 작업 내역이 없습니다.",
    "task.ai_cache_cleared": "내용이 변경되어 AI 캐시가 초기화되었습니다. `devfolio ai generate task`로 다시 생성하세요.",

    # 내보내기
    "export.done": "내보내기 완료: {path}",
    "export.sync_hint": "다음 단계: `devfolio sync run`으로 GitHub 백업을 갱신할 수 있습니다.",
    "export.invalid_format": "지원하지 않는 포맷입니다: {fmt}",
    "export.invalid_format_hint": "지원 포맷: {formats}",
    "export.no_projects": "등록된 프로젝트가 없습니다.",
    "export.no_projects_hint": "`devfolio project add`로 첫 프로젝트를 먼저 등록하세요.",
    "export.project_not_found": "지정한 프로젝트를 찾을 수 없습니다.",
    "export.project_not_found_hint": "`devfolio project list`로 프로젝트명과 ID를 확인하세요.",
    "export.generating": "문서를 생성하는 중...",
    "export.path_error": "출력 경로가 허용 범위를 벗어났습니다: {path}",
    "export.path_error_hint": "홈 디렉터리 또는 현재 작업 디렉터리 하위 경로를 지정하세요.",

    # AI
    "ai.not_configured": "AI Provider가 설정되지 않았습니다.",
    "ai.not_configured_hint": "`devfolio config ai set`으로 AI Provider를 설정하세요.",
    "ai.auth_error": "API 인증에 실패했습니다: {provider}",
    "ai.rate_limit": "API 요청 한도를 초과했습니다: {provider}",
    "ai.error": "AI 호출 중 오류가 발생했습니다: {message}",
    "ai.generating": "{provider}로 텍스트를 생성하는 중...",
    "ai.done": "AI 생성 완료.",

    # Sync
    "sync.not_configured": "GitHub 동기화가 설정되지 않았습니다.",
    "sync.not_configured_hint": "`devfolio sync setup`으로 저장소를 설정하세요.",
    "sync.done": "GitHub 동기화가 완료되었습니다.",
    "sync.no_changes": "변경 사항이 없어 GitHub 동기화는 건너뛰었습니다.",
    "sync.connected": "GitHub 동기화 저장소가 연결되었습니다: {url}",

    # 설정
    "config.saved": "기본값이 업데이트되었습니다.",
    "config.no_changes": "변경할 항목을 --format, --lang, --provider 옵션으로 지정하세요.",
    "config.invalid_format": "유효하지 않은 포맷: {fmt}",
    "config.invalid_lang": "유효하지 않은 언어: {lang}",

    # 유효성 검사
    "validate.team_size_invalid": "'{value}'은(는) 유효한 숫자가 아닙니다. 기본값 1로 설정합니다.",
    "validate.team_size_negative": "팀 규모는 1 이상이어야 합니다. 기본값 1로 설정합니다.",
    "validate.email_invalid": "유효하지 않은 이메일 형식입니다: {value}",
    "validate.url_invalid": "URL은 http:// 또는 https://로 시작해야 합니다: {value}",
    "validate.branch_invalid": "유효하지 않은 브랜치 이름입니다: {value}",
}
