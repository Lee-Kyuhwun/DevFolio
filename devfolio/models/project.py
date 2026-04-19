"""프로젝트 및 작업 내역 Pydantic 모델.

[Spring 비교]
  Spring 의 @Entity + Lombok @Data + @Valid 를 하나로 합친 역할.
  Pydantic BaseModel 을 상속하면 __init__, 타입 검증, JSON 직렬화가
  자동으로 생성된다 — 별도 @Getter/@Setter 불필요.
"""

# from __future__ import annotations
#   Python 3.11 미만에서도 "list[str]" 같은 최신 타입 힌트 문법을 쓸 수 있게 해주는
#   호환성 선언. 파일 맨 위에 한 번만 쓰면 된다.
from __future__ import annotations

import re

# Optional[X] = "X 이거나 None". Java 의 @Nullable 또는 Optional<X> 와 같은 의미.
from typing import Optional

# BaseModel    : Pydantic 의 핵심 클래스. 이 클래스를 상속하면 자동으로
#                __init__ / 타입 검증 / model_dump(JSON 변환) 등이 생긴다.
#                [Spring] @Entity 없이 순수 DTO/VO 처럼 쓰되 검증은 @Valid 수준.
# Field        : 필드에 메타데이터(기본값, 설명, 길이 제한 등)를 붙이는 함수.
#                [Spring] @Column + @JsonProperty + @Size 를 합쳐 놓은 것.
# field_validator : 특정 필드에 커스텀 검증 로직을 추가하는 데코레이터(어노테이션).
#                [Spring] @ConstraintValidator / @Pattern / @AssertTrue 와 동일.
from pydantic import BaseModel, Field, field_validator


class Period(BaseModel):
    """프로젝트/작업 기간.

    [Spring 비교] @Embeddable VO — Project/Task 안에 중첩되어 기간을 표현.
    """

    # Optional[str] → 이 필드는 문자열 또는 None 을 받는다.
    # Field(default=None) → 값이 없을 때 기본값은 None.
    #   [Spring] @Nullable + @Column(nullable=true) 와 유사.
    start: Optional[str] = Field(default=None, description="시작 월 (YYYY-MM)")
    end: Optional[str] = Field(default=None, description="종료 월 (YYYY-MM), None = 진행 중")

    # @field_validator("start", "end", mode="before")
    #   "start"와 "end" 두 필드에 동일한 검증 로직을 적용.
    #   mode="before" : 타입 변환(str → str) 이 일어나기 전에 먼저 실행.
    #                   [Spring] @JsonDeserialize 로 원본 값을 가공하는 것과 같은 시점.
    # @classmethod : 인스턴스가 없는 상태에서 클래스 레벨로 호출.
    #   Pydantic validator 는 반드시 @classmethod 로 선언해야 한다.
    #   [Spring] static 메서드처럼 객체 생성 전에 실행.
    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_yyyymm(cls, v: Optional[str]) -> Optional[str]:
        # 빈 문자열·None 모두 None으로 정규화 (start 포함)
        if v is None or str(v).strip() == "":
            return None
        # re.match(pattern, string) : Java 의 Pattern.matches(regex, input) 와 동일.
        # r"..." = raw string — 백슬래시를 이스케이프 없이 그대로 씀.
        #   Java 에서 "\\\\" 를 써야 할 것을 r"\\" 로 간결하게 표현.
        if not re.match(r"^\d{4}-\d{2}$", str(v).strip()):
            # Pydantic validator 에서 ValueError 를 raise 하면
            # 자동으로 HTTP 422 Unprocessable Entity 응답이 된다.
            # [Spring] MethodArgumentNotValidException 을 던지는 것과 같은 효과.
            # {v!r} : v 를 repr() 로 출력 — 따옴표 포함한 디버그 표현.
            raise ValueError(f"날짜 형식이 올바르지 않습니다 (YYYY-MM 필요): {v!r}")
        return str(v).strip()

    def display(self) -> str:
        # "A or B" : A 가 falsy(None/""/0) 이면 B 를 반환. Java 의 삼항연산자 대체.
        start = self.start or "?"
        # "A if 조건 else B" : 인라인 삼항 연산자. Java 의 조건 ? A : B.
        end = self.end if self.end else "현재"
        # f"..." = f-string. Java 의 String.format() 또는 STR 템플릿(Java 21+).
        return f"{start} ~ {end}"


