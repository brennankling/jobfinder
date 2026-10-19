from __future__ import annotations

from ..http import SourceError, get_json
from ..model import Job, html_to_text

API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch_slug(session, name: str, slug: str) -> list[Job]:
    from . import iso_from_any

    data = get_json(session, API.format(slug=slug))
    if not isinstance(data, list):
        raise SourceError(f"unexpected Lever response for '{slug}'")
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description"))]
        for lst in j.get("lists") or []:
            parts.append(lst.get("text") or "")
            parts.append(html_to_text(lst.get("content")))
        parts.append(j.get("additionalPlain") or "")
        locs = cats.get("allLocations") or [cats.get("location") or ""]
        jobs.append(Job(
            source=name,
            platform="lever",
            job_id=str(j.get("id")),
            title=(j.get("text") or "").strip(),
            url=j.get("hostedUrl") or "",
            location="; ".join(l for l in locs if l),
            posted=iso_from_any(j.get("createdAt")),
            employment_type=cats.get("commitment") or "",
            description=" ".join(p for p in parts if p),
        ))
    return jobs


def fetch(session, src: dict, ctx) -> list[Job]:
    return fetch_slug(session, src["name"], src["slug"])
