"""Keyword scoring: is this an internship where you'd write RTL?

A listing is kept when it
  1. is an internship/co-op (title, or the platform's employment type), unless interns_only=false
  2. isn't located only outside the US (config exclude_locations)
  3. reaches min_score, AND shows real RTL evidence: a strong title term or an
     HDL term (Verilog, SystemVerilog, VHDL, RTL, UVM, ...) in the description.

Every point awarded is recorded in job.reasons, so the dashboard can show why a
listing matched and the weights below are easy to tune.
"""
from __future__ import annotations

import re

from .model import Job

# --------------------------------------------------------------------- terms


def _rx(terms):
    return re.compile(r"(?<![a-z0-9])(" + "|".join(terms) + r")(?![a-z0-9])", re.I)


INTERN = _rx([r"intern", r"interns", r"internship", r"internships", r"co-?op", r"co-?ops",
              r"summer\s+20\d\d", r"student", r"apprentice"])
# Titles that look like internships but aren't
NOT_INTERN = _rx([r"internal", r"international", r"internet", r"intern(al)?\s+audit",
                  r"intern\s+program\s+manager", r"intern\s+recruit\w*", r"student\s+success"])

# Strong title terms: almost certainly RTL work.  (pattern, weight, category)
TITLE_STRONG = [
    (r"rtl", 6, "Design"),
    (r"asic", 6, "Design"),
    (r"design\s+verification", 7, "Verification"),
    (r"dv", 6, "Verification"),
    (r"(?:pre-?silicon\s+)?verification", 5, "Verification"),
    (r"fpga", 6, "FPGA"),
    (r"digital\s+(?:ic\s+|asic\s+|logic\s+)?design", 7, "Design"),
    (r"logic\s+design", 6, "Design"),
    (r"soc", 5, "Design"),
    (r"micro-?architecture", 5, "Architecture"),
    (r"(?:cpu|gpu)\s+(?:design|verification|architecture)", 6, "Design"),
    (r"physical\s+design", 6, "Physical design"),
    (r"vlsi", 5, "Design"),
    (r"silicon\s+(?:design|engineer\w*|architecture)", 5, "Design"),
    (r"dft|design\s+for\s+test", 4, "DFT"),
    (r"emulation|prototyping", 4, "Emulation"),
    (r"hardware\s+(?:design|verification|description)", 5, "Design"),
    (r"chip\s+design", 6, "Design"),
]
# Weak title terms: hardware-ish, needs description support.
TITLE_WEAK = [
    (r"hardware", 2), (r"computer\s+engineer\w*", 2), (r"electrical\s+engineer\w*", 1),
    (r"architecture", 1), (r"silicon", 2), (r"chip", 1), (r"digital", 1), (r"accelerator", 2),
]
# HDL evidence in description. Each distinct hit counts once.
DESC_HDL = [
    (r"verilog", 3), (r"system\s*verilog", 3), (r"vhdl", 3), (r"rtl", 3), (r"uvm", 3),
    (r"chisel", 2), (r"bluespec", 2), (r"spinal\s*hdl", 2), (r"hdl", 2),
]
# Supporting description terms, capped in total.
DESC_SUPPORT = [
    (r"synthesis", 1), (r"timing\s+closure", 1), (r"static\s+timing|sta", 1), (r"testbench(es)?", 1),
    (r"formal\s+verification|jaspergold", 1), (r"functional\s+coverage|coverage\s+closure", 1),
    (r"vivado|quartus|libero", 1), (r"cocotb", 1), (r"lint|spyglass", 1), (r"cdc", 1),
    (r"design\s+compiler|genus|innovus|icc2|fusion\s+compiler", 1), (r"vcs|xcelium|questa|verilator", 1),
    (r"micro-?architecture", 1), (r"axi|ahb|apb|amba", 1), (r"risc-?v", 1), (r"fpga", 1), (r"asic", 1),
]
DESC_SUPPORT_CAP = 6

