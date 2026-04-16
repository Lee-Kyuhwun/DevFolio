"""DevFolio 커스텀 예외 클래스."""


class DevfolioError(Exception):
    """DevFolio 기본 예외."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.hint = hint


class DevfolioConfigError(DevfolioError):
    """설정 관련 오류."""


class DevfolioNotInitializedError(DevfolioConfigError):
    """초기화되지 않은 상태에서 명령 실행."""

    def __init__(self):
        super().__init__(
            message="DevFolio가 초기화되지 않았습니다.",
            hint="`devfolio init` 명령으로 먼저 초기화하세요.",
        )


class DevfolioProjectNotFoundError(DevfolioError):
    """프로젝트를 찾을 수 없음."""

    def __init__(self, name: str):
        super().__init__(
            message=f"프로젝트를 찾을 수 없습니다: '{name}'",
            hint="`devfolio project list` 명령으로 등록된 프로젝트를 확인하세요.",
        )


class DevfolioTaskNotFoundError(DevfolioError):
    """작업 내역을 찾을 수 없음."""

    def __init__(self, task_name: str, project_name: str = ""):
        project_info = f" (프로젝트: {project_name})" if project_name else ""
        super().__init__(
            message=f"작업 내역을 찾을 수 없습니다: '{task_name}'{project_info}",
            hint="`devfolio task list <프로젝트명>` 명령으로 작업 목록을 확인하세요.",
        )


class DevfolioAIError(DevfolioError):
    """AI 서비스 관련 오류."""


class DevfolioAINotConfiguredError(DevfolioAIError):
    """AI Provider가 설정되지 않음."""

    def __init__(self):
        super().__init__(
            message="AI Provider가 설정되지 않았습니다.",
            hint="`devfolio config ai set` 명령으로 AI Provider를 등록하세요.",
        )


class DevfolioAIAuthError(DevfolioAIError):
    """AI API 인증 오류."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"{provider} API 키가 유효하지 않거나 설정되지 않았습니다.",
            hint=f"`devfolio config ai set --provider {provider}` 명령으로 API 키를 재등록하세요.",
        )


class DevfolioAIRateLimitError(DevfolioAIError):
    """AI API 요청 한도 초과."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"{provider} API 요청 한도를 초과했습니다.",
            hint="잠시 후 다시 시도하거나, 다른 Provider를 사용하세요.",
        )


class DevfolioTemplateError(DevfolioError):
    """템플릿 관련 오류."""

    def __init__(self, template_name: str):
        super().__init__(
            message=f"템플릿을 찾을 수 없거나 렌더링에 실패했습니다: '{template_name}'",
            hint=(
                "~/.devfolio/templates/ 경로를 확인하거나 "
                "`devfolio export --template default`로 기본 템플릿을 사용하세요."
            ),
        )


class DevfolioExportError(DevfolioError):
    """내보내기 관련 오류."""


class DevfolioSyncError(DevfolioError):
    """Git/GitHub 동기화 관련 오류."""


class DevfolioSyncNotConfiguredError(DevfolioSyncError):
    """GitHub sync 설정이 비어 있음."""

    def __init__(self):
        super().__init__(
            message="GitHub 동기화가 설정되지 않았습니다.",
            hint="`devfolio sync setup` 명령으로 백업 저장소를 먼저 연결하세요.",
        )


class DevfolioYAMLError(DevfolioError):
    """YAML 파일 파싱/저장 오류."""

    def __init__(self, path: str, detail: str = ""):
        super().__init__(
            message=f"YAML 파일을 처리할 수 없습니다: {path}" + (f"\n  {detail}" if detail else ""),
            hint="파일이 올바른 YAML 형식인지 확인하세요.",
        )
