"""Check that built documentation pages include their local scripts and styles."""

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageAssets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script":
            url = attributes.get("src")
        elif tag == "link" and attributes.get("rel") == "stylesheet":
            url = attributes.get("href")
        else:
            return
        if url:
            self.urls.append(url)


def check_page(page: Path) -> None:
    parser = PageAssets()
    parser.feed(page.read_text(encoding="utf-8"))
    for url in parser.urls:
        parts = urlsplit(url)
        if not parts.scheme and not parts.netloc and parts.path:
            if not (page.parent / unquote(parts.path)).is_file():
                raise SystemExit(f"{page}: missing local asset {url}")
    print(f"{page}: local stylesheets and scripts verified")


if __name__ == "__main__":
    for filename in sys.argv[1:]:
        check_page(Path(filename))
