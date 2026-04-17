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
    summary: str = Field(default="", description="한 줄 요약")
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
