#!/usr/bin/env python3
"""Open the outreach emails as REVIEWABLE Mail.app compose windows, flyer attached.

    python3 make_drafts.py <targets.xlsx> <flyer.pdf>            # all sends
    python3 make_drafts.py <targets.xlsx> <flyer.pdf> 0 10       # a batch (start, count)
    python3 make_drafts.py <targets.xlsx> <flyer.pdf> --list     # print the send list only

Windows open visible and are NOT saved or sent — review each, then Send by hand. The From:
address is read from ~/.listing-outreach/config.json (user.email); the signature is whatever
Mail applies to that account.

Notes learned the hard way (see the SKILL.md):
- mailto: links cannot carry an attachment; that is why this scripts Mail directly.
- The flyer must live somewhere normal — a file under the Mail container's Downloads cannot
  be reliably attached via AppleScript. Copy it next to the listing first.
- Body ends with a single trailing return so the attachment sits directly under the sign-off.
"""
import openpyxl, subprocess, sys, os, json

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(1)

SHEET, FLYER = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]

CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    SENDER = json.load(open(CFG))["user"]["email"]
except Exception:
    print("No sender email configured — run /listing-outreach-setup first.", file=sys.stderr)
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
        sends.append((
            ws.cell(row=r, column=H["Tenant"]).value,
            ws.cell(row=r, column=H["Broker / Contact"]).value,
            ws.cell(row=r, column=H["Email"]).value,
            ws.cell(row=r, column=H["Subject"]).value,
            ws.cell(row=r, column=H["Email Draft"]).value,
        ))

if "--list" in rest:
    for i, (tenant, who, email, subj, body) in enumerate(sends):
        print(f"{i:>3}  {who or '-':<20} {email:<34} {tenant}")
    print(f"\n{len(sends)} sends")
    raise SystemExit

nums = [a for a in rest if a.isdigit()]
START = int(nums[0]) if len(nums) > 0 else 0
COUNT = int(nums[1]) if len(nums) > 1 else len(sends)
batch = sends[START:START + COUNT]
print(f"total sends: {len(sends)} | opening {len(batch)} (index {START}-{START + len(batch) - 1})")


def asq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def asbody(s):
    return " & return & ".join(asq(p) for p in str(s).rstrip().split("\n"))


ok = fail = 0
for tenant, who, email, subj, body in batch:
    script = f'''
set flyerAlias to (POSIX file "{FLYER}") as alias
tell application "Mail"
  set msg to make new outgoing message with properties {{subject:{asq(subj)}, content:{asbody(body)} & return, visible:true}}
  tell msg
    set sender to "{SENDER}"
    make new to recipient at end of to recipients with properties {{address:{asq(email)}}}
    tell content
      make new attachment with properties {{file name:flyerAlias}} at after the last paragraph
    end tell
  end tell
end tell
'''
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if p.returncode == 0:
        ok += 1
        print(f"  opened  {tenant} -> {email}")
    else:
        fail += 1
        print(f"  FAILED  {tenant} ({email}): {p.stderr.strip()[:140]}")

print(f"\nopened {ok}, failed {fail} — review each window and send. Nothing was saved or sent automatically.")
