from __future__ import annotations

from ..http import SourceError, get_json
from ..model import Job, html_to_text

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false"


def fetch_slug(session, name: str, slug: str) -> list[Job]:
    from . import iso_from_any

    data = get_json(session, API.format(slug=slug))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SourceError("unexpected Ashby response for '" + slug + "'")
    jobs = []
    for j in data["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""]
        locs += [(s or {}).get("location", "") for s in j.get("secondaryLocations") or []]
        if j.get("isRemote"):
            locs.append("Remote")
        jobs.append(Job(
            source=name,
            platform="ashby",
            job_id=str(j.get("id")),
            title=(j.get("title") or "").strip(),
            url=j.get("jobUrl") or j.get("applyUrl") or "",
            location="; ".join(dict.fromkeys(l for l in locs if l)),
            posted=iso_from_any(j.get("publishedAt")),
            employment_type=j.get("employmentType") or "",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
        ))
    return jobs


def fetch(session, src: dict, ctx) -> list[Job]:
    return fetch_slug(session, src["name"], src["slug"])
