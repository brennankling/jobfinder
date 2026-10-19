"""Merge a run's matches into the saved history (docs/data/jobs.json).

History is what makes "new since last visit" and "first seen" work:
  * first_seen is kept from the first run that found the job
  * a job missing from a run is marked closed, but only if its source
    fetched successfully that run (a failed source never closes jobs)
  * closed jobs are dropped after RETENTION_DAYS
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .model import Job

RETENTION_DAYS = 30
FIELDS = ("source", "platform", "title", "url", "location", "posted", "employment_type",
          "score", "reasons", "categories", "degree", "season")


def load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    return {"jobs": []}


def merge(previous: dict, matched: list[Job], ok_sources: set[str], today: date) -> list[dict]:
    t = today.isoformat()
    old = {j["key"]: j for j in previous.get("jobs", [])}
    out: dict[str, dict] = {}

    for job in matched:
        rec = {"key": job.key, **{f: getattr(job, f) for f in FIELDS}}
        prev = old.get(job.key)
        rec["first_seen"] = prev["first_seen"] if prev else t
        rec["last_seen"] = t
        rec["closed"] = None
        out[job.key] = rec

    cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
    for key, rec in old.items():
        if key in out:
            continue
        if rec.get("source") in ok_sources and not rec.get("closed"):
            rec = {**rec, "closed": t}
        if rec.get("closed") and rec["closed"] < cutoff:
            continue
        out[key] = rec

    return sorted(out.values(), key=lambda r: (r.get("closed") is not None, -(r.get("score") or 0),
                                               r.get("first_seen") or ""), reverse=False)


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    tmp.replace(path)
