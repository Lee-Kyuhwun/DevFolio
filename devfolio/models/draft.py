"""웹 스튜디오용 초안 모델."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from devfolio.models.project import (
    Period,
    ProblemSolvingCase,
    ProjectArchitecture,
    ProjectAssets,
    ProjectFeature,
    ProjectLinks,
    ProjectOverview,
    ProjectResults,
    ProjectRetrospective,
    ProjectStudioMeta,
    TechStackDetail,
    UserFlowStep,
    PerformanceSecurityOperations,
    default_studio_meta_payload,
)

ExperienceKind = Literal["work", "personal", "study", "toy"]
DocumentType = Literal["resume", "career", "portfolio"]


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
    one_line_summary: str = Field(default="", description="프로젝트 한 줄 소개")
    summary: str = Field(default="", description="프로젝트 소개")
    links: ProjectLinks = Field(default_factory=ProjectLinks)
    overview: ProjectOverview = Field(default_factory=ProjectOverview)
    user_flow: list[UserFlowStep] = Field(default_factory=list)
    tech_stack_detail: TechStackDetail = Field(default_factory=TechStackDetail)
    architecture: ProjectArchitecture = Field(default_factory=ProjectArchitecture)
    features: list[ProjectFeature] = Field(default_factory=list)
    problem_solving_cases: list[ProblemSolvingCase] = Field(default_factory=list)
    performance_security_operations: PerformanceSecurityOperations = Field(default_factory=PerformanceSecurityOperations)
    results: ProjectResults = Field(default_factory=ProjectResults)
    retrospective: ProjectRetrospective = Field(default_factory=ProjectRetrospective)
    assets: ProjectAssets = Field(default_factory=ProjectAssets)
    studio_meta: ProjectStudioMeta = Field(default_factory=ProjectStudioMeta)
    tags: list[str] = Field(default_factory=list, description="태그")
    tasks: list[TaskDraft] = Field(default_factory=list, description="작업 초안 목록")
    raw_text: str = Field(default="", description="원본 자유 텍스트")

    @model_validator(mode="before")
    @classmethod
    def ensure_studio_meta_defaults(cls, data):
        if not isinstance(data, dict):
            return data
        if "studio_meta" not in data or data.get("studio_meta") is None:
            payload = dict(data)
            payload["studio_meta"] = default_studio_meta_payload(
                str(payload.get("type") or "company"),
                int(payload.get("team_size") or 1),
            )
            return payload
        return data


class ExperienceDraft(BaseModel):
    """웹 전용 경험 표현 계층.

    기존 YAML/CLI 호환을 위해 저장 시에는 ProjectDraft/Project 로 변환한다.
    """

    id: str = Field(default="")
    title: str = Field(default="", description="경험명")
    type: ExperienceKind = Field(default="work")
    status: Literal["done", "in_progress", "planned"] = Field(default="done")
    organization: str = Field(default="", description="소속/주관")
    period: Period = Field(default_factory=Period)
    role: str = Field(default="", description="역할")
    team_size: int = Field(default=1, ge=1, description="팀 규모")
    tech_stack: list[str] = Field(default_factory=list, description="기술 스택")
    one_line_summary: str = Field(default="", description="프로젝트 한 줄 소개")
    summary: str = Field(default="", description="프로젝트 소개")
    links: ProjectLinks = Field(default_factory=ProjectLinks)
    overview: ProjectOverview = Field(default_factory=ProjectOverview)
    user_flow: list[UserFlowStep] = Field(default_factory=list)
    tech_stack_detail: TechStackDetail = Field(default_factory=TechStackDetail)
    architecture: ProjectArchitecture = Field(default_factory=ProjectArchitecture)
    features: list[ProjectFeature] = Field(default_factory=list)
    problem_solving_cases: list[ProblemSolvingCase] = Field(default_factory=list)
    performance_security_operations: PerformanceSecurityOperations = Field(default_factory=PerformanceSecurityOperations)
    results: ProjectResults = Field(default_factory=ProjectResults)
    retrospective: ProjectRetrospective = Field(default_factory=ProjectRetrospective)
    assets: ProjectAssets = Field(default_factory=ProjectAssets)
    studio_meta: ProjectStudioMeta = Field(default_factory=ProjectStudioMeta)
    tags: list[str] = Field(default_factory=list, description="태그")
    tasks: list[TaskDraft] = Field(default_factory=list, description="작업 초안 목록")
    raw_text: str = Field(default="", description="원본 자유 텍스트")

    @model_validator(mode="before")
    @classmethod
    def ensure_studio_meta_defaults(cls, data):
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "studio_meta" not in payload or payload.get("studio_meta") is None:
            payload["studio_meta"] = {
                **default_studio_meta_payload(
                    str(payload.get("type") or "work"),
                    int(payload.get("team_size") or 1),
                ),
                "experience_kind": str(payload.get("type") or "work"),
            }
            return payload
        return payload


class ExperienceSummary(BaseModel):
    """경험 목록 요약."""

    total: int = Field(default=0)
    by_type: dict[ExperienceKind, int] = Field(default_factory=dict)
    by_document: dict[DocumentType, int] = Field(default_factory=dict)


class DraftPreviewRequest(BaseModel):
    """초안/저장 데이터 기반 미리보기 및 내보내기 요청."""

    doc_type: DocumentType = Field(default="portfolio")
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
