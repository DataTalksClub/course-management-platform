"""Tiny plain-text → HTML formatter for reviewer custom messages.

Reviewers type plain text in cadmin. Blank lines start new paragraphs,
single newlines become <br>, ``**bold**`` becomes <strong>, bare
http(s) URLs become links, and ``[text](url)`` becomes a named link.
Everything else is HTML-escaped. See ``custom_message_text`` for the
plain-text counterpart used in the text email body.
"""

import html
import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _strip_trailing_punctuation(url: str) -> tuple[str, str]:
    trailing = ""
    while url and url[-1] in ".,;:!?)":
        trailing = url[-1] + trailing
        url = url[:-1]
    return url, trailing


def _linkify_escaped(text: str) -> str:
    parts = _URL_RE.split(text)
    urls = _URL_RE.findall(text)
    chunks = [parts[0]]
    for url, rest in zip(urls, parts[1:]):
        url, trailing = _strip_trailing_punctuation(url)
        chunks.append(
            f'<a href="{url}">{url}</a>{html.escape(trailing)}'
        )
        chunks.append(rest)
    return "".join(chunks)


def _inline_escaped(text: str) -> str:
    # Stash [text](url) links first so the bare-URL linkifier never
    # touches the href it is about to generate (no nested anchors).
    saved: list[re.Match] = []

    def stash(match):
        saved.append(match)
        return f"\ue000{len(saved) - 1}\ue001"

    without_md_links = _MD_LINK_RE.sub(stash, text)
    escaped = html.escape(without_md_links)
    with_bold = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    linked = _linkify_escaped(with_bold)
    for index, match in enumerate(saved):
        label = html.escape(match.group(1))
        url, trailing = _strip_trailing_punctuation(match.group(2))
        linked = linked.replace(
            f"\ue000{index}\ue001",
            f'<a href="{url}">{label}</a>{html.escape(trailing)}',
        )
    return linked


def custom_message_text(message: str) -> str:
    """Plain-text version: markdown links render as ``label (url)``."""

    def replace(match):
        return f"{match.group(1)} ({match.group(2)})"

    return _MD_LINK_RE.sub(replace, message or "")


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