# Title terms that usually mean "not an RTL job" unless a strong term is also present.
TITLE_EXCLUDE = [
    r"software", r"firmware", r"sales", r"marketing", r"finance", r"accounting", r"legal",
    r"recruit\w*", r"human\s+resources|hr", r"supply\s+chain", r"procurement", r"business",
    r"data\s+scien\w*", r"data\s+analyst", r"machine\s+learning\s+engineer", r"product\s+manag\w*",
    r"program\s+manag\w*", r"technician", r"mechanical", r"facilities", r"manufacturing",
    r"process\s+engineer\w*", r"packaging", r"thermal", r"optical", r"photonics", r"materials",
    r"chemical", r"device\s+engineer\w*", r"yield", r"it\b", r"security\s+analyst", r"ux|ui\s+design",
    r"graphic", r"communications", r"writer",
]
# Penalties: RTL-adjacent but usually not RTL.
TITLE_PENALTY = [
    (r"analog", -5), (r"mixed[-\s]signal", -2), (r"rf\b", -4), (r"layout", -4), (r"pcb|board\s+design", -4),
    (r"power\s+electronics", -4), (r"test\s+engineer", -2), (r"product\s+engineer", -3),
    (r"application(s)?\s+engineer", -2), (r"post-?silicon", -1),
]

_TS = [(re.compile(r"(?<![a-z0-9])(" + p + r")(?![a-z0-9])", re.I), w, c) for p, w, c in TITLE_STRONG]
_TW = [(re.compile(r"(?<![a-z0-9])(" + p + r")(?![a-z0-9])", re.I), w) for p, w in TITLE_WEAK]
_DH = [(re.compile(r"(?<![a-z0-9])(" + p + r")(?![a-z0-9])", re.I), w) for p, w in DESC_HDL]
_DS = [(re.compile(r"(?<![a-z0-9])(" + p + r")(?![a-z0-9])", re.I), w) for p, w in DESC_SUPPORT]
_TX = _rx(TITLE_EXCLUDE)
_TP = [(re.compile(r"(?<![a-z0-9])(" + p + r")(?![a-z0-9])", re.I), w) for p, w in TITLE_PENALTY]

# Category hints from the description, used when the title alone doesn't say.
DESC_CATEGORY = [
    (re.compile(r"\buvm\b|testbench|functional coverage|verification plan|constrained[- ]random", re.I), "Verification"),
    (re.compile(r"\bfpga\b|vivado|quartus", re.I), "FPGA"),
    (re.compile(r"place and route|timing closure|floorplan|innovus|icc2", re.I), "Physical design"),
    (re.compile(r"\brtl design\b|micro-?architect|\brtl\b", re.I), "Design"),
]

# Degree level. Titles are trusted first ("Intern, Graduate", "PhD Intern"); if the
# title says nothing, explicit degree words in the description are used.
DEGREE_TITLE = [
    (re.compile(r"\bph\.?\s?d\b|doctoral", re.I), "PhD"),
    (re.compile(r"\bmaster'?s\b|\bm\.s\b|\bms\b|(?<!under)\bgraduate\b", re.I), "MS"),
    (re.compile(r"\bbachelor'?s\b|\bb\.s\b|\bbs\b|undergrad", re.I), "BS"),
]
DEGREE_DESC = [
    (re.compile(r"\bph\.?\s?d\.?\b|doctoral", re.I), "PhD"),
    (re.compile(r"\bmaster'?s\b|\bm\.s\.|\bms\b(?!\s*office)", re.I), "MS"),
    (re.compile(r"\bbachelor'?s\b|\bb\.s\.|\bbs\b|undergraduate", re.I), "BS"),
]
SEASON = re.compile(r"\b(summer|fall|autumn|winter|spring)\s*'?\s*(20)?(\d{2})\b", re.I)

