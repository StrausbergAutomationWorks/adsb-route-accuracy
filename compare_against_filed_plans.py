#!/usr/bin/env python3
"""Compare adsbdb's callsign->route answers against filed FAA flight plans.

This is the replication described in the README: US 28.6% on 395 flights.

WHAT YOU NEED
-------------
A route table built from the FAA's TFMS R14 Flight Data feed, available free
through the SWIM Cloud Distribution Service:

    https://www.faa.gov/air_traffic/technology/swim

Registration is free but not instant. The feed is JMS over Solace; the FAA
publishes a Jumpstart Kit that consumes it. Aggregate the messages by callsign
into a SQLite table with this shape:

    routes(acid, dep, arr, observations, user_category, trajectory, traj_points)

where `trajectory` is "lat,lon,elapsed;lat,lon,elapsed;..." taken from the
filed lateral path, and `dep`/`arr` are ICAO identifiers.

You also need an airport table mapping identifier -> lat/lon. OurAirports is
public domain and sufficient:

    https://davidmegginson.github.io/ourairports-data/airports.csv

THE ARBITER, AND ITS LIMIT
--------------------------
Only routes whose filed TRAJECTORY corroborates their filed ENDPOINTS are
compared - first and last point each within TOLERANCE_KM of the stated
airport. Measured across 4,000 routes, that holds 99.88% of the time.

This is NOT independent ground truth. It establishes that a flight plan is
internally consistent. It cannot detect a plan filed correctly and then flown
elsewhere, and where no plan exists adsbdb cannot be judged at all.

It is also a US measurement: the feed covers US airspace, so the sample is
US-heavy by construction. Do not quote the result as a global rate.
"""
import argparse
import json
import math
import random
import sqlite3
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "adsb-route-accuracy/1.0", "Accept": "application/json"}
TOLERANCE_KM = 25.0
# Airports whose coordinates disagree systematically with filed trajectories.
# VHHH showed an identical 29 km offset on every route through it.
EXCLUDE_AIRPORTS = {"VHHH"}


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def load_airports(path):
    """OurAirports CSV -> {ident: (lat, lon)}."""
    import csv
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            ident = (row.get("ident") or "").strip().upper()
            try:
                out[ident] = (float(row["latitude_deg"]),
                              float(row["longitude_deg"]))
            except (TypeError, ValueError, KeyError):
                continue
    return out


def corroborated(db, airports, limit, min_obs):
    """Routes whose filed trajectory agrees with their filed endpoints."""
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    rows = con.execute(
        """SELECT acid, dep, arr, trajectory, observations, user_category
           FROM routes
           WHERE traj_points > 2
             AND acid GLOB '[A-Z][A-Z][A-Z]*' AND acid NOT GLOB 'N[0-9]*'
             AND observations >= ?
           ORDER BY observations DESC LIMIT ?""", (min_obs, limit)).fetchall()
    con.close()

    keep = []
    for acid, dep, arr, traj, obs, cat in rows:
        if dep in EXCLUDE_AIRPORTS or arr in EXCLUDE_AIRPORTS:
            continue
        if dep == arr or dep not in airports or arr not in airports:
            continue
        pts = traj.split(";")
        try:
            fa, fo = (float(x) for x in pts[0].split(",")[:2])
            la, lo = (float(x) for x in pts[-1].split(",")[:2])
        except (ValueError, IndexError):
            continue
        if haversine_km(fa, fo, *airports[dep]) <= TOLERANCE_KM and \
           haversine_km(la, lo, *airports[arr]) <= TOLERANCE_KM:
            keep.append((acid, dep, arr, obs, cat))
    return keep, len(rows)


def ask_adsbdb(callsign):
    try:
        req = urllib.request.Request(
            "https://api.adsbdb.com/v0/callsign/" + callsign, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        fr = (d.get("response") or {}).get("flightroute")
        if isinstance(fr, dict):
            return ((fr.get("origin") or {}).get("icao_code"),
                    (fr.get("destination") or {}).get("icao_code"), "ok")
        return None, None, "no route"
    except urllib.error.HTTPError as e:
        return None, None, "HTTP %s" % e.code
    except Exception as ex:                                  # noqa: BLE001
        return None, None, type(ex).__name__


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="SQLite route table")
    ap.add_argument("--airports", required=True, help="OurAirports CSV")
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--min-obs", type=int, default=3,
                    help="ignore routes seen fewer times than this")
    ap.add_argument("--pool", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=38)
    ap.add_argument("--out", default="comparison.json")
    args = ap.parse_args()

    airports = load_airports(args.airports)
    pool, considered = corroborated(args.db, airports, args.pool, args.min_obs)
    print("considered %d routes, %d corroborated by their own trajectory (%.1f%%)"
          % (considered, len(pool), 100 * len(pool) / max(considered, 1)))

    random.seed(args.seed)
    sample = random.sample(pool, min(args.sample, len(pool)))
    print("comparing %d\n" % len(sample))

    results = []
    for i, (acid, dep, arr, obs, cat) in enumerate(sample, 1):
        a_dep, a_arr, status = ask_adsbdb(acid)
        results.append({"callsign": acid, "filed_dep": dep, "filed_arr": arr,
                        "observations": obs, "category": cat,
                        "adsbdb_dep": a_dep, "adsbdb_arr": a_arr,
                        "status": status})
        if i % 10 == 0:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=1)
        if i % 50 == 0:
            print("   %d/%d" % (i, len(sample)))
        time.sleep(0.25)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)

    ok = [r for r in results if r["status"] == "ok" and r["adsbdb_dep"]
          and r["adsbdb_arr"]]
    exact = sum(1 for r in ok
                if (r["adsbdb_dep"], r["adsbdb_arr"])
                == (r["filed_dep"], r["filed_arr"]))
    rev = sum(1 for r in ok
              if (r["adsbdb_arr"], r["adsbdb_dep"])
              == (r["filed_dep"], r["filed_arr"]))
    part = sum(1 for r in ok
               if r["adsbdb_dep"] == r["filed_dep"]
               or r["adsbdb_arr"] == r["filed_arr"]) - exact

    n = len(ok)
    print("\nsampled %d, adsbdb answered %d (%.1f%%)"
          % (len(results), n, 100 * n / max(len(results), 1)))
    print("   exact match   %4d  %5.1f%%" % (exact, 100 * exact / max(n, 1)))
    print("   reversed      %4d  %5.1f%%" % (rev, 100 * rev / max(n, 1)))
    print("   one end right %4d  %5.1f%%" % (part, 100 * part / max(n, 1)))
    print("   both wrong    %4d  %5.1f%%"
          % (n - exact - rev - part, 100 * (n - exact - rev - part) / max(n, 1)))
    print("\nwrote %s" % args.out)
    print("\nThis is a US measurement and the arbiter is the filed plan, not "
          "the flown route.\nSee the README before quoting it.")


if __name__ == "__main__":
    main()
