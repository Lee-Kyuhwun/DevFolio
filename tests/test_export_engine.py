"""내보내기 엔진 단위 테스트."""

from pathlib import Path
from unittest.mock import patch

import pytest

from devfolio.core.export_engine import ExportEngine


@pytest.fixture
def tmp_exports(tmp_path):
    with patch("devfolio.core.export_engine.EXPORTS_DIR", tmp_path):
        yield tmp_path


@pytest.fixture
def engine(tmp_exports):
    return ExportEngine()


SAMPLE_MD = """# 홍길동 경력기술서

- 이메일: hong@example.com
- GitHub: https://github.com/honggildong

---

## 커넥티드카 게이트웨이

| 항목 | 내용 |
|------|------|
| 기간 | 2024-01 ~ 2024-06 |
| 역할 | 백엔드 개발자 |

**주요 작업**

- **블루그린 배포 구축**: 다운타임 0으로 감소
- **API 성능 최적화**: 응답 속도 40% 향상
"""


class TestMarkdownExport:
    def test_creates_md_file(self, engine, tmp_exports):
        path = engine.export_markdown(SAMPLE_MD, "test_resume")
        assert path.exists()
        assert path.suffix == ".md"
        assert path.read_text(encoding="utf-8") == SAMPLE_MD

    def test_adds_extension_if_missing(self, engine, tmp_exports):
        path = engine.export_markdown(SAMPLE_MD, "no_extension")
        assert path.name.endswith(".md")

    def test_keeps_existing_extension(self, engine, tmp_exports):
        path = engine.export_markdown(SAMPLE_MD, "test.md")
        assert path.name == "test.md"


class TestHtmlExport:
    def test_creates_html_file(self, engine, tmp_exports):
        path = engine.export_html(SAMPLE_MD, "test_portfolio")
        assert path.exists()
        assert path.suffix == ".html"

    def test_html_contains_content(self, engine, tmp_exports):
        path = engine.export_html(SAMPLE_MD, "test_html")
        content = path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "홍길동" in content

    def test_html_has_styles(self, engine, tmp_exports):
        path = engine.export_html(SAMPLE_MD, "styled")
        content = path.read_text(encoding="utf-8")
        assert "<style>" in content


class TestDocxExport:
    def test_creates_docx_file(self, engine, tmp_exports):
        try:
            path = engine.export_docx(SAMPLE_MD, "test_resume")
            assert path.exists()
            assert path.suffix == ".docx"
        except RuntimeError as e:
            if "python-docx" in str(e):
                pytest.skip("python-docx not installed")
            raise


class TestPdfExport:
    def test_raises_without_weasyprint(self, engine, tmp_exports):
        import sys
        # weasyprint가 없는 환경 시뮬레이션
        with patch.dict(sys.modules, {"weasyprint": None}):
            with pytest.raises((RuntimeError, ImportError)):
                engine.export_pdf(SAMPLE_MD, "test_resume")


class TestSimpleMarkdownToHtml:
    def test_heading_conversion(self, engine):
        html = engine._simple_md_to_html("# 제목")
        assert "<h1>제목</h1>" in html

    def test_subheading(self, engine):
        html = engine._simple_md_to_html("## 소제목")
        assert "<h2>소제목</h2>" in html

    def test_list_conversion(self, engine):
        html = engine._simple_md_to_html("- 항목 1\n- 항목 2")
        assert "<ul>" in html
        assert "<li>항목 1</li>" in html
        assert "<li>항목 2</li>" in html

    def test_bold_inline(self, engine):
        html = engine._simple_md_to_html("이것은 **굵은** 텍스트")
        assert "<strong>굵은</strong>" in html

    def test_italic_inline(self, engine):
        html = engine._simple_md_to_html("이것은 *기울임* 텍스트")
        assert "<em>기울임</em>" in html

    def test_horizontal_rule(self, engine):
        html = engine._simple_md_to_html("---")
        assert "<hr>" in html


class TestCopyTo:
    def test_copy_to_custom_path(self, engine, tmp_exports, tmp_path):
        src = engine.export_markdown(SAMPLE_MD, "source")
        dest = tmp_path / "custom_dir" / "output.md"
        result = engine.copy_to(src, dest)
        assert result.exists()
        assert result.read_text(encoding="utf-8") == SAMPLE_MD
