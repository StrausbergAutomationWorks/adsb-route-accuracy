"""Phase 2 of the route-age study: VERIFY. SPENDS aviationstack quota.

One call per callsign, no bulk. Refuses to run without --spend N so quota
cannot be burned by accident. Caches every response; a verification spent is
gone for the month.

Selection is STRATIFIED BY hexdb RECORD AGE, never by whether a source looked
right. Stratifying on the predictor is legitimate; selecting on the outcome is
not.
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
STUDY_FILE = os.path.join(HERE, "route_study.json")
RAW_DIR = os.path.join(HERE, "route_study_raw")

import argparse, json, pathlib, sys, time, urllib.error, urllib.parse, urllib.request


def get_key():
    """Access key from AVIATIONSTACK_KEY, or a file named aviationstack.key
    beside this script. Never hardcode it; never commit the file."""
    key = os.environ.get("AVIATIONSTACK_KEY", "").strip()
    if key:
        return key
    p = os.path.join(HERE, "aviationstack.key")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return fh.read().strip()
    raise SystemExit(
        "No API key. Set AVIATIONSTACK_KEY, or create aviationstack.key "
        "beside this script. Free tier: 100 requests/month.")


def redact(text):
    """Strip the key from anything before it is printed."""
    try:
        k = get_key()
    except SystemExit:
        return text
    return text.replace(k, "***REDACTED***") if k else text

STORE = pathlib.Path(STUDY_FILE)
RAW = pathlib.Path(RAW_DIR)
BASE = "https://api.apilayer.net/aviationstack/v1/flights"
YEAR = 31557600


def load():
    if not STORE.exists():
        raise SystemExit(
            "No route_study.json yet. Run study_collect.py first, e.g.\n"
            "    python study_collect.py 51.4700 -0.4543 200 30")
    return json.loads(STORE.read_text(encoding="utf-8"))


def save(d):
    STORE.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")


def verify(callsign):
    """One aviationstack call. Returns (icao_route, note) or (None, note)."""
    url = BASE + "?" + urllib.parse.urlencode(
        {"access_key": get_key(),
         "flight_icao": callsign, "limit": 10})
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as ex:
        return None, redact(repr(ex))[:80]

    RAW.mkdir(exist_ok=True)
    (RAW / (callsign + ".json")).write_text(body, encoding="utf-8")

    try:
        rows = json.loads(body).get("data") or []
    except Exception:
        return None, "unparsable"
    if not rows:
        return None, "no data"

    # Prefer the row whose own flight ICAO matches; a codeshare partner's row
    # describes the same aircraft but under a different number.
    exact = [r for r in rows if ((r.get("flight") or {}).get("icao") or "").upper() == callsign]
    chosen, note = (exact[0], "exact") if exact else (rows[0], "codeshare:%s" % (
        (rows[0].get("flight") or {}).get("icao")))
    dep = (chosen.get("departure") or {}).get("icao")
    arr = (chosen.get("arrival") or {}).get("icao")
    if not dep or not arr:
        return None, note + "/no-icao"
    return "%s-%s" % (dep, arr), "%s %s" % (note, chosen.get("flight_date"))


def pick(data, n):
    """Stratify by hexdb record age so the sample spans the predictor."""
    pool = [(cs, v) for cs, v in data.items()
            if v.get("hexdb") and v.get("hexdb_updatetime") and v.get("truth") is None]
    if not pool:
        return []
    now = time.time()
    for cs, v in pool:
        v["_age"] = (now - v["hexdb_updatetime"]) / YEAR
    pool.sort(key=lambda kv: kv[1]["_age"])
    if n >= len(pool):
        return [cs for cs, _ in pool]
    step = len(pool) / n
    return [pool[int(i * step)][0] for i in range(n)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spend", type=int, required=True,
                   help="MAX aviationstack calls to make. Required on purpose.")
    p.add_argument("--delay", type=float, default=1.5)
    args = p.parse_args()

    data = load()
    todo = pick(data, args.spend)
    if not todo:
        print("Nothing to verify. Run study_collect.py for more records.")
        return
    print("will spend up to %d calls on: %s\n" % (len(todo), ", ".join(todo)))

    spent = 0
    for cs in todo:
        truth, note = verify(cs)
        spent += 1
        v = data[cs]
        v.pop("_age", None)
        v["truth"] = truth
        v["truth_source"] = "aviationstack:" + note
        save(data)
        age = (time.time() - v["hexdb_updatetime"]) / YEAR
        hx_ep = None
        if v["hexdb"] and "-" in v["hexdb"]:
            parts = [x for x in v["hexdb"].split("-") if x]
            hx_ep = "%s-%s" % (parts[0], parts[-1])
        mark = "?" if not truth else (
            "hexdb OK " if hx_ep == truth else
            ("adsbdb OK" if v["adsbdb"] == truth else "both wrong"))
        print("  %-9s age %4.1fy  truth=%-11s adsbdb=%-11s hexdb=%-11s %-10s (%s)"
              % (cs, age, truth or "-", v["adsbdb"] or "-", hx_ep or "-", mark, note))
        time.sleep(args.delay)

    print("\ncalls spent this run: %d" % spent)
    ver = sum(1 for v in data.values() if v.get("truth"))
    print("verified records now: %d of %d" % (ver, len(data)))


if __name__ == "__main__":
    main()
