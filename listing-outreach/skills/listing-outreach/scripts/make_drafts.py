#!/usr/bin/env python3
"""Open the outreach emails as REVIEWABLE compose windows, flyer attached.

    python make_drafts.py <targets.xlsx> <flyer.pdf>            # all sends
    python make_drafts.py <targets.xlsx> <flyer.pdf> 0 10       # a batch (start, count)
    python make_drafts.py <targets.xlsx> <flyer.pdf> --list     # print the send list only

(Use `python3` on macOS/Linux, `python` on Windows — try one, use the other if it's missing.)

Windows open visible and are NOT saved or sent — review each, then Send by hand.
- macOS: Mail.app.  - Windows: classic Outlook desktop (needs pywin32; New Outlook has no COM).
The From: address comes from ~/.listing-outreach/config.json (user.email); the signature is
whatever the mail client applies to that account.

Why script the client at all: mailto: links cannot carry an attachment. The flyer must live
somewhere normal — not inside the mail app's own container/Downloads — or attaching fails. Copy
it next to the listing first.
"""
import openpyxl
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import lo_mail  # noqa: E402

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(1)

SHEET, FLYER = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]

CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    SENDER = json.load(open(CFG))["user"]["email"]
except Exception:
    print("No sender email configured — run listing-outreach setup first.", file=sys.stderr)
    raise SystemExit(2)

if not os.path.exists(FLYER):
    print(f"Flyer not found: {FLYER}", file=sys.stderr)
    raise SystemExit(1)

ws = openpyxl.load_workbook(SHEET)["Targets"]
H = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}
SEND_COL = H["Send Email"]

sends = []
for r in range(2, ws.max_row + 1):
    if ws.cell(row=r, column=SEND_COL).hyperlink:          # only rows with a live Send button
        sends.append({
            "tenant": ws.cell(row=r, column=H["Tenant"]).value,
            "contact": ws.cell(row=r, column=H["Broker / Contact"]).value,
            "email": ws.cell(row=r, column=H["Email"]).value,
            "subject": ws.cell(row=r, column=H["Subject"]).value,
            "body": ws.cell(row=r, column=H["Email Draft"]).value,
        })

if "--list" in rest:
    for i, s in enumerate(sends):
        print(f"{i:>3}  {s['contact'] or '-':<20} {s['email']:<34} {s['tenant']}")
    print(f"\n{len(sends)} sends")
    raise SystemExit

nums = [a for a in rest if a.isdigit()]
START = int(nums[0]) if len(nums) > 0 else 0
COUNT = int(nums[1]) if len(nums) > 1 else len(sends)
batch = sends[START:START + COUNT]
print(f"total sends: {len(sends)} | opening {len(batch)} (index {START}-{START + len(batch) - 1})")

ok, fail = lo_mail.open_drafts(batch, os.path.abspath(FLYER), SENDER)
print(f"\nopened {ok}, failed {fail} — review each window and send. "
      f"Nothing was saved or sent automatically.")
