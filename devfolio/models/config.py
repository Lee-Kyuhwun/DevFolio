"""설정 파일 Pydantic 모델."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AIProviderConfig(BaseModel):
    """AI Provider 설정."""

    name: str = Field(description="Provider 이름 (anthropic|openai|gemini|ollama)")
    model: str = Field(description="사용할 모델명")
    key_stored: bool = Field(default=False, description="키체인에 API 키 저장 여부")
    base_url: Optional[str] = Field(default=None, description="커스텀 API base URL (Ollama 등)")


class ExportConfig(BaseModel):
    """내보내기 기본값 설정."""

    default_format: str = Field(default="md")
    default_template: str = Field(default="default")
    output_dir: str = Field(default="")  # 비어 있으면 platformdirs 경로 사용


class UserConfig(BaseModel):
    """사용자 프로필."""

    name: str = Field(default="")
    email: str = Field(default="")
    github: str = Field(default="")
    blog: str = Field(default="")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if v and "@" not in v:
            raise ValueError(f"유효하지 않은 이메일 형식입니다: {v!r}")
        return v

    @field_validator("github", "blog")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://", "github.com/")):
            raise ValueError(
                f"URL은 http:// 또는 https://로 시작해야 합니다: {v!r}"
            )
        return v


class SyncConfig(BaseModel):
    """GitHub 백업 동기화 설정."""

    enabled: bool = Field(default=False)
    repo_url: str = Field(default="")
    branch: str = Field(default="main")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        if v and not re.match(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$", v):
            raise ValueError(
                f"유효하지 않은 브랜치 이름입니다: {v!r}. "
                "영문자/숫자로 시작하고 영문자, 숫자, '.', '_', '/', '-'만 사용 가능합니다."
            )
        return v


class Config(BaseModel):
    """전체 설정."""

    version: str = Field(default="1.0")
    default_ai_provider: str = Field(default="")
    default_language: str = Field(default="ko", pattern="^(ko|en|both)$")
    timezone: str = Field(default="Asia/Seoul", description="타임존 (예: Asia/Seoul, UTC)")
    ai_providers: list[AIProviderConfig] = Field(default_factory=list)
    export: ExportConfig = Field(default_factory=ExportConfig)
    user: UserConfig = Field(default_factory=UserConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    def get_provider(self, name: str) -> Optional[AIProviderConfig]:
        for p in self.ai_providers:
            if p.name == name:
                return p
        return None

    def upsert_provider(self, provider: AIProviderConfig) -> None:
        for i, p in enumerate(self.ai_providers):
            if p.name == provider.name:
                self.ai_providers[i] = provider
                return
        self.ai_providers.append(provider)
