#!/usr/bin/env python3
"""Vet every address on the send list BEFORE anything goes out.

    python3 vet_contacts.py <targets.xlsx>

Run it after the sheet is built and before make_drafts.py. Four checks per row with an email:

  1. MX       — the domain accepts mail at all. A domain with no MX is a guaranteed bounce.
  2. MOVES    — ~/.listing-outreach/people_moves.json: people who LEFT a firm, people who
                MOVED (old address -> new), and a do-not-contact list. Seeded by hand as the
                user corrects us; it is the only check that catches "Amanda left three years ago".
  3. INDEX    — when a contact_index is configured: an address whose newest deal date is in the
                FUTURE is a mis-dated row and can't be trusted as "newest" (Matt Alexander's old
                Cushman address outranked his real one off an "08/31/28" row); one not seen in
                over two years is flagged stale. If the same person has a newer address, it's named.
  4. DUPES    — the same address on two rows (two tenants, one broker) is fine, but shown.

Exit code 1 when any row is BLOCKED (no MX, departed, moved, do-not-contact) — fix those rows
first. Warnings (stale, mis-dated, a newer address in the index) don't block; read them.

people_moves.json shape:
  {"departed": {"amanda@dochalex.com": "left DochAlex ~2023"},
   "moved":    {"matthew.alexander@cushwake.com": {"now": "matthew@dochalex.com",
                                                   "note": "co-founded DochAlex"}},
   "do_not_contact": {"someone@x.com": "real pass, Leesburg only"}}
"""
import datetime
import json
import os
import re
import subprocess
import sys
from collections import Counter

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import lo_config  # noqa: E402

BASE = os.path.join(os.path.expanduser("~"), ".listing-outreach")
MOVES = os.path.join(BASE, "people_moves.json")
TODAY = datetime.date.today()


def has_mx(domain, cache={}):
    if domain in cache:
        return cache[domain]
    try:
        out = subprocess.run(["nslookup", "-type=mx", domain], capture_output=True,
                             text=True, timeout=15).stdout.lower()
        ok = "mail exchanger" in out
    except Exception:
        ok = None                      # couldn't check — don't block on it
    cache[domain] = ok
    return ok


def parse_day(s):
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except (TypeError, ValueError):
            pass
    return None


def load_index():
    path = lo_config.contact_index(lo_config.load())
    if not path or not os.path.exists(path):
        return {}
    try:
        people = json.load(open(path)).get("people", {})
    except Exception:
        return {}
    by_email = {}
    for person, recs in people.items():
        for r in recs:
            e = (r.get("email") or "").lower()
            if e:
                by_email[e] = (person, recs)
    return by_email


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    ws = openpyxl.load_workbook(sys.argv[1])["Targets"]
    H = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}
    rows = []
    for r in range(2, ws.max_row + 1):
        email = (ws.cell(row=r, column=H["Email"]).value or "").strip()
        if email:
            rows.append((r, ws.cell(row=r, column=H["Tenant"]).value, email))

    moves = json.load(open(MOVES)) if os.path.exists(MOVES) else {}
    departed = {k.lower(): v for k, v in moves.get("departed", {}).items()}
    moved = {k.lower(): v for k, v in moves.get("moved", {}).items()}
    dnc = {k.lower(): v for k, v in moves.get("do_not_contact", {}).items()}
    index = load_index()
    counts = Counter(e.lower() for _, _, e in rows)

    blocked = warned = 0
    for r, tenant, email in rows:
        e = email.lower()
        notes, block = [], False
        if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", e):
            notes.append("not an email address")
            block = True
        else:
            mx = has_mx(e.split("@")[1])
            if mx is False:
                notes.append("domain has NO MX — will bounce")
                block = True
            elif mx is None:
                notes.append("MX not checked")
        if e in departed:
            notes.append(f"DEPARTED: {departed[e]}")
            block = True
        if e in dnc:
            notes.append(f"DO NOT CONTACT: {dnc[e]}")
            block = True
        if e in moved:
            m = moved[e]
            note = f" — {m['note']}" if m.get("note") else ""
            notes.append(f"MOVED: use {m.get('now')}{note}")
            block = True
        if e in index:
            person, recs = index[e]
            mine = next((x for x in recs if (x.get("email") or "").lower() == e), {})
            d = parse_day(mine.get("last"))
            if d and d > TODAY:
                notes.append(f"index date {mine.get('last')} is in the FUTURE — mis-dated row, "
                             f"don't trust it as newest")
            elif d and (TODAY - d).days > 730:
                notes.append(f"last seen {d:%b %Y} — stale")
            better = [x for x in recs if (x.get("email") or "").lower() != e
                      and parse_day(x.get("last")) and parse_day(x.get("last")) <= TODAY
                      and (not d or d > TODAY or parse_day(x.get("last")) > d)]
            if better:
                b = max(better, key=lambda x: parse_day(x["last"]))
                notes.append(f"newer address for {person}: {b['email']} ({b['last']})")
        if counts[e] > 1:
            notes.append(f"same address on {counts[e]} rows")
        tag = "BLOCK" if block else ("warn " if notes else "ok   ")
        blocked += block
        warned += bool(notes) and not block
        print(f"{tag}  row {r:<3} {str(tenant)[:30]:<30} {email:<38} {'; '.join(notes)}")

    print(f"\n{len(rows)} addresses: {blocked} blocked, {warned} with warnings")
    raise SystemExit(1 if blocked else 0)


if __name__ == "__main__":
    main()
