#!/usr/bin/env python3
"""Build a target list of LOCAL operators near a listing — the third list source.

The other two sources only reach chains. A comparable VTS pipeline reaches tenants
who have done a deal with us; web research reaches brands with a corporate real
estate team. Neither finds the three-office dental group, the independent vet, the
local salon chain — and those are real retail tenants, often the right ones for an
inline space.

So this reads the operators actually trading near the site out of OpenStreetMap,
which is free, needs no key, and is the same source the proximity classifier uses.

What it deliberately does NOT do:

  * invent a contact. OSM sometimes carries a website or phone; it almost never
    carries a person or an address. Those rows come out blank and go through the
    normal contact cascade, exactly like a chain with no contact on file.
  * decide anything. A nearby operator might be a prospect (expanding, wants a
    better corner) or the reason the space is unleasable (already across the street).
    Distance and the barrier side are reported; the call is the broker's.

Coverage caveat worth saying out loud: OSM is volunteer-mapped. Dense urban retail
is well covered, a new strip centre may not be, and chains are mapped far better
than independents -- which is the opposite of what we want here. Treat the result
as a strong start on a canvass list, never as the whole market. A state licensing
roster (dental board, vet board, ABC) is the complete source where one exists.

Usage:
    python find_local_operators.py "<site address>" --uses dentist [--radius-mi 5]
    python find_local_operators.py "<addr>" --uses dentist --exclude-chains
    python find_local_operators.py "<addr>" --uses salon,fitness --csv out.csv
"""
import csv
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from use_tags import USE_TAGS, resolve as resolve_tags  # noqa: E402

UA = {"User-Agent": "listing-outreach/1.0 (CRE prospecting)"}
OVERPASS = "https://overpass-api.de/api/interpreter"
ARCGIS = ("https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/"
          "findAddressCandidates?f=json&outFields=Addr_type&maxLocations=5&singleLine=")

# A brand appearing many times in one metro is a chain, not a local operator. Cheap
# structural test, no brand list to maintain and it stays current by construction.
CHAIN_MIN_SITES = 3


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
        return r.read().decode()


