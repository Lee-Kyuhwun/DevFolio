"""프로젝트 및 작업 내역 Pydantic 모델."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Period(BaseModel):
    """프로젝트/작업 기간."""

    # Optional[str]로 선언 — 빈 문자열 입력도 None으로 정규화
    start: Optional[str] = Field(default=None, description="시작 월 (YYYY-MM)")
    end: Optional[str] = Field(default=None, description="종료 월 (YYYY-MM), None = 진행 중")

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_yyyymm(cls, v: Optional[str]) -> Optional[str]:
        # 빈 문자열·None 모두 None으로 정규화 (start 포함)
        if v is None or str(v).strip() == "":
            return None
        if not re.match(r"^\d{4}-\d{2}$", str(v).strip()):
            raise ValueError(f"날짜 형식이 올바르지 않습니다 (YYYY-MM 필요): {v!r}")
        return str(v).strip()

    def display(self) -> str:
        start = self.start or "?"
        end = self.end if self.end else "현재"
        return f"{start} ~ {end}"


class Task(BaseModel):
    """프로젝트 내 세부 작업 내역."""

    id: str
    name: str = Field(min_length=1, description="작업명")
    period: Period = Field(default_factory=Period)
    problem: str = Field(default="", description="문제 상황 (AS-IS)")
    solution: str = Field(default="", description="해결 방법 (TO-BE)")
    result: str = Field(default="", description="성과/지표")
    tech_used: list[str] = Field(default_factory=list, description="사용 기술")
    keywords: list[str] = Field(default_factory=list, description="키워드 태그")
    ai_generated_text: str = Field(default="", description="AI 생성 문구 캐시")


class Project(BaseModel):
    """개발 프로젝트."""

    id: str
    name: str = Field(min_length=1, description="프로젝트명")
    type: str = Field(
        default="company",
        description="유형 (company | side | course)",
        pattern="^(company|side|course)$",
    )
    status: str = Field(
        default="done",
        description="상태 (done | in_progress | planned)",
        pattern="^(done|in_progress|planned)$",
    )
    organization: str = Field(default="", description="소속/주관")
    period: Period = Field(default_factory=Period)
    role: str = Field(default="", description="역할")
    team_size: int = Field(default=1, ge=1, description="팀 규모")
    tech_stack: list[str] = Field(default_factory=list, description="기술 스택")
    summary: str = Field(default="", description="한 줄 요약")
    tags: list[str] = Field(default_factory=list, description="태그")
    tasks: list[Task] = Field(default_factory=list, description="작업 내역 목록")

    def type_display(self) -> str:
        mapping = {"company": "회사 업무", "side": "사이드 프로젝트", "course": "인강/학습"}
        return mapping.get(self.type, self.type)

    def status_display(self) -> str:
        mapping = {"done": "완료", "in_progress": "진행 중", "planned": "예정"}
        return mapping.get(self.status, self.status)
