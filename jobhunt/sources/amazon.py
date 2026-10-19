"""amazon.jobs public search (covers Annapurna Labs, Lab126, AWS hardware)."""
from __future__ import annotations

from ..http import SourceError, get_json
from ..model import Job, html_to_text

API = "https://www.amazon.jobs/en/search.json"
BASE = "https://www.amazon.jobs"


def fetch(session, src: dict, ctx) -> list[Job]:
    from . import iso_from_any

    queries = src.get("queries") or ctx.settings.get("amazon_queries") or ["hardware intern"]
    seen: dict[str, Job] = {}
    for q in queries:
        data = get_json(session, API, params={
            "base_query": q, "result_limit": 100, "offset": 0, "sort": "recent",
            "normalized_country_code[]": src.get("countries") or ctx.settings.get("amazon_countries") or ["USA"],
        })
        if not isinstance(data, dict) or "jobs" not in data:
            raise SourceError("unexpected amazon.jobs response (no jobs)")
        for j in data["jobs"]:
            jid = str(j.get("id_icims") or j.get("id"))
            if jid in seen:
                continue
            company = j.get("company_name") or ""
            seen[jid] = Job(
                source=src["name"],
                platform="amazon",
                job_id=jid,
                title=(j.get("title") or "").strip() + (f" ({company})" if "annapurna" in company.lower() else ""),
                url=BASE + (j.get("job_path") or f"/en/jobs/{jid}"),
                location=j.get("normalized_location") or j.get("location") or "",
                posted=iso_from_any(j.get("posted_date")),
                description=" ".join(filter(None, [
                    html_to_text(j.get("description")),
                    html_to_text(j.get("basic_qualifications")),
                    html_to_text(j.get("preferred_qualifications")),
                ])),
            )
    return list(seen.values())
