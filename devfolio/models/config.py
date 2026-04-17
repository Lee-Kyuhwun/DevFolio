"""설정 파일 Pydantic 모델.

[Spring 비교]
  application.yml 의 구조를 Pydantic BaseModel 로 매핑한 것.
  Spring 의 @ConfigurationProperties + @Validated 역할을 하나로 합친 형태.
  YAML → dict → model_validate() 로 역직렬화하며, 검증 실패 시 ValidationError 발생.
"""

from __future__ import annotations

import re

# Optional[X] : "X 이거나 None". Java 의 @Nullable 또는 Optional<X> 와 같은 의미.
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AIProviderConfig(BaseModel):
    """AI Provider 설정.

    [Spring 비교]
      @ConfigurationProperties(prefix="ai.provider") 와 유사한 중첩 설정 블록.
      YAML 에서 한 Provider 항목 한 줄씩 매핑된다.
    """

    # str 기본값 없음 → required 필드. 값 없이 생성하면 ValidationError.
    # [Spring] @NotBlank 와 동일.
    name: str = Field(description="Provider 이름 (anthropic|openai|gemini|ollama)")
    model: str = Field(description="사용할 모델명")

    # bool : True/False 만 허용하는 파이썬 타입.
    # [Spring] Boolean (대소문자 무관) 또는 @NotNull boolean 과 동일.
    key_stored: bool = Field(default=False, description="키체인에 API 키 저장 여부")

    # Optional[str] = Field(default=None) : 문자열 or None, 기본값 None.
    # [Spring] @Nullable String / @Column(nullable=true) 와 유사.
    base_url: Optional[str] = Field(default=None, description="커스텀 API base URL (Ollama 등)")


class ExportConfig(BaseModel):
    """내보내기 기본값 설정.

    [Spring 비교]
      @ConfigurationProperties(prefix="export") 와 유사한 중첩 블록.
    """

    # default="md" : 값이 없을 때 사용할 기본값. [Spring] @Value("${export.format:md}")
    default_format: str = Field(default="md")
    default_template: str = Field(default="default")

    # 비어 있으면 platformdirs 경로를 사용 (runtime 에 결정).
    output_dir: str = Field(default="")


class UserConfig(BaseModel):
    """사용자 프로필.

    [Spring 비교]
      사용자가 `devfolio config user set` 명령으로 채우는 DTO.
      @ConfigurationProperties(prefix="user") + @Validated.
    """

    name: str = Field(default="")
    email: str = Field(default="")
    github: str = Field(default="")
    blog: str = Field(default="")

    # @field_validator("email")
    #   "email" 필드 하나에만 적용하는 커스텀 검증 로직.
    #   [Spring] @Email 어노테이션 또는 @ConstraintValidator<Email, String> 와 동일.
    # @classmethod : 인스턴스 없이 클래스 레벨에서 실행. Pydantic validator 필수 형식.
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # v : 검증 대상 값. 빈 문자열이면 검사 건너뜀.
        if v and "@" not in v:
            # ValueError 를 raise 하면 Pydantic 이 자동으로 ValidationError 로 변환.
            # [Spring] MethodArgumentNotValidException 과 같은 효과.
            raise ValueError(f"유효하지 않은 이메일 형식입니다: {v!r}")
        return v

    # @field_validator("github", "blog")
    #   두 필드에 동일한 검증 로직을 적용. [Spring] 동일 어노테이션을 두 필드에 붙이는 것.
    @field_validator("github", "blog")
    @classmethod
    def validate_url(cls, v: str) -> str:
        # str.startswith(tuple) : 인수로 튜플을 주면 "또는(OR)" 조건이 된다.
        # [Spring] v.startsWith("http://") || v.startsWith("https://") || ...
        if v and not v.startswith(("http://", "https://", "github.com/")):
            raise ValueError(
                f"URL은 http:// 또는 https://로 시작해야 합니다: {v!r}"
            )
        return v


class SyncConfig(BaseModel):
    """GitHub 백업 동기화 설정.

    [Spring 비교]
      @ConfigurationProperties(prefix="sync") — GitHub 저장소 URL, 브랜치명 등을 담는 VO.
    """

    enabled: bool = Field(default=False)
    repo_url: str = Field(default="")
    branch: str = Field(default="main")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        # re.match(pattern, string) : Java Pattern.matches(regex, input) 와 동일.
        # r"..." = raw string — 백슬래시를 이스케이프 없이 그대로 씀.
        if v and not re.match(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$", v):
            raise ValueError(
                f"유효하지 않은 브랜치 이름입니다: {v!r}. "
                "영문자/숫자로 시작하고 영문자, 숫자, '.', '_', '/', '-'만 사용 가능합니다."
            )
        return v


class Config(BaseModel):
    """전체 설정 루트 모델.

    [Spring 비교]
      application.yml 전체 구조를 담는 최상위 @ConfigurationProperties 클래스.
      내부에 중첩 VO(ExportConfig, UserConfig, SyncConfig)를 포함한다.
    """

    version: str = Field(default="1.0")
    default_ai_provider: str = Field(default="")

    # pattern="^(ko|en|both)$" : 정규식으로 허용 값을 제한.
    # [Spring] @Pattern(regexp="^(ko|en|both)$") 와 동일.
    default_language: str = Field(default="ko", pattern="^(ko|en|both)$")
    timezone: str = Field(default="Asia/Seoul", description="타임존 (예: Asia/Seoul, UTC)")

    # list[AIProviderConfig] : Java List<AIProviderConfig> 와 동일.
    # default_factory=list : 빈 리스트를 매번 새로 생성. default=[] 로 쓰면 모든 인스턴스가
    # 같은 리스트 객체를 공유하는 버그 발생 — 반드시 factory 사용.
    ai_providers: list[AIProviderConfig] = Field(default_factory=list)

    # default_factory=ExportConfig : 값이 없으면 ExportConfig() 를 생성.
    # [Spring] @NestedConfigurationProperty 필드의 기본값과 동일한 개념.
    export: ExportConfig = Field(default_factory=ExportConfig)
    user: UserConfig = Field(default_factory=UserConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    def get_provider(self, name: str) -> Optional[AIProviderConfig]:
        """이름으로 AI Provider 를 찾아 반환한다. 없으면 None.

        [Spring 비교]
          Repository.findByName() 과 유사하지만 DB 대신 메모리(list) 에서 검색.
        """
        # for ... in list : Java stream().filter(...).findFirst() 와 유사.
        for p in self.ai_providers:
            if p.name == name:
                return p
        # 못 찾으면 None 반환. [Spring] Optional.empty() 와 같은 의미.
        return None

    def upsert_provider(self, provider: AIProviderConfig) -> None:
        """Provider 가 이미 있으면 교체(update), 없으면 추가(insert).

        [Spring 비교]
          JPA save() — Entity 가 이미 있으면 merge, 없으면 persist.
        """
        # enumerate(list) : index 와 값을 동시에 반환.
        #   [Spring] for (int i=0; i<list.size(); i++) { ... } 와 동일.
        for i, p in enumerate(self.ai_providers):
            if p.name == provider.name:
                # 인덱스로 직접 교체 — 기존 위치에 덮어씌움.
                self.ai_providers[i] = provider
                return
        # 루프를 끝까지 돌았으면 → 신규 추가.
        self.ai_providers.append(provider)