class ProjectLinks(BaseModel):
    github: str = Field(default="", description="GitHub 저장소 링크")
    demo: str = Field(default="", description="배포 또는 데모 링크")
    docs: str = Field(default="", description="문서 링크")
    video: str = Field(default="", description="영상 링크")


class ProjectOverview(BaseModel):
    background: str = Field(default="", description="왜 만들었는지")
    problem: str = Field(default="", description="핵심 문제 정의")
    target_users: list[str] = Field(default_factory=list, description="대상 사용자")
    goals: list[str] = Field(default_factory=list, description="프로젝트 목표")
    non_goals: list[str] = Field(default_factory=list, description="의도적으로 제외한 범위")


class UserFlowStep(BaseModel):
    step: int = Field(default=1, ge=1, description="사용 흐름 순서")
    title: str = Field(default="", description="사용 흐름 단계명")
    description: str = Field(default="", description="사용 흐름 설명")


class StackReason(BaseModel):
    name: str = Field(default="", description="기술명")
    reason: str = Field(default="", description="선정 이유")


class TechStackDetail(BaseModel):
    frontend: list[StackReason] = Field(default_factory=list)
    backend: list[StackReason] = Field(default_factory=list)
    database: list[StackReason] = Field(default_factory=list)
    infra: list[StackReason] = Field(default_factory=list)
    tools: list[StackReason] = Field(default_factory=list)


class ArchitectureComponent(BaseModel):
    name: str = Field(default="", description="컴포넌트명")
    role: str = Field(default="", description="컴포넌트 역할")


class DataModelEntity(BaseModel):
    entity: str = Field(default="", description="엔터티명")
    fields: list[str] = Field(default_factory=list, description="주요 필드")


class ApiExample(BaseModel):
    method: str = Field(default="GET", description="HTTP 메서드")
    path: str = Field(default="", description="API 경로")
    purpose: str = Field(default="", description="API 목적")


class ProjectArchitecture(BaseModel):
    summary: str = Field(default="", description="아키텍처 요약")
    components: list[ArchitectureComponent] = Field(default_factory=list)
    data_model: list[DataModelEntity] = Field(default_factory=list)
    api_examples: list[ApiExample] = Field(default_factory=list)


class ProjectFeature(BaseModel):
    name: str = Field(default="", description="기능명")
    user_value: str = Field(default="", description="사용자 가치")
    implementation: str = Field(default="", description="구현 방식")


class ProblemSolvingCase(BaseModel):
    title: str = Field(default="", description="문제 해결 사례 제목")
    situation: str = Field(default="", description="문제 상황")
    cause: str = Field(default="", description="원인")
    action: str = Field(default="", description="내가 한 행동")
    decision_reason: str = Field(default="", description="기술적 판단 이유")
    result: str = Field(default="", description="결과")
    metric: str = Field(default="", description="수치 또는 정량 지표")
    tech_used: list[str] = Field(default_factory=list, description="사용 기술")


class PerformanceSecurityOperations(BaseModel):
    performance: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)


class QuantitativeResult(BaseModel):
    metric_name: str = Field(default="", description="지표명")
    before: str = Field(default="", description="개선 전")
    after: str = Field(default="", description="개선 후")
    impact: str = Field(default="", description="영향")


class ProjectResults(BaseModel):
    quantitative: list[QuantitativeResult] = Field(default_factory=list)
    qualitative: list[str] = Field(default_factory=list)


