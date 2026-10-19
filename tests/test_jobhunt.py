"""Offline tests: every platform parser, the filter, history merging, and a full run.

Run with:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path

from jobhunt import store
from jobhunt.__main__ import cmd_run
from jobhunt.filters import is_intern, location_allowed, score_job, title_candidate_factory
from jobhunt.model import Job, html_to_text
from jobhunt.sources import Context, FETCHERS, iso_from_any, workday_posted
from jobhunt.sources.workday import parse_site

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 18)
SETTINGS = {"min_score": 6, "interns_only": True,
            "exclude_locations": ["India", "Bangalore", "Canada", "Toronto", "Markham"]}


def fx(name):
    return json.loads((FIX / name).read_text())


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeSession:
    """Routes URLs to fixture files. Unknown URLs return 404."""

    def __init__(self, routes=None):
        self.calls = []
        self.routes = routes if routes is not None else {
            "boards-api.greenhouse.io/v1/boards/cerebrassystems/": fx("greenhouse.json"),
            "api.lever.co/v0/postings/sifive": fx("lever.json"),
            "api.ashbyhq.com/posting-api/job-board/etched?": fx("ashby.json"),
            "careers.amd.com/api/jobs": fx("jibe.json"),
            "www.amazon.jobs/en/search.json": fx("amazon.json"),
        }
        self.wd_detail = fx("workday_detail.json")

    def get(self, url, timeout=None, params=None, **kw):
        self.calls.append(("GET", url, params))
        if "/wday/cxs/" in url:
            path = url.split("/NVIDIAExternalCareerSite", 1)[1]
            return Resp(self.wd_detail[path]) if path in self.wd_detail else Resp({}, 404)
        for frag, data in self.routes.items():
            if frag in url:
                return Resp(data)
        return Resp({"error": "not found"}, 404)

    def post(self, url, json=None, timeout=None, **kw):
        self.calls.append(("POST", url, json))
        if url.endswith("/jobs") and "/wday/cxs/nvidia/" in url:
            data = fx("workday_list.json")
            if json and json.get("offset", 0) > 0:
                data = {"total": 0, "jobPostings": []}
            return Resp(data)
        return Resp({}, 404)


def ctx():
    return Context(settings=SETTINGS, title_candidate=title_candidate_factory(SETTINGS), today=TODAY)


def kept(jobs):
    return {j.title for j in jobs if score_job(j, SETTINGS)}


class TestHelpers(unittest.TestCase):
    def test_html_to_text_handles_double_escaped(self):
        self.assertEqual(html_to_text("&lt;p&gt;RTL &amp;amp; UVM&lt;/p&gt;"), "RTL & UVM")

    def test_dates(self):
        self.assertEqual(iso_from_any("2026-10-10T12:00:00-04:00"), "2026-10-10")
        self.assertEqual(iso_from_any("October 9, 2026"), "2026-10-09")
        self.assertEqual(iso_from_any(1760000000000), "2025-10-09")
        self.assertEqual(iso_from_any("2026-10-08T00:00:00+0000"), "2026-10-08")
        self.assertIsNone(iso_from_any("garbage"))
        self.assertEqual(workday_posted("Posted 3 Days Ago", TODAY), "2026-10-15")
        self.assertEqual(workday_posted("Posted Today", TODAY), "2026-10-18")
        self.assertIsNone(workday_posted("Posted 30+ Days Ago", TODAY))

    def test_parse_workday_url(self):
        self.assertEqual(parse_site("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/details/x"),
                         ("https://nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"))
        self.assertEqual(parse_site("https://intel.wd1.myworkdayjobs.com/External")[2], "External")


class TestFilter(unittest.TestCase):
    def j(self, title, desc="", loc="Austin, TX", etype=""):
        return Job("X", "greenhouse", "1", title, "u", location=loc, description=desc, employment_type=etype)

    def test_intern_detection(self):
        self.assertTrue(is_intern("ASIC Design Intern"))
        self.assertTrue(is_intern("FPGA Co-op"))
        self.assertTrue(is_intern("Hardware Engineer", "Intern"))
        self.assertTrue(is_intern("Summer 2027 - Silicon Engineering"))
        self.assertFalse(is_intern("Internal Audit Analyst"))
        self.assertFalse(is_intern("International Trade Compliance"))
        self.assertFalse(is_intern("Senior RTL Engineer"))

    def test_strong_titles_kept(self):
        for t in ["Design Verification Intern", "RTL Design Intern", "FPGA Engineering Intern",
                  "Digital Design Intern", "CPU Design Intern", "ASIC Intern"]:
            self.assertTrue(score_job(self.j(t, "We use SystemVerilog."), SETTINGS), t)

    def test_weak_title_needs_hdl_evidence(self):
        self.assertFalse(score_job(self.j("Hardware Engineering Intern", "Board bring-up and lab work."), SETTINGS))
        self.assertTrue(score_job(self.j("Hardware Engineering Intern", "Write RTL in SystemVerilog, run synthesis."), SETTINGS))

    def test_excluded_and_penalized(self):
        self.assertFalse(score_job(self.j("Software Engineering Intern", "C++ and some Verilog exposure"), SETTINGS))
        self.assertFalse(score_job(self.j("Analog Design Intern", "Verilog-A models"), SETTINGS))
        self.assertTrue(score_job(self.j("FPGA Firmware Intern", "VHDL on Xilinx"), SETTINGS))

    def test_location(self):
        ex = SETTINGS["exclude_locations"]
        self.assertFalse(location_allowed("Bangalore, India", ex))
        self.assertTrue(location_allowed("Santa Clara, CA; Bangalore, India", ex))
        self.assertTrue(location_allowed("US, CA, Santa Clara", ex))
        self.assertTrue(location_allowed("", ex))

    def test_metadata(self):
        job = self.j("Design Verification Intern (Summer 2027)", "UVM testbench. Pursuing a Bachelor's or Master's.")
        self.assertTrue(score_job(job, SETTINGS))
        self.assertEqual(job.season, "Summer 2027")
        self.assertEqual(job.degree, ["MS", "BS"])
        self.assertIn("Verification", job.categories)
        self.assertTrue(job.reasons)
        phd = self.j("ASIC Physical Design Intern, PhD", "Timing closure. RTL handoff.")
        self.assertTrue(score_job(phd, SETTINGS))
        self.assertEqual(phd.degree, ["PhD"])

    def test_interns_only_off(self):
        s = {**SETTINGS, "interns_only": False}
        self.assertTrue(score_job(self.j("RTL Design Engineer", "SystemVerilog"), s))


class TestSources(unittest.TestCase):
    def test_greenhouse(self):
        jobs = FETCHERS["greenhouse"](FakeSession(), {"name": "Cerebras", "slug": "cerebrassystems"}, ctx())
        self.assertEqual(len(jobs), 6)
        self.assertEqual(kept(jobs), {"Design Verification Intern (Summer 2027)", "Hardware Engineering Intern"})
        dv = next(j for j in jobs if j.job_id == "101")
        self.assertEqual(dv.posted, "2026-10-10")
        self.assertIn("UVM", dv.description)

    def test_lever(self):
        jobs = FETCHERS["lever"](FakeSession(), {"name": "SiFive", "slug": "sifive"}, ctx())
        self.assertEqual(kept(jobs), {"FPGA Engineering Co-op"})
        self.assertIn("Vivado", jobs[0].description)

    def test_ashby(self):
        jobs = FETCHERS["ashby"](FakeSession(), {"name": "Etched", "slug": "etched"}, ctx())
        self.assertEqual(kept(jobs), {"Silicon Engineering Intern"})

    def test_auto_falls_through_to_ashby(self):
        src = {"name": "Etched", "slugs": ["etchedai", "etched"]}
        jobs = FETCHERS["auto"](FakeSession(), src, ctx())
        self.assertEqual(src["_resolved"], "ashby/etched")
        self.assertEqual(len(jobs), 2)

    def test_workday_only_fetches_candidate_details(self):
        s = FakeSession()
        src = {"name": "NVIDIA", "url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"}
        settings = {**SETTINGS, "workday_search_terms": ["intern"]}
        c = Context(settings=settings, title_candidate=title_candidate_factory(settings), today=TODAY)
        jobs = FETCHERS["workday"](s, src, c)
        self.assertEqual({j.title for j in jobs},
                         {"Hardware Verification Intern - Summer 2027", "ASIC Physical Design Intern, PhD"})
        detail_calls = [u for m, u, _ in s.calls if m == "GET"]
        self.assertEqual(len(detail_calls), 2)          # software intern detail never fetched
        self.assertEqual(src["_scanned"], 3)
        pd = next(j for j in jobs if "Physical" in j.title)
        self.assertIn("Santa Clara", pd.location)
        self.assertIsNone(pd.posted)
        self.assertEqual(kept(jobs), {j.title for j in jobs})

    def test_jibe(self):
        jobs = FETCHERS["jibe"](FakeSession(), {"name": "AMD", "url": "https://careers.amd.com"}, ctx())
        self.assertEqual(kept(jobs), {"Digital Design Engineering Intern/Co-op"})
        self.assertEqual(jobs[0].url, "https://careers.amd.com/careers-home/jobs/63823")

    def test_amazon(self):
        settings = {**SETTINGS, "amazon_queries": ["a", "b"]}
        c = Context(settings=settings, title_candidate=title_candidate_factory(settings), today=TODAY)
        jobs = FETCHERS["amazon"](FakeSession(), {"name": "Amazon"}, c)
        self.assertEqual(len(jobs), 2)                   # deduped across both queries
        self.assertEqual(kept(jobs), {"Hardware Design Engineer Intern - ASIC (Annapurna Labs (U.S.) Inc.)"})


class TestStore(unittest.TestCase):
    def job(self, jid, source="A"):
        j = Job(source, "greenhouse", jid, f"RTL Intern {jid}", "u", location="Austin, TX", description="RTL")
        score_job(j, SETTINGS)
        return j

    def test_history(self):
        d1, d2 = date(2026, 10, 1), date(2026, 10, 2)
        first = store.merge({"jobs": []}, [self.job("1"), self.job("2"), self.job("9", "B")], {"A", "B"}, d1)
        prev = {"jobs": first}
        # day 2: job 1 still listed, job 2 gone, source B failed
        second = {r["key"]: r for r in store.merge(prev, [self.job("1")], {"A"}, d2)}
        self.assertEqual(second["greenhouse:A:1"]["first_seen"], "2026-10-01")
        self.assertEqual(second["greenhouse:A:1"]["last_seen"], "2026-10-02")
        self.assertEqual(second["greenhouse:A:2"]["closed"], "2026-10-02")
        self.assertIsNone(second["greenhouse:B:9"]["closed"])  # failed source never closes jobs
        # 31 days later the closed job is dropped
        later = {r["key"] for r in store.merge({"jobs": list(second.values())}, [], {"A"}, date(2026, 11, 3))}
        self.assertNotIn("greenhouse:A:2", later)


class TestEndToEnd(unittest.TestCase):
    def test_full_run(self):
        cfg = textwrap.dedent("""
            [filter]
            min_score = 6
            exclude_locations = ["India", "Canada", "Toronto", "Markham"]
            workday_search_terms = ["intern"]
            amazon_queries = ["hardware intern"]
            [[source]]
            name = "Cerebras"
            platform = "greenhouse"
            slug = "cerebrassystems"
            [[source]]
            name = "NVIDIA"
            platform = "workday"
            url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
            [[source]]
            name = "Ghost"
            platform = "greenhouse"
            slug = "doesnotexist"
            [[manual]]
            name = "Apple"
            url = "https://jobs.apple.com"
        """)
        with tempfile.TemporaryDirectory() as d:
            cfg_path, out = Path(d) / "c.toml", Path(d) / "jobs.json"
            cfg_path.write_text(cfg)
            args = Namespace(config=str(cfg_path), out=str(out), only=None, today="2026-10-18")
            rc = cmd_run(args, session_factory=FakeSession)
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text())
            self.assertEqual(len(data["jobs"]), 4)
            status = {s["name"]: s["status"] for s in data["sources"]}
            self.assertEqual(status, {"Cerebras": "ok", "NVIDIA": "ok", "Ghost": "error"})
            self.assertEqual(data["manual"][0]["name"], "Apple")
            self.assertTrue(all(j["first_seen"] == "2026-10-18" for j in data["jobs"]))


if __name__ == "__main__":
    unittest.main()
