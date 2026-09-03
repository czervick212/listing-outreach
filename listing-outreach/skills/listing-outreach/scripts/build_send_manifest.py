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

    python3 build_send_manifest.py <targets.xlsx> <property_id> [out.json]
"""
import json, sys, datetime, openpyxl

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(1)

import os
if len(sys.argv) < 4:
    print("usage: build_send_manifest.py <targets.xlsx> <vts_property_id> <listing_name>")
    raise SystemExit(1)
SHEET, PROP, LISTING = sys.argv[1], int(sys.argv[2]), sys.argv[3]
OUT = os.path.join(os.path.expanduser("~"), ".listing-outreach", "send-manifest.json")
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
        "tenants": [],
    })
    subj = ws.cell(row=r, column=H["Subject"]).value
    if subj:
        g["subject"] = subj
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

multi = [g for g in manifest["sends"] if len(g["tenants"]) > 1]
print(f"wrote {OUT}")
print(f"  {len(manifest['sends'])} sends covering "
      f"{sum(len(g['tenants']) for g in manifest['sends'])} tenants")
print(f"  {len(multi)} send(s) cover more than one tenant — these are the ones a reply "
      f"has to be split across:")
for g in multi:
    print(f"    {g['contact'] or g['to']:<18} ({len(g['tenants'])}): "
          f"{', '.join(t['tenant'] for t in g['tenants'])}")
