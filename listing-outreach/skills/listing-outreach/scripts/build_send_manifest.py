#!/usr/bin/env python3
"""Freeze the join table that makes reply-attribution EXACT instead of probabilistic.

Why this exists: outreach emails are consolidated per broker, so one message can cover
several tenants ("no for three, yes for one"). A reply therefore has to be split back
out per tenant, and each tenant routed to its own VTS deal.

The general attribution engine (data/deal-index.json) resolves 89% of addresses to one
property — but the ambiguous 11% are exactly the brokers we send to most
(jmekulski@klnb.com spans 3 properties, pomeara@rappaportco.com spans 6). For mail WE
sent, we don't need to guess: (recipient + subject) is a deterministic key back to the
exact tenant set, as long as we record it at send time. That's what this writes.

    python3 build_send_manifest.py <targets.xlsx> <vts_property_id|0> "<Listing Name>"
        [--receipts] [--followup "<nudge 1>"] [--followup2 "<nudge 2>"] [--cadence 3,10]
        [--flyer <flyer.pdf>]

It also writes this blast's own log, ~/.listing-outreach/blasts/<listing>.json, which is
what follow-ups run from (followups.py). The follow-up messages are written once for the
whole blast and may use {first_name} {tenant} {listing}. --receipts records that the
drafts asked for read receipts (pass the same flag to make_drafts.py). Re-running for the
same listing keeps every recipient's tracking — sent, read, replied, nudges — intact.
"""
import json, sys, datetime, os, openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib"))
import lo_blasts  # noqa: E402

pos = [a for i, a in enumerate(sys.argv[1:], 1)
       if not a.startswith("--") and not sys.argv[i - 1] in ("--followup", "--followup2", "--cadence", "--flyer")]
if len(pos) < 3:
    print(__doc__)
    raise SystemExit(1)
SHEET, PROP, LISTING = pos[0], int(pos[1]), pos[2]


def opt(flag):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


OUT = lo_blasts.LEGACY
os.makedirs(os.path.dirname(OUT), exist_ok=True)

ws = openpyxl.load_workbook(SHEET)["Targets"]
H = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}

groups = {}
for r in range(2, ws.max_row + 1):
    email = (ws.cell(row=r, column=H["Email"]).value or "").strip()
    if not email:
        continue
    g = groups.setdefault(email.lower(), {
        "to": email,
        "contact": ws.cell(row=r, column=H["Broker / Contact"]).value or "",
        "firm": ws.cell(row=r, column=H["Firm"]).value or "",
        "subject": None,
        "body": None,
        "tenants": [],
    })
    subj = ws.cell(row=r, column=H["Subject"]).value
    if subj:
        g["subject"] = subj
    body = ws.cell(row=r, column=H["Email Draft"]).value if "Email Draft" in H else None
    if body:
        g["body"] = body
    g["tenants"].append({
        "tenant": ws.cell(row=r, column=H["Tenant"]).value,
        "category": ws.cell(row=r, column=H["Category"]).value,
        "tier": ws.cell(row=r, column=H["Tier"]).value,
        "source": ws.cell(row=r, column=H["Where this came from"]).value,
        "vts_deal_id": None,      # filled in once the deals are created on the property
        "outcome": None,          # yes | no | later | no_reply  -- set by the triage pass
    })

manifest = {
    "built": datetime.datetime.now().isoformat(timespec="seconds"),
    "listing": LISTING,
    "vts_property_id": PROP,
    "sheet": SHEET,
    "note": ("Join key for replies is (recipient email + subject). One message may cover "
             "several tenants — split the reply per tenant before writing to VTS."),
    "sends": sorted(groups.values(), key=lambda g: (g["contact"] or "").lower()),
}
with open(OUT, "w") as f:
    json.dump(manifest, f, indent=1)

# ---- this blast's own log (follow-ups + receipts run from it)
slug = lo_blasts.slugify(LISTING)
try:
    old = lo_blasts.load(slug)
except Exception:
    old = {}
kept = {s["to"].lower(): s for s in old.get("sends", [])}
TRACK = ("sent_at", "sent_mid", "read_at", "not_read_at", "replied_at", "followups")
sends = []
for g in manifest["sends"]:
    s = lo_blasts.new_send(g["to"], g["contact"], g["firm"], g["subject"] or "",
                           g["body"] or "", g["tenants"])
    for k in TRACK:
        if kept.get(g["to"].lower(), {}).get(k):
            s[k] = kept[g["to"].lower()][k]
    sends.append(s)
followup = dict(old.get("followup") or {})
if opt("--followup"):
    followup["1"] = opt("--followup")
if opt("--followup2"):
    followup["2"] = opt("--followup2")
cadence = ([int(x) for x in opt("--cadence").split(",")] if opt("--cadence")
           else old.get("cadence") or lo_blasts.DEFAULT_CADENCE)
blast = {
    "slug": slug, "listing": LISTING, "vts_property_id": PROP, "sheet": os.path.abspath(SHEET),
    "built": old.get("built") or lo_blasts.iso(lo_blasts.now()),
    "receipts": bool("--receipts" in sys.argv or old.get("receipts")),
    "followup": followup, "cadence": cadence, "closed": False, "sends": sends,
    "flyer": (lo_blasts.keep_flyer(slug, opt("--flyer")) if opt("--flyer") else None)
             or old.get("flyer"),
}
lo_blasts.save(blast)
print(f"wrote {lo_blasts.path_for(slug)}")
print(f"  read receipts: {'yes' if blast['receipts'] else 'no'} | follow-ups at "
      f"{' / '.join(str(d) for d in cadence)} business days | messages written: "
      f"{', '.join('nudge ' + k for k in sorted(followup)) or 'NONE — no nudges will be drafted'}")

multi = [g for g in manifest["sends"] if len(g["tenants"]) > 1]
print(f"wrote {OUT}")
print(f"  {len(manifest['sends'])} sends covering "
      f"{sum(len(g['tenants']) for g in manifest['sends'])} tenants")
print(f"  {len(multi)} send(s) cover more than one tenant — these are the ones a reply "
      f"has to be split across:")
for g in multi:
    print(f"    {g['contact'] or g['to']:<18} ({len(g['tenants'])}): "
          f"{', '.join(t['tenant'] for t in g['tenants'])}")
