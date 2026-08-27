"""Phase 1: COLLECT. Spends no aviationstack quota.

    python study_collect.py <lat> <lon> <radius_nm> <max_records>
    e.g. python study_collect.py 51.4700 -0.4543 200 30

Samples airline callsigns from the live feed WITHOUT reference to whether
adsbdb succeeded - the selection bias that made the first three cases
unusable. Records adsbdb's answer, hexdb's answer, and hexdb's updatetime.

Writes/updates route_study.json beside this script. Re-runnable: new
callsigns are appended, existing ones left alone, so several passes at
different times of day build the sample without re-spending anything.
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
STUDY_FILE = os.path.join(HERE, "route_study.json")
RAW_DIR = os.path.join(HERE, "route_study_raw")

import json, os, pathlib, sys, time, urllib.error, urllib.parse, urllib.request

AUD = os.path.join(HERE, "route_audit.py")
import importlib.util
spec = importlib.util.spec_from_file_location("ra", AUD)
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)

STORE = pathlib.Path(STUDY_FILE)
UA = {"User-Agent": "route-age-study/1.0", "Accept": "application/json"}
_airports = {}


def get(url, t=40):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def hexdb(cs):
    st, b = get("https://hexdb.io/api/v1/route/icao/" + cs)
    if st != 200:
        return None, None
    try:
        d = json.loads(b)
    except Exception:
        return None, None
    r = d.get("route")
    return (r if isinstance(r, str) else None), d.get("updatetime")


def load():
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save(data):
    STORE.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def main():
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    nm = int(sys.argv[3]) if len(sys.argv) > 3 else 250
    cap = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    data = load()
    print("existing records: %d" % len(data))

    ac = ra.live_aircraft("adsb.fi", lat, lon, nm)
    print("feed returned %d aircraft (%.3f,%.3f r=%dnm)" % (len(ac), lat, lon, nm))

    added = 0
    for a in ac:
        cs = (a.get("flight") or "").strip().upper()
        aclat, aclon, alt = a.get("lat"), a.get("lon"), a.get("alt_baro")
        if not cs or aclat is None or not ra.is_airline_callsign(cs):
            continue
        if cs in data:
            continue

        adb = ra.lookup_route(cs)
        time.sleep(0.35)
        hx, ut = hexdb(cs)
        time.sleep(0.35)

        # NOTE: geometry verdict is RECORDED but NOT used to decide inclusion.
        # Selecting on it is exactly the bias this study exists to avoid.
        geom = None
        if adb:
            alt_ft = alt if isinstance(alt, (int, float)) else None
            geom = ra.contradiction(adb, aclat, aclon, alt_ft)

        data[cs] = {
            "collected": int(time.time()),
            "lat": aclat, "lon": aclon, "alt_ft": alt if isinstance(alt, (int, float)) else None,
            "adsbdb": adb["label"] if adb else None,
            "adsbdb_geometry_rejected": bool(geom),
            "adsbdb_reason": geom,
            "hexdb": hx,
            "hexdb_updatetime": ut,
            "truth": None,          # filled by phase 2
            "truth_source": None,
        }
        added += 1
        save(data)
        print("  +%-9s adsbdb=%-11s hexdb=%-16s age=%s" % (
            cs, data[cs]["adsbdb"] or "-", hx or "-",
            "?" if not ut else "%.1fy" % ((time.time() - ut) / 31557600)))
        if added >= cap:
            break

    both = sum(1 for v in data.values() if v["adsbdb"] and v["hexdb"])
    aged = sum(1 for v in data.values() if v["hexdb_updatetime"])
    unver = sum(1 for v in data.values() if v["truth"] is None)
    print("\nadded %d. total %d records." % (added, len(data)))
    print("  with BOTH sources : %d" % both)
    print("  with hexdb age    : %d   <- these are the study population" % aged)
    print("  awaiting truth    : %d" % unver)
    print("\nNo aviationstack quota spent. Run study_verify.py to spend it.")


if __name__ == "__main__":
    main()
