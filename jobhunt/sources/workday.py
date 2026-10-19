"""Workday career sites (NVIDIA, Intel, Marvell, Broadcom, ...).

Every Workday site exposes the JSON API its own front end uses:
  POST {host}/wday/cxs/{tenant}/{site}/jobs          search, 20 results per page
  GET  {host}/wday/cxs/{tenant}/{site}{externalPath}  one job's full description

The list call has titles only, so descriptions are fetched just for listings
whose title already looks like an internship (ctx.title_candidate).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from ..http import SourceError, get_json, post_json
from ..model import Job, html_to_text

PAGE = 20
MAX_PER_TERM = 400      # safety cap per search term
DETAIL_WORKERS = 4


def parse_site(url: str):
    """'https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite' -> (host, tenant, site)."""
    u = urlparse(url)
    if "myworkdayjobs.com" not in u.netloc:
        raise SourceError(f"not a myworkdayjobs.com URL: {url}")
    tenant = u.netloc.split(".")[0]
    parts = [p for p in u.path.split("/") if p]
    if parts and len(parts[0]) in (2, 5) and (parts[0][2:3] in ("", "-")) and len(parts) > 1:
        parts = parts[1:]                      # drop locale like en-US
    if not parts:
        raise SourceError(f"Workday URL is missing the site name: {url}")
    return f"{u.scheme}://{u.netloc}", tenant, parts[0]


def fetch(session, src: dict, ctx) -> list[Job]:
    from . import iso_from_any, workday_posted

    host, tenant, site = parse_site(src["url"])
    api = f"{host}/wday/cxs/{tenant}/{site}"
    terms = src.get("search_terms") or ctx.settings.get("workday_search_terms") or ["intern"]

    listings: dict[str, dict] = {}
    for term in terms:
        offset, total = 0, None
        while True:
            data = post_json(session, f"{api}/jobs", {
                "appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": term,
            })
            postings = data.get("jobPostings")
            if postings is None:
                raise SourceError("unexpected Workday response (no jobPostings)")
            if total is None:                      # only the first page has a reliable total
                total = int(data.get("total") or 0)
            for p in postings:
                path = p.get("externalPath")
                if path:
                    listings.setdefault(path, p)
            offset += PAGE
            if not postings or offset >= min(total, MAX_PER_TERM):
                break

    candidates = [p for p in listings.values() if ctx.title_candidate(p.get("title") or "", "")]

    def detail(p):
        path = p["externalPath"]
        info = {}
        try:
            info = get_json(session, f"{api}{path}").get("jobPostingInfo") or {}
        except SourceError:
            pass                                   # keep the listing, score on title alone
        locs = [info.get("location") or p.get("locationsText") or ""]
        locs += info.get("additionalLocations") or []
        return Job(
            source=src["name"],
            platform="workday",
            job_id=(info.get("jobReqId") or (p.get("bulletFields") or [path])[0]),
            title=(info.get("title") or p.get("title") or "").strip(),
            url=info.get("externalUrl") or f"{host}/en-US/{site}{path}",
            location="; ".join(dict.fromkeys(l for l in locs if l)),
            posted=iso_from_any(info.get("startDate")) or workday_posted(p.get("postedOn"), ctx.today),
            employment_type=info.get("timeType") or "",
            description=html_to_text(info.get("jobDescription")),
        )

    with ThreadPoolExecutor(DETAIL_WORKERS) as pool:
        jobs = list(pool.map(detail, candidates))
    src["_scanned"] = len(listings)
    return jobs
