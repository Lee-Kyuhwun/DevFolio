"""Markdown 변환 결과에 문서 표시용 태그와 안전한 링크만 허용한다."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


class _DocumentHTML(HTMLParser):
    tags = frozenset(
        "p br hr h1 h2 h3 h4 h5 h6 ul ol li strong em b i del s blockquote "
        "pre code table thead tbody tfoot tr th td a img div span sup sub".split()
    )
    void_tags = frozenset({"br", "hr", "img"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []

    @staticmethod
    def _safe_url(value: str, *, image: bool) -> bool:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            return False
        try:
            scheme = urlsplit(value.strip()).scheme.lower()
        except ValueError:
            return False
        return scheme in (
            {"http", "https"} if image else {"", "http", "https", "mailto"}
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.tags:
            self.output.append(html.escape(self.get_starttag_text()))
            return
        safe: dict[str, str] = {}
        for key, value in attrs:
            if value is None:
                continue
            if key == "href" and tag == "a" and self._safe_url(value, image=False):
                safe[key] = value
            elif key == "src" and tag == "img" and self._safe_url(value, image=True):
                safe[key] = value
            elif key in {"title", "alt"}:
                safe[key] = value
            elif (
                key == "class"
                and tag == "code"
                and re.fullmatch(r"language-[\w-]+", value)
            ):
                safe[key] = value
            elif (
                key == "align"
                and tag in {"th", "td"}
                and value in {"left", "center", "right"}
            ):
                safe[key] = value
        attributes = "".join(
            f' {key}="{html.escape(value, quote=True)}"' for key, value in safe.items()
        )
        self.output.append(f"<{tag}{attributes}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.tags and tag not in self.void_tags:
            self.output.append(f"</{tag}>")
        elif tag not in self.tags:
            self.output.append(html.escape(f"</{tag}>"))

    def handle_data(self, data: str) -> None:
        self.output.append(html.escape(data, quote=False))


def sanitize_document_html(content: str) -> str:
    parser = _DocumentHTML()
    parser.feed(content)
    parser.close()
    return "".join(parser.output)
