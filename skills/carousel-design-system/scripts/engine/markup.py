"""Inline copy markup.

Copywriters get exactly three pieces of inline formatting:
  **words**   highlighted in the slide's highlight colour
  *words*     italic
  line break  a new line inside the copy (YAML block or multi-line brief value);
              a blank line starts a new paragraph

Everything else is HTML-escaped, so copy can never break a template.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape

_HIGHLIGHT = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S)


def problems(text: str) -> list[str]:
    """Markup mistakes worth stopping for (they would show up as stray asterisks)."""
    if text.count("**") % 2:
        return ["unmatched ** (highlight markers must come in pairs)"]
    issues = []
    leftover = _HIGHLIGHT.sub("", text)
    leftover = _ITALIC.sub("", leftover)
    if "*" in leftover:
        issues.append("stray * (use *italic* or **highlight**, or remove it)")
    return issues


def render(text: str | None) -> Markup:
    if not text:
        return Markup("")
    html = str(escape(text.strip()))
    html = _HIGHLIGHT.sub(r'<strong class="hl">\1</strong>', html)
    html = _ITALIC.sub(r"<em>\1</em>", html)
    html = re.sub(r"[ \t]*\n[ \t]*\n\s*", '<span class="para-gap"></span>', html)
    html = re.sub(r"[ \t]*\n[ \t]*", "<br>", html)
    return Markup(html)


def plain(text: str | None) -> str:
    """Copy as the reader sees it: markers removed, whitespace collapsed."""
    if not text:
        return ""
    text = _HIGHLIGHT.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()
