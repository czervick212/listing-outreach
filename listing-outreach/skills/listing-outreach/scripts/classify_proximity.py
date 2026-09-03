#!/usr/bin/env python3
"""Proximity / relocation classifier — Step 3+4 of the outreach flow.

For a tenant already operating near the listing, decide: too close (skip), or far enough / wrong
format (pitch a RELOCATION). The naive "within N miles -> cannibalization -> skip" rule is wrong
often enough to matter, because a barrier (an interstate, a river) — not raw mileage — is what
separates trade areas. It scripts the "which side of the interstate is their store on?" test.

    python classify_proximity.py "<site address>" --brands "Chipotle,Panera,Wendy's" \\
        [--barrier "I 270"] [--radius-mi 3]

What it does (stdlib only — ArcGIS + OpenStreetMap/Overpass, no API keys, cross-platform):
  1. Geocode the site to ROOFTOP (ArcGIS PointAddress — never Census centerline).
  2. If --barrier is given, pull that road's geometry from Overpass and work out which side the
     site is on (nearest-segment 2D cross-product sign — a latitude compare is wrong wherever the
     road runs diagonally, which it usually does).
  3. One bbox Overpass query for nearby food/retail/bank POIs (a regex-over-area name query
     times out — filter names client-side instead).
  4. For each requested brand found: distance, which side of the barrier, drive-through flag, and
     a SUGGESTED verdict. Advisory — the human makes the call on the Ruled out tab.

Writes ~/.listing-outreach/proximity.json for the sheet builder to read.
"""
import sys
import os
import json
import math
import urllib.parse
import urllib.request

if len(sys.argv) < 2 or "--brands" not in sys.argv:
    print(__doc__)
    raise SystemExit(1)


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


