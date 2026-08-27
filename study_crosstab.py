"""Full cross-tabulation: age band x region, hexdb and adsbdb accuracy."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
STUDY_FILE = os.path.join(HERE, "route_study.json")
RAW_DIR = os.path.join(HERE, "route_study_raw")

import json, pathlib, time, collections

YEAR = 31557600
data = json.loads(pathlib.Path(STUDY_FILE)
                  .read_text(encoding="utf-8"))
now = time.time()

def ep(hx):
    if not hx or "-" not in hx:
        return None
    p = [x for x in hx.split("-") if x]
    return "%s-%s" % (p[0], p[-1])

NORDIC = {"Denmark", "Sweden", "Norway"}
WORLD = {"East Asia", "Oceania", "Latin America", "Southeast Asia",
         "Africa", "Middle East", "South Asia"}
rows = []
for cs, v in data.items():
    if not v.get("truth") or not v.get("hexdb_updatetime"):
        continue
    c = v.get("country")
    coh = v.get("cohort", "random")
    if c in NORDIC:
        region = "Nordics"
    elif c == "Canada":
        region = "Canada"
    elif c in WORLD:
        region = c
    elif coh == "random":
        region = "US"
    else:
        region = "Europe"
    rows.append(dict(cs=cs, region=region,
                     age=(now - v["hexdb_updatetime"]) / YEAR,
                     truth=v["truth"], adsbdb=v.get("adsbdb"), hexdb=ep(v.get("hexdb"))))

def pct(g, k):
    return 100 * sum(r[k] == r["truth"] for r in g) / len(g) if g else 0

ORDER = ("Nordics", "Europe", "Canada", "Oceania", "East Asia",
         "Southeast Asia", "Latin America", "US")
print("VERIFIED RECORDS: %d\n" % len(rows))
print("%-16s %4s %8s %8s %10s" % ("region", "n", "hexdb", "adsbdb", "median age"))
for reg in ORDER:
    g = [r for r in rows if r["region"] == reg]
    if not g:
        continue
    ages = sorted(r["age"] for r in g)
    print("%-14s %4d %7.0f%% %7.0f%% %9.2fy"
          % (reg, len(g), pct(g, "hexdb"), pct(g, "adsbdb"), ages[len(ages)//2]))

print("\n--- AGE BAND, ignoring region ---")
print("%-14s %4s %8s %8s" % ("age band", "n", "hexdb", "adsbdb"))
for lo, hi, lbl in ((0, 2, "< 2y"), (2, 4, "2-4y"), (4, 8, "4-8y"), (8, 99, "> 8y")):
    g = [r for r in rows if lo <= r["age"] < hi]
    if g:
        print("%-14s %4d %7.0f%% %7.0f%%" % (lbl, len(g), pct(g, "hexdb"), pct(g, "adsbdb")))

print("\n--- THE KEY TEST: OLD records (>=4y), by region ---")
for reg in ORDER:
    g = [r for r in rows if r["region"] == reg and r["age"] >= 4]
    if g:
        print("  %-16s n=%-3d hexdb %3.0f%%  adsbdb %3.0f%%"
              % (reg, len(g), pct(g, "hexdb"), pct(g, "adsbdb")))

print("\n--- and YOUNG records (<4y), by region ---")
for reg in ORDER:
    g = [r for r in rows if r["region"] == reg and r["age"] < 4]
    if g:
        print("  %-16s n=%-3d hexdb %3.0f%%  adsbdb %3.0f%%"
              % (reg, len(g), pct(g, "hexdb"), pct(g, "adsbdb")))

print("\n--- US vs EVERYWHERE ELSE ---")
us = [r for r in rows if r["region"] == "US"]
rest = [r for r in rows if r["region"] != "US"]
print("  US             n=%-3d hexdb %3.0f%%  adsbdb %3.0f%%"
      % (len(us), pct(us, "hexdb"), pct(us, "adsbdb")))
print("  everywhere else n=%-3d hexdb %3.0f%%  adsbdb %3.0f%%"
      % (len(rest), pct(rest, "hexdb"), pct(rest, "adsbdb")))
old_rest = [r for r in rest if r["age"] >= 4]
print("  non-US, OLD recs n=%-3d hexdb %3.0f%%  adsbdb %3.0f%%   <- age held constant"
      % (len(old_rest), pct(old_rest, "hexdb"), pct(old_rest, "adsbdb")))
