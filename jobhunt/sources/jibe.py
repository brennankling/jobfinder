"""Jibe-hosted career sites (e.g. careers.amd.com). GET {root}/api/jobs?keywords=..."""
from __future__ import annotations

from ..http import SourceError, get_json
from ..model import Job, html_to_text

LIMIT = 100
MAX_PAGES = 5


def fetch(session, src: dict, ctx) -> list[Job]:
    from . import iso_from_any

    root = src["url"].rstrip("/")
    terms = src.get("search_terms") or ctx.settings.get("workday_search_terms") or ["intern"]
    seen: dict[str, Job] = {}
    for term in terms:
        for page in range(1, MAX_PAGES + 1):
            data = get_json(session, f"{root}/api/jobs", params={
                "keywords": term, "page": page, "limit": LIMIT, "sortBy": "posted_date",
                "descending": "true",
            })
            if not isinstance(data, dict) or "jobs" not in data:
                raise SourceError("unexpected Jibe response (no jobs)")
            rows = data["jobs"]
            for row in rows:
                d = row.get("data") or row
                jid = str(d.get("req_id") or d.get("slug") or d.get("id"))
                if jid in seen:
                    continue
                slug = d.get("slug") or jid
                seen[jid] = Job(
                    source=src["name"],
                    platform="jibe",
                    job_id=jid,
                    title=(d.get("title") or "").strip(),
                    url=d.get("canonical_url") or f"{root}/careers-home/jobs/{slug}",
                    location=d.get("full_location") or d.get("location_name") or "",
                    posted=iso_from_any(d.get("posted_date") or d.get("create_date")),
                    employment_type=d.get("employment_type") or "",
                    description=" ".join(filter(None, [
                        html_to_text(d.get("description")),
                        html_to_text(d.get("qualifications")),
                        html_to_text(d.get("responsibilities")),
                    ])),
                )
            total = int(data.get("totalCount") or data.get("count") or 0)
            if len(rows) < LIMIT or page * LIMIT >= total:
                break
    return list(seen.values())