class ProjectRetrospective(BaseModel):
    what_went_well: list[str] = Field(default_factory=list)
    what_was_hard: list[str] = Field(default_factory=list)
    what_i_learned: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class AssetItem(BaseModel):
    title: str = Field(default="", description="자산 제목")
    description: str = Field(default="", description="자산 설명")
    path: str = Field(default="", description="자산 경로 또는 링크")


class ProjectAssets(BaseModel):
    screenshots: list[AssetItem] = Field(default_factory=list)
    diagrams: list[AssetItem] = Field(default_factory=list)


class Task(BaseModel):
    """프로젝트 내 세부 작업 내역.

    [Spring 비교] @Embeddable 또는 @OneToMany 관계 없이 YAML 에 직렬화되는 VO.
    """

    # 기본값(default) 없이 타입만 선언하면 → required 필드.
    # [Spring] @NotNull 과 동일하게, 이 값 없이 객체를 만들면 ValidationError 발생.
    id: str
    name: str = Field(min_length=1, description="작업명")  # min_length=1 : @Size(min=1)

    # default_factory=Period : 값이 없을 때 Period() 를 매번 새로 생성.
    #   ※ default=Period() 로 쓰면 모든 인스턴스가 같은 객체를 공유하는 버그 발생.
    #   ※ [Spring] new ArrayList<>() 를 필드 초기화 시 인라인으로 쓰는 것과 같은 맥락.
    period: Period = Field(default_factory=Period)

    problem: str = Field(default="", description="문제 상황 (AS-IS)")
    solution: str = Field(default="", description="해결 방법 (TO-BE)")
    result: str = Field(default="", description="성과/지표")

    # list[str] : Python 3.9+ 에서 List[str] 대신 소문자로 쓸 수 있다.
    # default_factory=list : 빈 리스트를 매번 새로 만든다 (위와 같은 이유).
    tech_used: list[str] = Field(default_factory=list, description="사용 기술")
    keywords: list[str] = Field(default_factory=list, description="키워드 태그")
    ai_generated_text: str = Field(default="", description="AI 생성 문구 캐시")


class Project(BaseModel):
    """개발 프로젝트.

    [Spring 비교]
      @Entity 없이 YAML 파일에 영속되는 도메인 모델.
      Pydantic 이 @Data + @Builder + @Valid 역할을 모두 담당.
    """

    id: str
    name: str = Field(min_length=1, description="프로젝트명")

    # pattern="^...$" : @Pattern(regexp="...") 과 동일.
    # "|" 는 정규식 OR 연산 — 세 값 중 하나만 허용.
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

    # ge=1 : greater than or equal → @Min(1) 과 동일.
    team_size: int = Field(default=1, ge=1, description="팀 규모")
    tech_stack: list[str] = Field(default_factory=list, description="기술 스택")
    one_line_summary: str = Field(default="", description="한 줄 소개")
    summary: str = Field(default="", description="한 줄 요약")
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
    tags: list[str] = Field(default_factory=list, description="태그")
    tasks: list[Task] = Field(default_factory=list, description="작업 내역 목록")

    # Git Scan 기능 전용 캐싱 필드 (devfolio scan 명령이 채운다)
    repo_url: str = Field(default="", description="원본 Git 저장소 URL (scan 캐싱용)")
    last_commit_sha: str = Field(default="", description="마지막으로 스캔한 커밋 SHA")
    # dict : Java 의 Map<String, Object> (어떤 타입이든 담을 수 있는 범용 맵)
    scan_metrics: dict = Field(default_factory=dict, description="git scan 지표 캐시")

    def type_display(self) -> str:
        # dict literal : Java 의 Map.of("key", "value") 와 동일.
        mapping = {"company": "회사 업무", "side": "사이드 프로젝트", "course": "인강/학습"}
        # dict.get(key, default) : Java Map.getOrDefault(key, defaultValue).
        return mapping.get(self.type, self.type)

    def status_display(self) -> str:
        mapping = {"done": "완료", "in_progress": "진행 중", "planned": "예정"}
        return mapping.get(self.status, self.status)
