"""Tiny plain-text → HTML formatter for reviewer custom messages.

Reviewers type plain text in cadmin. Blank lines start new paragraphs,
single newlines become <br>, ``**bold**`` becomes <strong>, and bare
http(s) URLs become links. Everything else is HTML-escaped. The plain
text version is sent unchanged in the text email body.
"""

import html
import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _linkify_escaped(text: str) -> str:
    parts = _URL_RE.split(text)
    urls = _URL_RE.findall(text)
    chunks = [parts[0]]
    for url, rest in zip(urls, parts[1:]):
        trailing = ""
        while url and url[-1] in ".,;:!?)":
            trailing = url[-1] + trailing
            url = url[:-1]
        chunks.append(
            f'<a href="{url}">{url}</a>{html.escape(trailing)}'
        )
        chunks.append(rest)
    return "".join(chunks)


def _inline_escaped(text: str) -> str:
    escaped = html.escape(text)
    with_bold = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return _linkify_escaped(with_bold)


def custom_message_html(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    return "".join(
        f"<p>{_inline_escaped(p).replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
