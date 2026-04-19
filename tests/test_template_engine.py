"""템플릿 엔진 렌더링 테스트."""

from devfolio.core.template_engine import TemplateEngine
from devfolio.models.config import Config
from devfolio.models.project import Period, Project, Task


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
        tech_stack=["Python", "JavaScript", "HTML", "CSS", "Typer", "Jinja2", "ruamel.yaml", "Keyring", "Pydantic"],
        summary="로컬 우선 포트폴리오 스튜디오입니다.",
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


def test_portfolio_template_includes_stack_section_and_mermaid_diagram():
    config = Config()
    config.user.name = "홍길동"

    rendered = TemplateEngine().render(
        projects=[make_project()],
        config=config,
        template_name="default",
        doc_type="portfolio",
    )

    assert "기술 스택 구성" in rendered
    assert "인터페이스 레이어" in rendered
    assert "```mermaid" in rendered
    assert "flowchart LR" in rendered


def test_project_single_template_includes_architecture_diagram():
    config = Config()
    config.user.name = "홍길동"

    rendered = TemplateEngine().render_project(make_project(), config)

    assert "아키텍처" in rendered
    assert "Core Application" in rendered
    assert "AI Providers" not in rendered