SITE = sys.argv[1]
BRANDS = [b.strip() for b in arg("--brands", "").split(",") if b.strip()]
BARRIER = arg("--barrier")
RADIUS_MI = float(arg("--radius-mi", "3"))
OUT = os.path.join(os.path.expanduser("~"), ".listing-outreach", "proximity.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

UA = {"User-Agent": "listing-outreach/1.0 (CRE prospecting)"}
OVERPASS = "https://overpass-api.de/api/interpreter"


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def _post(url, data):
    req = urllib.request.Request(url, data=data.encode(), headers=UA)
    return urllib.request.urlopen(req, timeout=90).read()


def geocode(addr):
    """Rooftop geocode via ArcGIS. Returns (lat, lon) or None."""
    q = urllib.parse.urlencode({"SingleLine": addr, "outFields": "Addr_type",
                                "maxLocations": 1, "f": "json"})
    j = json.loads(_get(f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/"
                         f"findAddressCandidates?{q}"))
    c = (j.get("candidates") or [None])[0]
    if not c:
        return None
    return c["location"]["y"], c["location"]["x"]


def miles(a, b):
    return math.hypot((a[1] - b[1]) * math.cos(math.radians(a[0])) * 69.0, (a[0] - b[0]) * 69.0)


def barrier_segments(ref, lat, lon, pad=0.15):
    """Fetch the barrier road's node geometry near the site."""
    bbox = f"{lat-pad},{lon-pad},{lat+pad},{lon+pad}"
    q = f'[out:json][timeout:60];way["ref"="{ref}"]["highway"~"motorway|trunk|primary"]({bbox});out geom;'
    j = json.loads(_post(OVERPASS, "data=" + urllib.parse.quote(q)))
    pts = sorted({(g["lat"], g["lon"]) for el in j.get("elements", [])
                  for g in (el.get("geometry") or [])})
    return pts


def side_sign(lat, lon, pts):
    """Nearest-segment cross-product sign; +/- = the two sides. None if no geometry."""
    if len(pts) < 2:
        return None
    best = None
    for i in range(len(pts) - 1):
        (y1, x1), (y2, x2) = pts[i], pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            continue
        t = max(0, min(1, ((lon - x1) * dx + (lat - y1) * dy) / (dx * dx + dy * dy)))
        px, py = x1 + t * dx, y1 + t * dy
        dist = math.hypot((lon - px) * math.cos(math.radians(lat)) * 69, (lat - py) * 69)
        cross = dx * (lat - y1) - dy * (lon - x1)
        if best is None or dist < best[0]:
            best = (dist, cross)
    return 1 if best[1] > 0 else -1


def nearby_pois(lat, lon, pad=0.06):
    bbox = f"{lat-pad},{lon-pad},{lat+pad},{lon+pad}"
    q = (f'[out:json][timeout:90];(nwr["amenity"~"^(fast_food|restaurant|cafe|bank)$"]({bbox}););'
         f'out center tags;')
    j = json.loads(_post(OVERPASS, "data=" + urllib.parse.quote(q)))
    out = []
    for el in j.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if name and la is not None:
            out.append({"name": name, "lat": la, "lon": lo,
                        "addr": f"{t.get('addr:housenumber','')} {t.get('addr:street','')}".strip(),
                        "drive_through": t.get("drive_through") or t.get("drive_in") or ""})
    return out


def normname(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


print(f"geocoding site: {SITE}")
site = geocode(SITE)
if not site:
    print("could not geocode the site address", file=sys.stderr)
    raise SystemExit(1)
print(f"  rooftop: {site[0]:.5f}, {site[1]:.5f}")

seg, site_sign = [], None
if BARRIER:
    print(f"fetching barrier geometry: {BARRIER}")
    seg = barrier_segments(BARRIER, *site)
    site_sign = side_sign(site[0], site[1], seg)
    print(f"  {len(seg)} barrier nodes; site is on side {site_sign}")

print("querying nearby POIs …")
pois = nearby_pois(*site)
print(f"  {len(pois)} food/retail/bank POIs in the box")

results = []
for brand in BRANDS:
    nb = normname(brand)
    hits = [p for p in pois if nb and nb in normname(p["name"])]
    if not hits:
        results.append({"brand": brand, "found": False,
                        "suggested_verdict": "no nearby store found — treat as a fresh submittal"})
        continue
    # nearest store of that brand
    hits.sort(key=lambda p: miles(site, (p["lat"], p["lon"])))
    p = hits[0]
    dist = round(miles(site, (p["lat"], p["lon"])), 2)
    same_side = None
    if site_sign is not None:
        same_side = (side_sign(p["lat"], p["lon"], seg) == site_sign)
    dt = str(p["drive_through"]).lower()
    dt_yes = dt in ("yes", "designated")
    dt_no = dt == "no"

    if same_side is False:
        verdict = f"RELO candidate — nearest store is across {BARRIER} ({dist} mi), a different trade area"
    elif dt_no:
        verdict = (f"RELO candidate — store is {dist} mi away with no drive-through; "
                   f"pitch a relocation into the pad's format")
    elif dt_yes and dist <= RADIUS_MI:
        verdict = f"SKIP — same side, {dist} mi away, already has a drive-through"
    elif dist <= RADIUS_MI:
        verdict = (f"VERIFY — same side, {dist} mi away, drive-through UNKNOWN in OSM; "
                   f"check the store: has drive-through -> skip, lacks one -> relo")
    else:
        verdict = f"OPEN — {dist} mi away, beyond the {RADIUS_MI} mi radius; judgment call"

    results.append({"brand": brand, "found": True, "nearest_addr": p["addr"],
                    "distance_mi": dist, "same_side_as_site": same_side,
                    "drive_through": p["drive_through"] or "unknown",
                    "suggested_verdict": verdict})

payload = {"site": SITE, "site_latlon": site, "barrier": BARRIER,
           "radius_mi": RADIUS_MI, "results": results}
json.dump(payload, open(OUT, "w"), indent=1)

print("\n{:<26} {:>7}  {:<10} {}".format("BRAND", "DIST", "SIDE", "SUGGESTED VERDICT"))
print("-" * 100)
for r in results:
    if not r["found"]:
        print(f"{r['brand']:<26} {'—':>7}  {'—':<10} {r['suggested_verdict']}")
    else:
        side = ("same" if r["same_side_as_site"] else "opposite") if r["same_side_as_site"] is not None else "n/a"
        print(f"{r['brand']:<26} {r['distance_mi']:>6} mi {side:<10} {r['suggested_verdict']}")
print(f"\nwrote {OUT} — verdicts are advisory; confirm on the Ruled out tab")
