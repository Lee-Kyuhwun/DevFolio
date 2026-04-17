"""웹 스튜디오용 초안 모델."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from devfolio.models.project import Period


class TaskDraft(BaseModel):
    """저장 전/저장 후 편집용 작업 초안."""

    id: str = Field(default="")
    name: str = Field(default="", description="작업명")
    period: Period = Field(default_factory=Period)
    problem: str = Field(default="", description="문제 상황 (AS-IS)")
    solution: str = Field(default="", description="해결 방법 (TO-BE)")
    result: str = Field(default="", description="성과/지표")
    tech_used: list[str] = Field(default_factory=list, description="사용 기술")
    keywords: list[str] = Field(default_factory=list, description="키워드 태그")
    ai_generated_text: str = Field(default="", description="AI 생성 문구 초안")


class ProjectDraft(BaseModel):
    """프로젝트 입력/AI 초안/저장 편집용 모델."""

    id: str = Field(default="")
    name: str = Field(default="", description="프로젝트명")
    type: Literal["company", "side", "course"] = Field(default="company")
    status: Literal["done", "in_progress", "planned"] = Field(default="done")
    organization: str = Field(default="", description="소속/주관")
    period: Period = Field(default_factory=Period)
    role: str = Field(default="", description="역할")
    team_size: int = Field(default=1, ge=1, description="팀 규모")
    tech_stack: list[str] = Field(default_factory=list, description="기술 스택")
    summary: str = Field(default="", description="프로젝트 소개")
    tags: list[str] = Field(default_factory=list, description="태그")
    tasks: list[TaskDraft] = Field(default_factory=list, description="작업 초안 목록")
    raw_text: str = Field(default="", description="원본 자유 텍스트")


class DraftPreviewRequest(BaseModel):
    """초안/저장 데이터 기반 미리보기 및 내보내기 요청."""

    doc_type: Literal["resume", "portfolio"] = Field(default="portfolio")
    source: Literal["draft", "saved"] = Field(default="draft")
    project_ids: list[str] = Field(default_factory=list)
    draft_project: Optional[ProjectDraft] = Field(default=None)
    template: str = Field(default="default")
    format: str = Field(default="html")

    @model_validator(mode="after")
    def validate_source_payload(self) -> "DraftPreviewRequest":
        if self.source == "draft" and self.draft_project is None:
            raise ValueError("source가 draft인 경우 draft_project가 필요합니다.")
        return self
