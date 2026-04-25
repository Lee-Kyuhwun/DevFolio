"""템플릿 엔진 렌더링 테스트."""

from devfolio.core.template_engine import TemplateEngine
from devfolio.models.config import Config
from devfolio.models.project import (
    Period,
    ProblemSolvingCase,
    Project,
    ProjectFeature,
    ProjectOverview,
    ProjectResults,
    ProjectRetrospective,
    QuantitativeResult,
    StackReason,
    Task,
    TechStackDetail,
    UserFlowStep,
)


def make_project() -> Project:
    return Project(
        id="devfolio",
        name="DevFolio",
        type="company",
        status="done",
        organization="DevFolio",
        period=Period(start="2026-04", end="2026-04"),
        role="개발자",
        team_size=1,
        tech_stack=["Python", "JavaScript", "HTML", "CSS", "Typer", "Jinja2", "ruamel.yaml", "Keyring", "Pydantic", "GitHub"],
        one_line_summary="로컬 우선 개발자 포트폴리오 스튜디오",
        summary="로컬 우선 포트폴리오 스튜디오로 프로젝트 입력, AI draft 생성, 미리보기, 내보내기, GitHub sync를 지원합니다.",
        overview=ProjectOverview(
            background="같은 프로젝트를 이력서와 포트폴리오에 반복해서 정리해야 하는 문제가 있었습니다.",
            problem="커리어 데이터가 문서마다 분산돼 수정 비용이 커지는 문제를 해결해야 했습니다.",
            target_users=["개발자", "취업 준비생"],
            goals=["원천 데이터 재사용", "AI 초안 생성", "문서 내보내기 자동화"],
        ),
        user_flow=[
            UserFlowStep(step=1, title="입력", description="자유 텍스트나 Git 저장소를 기반으로 프로젝트 초안을 생성합니다."),
            UserFlowStep(step=2, title="검토", description="AI가 생성한 요약과 task bullet을 확인하고 수정합니다."),
        ],
        tech_stack_detail=TechStackDetail(
            backend=[StackReason(name="Python", reason="CLI, 웹 API, 템플릿 렌더링을 하나의 언어로 통합하기 위해 사용했습니다.")],
            tools=[StackReason(name="Jinja2", reason="같은 구조화 데이터를 여러 문서 형식으로 재사용하기 위해 선택했습니다.")],
        ),
        features=[
            ProjectFeature(
                name="AI Draft 생성",
                user_value="자유 텍스트를 바로 포트폴리오 초안으로 전환할 수 있습니다.",
                implementation="구조화 draft와 review 기반 생성 흐름으로 구현했습니다.",
            )
        ],
        problem_solving_cases=[
            ProblemSolvingCase(
                title="입력 채널 분산 문제 해결",
                situation="CLI와 웹 편집 흐름이 따로 놀았습니다.",
                cause="원천 데이터와 문서 결과가 같은 구조를 공유하지 않았습니다.",
                action="ProjectManager를 공용 서비스 계층으로 두고 draft와 saved 프로젝트 흐름을 통합했습니다.",
                decision_reason="입력 채널이 달라도 검증 규칙과 저장 형식은 하나로 유지해야 유지보수가 쉬웠기 때문입니다.",
                result="입력과 저장, 미리보기 흐름이 일관되게 이어졌습니다.",
                metric="중복 편집 경로 제거",
                tech_used=["Python", "Pydantic"],
            )
        ],
        results=ProjectResults(
            quantitative=[
                QuantitativeResult(metric_name="문서 재사용성", before="문서별 개별 수정", after="원천 데이터 기반 재생성", impact="수정 비용 감소"),
            ],
            qualitative=["입력부터 export까지 한 흐름으로 이어지는 사용자 경험을 만들었습니다."],
        ),
        retrospective=ProjectRetrospective(
            what_i_learned=["문서 문제를 구조화된 데이터 모델 문제로 바꾸면 재사용성과 확장성이 높아집니다."],
            next_steps=["링크와 시각 자산 입력을 더 쉽게 만드는 편집 UI를 보강할 계획입니다."],
        ),
        tasks=[
            Task(
                id="task-1",
                name="웹 스튜디오 및 CLI 구현",
                period=Period(start="2026-04", end="2026-04"),
                problem="입력과 관리 경로가 분산됨",
                solution="웹 UI와 CLI를 통합한 로컬 우선 워크플로를 구성",
                result="입력·저장·내보내기 흐름을 한곳에서 관리",
                tech_used=["Python", "Typer", "JavaScript"],
                ai_generated_text="- 웹 UI와 CLI를 하나의 데이터 모델 위에 올려 입력 채널을 통합했습니다.",
            )
        ],
    )


