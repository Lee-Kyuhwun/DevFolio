"""설정 파일 Pydantic 모델."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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


class SyncConfig(BaseModel):
    """GitHub 백업 동기화 설정."""

    enabled: bool = Field(default=False)
    repo_url: str = Field(default="")
    branch: str = Field(default="main")


class Config(BaseModel):
    """전체 설정."""

    version: str = Field(default="1.0")
    default_ai_provider: str = Field(default="")
    default_language: str = Field(default="ko", pattern="^(ko|en|both)$")
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
