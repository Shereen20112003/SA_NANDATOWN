from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_HOSTS = (
    "learn.microsoft.com", "arxiv.org", "www.rfc-editor.org",
    "github.com", "raw.githubusercontent.com", "docs.github.com",
    "www.media.mit.edu", "media.mit.edu", "projectnanda.org",
    "en.wikipedia.org", "a2a-protocol.org", "modelcontextprotocol.io",
    "docs.python.org", "openai.com", "platform.openai.com", "docs.anthropic.com",
)


class SourceError(ValueError):
    pass


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise SourceError("The public source URL is malformed.") from exc
    if (len(url) > 2000 or parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or port not in (None, 443)):
        raise SourceError("Use an HTTPS URL from a supported public documentation source.")
    return url


class ExtractText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


async def fetch_source(client: httpx.AsyncClient, url: str, source_id: str) -> dict:
    original = validate_url(url)
    for _ in range(4):
        validate_url(url)
        try:
            async with client.stream("GET", url, follow_redirects=False, timeout=20,
                                     headers={"User-Agent": "NandaWorkbench/0.1"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceError("Source redirect did not include a destination.")
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200:
                    raise SourceError(f"Source returned HTTP {response.status_code}.")
                content_type = response.headers.get("content-type", "")
                if not any(kind in content_type for kind in ("text/html", "text/plain", "text/markdown")):
                    raise SourceError("This workspace accepts public HTML or text sources, not PDFs.")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > 1_000_000:
                        raise SourceError("Source exceeds the 1 MB download limit.")
                text = data.decode("utf-8", errors="replace")
                if "html" in content_type:
                    parser = ExtractText()
                    parser.feed(text)
                    text = "\n".join(parser.parts)
                text = text.strip()
                if len(text) < 100:
                    raise SourceError("The source did not contain enough readable text.")
                return {"id": source_id, "url": original, "resolved_url": url,
                        "text": text[:10000], "truncated": len(text) > 10000}
        except httpx.HTTPError as exc:
            raise SourceError("Could not retrieve the public source.") from exc
    raise SourceError("Source exceeded the redirect limit.")
