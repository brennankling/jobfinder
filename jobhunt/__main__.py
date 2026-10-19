"""Command line.

  python -m jobhunt run                 fetch every source, update docs/data/jobs.json
  python -m jobhunt run --only NVIDIA   fetch one source (handy when adding one)
  python -m jobhunt probe groq etched   find which platform a company slug lives on
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from . import store
from .filters import score_job, title_candidate_factory
from .http import SourceError, make_session
from .sources import FETCHERS, Context
from .sources.auto import resolve

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("filter", {})
    cfg.setdefault("source", [])
    cfg.setdefault("manual", [])
    return cfg


def run_source(src: dict, ctx: Context, session_factory) -> dict:
    t0 = time.monotonic()
    report = {"name": src["name"], "platform": src["platform"], "status": "ok",
              "fetched": 0, "matched": 0, "error": None}
    fetch = FETCHERS.get(src["platform"])
    if fetch is None:
        report.update(status="error", error=f"unknown platform '{src['platform']}'")
        return {"report": report, "jobs": []}
    try:
        jobs = fetch(session_factory(), src, ctx)
    except SourceError as e:
        report.update(status="error", error=str(e))
        jobs = []
    except Exception as e:  # a parser bug in one source must not sink the run
        report.update(status="error", error=f"{e.__class__.__name__}: {e}")
        jobs = []
    matched = [j for j in jobs if score_job(j, ctx.settings)]
    report["fetched"] = src.get("_scanned", len(jobs))
    report["matched"] = len(matched)
    if src.get("_resolved"):
        report["resolved"] = src["_resolved"]
    report["seconds"] = round(time.monotonic() - t0, 1)
    return {"report": report, "jobs": matched}


def cmd_run(args, session_factory=make_session) -> int:
    cfg = load_config(Path(args.config))
    settings = cfg["filter"]
    today = date.fromisoformat(args.today) if args.today else date.today()
    ctx = Context(settings=settings, title_candidate=title_candidate_factory(settings), today=today)

    sources = cfg["source"]
    if args.only:
        wanted = {n.lower() for n in args.only}
        sources = [s for s in sources if s["name"].lower() in wanted]
        if not sources:
            print("No source matches --only", file=sys.stderr)
            return 2

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda s: run_source(dict(s), ctx, session_factory), sources))

    reports = [r["report"] for r in results]
    matched = [j for r in results for j in r["jobs"]]
    ok = {r["name"] for r in reports if r["status"] == "ok"}

    out = Path(args.out)
    previous = store.load(out)
    if args.only:  # keep other sources' reports from the last full run
        keep = [r for r in previous.get("sources", []) if r["name"] not in {x["name"] for x in reports}]
        reports = keep + reports
    jobs = store.merge(previous, matched, ok, today)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {"min_score": settings.get("min_score", 6),
                     "interns_only": settings.get("interns_only", True)},
        "sources": sorted(reports, key=lambda r: r["name"].lower()),
        "manual": cfg["manual"],
        "jobs": jobs,
    }
    store.save(out, payload)
    summarize(payload, today)
    # Exit non-zero only if *everything* failed (likely a network problem worth noticing)
    return 1 if reports and not ok else 0


def summarize(payload: dict, today: date) -> None:
    t = today.isoformat()
    open_jobs = [j for j in payload["jobs"] if not j.get("closed")]
    new = [j for j in open_jobs if j.get("first_seen") == t]
    lines = [f"## RTL internship scan — {t}", "",
             f"**{len(open_jobs)}** open matches, **{len(new)}** new today.", ""]
    if new:
        lines += ["| Score | Company | Title | Location |", "|---|---|---|---|"]
        for j in sorted(new, key=lambda j: -j["score"])[:40]:
            lines.append(f"| {j['score']} | {j['source']} | [{j['title']}]({j['url']}) | {j['location'][:60]} |")
        lines.append("")
    lines += ["### Sources", "", "| Source | Status | Fetched | Matched | Note |", "|---|---|---|---|---|"]
    for r in payload["sources"]:
        note = r.get("error") or (f"found at {r['resolved']}" if r.get("resolved") else "")
        icon = "✅" if r["status"] == "ok" else "❌"
        lines.append(f"| {r['name']} | {icon} | {r['fetched']} | {r['matched']} | {note} |")
    text = "\n".join(lines)
    print(text)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(text + "\n")


def cmd_probe(args, session_factory=make_session) -> int:
    session = session_factory()
    status = 0
    for slug in args.slugs:
        try:
            platform, found, jobs = resolve(session, slug, [slug])
            print(f"{slug}: {platform} board '{found}' with {len(jobs)} open jobs")
            print(f'    [[source]]\n    name = "{slug}"\n    platform = "{platform}"\n    slug = "{found}"')
        except SourceError as e:
            print(f"{slug}: {e}")
            status = 1
    return status


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jobhunt")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch all sources and update the dashboard data")
    r.add_argument("--config", default=str(ROOT / "config.toml"))
    r.add_argument("--out", default=str(ROOT / "docs" / "data" / "jobs.json"))
    r.add_argument("--only", nargs="+", help="source names to fetch")
    r.add_argument("--today", help=argparse.SUPPRESS)
    pr = sub.add_parser("probe", help="find which platform a company slug is on")
    pr.add_argument("slugs", nargs="+")
    args = p.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_probe(args)


if __name__ == "__main__":
    sys.exit(main())
