from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str | None) -> str:
    """Turn (possibly entity-escaped) HTML into collapsed plain text."""
    if not raw:
        return ""
    text = html.unescape(raw)          # Greenhouse double-escapes its HTML
    text = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h\d)\s*/?>", " \n ", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()


@dataclass
class Job:
    source: str                 # company / source name from config
    platform: str               # greenhouse, lever, ashby, workday, jibe, amazon
    job_id: str                 # id unique within the platform+source
    title: str
    url: str
    location: str = ""
    posted: str | None = None   # ISO date (YYYY-MM-DD) when known
    employment_type: str = ""   # e.g. "Intern" when the platform says so
    description: str = ""       # plain text; used for scoring, not stored

    # Filled by filters.score_job
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    degree: list[str] = field(default_factory=list)
    season: str = ""

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.source}:{self.job_id}"
