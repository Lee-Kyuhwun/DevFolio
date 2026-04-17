"""DevFolio 커스텀 예외 클래스.

[Spring 비교]
  Spring 에서 @ResponseStatus 나 ResponseEntityExceptionHandler 로 처리하는
  도메인 예외 계층을 Python 예외 상속 구조로 구현한 것.

  DevfolioError (기반)
    ├── DevfolioConfigError        → 설정/초기화 관련
    │     └── DevfolioNotInitializedError
    ├── DevfolioProjectNotFoundError → 프로젝트 조회 실패 (404)
    ├── DevfolioTaskNotFoundError    → 작업 조회 실패 (404)
    ├── DevfolioAIError              → AI 서비스 관련
    │     ├── DevfolioAINotConfiguredError
    │     ├── DevfolioAIAuthError
    │     └── DevfolioAIRateLimitError
    ├── DevfolioTemplateError        → Jinja2 템플릿 관련
    ├── DevfolioExportError          → 내보내기 관련
    ├── DevfolioSyncError            → GitHub 동기화 관련
    │     └── DevfolioSyncNotConfiguredError
    └── DevfolioYAMLError            → YAML 파싱/저장 관련
"""


# Exception : Python 모든 예외의 최상위 클래스.
#   [Spring] java.lang.Exception 을 상속하는 것과 동일.
class DevfolioError(Exception):
    """DevFolio 기반 예외 클래스.

    [Spring 비교]
      모든 도메인 예외의 최상위. Spring 의 RuntimeException 역할.
      message(메시지) + hint(해결 방법 힌트) 두 필드를 표준 인터페이스로 제공한다.
    """

    # __init__ : 생성자. [Spring] 생성자 오버로딩과 동일.
    # hint: str = "" : 기본값이 있는 매개변수. [Spring] 선택적 파라미터.
    def __init__(self, message: str, hint: str = ""):
        # super().__init__(message) : 부모 클래스(Exception) 생성자 호출.
        # [Spring] super(message) — Exception(String message) 생성자 호출.
        super().__init__(message)
        # 인스턴스 변수 저장. [Spring] this.message = message 와 동일.
        self.message = message
        self.hint = hint


# class 자식(부모): ... → Java class 자식 extends 부모 와 동일.
class DevfolioConfigError(DevfolioError):
    """설정 관련 오류 — 기반 클래스.

    [Spring 비교]
      설정 관련 예외를 한 계층으로 묶어 catch 할 수 있게 하는 마커 예외.
    """
    # 별도 __init__ 없음 → 부모(DevfolioError) 의 __init__ 을 그대로 상속.
    # [Spring] 생성자 없이 super 생성자를 암묵적으로 사용하는 것과 동일.


class DevfolioNotInitializedError(DevfolioConfigError):
    """초기화되지 않은 상태에서 명령 실행 시 발생.

    [Spring 비교]
      IllegalStateException — "초기화 전에 호출" 과 동일한 의미.
    """

    # __init__(self) : 인자 없는 생성자. 메시지/힌트가 고정되어 있어 재정의.
    # [Spring] new DevfolioNotInitializedError() 처럼 매개변수 없이 생성.
    def __init__(self):
        # super().__init__(message=..., hint=...) : 부모 생성자를 키워드 인수로 호출.
        super().__init__(
            message="DevFolio가 초기화되지 않았습니다.",
            hint="`devfolio init` 명령으로 먼저 초기화하세요.",
        )


class DevfolioProjectNotFoundError(DevfolioError):
    """프로젝트를 찾을 수 없을 때 발생.

    [Spring 비교]
      @ResponseStatus(HttpStatus.NOT_FOUND) 를 붙인 예외.
      EntityNotFoundException / NoSuchElementException 계열.
    """

    # name: str : 못 찾은 프로젝트명을 받아 메시지에 포함.
    def __init__(self, name: str):
        # f"..." : f-string. Java String.format("...", name) 과 동일.
        super().__init__(
            message=f"프로젝트를 찾을 수 없습니다: '{name}'",
            hint="`devfolio project list` 명령으로 등록된 프로젝트를 확인하세요.",
        )


class DevfolioTaskNotFoundError(DevfolioError):
    """작업 내역을 찾을 수 없을 때 발생.

    [Spring 비교]
      DevfolioProjectNotFoundError 와 동일, Task 전용 버전.
    """

    # project_name: str = "" : 기본값이 있는 선택적 매개변수.
    def __init__(self, task_name: str, project_name: str = ""):
        # 조건부 문자열 조합.
        # "A if 조건 else B" : Java 의 조건 ? A : B 삼항 연산자.
        project_info = f" (프로젝트: {project_name})" if project_name else ""
        super().__init__(
            message=f"작업 내역을 찾을 수 없습니다: '{task_name}'{project_info}",
            hint="`devfolio task list <프로젝트명>` 명령으로 작업 목록을 확인하세요.",
        )


class DevfolioAIError(DevfolioError):
    """AI 서비스 관련 오류 — 기반 클래스."""


class DevfolioAINotConfiguredError(DevfolioAIError):
    """AI Provider 가 설정되지 않았을 때 발생."""

    def __init__(self):
        super().__init__(
            message="AI Provider가 설정되지 않았습니다.",
            hint="`devfolio config ai set` 명령으로 AI Provider를 등록하세요.",
        )


class DevfolioAIAuthError(DevfolioAIError):
    """AI API 인증 오류 — 잘못된 API 키 등."""

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
    """Jinja2 템플릿 관련 오류.

    [Spring 비교]
      Thymeleaf TemplateEngineException / TemplateNotFoundException 에 해당.
    """

    def __init__(self, template_name: str):
        super().__init__(
            message=f"템플릿을 찾을 수 없거나 렌더링에 실패했습니다: '{template_name}'",
            hint=(
                "~/.devfolio/templates/ 경로를 확인하거나 "
                "`devfolio export --template default`로 기본 템플릿을 사용하세요."
            ),
        )


class DevfolioExportError(DevfolioError):
    """내보내기(MD/PDF/DOCX/HTML) 관련 오류."""


class DevfolioSyncError(DevfolioError):
    """Git/GitHub 동기화 관련 오류."""


class DevfolioSyncNotConfiguredError(DevfolioSyncError):
    """GitHub sync 설정이 비어 있을 때 발생."""

    def __init__(self):
        super().__init__(
            message="GitHub 동기화가 설정되지 않았습니다.",
            hint="`devfolio sync setup` 명령으로 백업 저장소를 먼저 연결하세요.",
        )


class DevfolioYAMLError(DevfolioError):
    """YAML 파일 파싱/저장 오류.

    [Spring 비교]
      Jackson JsonParseException / YAMLException 에 해당.
    """

    def __init__(self, path: str, detail: str = ""):
        super().__init__(
            # detail 이 있으면 개행 + 들여쓰기로 추가. 없으면 빈 문자열.
            message=f"YAML 파일을 처리할 수 없습니다: {path}" + (f"\n  {detail}" if detail else ""),
            hint="파일이 올바른 YAML 형식인지 확인하세요.",
        )
