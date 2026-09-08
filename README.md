# adsbdb / hexdb.io route accuracy — measured

*Why is adsbdb returning the wrong origin and destination? Why does hexdb.io
have no route for my callsign? Is the route data stale?*

Short answer: **the error is overwhelmingly regional, not stale.** adsbdb is
27% correct on US domestic flights and 79% correct everywhere else. Record age
barely matters — Australian routes verify at 100% on database rows with a
median age of 11.5 years.

**Update 2026-09-05: the US figure has been replicated at thirteen times the
sample size — 28.6% on 395 flights, by an independent method.** See
[Replication](#replication-us-286-on-395-flights) below.

---

**How accurate are free callsign→route lookups, and where do they fail?**

ADS-B broadcasts a callsign but no origin or destination. Integrations and
apps that want to show "this aircraft is flying Denver to Chicago" resolve the
callsign against a free database — usually [adsbdb](https://www.adsbdb.com) or
[hexdb.io](https://hexdb.io). Both are widely used and both are frequently
wrong.

This is a measurement of *how* wrong, and of where the error actually lives.

## Result

**It is not database staleness. It is which market the flight is in.**

82 routes verified against an independent third source, across nine regions:

| Region | n | hexdb correct | adsbdb correct | median hexdb record age |
|---|---|---|---|---|
| Oceania | 6 | **100%** | **100%** | **11.5 y** |
| Nordics | 15 | 93% | 87% | 1.3 y |
| Europe | 9 | 78% | 67% | 1.3 y |
| Canada | 11 | 73% | 73% | 2.4 y |
| SE Asia | 5 | 60% | 60% | 7.8 y |
| **United States** | **30** | **13%** | **27%** | 7.5 y |
| Latin America | 5 | 0% | 80% | 11.4 y |

**US 27%. Everywhere else 79%.**

With 95% intervals: US **14–44%** (n=30), everywhere else **66–88%** (n=52).
They do not overlap, so the split is not sampling noise. ⚠ **The individual
regional rows are a different matter** — four of the seven have n≤6, and
Oceania's 100% carries an interval of 61–100%. Those rows show where the
sample went, not what a region's true rate is.

## Why it is not age

The obvious hypothesis is that old records go stale. hexdb exposes an
`updatetime` per route, so it is testable. Holding record age constant and
varying region:

| Records ≥ 4 years old | n | hexdb | adsbdb |
|---|---|---|---|
| non-US | 22 | 55% | **82%** |
| US | 29 | 14% | **28%** |

Same age band, threefold gap. And **adsbdb exposes no record age at all**, yet
splits the same way — so the effect cannot be about database freshness.

Australia is the clearest single case: median record age **11.5 years**, older
than the US sample, and **100% correct on both sources**. A 14.5-year-old
record for QFA776 Perth–Melbourne is still right. A 14.9-year-old record for
CPA135 Hong Kong–Melbourne is still right. Those city pairs have not changed.

## The mechanism

*Inferred, not measured.* These databases key on **flight number**. Where a
number means a fixed city pair for a decade — Australia, East Asia, the Nordics
— every database is right at any age. Where numbers churn seasonally and are
reused across regional operators, every database is wrong at any age. The US
failures are heavy with regional carriers flying under mainline codes
(SkyWest, Endeavor, Envoy, Republic) plus mainline domestic.

## Replication: US 28.6% on 395 flights

The original US cell was **n=30**, sampled on a single day. It has since been
re-measured against a larger sample by a different method, and the result holds.

| | Original | Replication |
|---|---|---|
| date | 2026-08-27 | 2026-09-05 |
| n (US) | 30 | **395** |
| ground truth | aviationstack | filed FAA flight plans |
| **adsbdb correct** | **27%** | **28.6%** |

Full breakdown of the replication:

| | n | share |
|---|---|---|
| adsbdb returned a route | 395 | **98.8%** |
| exact match | 113 | **28.6%** |
| both ends wrong | 241 | **61.0%** |
| one end right | 35 | 8.9% |
| reversed (origin/destination swapped) | 6 | 1.5% |

**The pattern is high coverage and low accuracy.** adsbdb answers almost every
callsign and is wrong about two thirds of them, and the failures are not near
misses. `SWA938` returns `KMDW-KBOS` where the flight plan says `KBWI-KDEN`.
`DAL2768` returns `KOAK-KSLC` against `KSEA-PANC`. Those are different flights,
not stale variants of the same one.

By operation type:

| Category | n | correct |
|---|---|---|
| Commercial | 364 | 29.1% |
| **On-demand / air taxi** | 25 | **8.0%** |
| Cargo | 6 | 83.3% ⚠ n=6 |

On-demand charter is the worst-served category by a wide margin — those
callsigns are not published schedules and no curated database has them.

### Method

Flight plans filed with the FAA are available free through the
[SWIM Cloud Distribution Service](https://www.faa.gov/air_traffic/technology/swim),
which publishes the TFMS R14 Flight Data feed. Each message carries the
departure and arrival airport and, on most, the filed lateral trajectory.

1. Collect flight plans continuously and aggregate by callsign.
2. Keep only routes whose **filed trajectory corroborates the filed endpoints**
   — first and last trajectory point each within 25 km of the stated airports.
3. Query adsbdb for the same callsign and compare.

Step 2 is the arbiter. Measured across 4,000 routes, the filed trajectory
agrees with the filed endpoints **99.88%** of the time, which is what makes it
usable as a check.

### ⚠ What this does not establish

**The trajectory is not independent ground truth.** It establishes that the
flight plan is internally consistent — the filed path agrees with the filed
endpoints. It cannot detect a plan filed correctly and then flown somewhere
else, and where no flight plan exists adsbdb cannot be judged at all. That is
weaker evidence than the aviationstack verification used in the original study,
and it is why this is presented as a replication of one cell rather than a
replacement for the whole table.

**It is a US number.** The FAA feed covers US airspace, so this sample is US-
heavy by construction. 28.6% is comparable to the **27% US** figure above, and
**not** to the 79% measured everywhere else. Quoting it as a global accuracy
rate would misrepresent both measurements.

**Four routes were excluded.** All four Cathay Pacific flights through Hong
Kong showed an identical 29 km offset between the trajectory endpoint and the
airport — a systematic error in one airport record rather than four bad routes,
but it would distort the arbiter.

## Three distinct failure modes

1. **Records exist and are wrong** — the US. No source-switching helps; both
   sources fail on the same flights.
2. **Records exist and are right** — Australia, East Asia, the Nordics,
   regardless of record age.
3. **Records are absent** — Timor-Leste (0 of 12 in hexdb), South Asia (16 of
   22 callsigns with no hexdb record). Not wrong, missing. Nothing to fall
   back to.

Latin America is its own oddity: hexdb 0/5, adsbdb 4/5, Brazilian domestic.

## What actually helps

A **geometric plausibility check** — reject a route the aircraft's own position
contradicts. No API key, no account, no regional assumption. Measured against
verified truth:

| adsbdb answers | n | actually correct |
|---|---|---|
| passed the check | 25 | **72%** |
| rejected by the check | 18 | **11%** |

Roughly seven to one separation. It discards a correct route about 11% of the
time it fires — the price of turning a confident wrong answer into a blank.

*Corrected 2026-09-07.* This table first read 8 / 22 at 75% and 9%. Those
figures came from a flag stored during collection, which was only computed for
one 60-record cohort rather than for every verified row. Recomputing the check
over all 43 verified rows that carry coordinates gives the numbers above. The
separation and the conclusion are unchanged; the sample is larger and the
population is now stated.

Restricted to US flights alone, where the underlying route data is worst, the
check separates 7 kept at 71% from 16 rejected at 12%.

### Tested on data it was never tuned against

The figures above have an obvious weakness: the check was designed and scored
on the same 82 flights. A rule evaluated on the data that shaped it flatters
itself.

So it was re-scored against the 395 replication flights, which it had never
seen, using filed flight plans as the arbiter:

| | passed the check | rejected | separation |
|---|---|---|---|
| designed-against, n=43 | 72% | 11% | 6.5 : 1 |
| **unseen, n=395** | **59%** | **7%** | **8.4 : 1** |

95% intervals on the unseen data are 51–66% and 4–11%, which do not approach
each other. **The separation is not an artefact of tuning.**

The absolute rates differ for two reasons worth stating. The arbiter is
weaker — agreement with a filed plan rather than with a verified flight. And
the aircraft position used is the midpoint of the filed trajectory, which is by
construction far from both airports, so the rule that accepts anything within
150 km of either end almost never fires. That biases the unseen test toward
rejection: 58% of flights were rejected there against 42% in the original.

See [`route_audit.py`](route_audit.py), which is standalone and runnable
against any location.

## Limitations, stated plainly

* ⚠ **The sample is stratified, not random.** Flights were drawn in cohorts
  chosen to test specific ideas — a 30-flight random pull, then deliberate
  cohorts for Canada, Sweden, Norway, Denmark, Oceania, Latin America, East and
  Southeast Asia, plus `old_eu` and `young` cohorts selected on record age. So
  **"79% everywhere else" is an average over regions that were picked, not an
  estimate of global accuracy.** The US–non-US contrast is the finding; the
  aggregate is not a population figure.
* **One day** for the regional table — all sampling on 2026-08-27. The US
  replication was sampled separately on 2026-09-05.
* **One ground-truth source** for the regional table (aviationstack). Its own
  coverage may vary by region; that confound cannot be ruled out. A check
  confirmed mismatches were against *every* leg a flight number flew that day,
  not just the chosen one. The replication used a **different** source — filed
  FAA flight plans — which is why it is evidence rather than repetition.
* **Small cells.** n=5–6 for several regions. ⚠ The US cell was n=30 and is
  now separately supported at n=395; **the non-US cells have not been
  replicated and remain small.** The 79% figure rests on 52 flights.
* ⚠ **The two measurements are not the same test.** aviationstack verifies
  against what was *flown*; the replication verifies against what was *filed*.
  They agree here, which is informative, but they are not interchangeable.
* **A rate is not a quality score.** Discard rates below are counts, not
  verdicts on whether discarding was right.
* **Per-flight records are not published — see below.** Nobody can check the
  arithmetic; they can only re-run the method. That is a real weakness and the
  honest cost of the licensing position.

## Why the raw data is not here

Ground truth came from aviationstack under a **personal-tier licence**, and
adsbdb's route data carries a restriction on copying or republication. A table
of per-flight answers would redistribute two restricted datasets at once.

Published here: **the method, the scripts, and aggregate statistics** — which
are measurements over that data rather than the data itself. Withheld: raw API
responses and per-flight rows.

## Reproducing

The regional table:

```
python study_collect.py  <lat> <lon> <radius_nm> <max>   # free
python study_verify.py   --spend N                        # uses your quota
python study_crosstab.py                                  # free
```

The US replication, which spends no quota but needs your own FAA SWIM
subscription and a route table built from it:

```
python compare_against_filed_plans.py --db routes.db --airports airports.csv
```

`study_verify.py` needs an aviationstack access key. It refuses to run without
an explicit `--spend N` so quota cannot be burned by accident, and it caches
every response, because a verification spent is gone for the month.

⚠ **Point the collector at a nearby airport, not your own coordinates.** Your
sampling centre ends up in your results.

## Licence

MIT for the code. The findings are measurements, freely usable. The underlying
route and flight-status data belongs to its respective providers.
