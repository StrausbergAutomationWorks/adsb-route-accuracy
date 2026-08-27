# adsbdb / hexdb.io route accuracy — measured

*Why is adsbdb returning the wrong origin and destination? Why does hexdb.io
have no route for my callsign? Is the route data stale?*

Short answer: **the error is overwhelmingly regional, not stale.** adsbdb is
27% correct on US domestic flights and 79% correct everywhere else. Record age
barely matters — Australian routes verify at 100% on database rows with a
median age of 11.5 years.

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
| passed the check | 8 | **75%** |
| rejected by the check | 22 | **9%** |

Roughly eight to one separation. It discards a correct route about 9% of the
time it fires — the price of turning a confident wrong answer into a blank.

See [`route_audit.py`](route_audit.py), which is standalone and runnable
against any location.

## Limitations, stated plainly

* **One day.** All sampling on 2026-08-27.
* **One ground-truth source** (aviationstack). Its own coverage may vary by
  region; that confound cannot be ruled out. A check confirmed mismatches were
  against *every* leg a flight number flew that day, not just the chosen one.
* **Small cells.** n=30 for the US, n=5–6 for several regions.
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

```
python study_collect.py  <lat> <lon> <radius_nm> <max>   # free
python study_verify.py   --spend N                        # uses your quota
python study_crosstab.py                                  # free
```

`study_verify.py` needs an aviationstack access key. It refuses to run without
an explicit `--spend N` so quota cannot be burned by accident, and it caches
every response, because a verification spent is gone for the month.

⚠ **Point the collector at a nearby airport, not your own coordinates.** Your
sampling centre ends up in your results.

## Licence

MIT for the code. The findings are measurements, freely usable. The underlying
route and flight-status data belongs to its respective providers.
