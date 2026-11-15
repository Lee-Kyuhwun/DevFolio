"""성과노트 도메인 모델.

핵심 구분:
  - Activity(업무 활동): 실제로 수행한 일의 원본 기록.
  - Achievement(성과): 활동을 통해 해결한 문제와 조직에 남긴 가치. 활동 여러 개를 연결할 수 있다.
  - Evidence(근거): 성과를 뒷받침하는 커밋·티켓·문서·테스트 결과 등.
  - Metric(지표): 근거가 있을 때만 쓰는 수치. 단위·기간·측정 기준·근거를 함께 저장한다.

원칙: 근거 없는 수치를 만들지 않는다. 숫자는 `Metric` 으로만 보고서에 들어가며,
`verified` 가 아닌 지표는 본문이 아니라 "확인 필요" 목록에 표시된다.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ACTIVITY_TYPES = (
    "feature",  # 신규 개발·기능 개선
    "incident",  # 장애 대응·문제 해결
    "operations",  # 운영·유지보수
    "performance",  # 성능 개선·자동화
    "quality",  # 품질 개선
    "security",  # 보안·리스크 대응
    "request",  # 고객·타 부서 요청 처리
    "research",  # 기술 조사·업무 개선
    "collaboration",  # 협업·지원
    "general",  # 기타
)

IMPACT_CATEGORIES = (
    "productivity",  # 생산성 향상
    "efficiency",  # 업무 효율화
    "stability",  # 안정성 개선
    "quality",  # 품질 향상
    "cost",  # 비용 절감
    "incident_prevention",  # 장애 예방·해결
    "automation",  # 업무 자동화
    "customer",  # 고객 만족도 개선
    "schedule",  # 일정 준수·납기 기여
    "risk",  # 리스크 감소
    "collaboration",  # 조직 간 협업 기여
    "technical",  # 기술적 문제 해결
    "process",  # 프로세스 개선
)

EVIDENCE_TYPES = (
    "git_commit",
    "pull_request",
    "jira",
    "confluence",
    "test_result",
    "deployment",
    "incident",
    "report",
    "file",
    "url",
    "note",
)

ACHIEVEMENT_STATUSES = (
    "verified",  # 근거 확인됨
    "partially_verified",  # 일부 근거 확인됨
    "user_input",  # 사용자 입력 기반
    "needs_review",  # 추가 확인 필요
)

REPORT_TEMPLATES = {
    "weekly": "주간 업무보고",
    "monthly": "월간 업무실적 보고",
    "quarterly": "분기 성과보고",
    "half_yearly": "반기 성과보고",
    "annual": "연간 자기평가서",
    "custom": "자유 형식 성과 제출",
}

PERIOD_KINDS = ("custom", "week", "month", "quarter", "half", "year")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {value!r}")
    date.fromisoformat(text)  # 존재하는 날짜인지 검증
    return text


class Activity(BaseModel):
    """업무 활동 1건 — 사용자가 평소에 남기는 원본 기록."""

    id: str = Field(default_factory=lambda: new_id("act"))
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    date: str = Field(default_factory=lambda: date.today().isoformat())
    period_end: Optional[str] = None
    project: str = Field(default="", max_length=120)
    activity_type: str = Field(default="general")
    problem: str = Field(default="", max_length=2000)
    action: str = Field(default="", max_length=2000)
    result: str = Field(default="", max_length=2000)
    status: Literal["planned", "in_progress", "done"] = "done"
    collaborators: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source: Literal["manual", "git", "migration", "ai"] = "manual"
    source_ref: str = Field(default="", max_length=500)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    _validate_dates = field_validator("date", "period_end")(_normalize_date)

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, value: str) -> str:
        # 개발자 전용으로 고정하지 않는다 — 알 수 없는 유형도 허용하되 빈 값은 general.
        return (value or "general").strip() or "general"

    @field_validator("tags", "collaborators")
    @classmethod
    def dedupe_list(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in values if item.strip()))

    @model_validator(mode="after")
    def validate_period(self) -> "Activity":
        if self.period_end and self.period_end < self.date:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        return self


class Evidence(BaseModel):
    """성과·활동을 뒷받침하는 근거 자료."""

    id: str = Field(default_factory=lambda: new_id("evd"))
    type: str = Field(default="url")
    title: str = Field(min_length=1, max_length=200)
    reference: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=2000)
    # 사용자가 직접 확인했거나 시스템이 존재를 확인한 근거만 True.
    verified: bool = False
    created_at: str = Field(default_factory=utc_now)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        return value if value in EVIDENCE_TYPES else "url"


class Metric(BaseModel):
    """정량 지표 — 근거가 있을 때만 성과에 붙인다."""

    id: str = Field(default_factory=lambda: new_id("met"))
    achievement_id: str = ""
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=120)
    unit: str = Field(default="", max_length=40)
    period: str = Field(default="", max_length=80)
    basis: str = Field(default="", max_length=500, description="측정 기준/산출 방식")
    evidence_id: str = ""
    verified: bool = False
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_basis_for_verified(self) -> "Metric":
        # 근거 없는 수치는 verified 가 될 수 없다.
        if self.verified and not (self.evidence_id or self.basis.strip()):
            self.verified = False
        return self


class Contribution(BaseModel):
    """개인 기여도 — 팀 성과를 개인 성과로 부풀리지 않기 위한 구분."""

    role: str = Field(default="", max_length=200)
    solo: list[str] = Field(default_factory=list)
    shared: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    organization_role: str = Field(default="", max_length=500)


class Achievement(BaseModel):
    """성과 — 활동을 통해 해결한 문제와 가치."""

    id: str = Field(default_factory=lambda: new_id("ach"))
    title: str = Field(min_length=1, max_length=200)
    activity_ids: list[str] = Field(default_factory=list)
    problem: str = Field(default="", max_length=3000)
    action: str = Field(default="", max_length=3000)
    result: str = Field(default="", max_length=3000)
    impact_categories: list[str] = Field(default_factory=list)
    contribution: Contribution = Field(default_factory=Contribution)
    evidence_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="user_input")
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    source: Literal["manual", "ai", "git", "migration"] = "manual"
    needs_review: bool = False
    # AI/Git 이 제안한 성과는 사용자가 확인(confirmed)하기 전까지 확정하지 않는다.
    confirmed: bool = False
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    _validate_dates = field_validator("period_start", "period_end")(_normalize_date)

    @field_validator("impact_categories")
    @classmethod
    def validate_categories(cls, values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(values) if value in IMPACT_CATEGORIES]

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        return value if value in ACHIEVEMENT_STATUSES else "user_input"

    @model_validator(mode="after")
    def validate_period(self) -> "Achievement":
        if (
            self.period_start
            and self.period_end
            and self.period_end < self.period_start
        ):
            raise ValueError("성과 기간의 종료일이 시작일보다 빠를 수 없습니다.")
        return self


class Goal(BaseModel):
    """목표/KPI/OKR — 보고서의 '목표 대비 실적'에 쓰인다."""

    id: str = Field(default_factory=lambda: new_id("goal"))
    title: str = Field(min_length=1, max_length=200)
    period_start: str = ""
    period_end: str = ""
    target: str = Field(default="", max_length=300)
    actual: str = Field(default="", max_length=300)
    unit: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=500)
    created_at: str = Field(default_factory=utc_now)


class Report(BaseModel):
    """생성된 제출 문서 1건(버전 포함)."""

    id: str = Field(default_factory=lambda: new_id("rpt"))
    title: str = Field(min_length=1, max_length=200)
    template: str = "monthly"
    period_kind: str = "month"
    period_start: str = ""
    period_end: str = ""
    achievement_ids: list[str] = Field(default_factory=list)
    activity_ids: list[str] = Field(default_factory=list)
    content: str = ""
    format: str = "md"
    file_name: str = ""
    version: int = 1
    status: Literal["draft", "submitted"] = "draft"
    note: str = Field(default="", max_length=1000)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AIAnalysis(BaseModel):
    """AI 분석 결과 — 원본 기록은 건드리지 않고 별도로 보관한다."""

    id: str = Field(default_factory=lambda: new_id("ana"))
    activity_id: str = ""
    provider: str = ""
    model: str = ""
    status: Literal["completed", "failed", "skipped"] = "completed"
    error_code: str = ""
    error_message: str = ""
    result: dict = Field(default_factory=dict)
    applied_achievement_id: str = ""
    created_at: str = Field(default_factory=utc_now)


class Settings(BaseModel):
    """로컬 설정 — 외부 AI 전송 동의가 기본값은 꺼짐이다."""

    user_name: str = ""
    organization: str = ""
    external_ai_consent: bool = False
    allowed_providers: list[str] = Field(default_factory=list)
    default_provider: str = ""
    updated_at: str = Field(default_factory=utc_now)


__all__ = [
    "ACHIEVEMENT_STATUSES",
    "ACTIVITY_TYPES",
    "Activity",
    "Achievement",
    "AIAnalysis",
    "Contribution",
    "EVIDENCE_TYPES",
    "Evidence",
    "Goal",
    "IMPACT_CATEGORIES",
    "Metric",
    "PERIOD_KINDS",
    "REPORT_TEMPLATES",
    "Report",
    "Settings",
]
