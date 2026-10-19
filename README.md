# RTL internship radar

Scans company hiring feeds once a day for internships where you'd write RTL
(design, verification, FPGA, physical design, emulation, DFT), and shows the
matches on a dashboard hosted on GitHub Pages.

It reads the public JSON feeds that company career sites already use
(Greenhouse, Lever, Ashby, Workday, Jibe, amazon.jobs). It does not scrape
LinkedIn or Indeed, so nothing here breaks those sites' terms or needs a login.

## Setup (about 5 minutes)

1. Create a new GitHub repository and push this folder to it.
   GitHub Pages is free on **public** repos; a private repo needs a paid plan for Pages.
2. **Settings → Pages**: under *Build and deployment*, choose *Deploy from a branch*,
   branch `main`, folder `/docs`. Save.
3. **Settings → Actions → General → Workflow permissions**: choose *Read and write permissions*.
4. **Actions tab → Scan job boards → Run workflow** to do the first scan now.
   After that it runs every morning on its own.
5. Open `https://<your-username>.github.io/<repo-name>/`.

The workflow's run page has a summary table: new matches, and which sources
worked. The same source health shows at the bottom of the dashboard.

## Using the dashboard

- **New** marks listings found since the scan you saw on your last visit.
- **Mark applied** and **Hide** are saved in your browser (per device).
- **Why it matched** lists every keyword that scored points. Use it to tune the filter.
- **Closed** shows listings that disappeared from their company's board in the last 30 days.

## Running locally

```bash
pip install -r requirements.txt
python -m jobhunt run                  # all sources -> docs/data/jobs.json
python -m jobhunt run --only NVIDIA    # one source, keeps the rest of the data
python -m http.server -d docs          # then open http://localhost:8000
python -m unittest discover -s tests   # offline tests, no network needed
```

## Adding or fixing a company

Everything is in `config.toml`.

- **Startups** usually use Greenhouse, Ashby, or Lever. Guess the slug (usually
  the company name) and test it:
  `python -m jobhunt probe groq` prints a ready-to-paste config block if the guess works.
  Or use `platform = "auto"` with a list of guesses and let each scan figure it out.
- **Workday companies**: open any of their job postings. If the address contains
  `myworkdayjobs.com`, copy the part up to and including the site name, e.g.
  `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`.
- **No feed** (Apple, Google, Meta, ...): add a `[[manual]]` link instead.

A source that fails never stops the scan; it's just reported as failed. Some
entries in the starter config are best guesses — check the source table after
the first run and fix or remove anything marked failed.

## Tuning the filter

`[filter]` in `config.toml`:

| Setting | What it does |
|---|---|
| `min_score` | Raise to see fewer, stronger matches; lower to see more. Default 6. |
| `interns_only` | `false` also shows new-grad and full-time roles. |
| `exclude_locations` | Drops listings located only in these places. Listings that also name a US site are kept. |
| `workday_search_terms` | What to search Workday and Jibe sites for. |

The keyword lists and weights live in `jobhunt/filters.py`. A listing needs
either a strong title term (RTL, ASIC, design verification, FPGA, digital design,
...) or HDL evidence in the description (Verilog, SystemVerilog, VHDL, UVM, ...).
Software, analog, layout, and board-level titles are excluded or penalized.

## Layout

```
config.toml              companies and filter settings
jobhunt/sources/         one parser per platform
jobhunt/filters.py       intern check, location filter, scoring
jobhunt/store.py         history: first seen, closed listings
docs/index.html          the dashboard (static, no build step)
docs/data/jobs.json      written by each scan
.github/workflows/       daily scheduled scan
tests/                   offline tests with sample responses for every platform
```
