#!/usr/bin/env python3
"""route_audit.py - measure how often a callsign->route lookup disagrees with
where the aircraft actually is.

Takes live ADS-B positions from a free community feed, looks up each airline
callsign against adsbdb, and flags routes that the aircraft's own position
contradicts. Prints a rate and the offending rows.

    python3 route_audit.py --lat 51.4700 --lon -0.4543 --radius 100

Standard library only. No API keys. No account. Python 3.9+.

The check is geometric, not a second data source: given an origin, a
destination and where the aircraft is right now, some routes are simply not
possible. It answers "is this route contradicted?", never "is this route
correct" - a stale route that happens to look plausible will pass.

MIT licence. Written for https://github.com/mrjackwills/adsbdb issue
discussion; reuse freely.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "route-audit/1.0 (+https://github.com/mrjackwills/adsbdb)"

# Free, no-key position feeds. Response shapes differ slightly; both handled.
FEEDS = {
    "adsb.fi": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}",
    "adsb.lol": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}",
}
ADSBDB = "https://api.adsbdb.com/v0/callsign/"

EARTH_KM = 6371.0088

# --- tuning ---------------------------------------------------------------
# Empirical. See the "Limits" section at the bottom of this file: these cannot
# be tuned honestly without verified routes to tune against.
TERMINAL_RANGE_KM = 150.0   # within this of either endpoint, accept
MIN_CROSS_TRACK_KM = 150.0  # floor on allowed distance from the great circle
CROSS_TRACK_FRACTION = 0.06  # ...or this share of leg length, whichever larger
TERMINAL_ALT_FT = 10000     # below this AND far from both ends -> reject
PAST_END_FACTOR = 1.25      # beyond this multiple of leg length -> reject


# --- geometry -------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlam)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def cross_track_km(o_lat, o_lon, d_lat, d_lon, lat, lon):
    """Perpendicular distance from the aircraft to the origin->destination
    great circle."""
    d13 = haversine_km(o_lat, o_lon, lat, lon) / EARTH_KM
    t13 = math.radians(bearing_deg(o_lat, o_lon, lat, lon))
    t12 = math.radians(bearing_deg(o_lat, o_lon, d_lat, d_lon))
    return abs(math.asin(math.sin(d13) * math.sin(t13 - t12)) * EARTH_KM)


def contradiction(route, lat, lon, altitude_ft=None):
    """Return a short reason string if the position contradicts the route,
    or None if the route survives. Unprovable is NOT contradicted."""
    o_lat, o_lon = route["origin_lat"], route["origin_lon"]
    d_lat, d_lon = route["dest_lat"], route["dest_lon"]
    if None in (o_lat, o_lon, d_lat, d_lon):
        return None

    leg = haversine_km(o_lat, o_lon, d_lat, d_lon)
    if leg < 1.0:                       # origin == destination, nothing to test
        return None

    to_origin = haversine_km(lat, lon, o_lat, o_lon)
    to_dest = haversine_km(lat, lon, d_lat, d_lon)

    # Rule 0 MUST come first. Arrivals get vectored onto downwind legs and into
    # holds; departures turn out before turning on course. Cross-track distance
    # is meaningless near an airport, so anything close to either end is
    # accepted without further question. Checking this later would reject
    # perfectly good arrivals.
    if min(to_origin, to_dest) <= TERMINAL_RANGE_KM:
        return None

    limit = max(MIN_CROSS_TRACK_KM, leg * CROSS_TRACK_FRACTION)
    xtk = cross_track_km(o_lat, o_lon, d_lat, d_lon, lat, lon)
    if xtk > limit:
        return "%.0fkm off track (limit %.0f)" % (xtk, limit)

    # On the great circle is not enough: its extension runs round the planet.
    if to_origin > leg * PAST_END_FACTOR or to_dest > leg * PAST_END_FACTOR:
        return "past an endpoint (leg %.0fkm, to_o %.0f, to_d %.0f)" % (
            leg, to_origin, to_dest)

    # Low means near an airport - but rule 0 established neither end is close.
    if altitude_ft is not None and altitude_ft < TERMINAL_ALT_FT:
        return "%.0fft but %.0fkm from nearest endpoint" % (
            altitude_ft, min(to_origin, to_dest))

    return None


# --- fetching -------------------------------------------------------------

def fetch_json(url, timeout=45):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def live_aircraft(feed, lat, lon, nm):
    url = FEEDS[feed].format(lat="%.4f" % lat, lon="%.4f" % lon, nm=int(nm))
    status, data = fetch_json(url)
    if status != 200 or not data:
        raise SystemExit("%s returned HTTP %s" % (feed, status))
    return data.get("aircraft") or data.get("ac") or []


def is_airline_callsign(cs):
    """Three-letter ICAO operator + digits. Registrations (N12345, G-ABCD)
    have no route in any source, so including them measures GA coverage
    rather than route accuracy."""
    return len(cs) >= 4 and cs[:3].isalpha() and cs[3:].isdigit()


def lookup_route(callsign):
    status, data = fetch_json(ADSBDB + urllib.parse.quote(callsign))
    if status != 200 or not data:
        return None
    try:
        fr = data["response"]["flightroute"]
        o, d = fr["origin"], fr["destination"]
        return {
            "origin_lat": o["latitude"], "origin_lon": o["longitude"],
            "dest_lat": d["latitude"], "dest_lon": d["longitude"],
            "label": "%s-%s" % (o.get("icao_code"), d.get("icao_code")),
        }
    except (KeyError, TypeError):
        return None


# --- main -----------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Measure how often adsbdb routes are contradicted by the "
                    "aircraft's own position.")
    p.add_argument("--lat", type=float, required=True, help="centre latitude")
    p.add_argument("--lon", type=float, required=True, help="centre longitude")
    p.add_argument("--radius", type=float, default=100,
                   help="nautical miles (default 100)")
    p.add_argument("--limit", type=int, default=40,
                   help="max callsigns to look up (default 40). Keep modest: "
                        "every one is a request to a free service.")
    p.add_argument("--feed", choices=sorted(FEEDS), default="adsb.fi")
    p.add_argument("--delay", type=float, default=0.4,
                   help="seconds between lookups (default 0.4)")
    p.add_argument("--json", metavar="FILE", help="also write raw rows here")
    args = p.parse_args(argv)

    aircraft = live_aircraft(args.feed, args.lat, args.lon, args.radius)
    print("%s returned %d aircraft within %.0f nm of %.4f,%.4f"
          % (args.feed, len(aircraft), args.radius, args.lat, args.lon))

    rows, seen, no_route = [], set(), 0
    for ac in aircraft:
        cs = (ac.get("flight") or "").strip().upper()
        lat, lon = ac.get("lat"), ac.get("lon")
        alt = ac.get("alt_baro")
        if not cs or lat is None or lon is None or cs in seen:
            continue
        if not is_airline_callsign(cs):
            continue
        seen.add(cs)

        route = lookup_route(cs)
        time.sleep(args.delay)
        if route is None:
            no_route += 1
        else:
            alt_ft = alt if isinstance(alt, (int, float)) else None
            rows.append((cs, route["label"],
                         contradiction(route, lat, lon, alt_ft)))
        if len(rows) >= args.limit:
            break

    if not rows:
        print("No airline callsigns with routes in this sample. Try a larger "
              "radius, or a busier time of day.")
        return 1

    bad = [r for r in rows if r[2]]
    print("\nroutes checked      : %d" % len(rows))
    print("no route returned   : %d (not counted above)" % no_route)
    print("contradicted        : %d  (%.0f%%)" % (len(bad), 100 * len(bad) / len(rows)))

    if bad:
        print("\ncontradicted routes:")
        for cs, label, why in bad:
            print("   %-9s %-11s %s" % (cs, label, why))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([{"callsign": c, "route": l, "contradiction": w}
                       for c, l, w in rows], fh, indent=1)
        print("\nwrote %s" % args.json)

    print("""
Limits, stated plainly:
  * A contradiction rate is a RATE, not a quality score. Rejecting more is not
    self-evidently better - without verified routes it cannot be told apart
    from over-rejection. The constants at the top of this file are empirical
    and were deliberately NOT tuned for that reason.
  * Only geometrically impossible routes are caught. A stale route that happens
    to look plausible passes.
  * The rate depends heavily on the sample. Near a busy airport most aircraft
    are close to an endpoint, rule 0 fires, and the rate reads low. Sampled far
    from airports it reads much higher. Always quote the radius beside it.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