def test_portfolio_template_renders_restructured_sections_in_order():
    config = Config()
    config.user.name = "홍길동"

    rendered = TemplateEngine().render(
        projects=[make_project()],
        config=config,
        template_name="default",
        doc_type="portfolio",
    )

    assert rendered.index("## 프로젝트 개요") < rendered.index("## 왜 만들었는지")
    assert rendered.index("## 왜 만들었는지") < rendered.index("## 문제 정의")
    assert rendered.index("## 문제 정의") < rendered.index("## 사용자 흐름")
    assert rendered.index("## 사용자 흐름") < rendered.index("## 기술 스택 및 선정 이유")
    assert rendered.index("## 기술 스택 및 선정 이유") < rendered.index("## 아키텍처")
    assert rendered.index("## 아키텍처") < rendered.index("## 핵심 기능")
    assert rendered.index("## 핵심 기능") < rendered.index("## 문제 해결 사례")
    assert rendered.index("## 문제 해결 사례") < rendered.index("## 결과 및 확장성")
    assert "AI draft" in rendered
    assert "기술 스택 및 선정 이유" in rendered
    assert "Python" in rendered
    assert "선택했습니다." in rendered
    assert "```mermaid" in rendered
    assert "flowchart LR" in rendered
    assert "자유 텍스트나 Git 저장소를 기반으로 프로젝트 초안을 생성합니다." in rendered
    assert "입력 채널 분산 문제 해결" in rendered


def test_project_single_template_includes_architecture_diagram():
    config = Config()
    config.user.name = "홍길동"

    project = make_project().model_copy(update={"summary": "로컬 우선 포트폴리오 스튜디오입니다."})
    rendered = TemplateEngine().render_project(project, config)

    assert "아키텍처" in rendered
    assert "Core Application" in rendered
    assert "문제 정의" in rendered
    assert "결과 및 성과" in rendered


def test_describe_project_purpose_returns_background_when_present():
    from devfolio.core.template_engine import describe_project_purpose

    project = make_project()
    result = describe_project_purpose(project)
    assert result == project.overview.background.strip()


def test_describe_project_purpose_no_synthetic_fallback_when_overview_empty():
    """overview 가 비어 있을 때 "흩어진 작업 과정" 같은 판박이 문구를 만들지 않는다."""
    from devfolio.core.template_engine import describe_project_purpose

    project = make_project().model_copy(
        update={
            "overview": ProjectOverview(),
            "summary": "간단한 요약입니다.",
        }
    )
    result = describe_project_purpose(project)
    assert "흩어진 작업 과정" not in result
    assert "구조화된 흐름으로 묶고" not in result
    assert result == "간단한 요약입니다."


def test_describe_project_purpose_problem_only_falls_back_without_slogans():
    from devfolio.core.template_engine import describe_project_purpose

    project = make_project().model_copy(
        update={
            "overview": ProjectOverview(
                problem="문서 재작성 비용이 반복해서 발생했습니다.",
            ),
            "summary": "",
        }
    )
    result = describe_project_purpose(project)
    assert "핵심적으로는" in result
    assert "같은 원천 데이터" not in result
