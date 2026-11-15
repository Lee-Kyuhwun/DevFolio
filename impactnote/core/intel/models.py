"""프로젝트 분석 결과 모델.

신뢰도 등급은 AI 자기평가가 아니라 근거의 종류로 결정한다.
- VERIFIED: 코드/테스트/측정 자료가 직접 확인됨
- SUPPORTED_INFERENCE: 여러 자료로 뒷받침되지만 직접 측정은 없음
- HYPOTHESIS: 단일 단서 또는 문서 주장만 있음
- INSUFFICIENT_EVIDENCE: 근거 부족
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from impactnote.core.models import new_id, utc_now

QUALITY_LEVELS = (
    "VERIFIED",
    "SUPPORTED_INFERENCE",
    "HYPOTHESIS",
    "INSUFFICIENT_EVIDENCE",
)

QUALITY_LABELS = {
    "VERIFIED": "검증됨",
    "SUPPORTED_INFERENCE": "근거 기반 추론",
    "HYPOTHESIS": "가설",
    "INSUFFICIENT_EVIDENCE": "근거 부족",
}

DOC_KINDS = (
    "requirements",
    "design",
    "technical_review",
    "implementation",
    "incident",
    "test",
    "performance",
    "deployment",
    "report",
    "reference",
)

DOC_KIND_LABELS = {
    "requirements": "요구사항·기획",
    "design": "설계·의사결정",
    "technical_review": "기술 검토",
    "implementation": "구현 설명",
    "incident": "장애 분석",
    "test": "테스트·검증",
    "performance": "성능 측정",
    "deployment": "배포·운영",
    "report": "업무 결과·보고",
    "reference": "참고 자료",
}


class EvidenceRef(BaseModel):
    """성과 후보가 참조하는 근거 한 건."""

    id: str = Field(default_factory=lambda: new_id("evd"))
    kind: Literal["document", "code", "commit", "test", "measurement", "claim"]
    title: str = Field(min_length=1, max_length=240)
    path: str = Field(default="", max_length=1000)
    locator: str = Field(default="", max_length=500)
    excerpt: str = Field(default="", max_length=2000)
    verified: bool = False
    detail: dict = Field(default_factory=dict)


class DocRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("doc"))
    path: str
    title: str
    kind: str = "reference"
    chars: int = 0
    headings: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=1200)
    excerpt: str = Field(default="", max_length=4000)
    git_tracked: bool = True
    deleted: bool = False
    modified_at: str = ""


class CodeFile(BaseModel):
    path: str
    language: str = ""
    lines: int = 0
    symbols: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    change_count: int = 0
    categories: list[str] = Field(default_factory=list)
    excerpt: str = Field(default="", max_length=2000)


class GitCommit(BaseModel):
    sha: str
    short: str = ""
    date: str = ""
    author: str = ""
    email: str = ""
    subject: str = ""
    insertions: int = 0
    deletions: int = 0
    files: list[str] = Field(default_factory=list)
    is_revert: bool = False
    is_merge: bool = False
    categories: list[str] = Field(default_factory=list)


class TimelineStep(BaseModel):
    id: str = Field(default_factory=lambda: new_id("tl"))
    label: str
    sha: str = ""
    date: str = ""
    summary: str = ""
    before: str = ""
    after: str = ""
    change_kind: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("fnd"))
    title: str
    detail: str = ""
    kind: Literal[
        "doc_code_match",
        "doc_only",
        "code_only",
        "conflict",
        "evolution",
        "measurement",
        "risk",
    ] = "code_only"
    quality: str = "SUPPORTED_INFERENCE"
    paths: list[str] = Field(default_factory=list)
    shas: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Measurement(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msr"))
    metric: str = ""
    before: str = ""
    after: str = ""
    unit: str = ""
    delta: float = 0.0
    change_percent: Optional[float] = None
    conditions: str = ""
    source_path: str = ""
    evidence_id: str = ""
    verified: bool = False
    note: str = ""


class Candidate(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cand"))
    title: str
    problem: str = ""
    action: str = ""
    result: str = ""
    impact_categories: list[str] = Field(default_factory=list)
    quality: str = "SUPPORTED_INFERENCE"
    confidence: int = Field(default=50, ge=0, le=100)
    evidence_ids: list[str] = Field(default_factory=list)
    measurement_id: str = ""
    contribution: dict = Field(default_factory=dict)
    status: Literal["candidate", "needs_validation", "applied", "dismissed"] = (
        "candidate"
    )
    notes: list[str] = Field(default_factory=list)
    applied_achievement_id: str = ""


class AIStageInfo(BaseModel):
    requested: bool = False
    used: bool = False
    provider: str = ""
    model: str = ""
    status: str = "skipped"
    error: str = ""
    prompt_chars: int = 0
    notes: list[str] = Field(default_factory=list)


class ProjectAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("int"))
    project_path: str
    project_name: str = ""
    head_sha: str = ""
    status: Literal["completed", "partial", "failed"] = "completed"
    quality_summary: dict = Field(default_factory=dict)
    documents: list[DocRecord] = Field(default_factory=list)
    code_files: list[CodeFile] = Field(default_factory=list)
    commits: list[GitCommit] = Field(default_factory=list)
    timeline: list[TimelineStep] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    ai: AIStageInfo = Field(default_factory=AIStageInfo)
    fingerprint: str = ""
    incremental: bool = False
    created_at: str = Field(default_factory=utc_now)


__all__ = [
    "AIStageInfo",
    "Candidate",
    "CodeFile",
    "DOC_KINDS",
    "DOC_KIND_LABELS",
    "DocRecord",
    "EvidenceRef",
    "Finding",
    "GitCommit",
    "Measurement",
    "ProjectAnalysis",
    "QUALITY_LABELS",
    "QUALITY_LEVELS",
    "TimelineStep",
]
