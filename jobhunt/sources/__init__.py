from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from ..http import SourceError


@dataclass
class Context:
    settings: dict
    # Cheap title-only check used to skip fetching full descriptions for
    # listings that can't match (Workday, Jibe need one request per detail).
    title_candidate: Callable[[str, str], bool]
    today: date


def iso_from_any(value) -> str | None:
    """Best-effort conversion of the date formats these feeds use to YYYY-MM-DD."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):            # Lever: epoch milliseconds
        secs = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(secs, tz=timezone.utc).date().isoformat()
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def workday_posted(text: str | None, today: date) -> str | None:
    """Workday list pages say 'Posted Today', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    if not text:
        return None
    t = text.lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    if "+" in t:
        return None
    digits = "".join(ch for ch in t if ch.isdigit())
    if digits:
        return (today - timedelta(days=int(digits))).isoformat()
    return None


from . import amazon, ashby, auto, greenhouse, jibe, lever, workday  # noqa: E402

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "auto": auto.fetch,
    "workday": workday.fetch,
    "jibe": jibe.fetch,
    "amazon": amazon.fetch,
}

__all__ = ["Context", "FETCHERS", "SourceError", "iso_from_any", "workday_posted"]
