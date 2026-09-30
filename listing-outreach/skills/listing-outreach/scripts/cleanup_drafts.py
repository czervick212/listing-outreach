#!/usr/bin/env python3
"""Clear an outreach batch out of the mail client: save any open compose windows, then delete
the drafts matching a subject from a given day.

    python cleanup_drafts.py "Listing subject fragment"              # today
    python cleanup_drafts.py "Listing subject fragment" 2026-01-15   # a specific day
    python cleanup_drafts.py "Listing subject fragment" --count      # count only, delete nothing
    python cleanup_drafts.py "Listing subject fragment" --all-dates  # every matching draft, any day

(Use `python3` on macOS/Linux, `python` on Windows.)

Deleted drafts go to the Deleted Items / Trash — recoverable, not destroyed.

macOS: closing an unsaved compose window raises a modal "Save this message as a draft?" sheet;
with many windows open that stack of sheets jams AppleScript. So we save them all first, then
delete from Drafts where scripting is reliable. Mail still throttles scripted deletes
unpredictably — if it stalls, do it by hand: Drafts -> search the subject -> select all -> Delete.

Windows: deletes matching items straight from the Outlook Drafts folder via COM.

Outlook/Graph: deletes server-side from the Drafts folder — no windows to save, and
`mail.account` is ignored (the drafts are wherever you signed in).
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
ALL_DATES = "--all-dates" in sys.argv
rest = [a for a in sys.argv[2:] if not a.startswith("--")]
DAY = rest[0] if rest else datetime.date.today().isoformat()

# Mail account holding Drafts (Apple Mail only; the Outlook backends use the mailbox
# you're signed in to).
CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    ACCOUNT = json.load(open(CFG)).get("mail", {}).get("account") or "Exchange"
except Exception:
    ACCOUNT = "Exchange"

if COUNT_ONLY:
    print("--count is advisory; re-run without it to delete. "
          "On Apple Mail this still saves any open compose windows first.")

result = lo_mail.cleanup_drafts(SUBJECT, DAY, ACCOUNT, ALL_DATES)
when = "any date" if ALL_DATES else f"dated {DAY}"
print(f"deleted {result} draft(s) matching '{SUBJECT}' {when} -> Deleted Items")
if str(result).startswith("ERR"):
    print("  Nothing was deleted. Re-run with --all-dates if the drafts are from another day,\n"
          "  or clear them by hand: Drafts -> search the subject -> select all -> Delete.")
elif "/" in str(result):
    gone, found = str(result).split("/", 1)
    if gone != found:
        print(f"  {found} matched but only {gone} deleted - Mail throttles scripted deletes. "
              f"Re-run to finish the rest.")