US_HINT = re.compile(
    r"united states|\busa\b|\bus\b|remote|,\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b|"
    r"california|texas|oregon|washington|massachusetts|colorado|arizona|georgia|north carolina|new york|florida|"
    r"santa clara|san jose|sunnyvale|austin|boston|hillsboro|folsom|seattle|atlanta|durham|boise|"
    r"fort collins|chandler|phoenix|san diego|los altos|mountain view|cupertino|palo alto|bellevue",
)


# --------------------------------------------------------------------- helpers

def is_intern(title: str, employment_type: str = "") -> bool:
    if employment_type and re.search(r"intern|co-?op|student", employment_type, re.I):
        return True
    t = NOT_INTERN.sub(" ", title)
    return bool(INTERN.search(t))


def title_candidate_factory(settings: dict):
    """Cheap title-only check used before fetching full descriptions."""
    interns_only = settings.get("interns_only", True)

    def check(title: str, employment_type: str = "") -> bool:
        if interns_only and not is_intern(title, employment_type):
            return False
        strong = any(rx.search(title) for rx, _, _ in _TS)
        if _TX.search(title) and not strong:
            return False
        return True

    return check


def location_allowed(location: str, excluded: list[str]) -> bool:
    if not location or not excluded:
        return True
    if US_HINT.search(location):
        return True
    low = location.lower()
    return not any(re.search(r"(?<![a-z])" + re.escape(x.lower()) + r"(?![a-z])", low) for x in excluded)


def detect_season(text: str) -> str:
    m = SEASON.search(text)
    if not m:
        return ""
    season = m.group(1).capitalize().replace("Autumn", "Fall")
    return f"{season} 20{m.group(3)}"


# --------------------------------------------------------------------- scoring

def score_job(job: Job, settings: dict) -> bool:
    """Score in place; return True if the job should be kept."""
    title, desc = job.title, job.description
    reasons: list[str] = []
    cats: list[str] = []
    score = 0

    if settings.get("interns_only", True) and not is_intern(title, job.employment_type):
        return False
    if not location_allowed(job.location, settings.get("exclude_locations", [])):
        return False

    strong_hit = False
    for rx, w, cat in _TS:
        m = rx.search(title)
        if m:
            strong_hit = True
            score += w
            reasons.append(f"title: {m.group(1)} +{w}")
            if cat not in cats:
                cats.append(cat)
    # Only the best strong match should dominate; cap stacking ("ASIC RTL Design Verification")
    if strong_hit:
        score = min(score, 12)

    if _TX.search(title) and not strong_hit:
        return False

    for rx, w in _TW:
        m = rx.search(title)
        if m:
            score += w
            reasons.append(f"title: {m.group(1)} +{w}")

    for rx, w in _TP:
        m = rx.search(title)
        if m:
            score += w
            reasons.append(f"title: {m.group(1)} {w}")

    hdl_hit = False
    hdl_seen = set()
    for rx, w in _DH:
        m = rx.search(desc)
        if m:
            key = m.group(1).lower().replace(" ", "")
            if key == "verilog" and "systemverilog" in hdl_seen:
                continue
            hdl_seen.add(key)
            hdl_hit = True
            score += w
            reasons.append(f"desc: {m.group(1)} +{w}")

    support = 0
    for rx, w in _DS:
        if support >= DESC_SUPPORT_CAP:
            break
        m = rx.search(desc)
        if m:
            support += w
            reasons.append(f"desc: {m.group(1)} +{w}")
    score += support

    if not (strong_hit or hdl_hit):
        return False
    if score < settings.get("min_score", 6):
        return False

    for rx, cat in DESC_CATEGORY:
        if rx.search(desc) and cat not in cats:
            cats.append(cat)

    job.degree = [label for rx, label in DEGREE_TITLE if rx.search(title)] or \
                 [label for rx, label in DEGREE_DESC if rx.search(desc[:4000])]
    job.season = detect_season(title) or detect_season(desc[:2000])
    job.score = score
    job.reasons = reasons
    job.categories = cats or ["Hardware"]
    return True
