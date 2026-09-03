#!/usr/bin/env python3
"""Clear an outreach batch out of Mail: save any open compose windows, then delete
every draft matching a subject from a given day.

Why it works this way: closing an unsaved compose window raises a modal
"Save this message as a draft?" sheet, one per window. With 40 windows open that
stack of sheets jams AppleScript's `close` entirely. Pressing Return takes the
DEFAULT button, which is Save — so instead of fighting the dialogs, let them all
save, then delete from Drafts where AppleScript works cleanly and reliably.

Usage:
    python3 cleanup_drafts.py "Listing subject fragment"              # today
    python3 cleanup_drafts.py "Listing subject fragment" 2026-01-15   # a specific day
    python3 cleanup_drafts.py "Listing subject fragment" --count      # count only, delete nothing

Deleted drafts go to Deleted Items — recoverable, not destroyed.

CAVEAT: Mail throttles scripted deletes badly and unpredictably — sometimes 20+ go
through cleanly, sometimes one per 50 attempts. If this stalls, do NOT grind on it:
in Mail, select the Drafts mailbox, search the subject, Cmd-A, Delete. Two seconds.
The save-then-bulk-delete idea is still right; the per-item scripting is the weak part.
"""
import subprocess, sys, datetime, os, json

# The Mail account holding your Drafts. Configurable — defaults to the account whose
# address matches user.email, else "Exchange".
_CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    _c = json.load(open(_CFG))
    ACCOUNT = _c.get("mail", {}).get("account") or "Exchange"
except Exception:
    ACCOUNT = "Exchange"

if len(sys.argv) < 2:
    print(__doc__)
    raise SystemExit(1)

SUBJECT = sys.argv[1]
COUNT_ONLY = "--count" in sys.argv
rest = [a for a in sys.argv[2:] if not a.startswith("--")]
DAY = rest[0] if rest else datetime.date.today().isoformat()
y, m, d = (int(x) for x in DAY.split("-"))


def osa(script):
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# 1. Save anything still open, so nothing is lost behind a modal sheet.
rc, out, err = osa(f'''
tell application "Mail"
  set n to 0
  repeat with msg in outgoing messages
    try
      if (subject of msg) contains "{SUBJECT}" then
        save msg
        delay 0.2
        close msg saving no
        set n to n + 1
      end if
    end try
  end repeat
  return n
end tell''')
print(f"saved {out or 0} open compose window(s) matching '{SUBJECT}'")
if err:
    print("  note:", err.splitlines()[0][:120])

# 2. Count what is now sitting in Drafts from that day.
# NOTE: `month of <date> as integer` mis-parses in AppleScript. Compare a date RANGE instead.
DAYDEF = (f'set d0 to (current date)\n'
          f'  set year of d0 to {y}\n  set month of d0 to {m}\n  set day of d0 to {d}\n'
          f'  set time of d0 to 0\n  set d1 to d0 + (1 * days)\n')
matcher = (f'(subject of msg contains "{SUBJECT}") and '
           f'(date received of msg >= d0) and (date received of msg < d1)')

rc, out, err = osa(f'''
tell application "Mail"
  {DAYDEF}
  set a to first account whose name is "{ACCOUNT}"
  set dm to first mailbox of a whose name is "Drafts"
  set k to 0
  repeat with msg in (messages of dm)
    try
      if {matcher} then set k to k + 1
    end try
  end repeat
  return k
end tell''')
if rc != 0:
    print("could not read Drafts:", err[:200])
    raise SystemExit(1)
n = int(out or 0)
print(f"drafts matching '{SUBJECT}' dated {DAY}: {n}")

if COUNT_ONLY or n == 0:
    raise SystemExit(0)

# 3. Delete them (goes to Deleted Items). Must use a `whose` clause -- holding a
#    reference from a manual repeat loop goes stale and `delete` then errors.
rc, out, err = osa(f'''
tell application "Mail"
  {DAYDEF}
  set a to first account whose name is "{ACCOUNT}"
  set dm to first mailbox of a whose name is "Drafts"
  set gone to 0
  repeat 400 times
    try
      delete (first message of dm whose subject contains "{SUBJECT}" and date received >= d0 and date received < d1)
      set gone to gone + 1
      delay 0.15
    on error
      exit repeat
    end try
  end repeat
  return gone
end tell''')
print(f"deleted {out or 0} draft(s) -> Deleted Items")
if err:
    print("  note:", err.splitlines()[0][:120])
