from __future__ import annotations

from ..http import SourceError, get_json
from ..model import Job, html_to_text

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch_slug(session, name: str, slug: str) -> list[Job]:
    data = get_json(session, API.format(slug=slug))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("unexpected Greenhouse response for '" + slug + "'")
    jobs = []
    for j in data["jobs"]:
        jobs.append(Job(
            source=name,
            platform="greenhouse",
            job_id=str(j.get("id")),
            title=(j.get("title") or "").strip(),
            url=j.get("absolute_url") or "",
            location=((j.get("location") or {}).get("name") or "").strip(),
            posted=_date(j.get("first_published") or j.get("updated_at")),
            description=html_to_text(j.get("content")),
        ))
    return jobs


def _date(v):
    from . import iso_from_any
    return iso_from_any(v)


def fetch(session, src: dict, ctx) -> list[Job]:
    return fetch_slug(session, src["name"], src["slug"])
