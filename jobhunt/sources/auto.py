"""Try a list of slug guesses across Greenhouse, Ashby and Lever.

Used for startups whose hiring platform isn't known in advance. The first
platform+slug that answers with a valid board wins. The winner is reported in
the run summary so it can be pinned in config.toml.
"""
from __future__ import annotations

from ..http import SourceError
from . import ashby, greenhouse, lever

ORDER = (("greenhouse", greenhouse.fetch_slug), ("ashby", ashby.fetch_slug), ("lever", lever.fetch_slug))


def resolve(session, name: str, slugs: list[str]):
    """Return (platform, slug, jobs) for the first board that answers."""
    tried = []
    for slug in slugs:
        for platform, fn in ORDER:
            try:
                jobs = fn(session, name, slug)
            except SourceError:
                tried.append(f"{platform}/{slug}")
                continue
            return platform, slug, jobs
    raise SourceError("no board found (tried " + ", ".join(tried) + ")")


def fetch(session, src: dict, ctx):
    platform, slug, jobs = resolve(session, src["name"], src.get("slugs") or [src.get("slug")])
    src["_resolved"] = f"{platform}/{slug}"
    return jobs
