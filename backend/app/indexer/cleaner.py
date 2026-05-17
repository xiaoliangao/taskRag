from __future__ import annotations

import re

_WS_RE = re.compile(r"[ \t\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    # PostgreSQL TEXT cannot store NUL bytes; PyMuPDF occasionally emits them.
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return text.strip()
