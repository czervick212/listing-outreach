#!/usr/bin/env python3
"""Clear an outreach batch out of the mail client: save any open compose windows, then delete
the drafts matching a subject from a given day.

    python cleanup_drafts.py "Listing subject fragment"              # today
    python cleanup_drafts.py "Listing subject fragment" 2026-01-15   # a specific day
    python cleanup_drafts.py "Listing subject fragment" --count      # count only, delete nothing

(Use `python3` on macOS/Linux, `python` on Windows.)

Deleted drafts go to the Deleted Items / Trash — recoverable, not destroyed.

macOS: closing an unsaved compose window raises a modal "Save this message as a draft?" sheet;
with many windows open that stack of sheets jams AppleScript. So we save them all first, then
delete from Drafts where scripting is reliable. Mail still throttles scripted deletes
unpredictably — if it stalls, do it by hand: Drafts -> search the subject -> select all -> Delete.

Windows: deletes matching items straight from the Outlook Drafts folder via COM.
"""
import sys
import os
import json
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import lo_mail  # noqa: E402

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(1)

SUBJECT = sys.argv[1]
COUNT_ONLY = "--count" in sys.argv
rest = [a for a in sys.argv[2:] if not a.startswith("--")]
DAY = rest[0] if rest else datetime.date.today().isoformat()

# Mail account holding Drafts (macOS only; Windows uses the default Outlook profile).
CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    ACCOUNT = json.load(open(CFG)).get("mail", {}).get("account") or "Exchange"
except Exception:
    ACCOUNT = "Exchange"

if COUNT_ONLY:
    print("--count is advisory; re-run without it to delete. "
          "On macOS this still saves any open compose windows first.")

result = lo_mail.cleanup_drafts(SUBJECT, DAY, ACCOUNT)
print(f"deleted {result} draft(s) matching '{SUBJECT}' dated {DAY} -> Deleted Items")