def _post(url, data):
    """POST with backoff. Overpass is a free shared service and rate-limits (429) or
    reports itself busy (504) without warning; one bare attempt fails the whole run
    for no good reason."""
    last = None
    for attempt in range(4):
        req = urllib.request.Request(url, data=data.encode(), headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 502, 503, 504):
                sys.exit(f"Overpass returned {e.code}: "
                         f"{e.read()[:300].decode('utf-8', 'ignore')}")
            wait = 5 * (attempt + 1)
            print(f"  Overpass busy ({e.code}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError as e:
            last = e
            time.sleep(5 * (attempt + 1))
    sys.exit(f"Overpass unreachable after 4 tries: {last}")


def geocode(addr):
    """Rooftop only. A Census centerline point lands mid-street and skews every distance."""
    j = json.loads(_get(ARCGIS + urllib.parse.quote(addr)))
    for c in j.get("candidates", []):
        if c.get("attributes", {}).get("Addr_type") in ("PointAddress", "Subaddress"):
            return c["location"]["y"], c["location"]["x"]
    if j.get("candidates"):
        c = j["candidates"][0]
        print(f"  ! only a {c.get('attributes', {}).get('Addr_type')} match for the site "
              f"— distances are approximate", file=sys.stderr)
        return c["location"]["y"], c["location"]["x"]
    sys.exit(f"could not geocode {addr!r}")


def miles(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = (math.sin((la2 - la1) * p / 2) ** 2
         + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2)
    return 7917.5 * math.asin(min(1, math.sqrt(h)))


def tags_for(uses):
    try:
        return resolve_tags(uses)
    except KeyError as e:
        sys.exit(str(e).strip('"'))


def fetch(lat, lon, radius_mi, uses):
    tags = tags_for(uses)
    metres = int(radius_mi * 1609.34)
    parts = []
    for key, vals in tags.items():
        if vals:
            parts.append(f'nwr["{key}"~"^({"|".join(sorted(vals))})$"]'
                         f'(around:{metres},{lat},{lon});')
    if not parts:
        sys.exit("no OSM tags for those uses")
    # around: rather than a bbox -- a bbox corner is 1.4x the radius away, which drags
    # in operators from the next trade area and makes the list look padded.
    q = f'[out:json][timeout:120];({"".join(parts)});out center tags;'
    return json.loads(_post(OVERPASS, "data=" + urllib.parse.quote(q))).get("elements", [])


def norm_brand(name):
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(llc|inc|pc|pa|dds|dmd|dvm|md|the|of|and|at)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        sys.exit(__doc__)
    site = sys.argv[1]
    uses = [u.strip().lower() for u in arg("--uses", "dentist").split(",") if u.strip()]
    radius = float(arg("--radius-mi", "5"))
    drop_chains = "--exclude-chains" in sys.argv

    lat, lon = geocode(site)
    print(f"site: {site}  ({lat:.5f}, {lon:.5f})")
    print(f"looking for {', '.join(uses)} within {radius} mi ...")
    els = fetch(lat, lon, radius, uses)

    rows, brands = [], {}
    for el in els:
        t = el.get("tags", {})
        name = t.get("name")
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if not name or la is None:
            continue                      # an unnamed point is not a prospect
        key = norm_brand(name)
        brands[key] = brands.get(key, 0) + 1
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        rows.append({
            "name": name, "brand_key": key,
            "use": (t.get("amenity") or t.get("shop") or t.get("healthcare")
                    or t.get("leisure", "")),
            "address": addr, "city": t.get("addr:city", ""),
            "phone": t.get("phone") or t.get("contact:phone") or "",
            "website": t.get("website") or t.get("contact:website") or "",
            "miles": round(miles((lat, lon), (la, lo)), 2),
            "lat": la, "lon": lo,
        })

    for r in rows:
        r["sites_in_area"] = brands[r["brand_key"]]
        r["looks_like"] = "chain" if brands[r["brand_key"]] >= CHAIN_MIN_SITES else "local"
    if drop_chains:
        rows = [r for r in rows if r["looks_like"] == "local"]

    # Nearest first: proximity is the whole reason a local operator would look.
    rows.sort(key=lambda r: r["miles"])
    seen, deduped = set(), []
    for r in rows:
        if (r["brand_key"], r["address"]) in seen:
            continue
        seen.add((r["brand_key"], r["address"]))
        deduped.append(r)
    rows = deduped

    out = os.path.join(os.path.expanduser("~"), ".listing-outreach", "local_operators.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"site": site, "lat": lat, "lon": lon, "uses": uses,
               "radius_mi": radius, "operators": rows}, open(out, "w"), indent=1)

    local = sum(1 for r in rows if r["looks_like"] == "local")
    print(f"\n{len(rows)} operators  ({local} look local, {len(rows) - local} look like chains)")
    print(f"  with a phone:   {sum(1 for r in rows if r['phone'])}")
    print(f"  with a website: {sum(1 for r in rows if r['website'])}")
    print(f"\n  {'NAME':34} {'MI':>5}  {'TYPE':6} {'ADDRESS':26} PHONE")
    for r in rows[:25]:
        print(f"  {r['name'][:34]:34} {r['miles']:5.2f}  {r['looks_like']:6} "
              f"{r['address'][:26]:26} {r['phone']}")
    if len(rows) > 25:
        print(f"  ... {len(rows) - 25} more")
    print(f"\nwrote {out}")

    if "--csv" in sys.argv:
        dest = arg("--csv")
        with open(dest, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["name"])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {dest}")

    print("\nNo contacts here by design — OSM carries a business, not a person. These rows "
          "go through the contact cascade like any other target, and a state licensing "
          "roster is the complete source where one exists.")


if __name__ == "__main__":
    main()
