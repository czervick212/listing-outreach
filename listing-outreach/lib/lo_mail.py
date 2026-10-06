#!/usr/bin/env python3
"""Cross-platform mail backend for Listing Outreach.

Three operations, three backends:
  * open_drafts(sends, flyer, sender, receipts)  -> drafts for review, flyer attached
  * cleanup_drafts(subject, day, account)        -> delete those drafts again, by subject+day
  * draft_followup(send, text, sender)           -> a nudge as a REPLY on the original thread

graph       -> Microsoft Graph (lib/lo_graph.py). Any Outlook, either platform, new app or
               classic — nothing is scripted locally, so it also works with no mail client
               installed. Drafts land in the Outlook Drafts folder rather than opening on
               screen. Chosen automatically once an app registration is configured.
apple-mail  -> Mail.app via AppleScript (tested). The macOS default.
outlook-com -> classic Outlook desktop via COM / pywin32 (win32com). Written carefully but
               NOT tested on real Windows — the honest caveat, same as the VTS toolkit. The
               Windows default. New Outlook does NOT expose COM: those users need `graph`.

Which one runs is `mail.backend` in ~/.listing-outreach/config.json when it is set, else
Graph if it is configured, else the platform default.

`sends` is a list of dicts: {tenant, contact, email, subject, body}.
By default the compose window is opened for REVIEW — never sent. `send_now` is the one
exception: an explicit `--send` from make_drafts.py, Apple Mail only, after the user has
approved the list.
"""
import json
import os
import sys
import platform
import subprocess

IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"


# ----------------------------------------------------------------------------- macOS
def _mac_asq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mac_asbody(s):
    return " & return & ".join(_mac_asq(p) for p in str(s).rstrip().split("\n"))


def _mac_open_one(send, flyer, sender, receipt=False):
    # receipts on Apple Mail are a mailbox-wide switch, not per message — see lo_receipts.py
    script = f'''
set flyerAlias to (POSIX file "{flyer}") as alias
tell application "Mail"
  set msg to make new outgoing message with properties {{subject:{_mac_asq(send["subject"])}, content:{_mac_asbody(send["body"])} & return, visible:true}}
  tell msg
    set sender to "{sender}"
    make new to recipient at end of to recipients with properties {{address:{_mac_asq(send["email"])}}}
    tell content
      make new attachment with properties {{file name:flyerAlias}} at after the last paragraph
    end tell
  end tell
end tell
'''
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return p.returncode == 0, p.stderr.strip()[:140]


def _mac_send_one(send, flyer, sender):
    """Send ONE message headless — the opt-in `--send` path, never the default.
    The pause before `send` lets Mail finish attaching a large flyer; sending sooner has gone
    out with the attachment missing."""
    script = f'''
set flyerAlias to (POSIX file "{flyer}") as alias
tell application "Mail"
  set msg to make new outgoing message with properties {{subject:{_mac_asq(send["subject"])}, content:{_mac_asbody(send["body"])} & return, visible:false}}
  tell msg
    set sender to "{sender}"
    make new to recipient at end of to recipients with properties {{address:{_mac_asq(send["email"])}}}
    tell content
      make new attachment with properties {{file name:flyerAlias}} at after the last paragraph
    end tell
  end tell
  delay 4
  send msg
end tell
return "sent"'''
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
    return p.returncode == 0, (p.stderr.strip() or p.stdout.strip())[:140]


def _mac_cleanup(subject, day, account, all_dates=False):
    y, m, d = (int(x) for x in day.split("-"))
    daydef = (f'set d0 to (current date)\n  set year of d0 to {y}\n  set month of d0 to {m}\n'
              f'  set day of d0 to {d}\n  set time of d0 to 0\n  set d1 to d0 + (1 * days)\n')
    # save any open compose windows first so nothing is lost behind a modal Save sheet
    subprocess.run(["osascript", "-e", f'''
tell application "Mail"
  repeat with msg in outgoing messages
    try
      if (subject of msg) contains "{subject}" then
        save msg
        delay 0.2
        close msg saving no
      end if
    end try
  end repeat
end tell'''], capture_output=True, text=True)
    # Resolving the mailbox: the account-scoped name lookup is primary and works whether or
    # not "Store draft messages on the server" is on. `drafts mailbox` is NOT a property of
    # an account (that's the `message viewer` class) — only the application-level one exists,
    # and it returns the unified "All Drafts" across every account, so it's the fallback.
    #
    # The date filter is deliberately soft. Drafts were never *received*, so `date received`
    # is unreliable on them: a draft whose date won't read is still deleted on a subject
    # match rather than skipped, because skipping is what lets drafts pile up unnoticed.
    # Pass all_dates=True to drop the date test entirely.
    datetest = ('' if all_dates else '''
        try
          set dr to date received of m
          if dr < d0 or dr >= d1 then set hit to false
        end try''')
    r = subprocess.run(["osascript", "-e", f'''
tell application "Mail"
  {daydef}
  set dm to missing value
  try
    set dm to first mailbox of (first account whose name is "{account}") whose name is "Drafts"
  end try
  if dm is missing value then
    try
      set dm to drafts mailbox
    end try
  end if
  if dm is missing value then return "ERR no Drafts mailbox for account {account}"
  -- snapshot first: deleting while enumerating a live collection shifts it and skips messages
  set victims to {{}}
  repeat with m in (get messages of dm)
    try
      if (subject of m) contains "{subject}" then
        set hit to true{datetest}
        if hit then set end of victims to m
      end if
    end try
  end repeat
  set found to count of victims
  set gone to 0
  repeat with m in victims
    try
      delete m
      set gone to gone + 1
      delay 0.1
    end try
  end repeat
  return (gone as text) & "/" & (found as text)
end tell'''], capture_output=True, text=True)
    out = r.stdout.strip()
    if not out:
        return f"ERR {r.stderr.strip()[:120] or 'osascript returned nothing'}"
    return out


# --------------------------------------------------------------------------- Windows
def _win_outlook():
    import win32com.client  # from pywin32
    return win32com.client.Dispatch("Outlook.Application")


def _win_body_html(body):
    import html
    return "".join(f"<div>{html.escape(line) if line else '&nbsp;'}</div>"
                   for line in str(body).rstrip().split("\n"))


def _win_open_one(send, flyer, sender, receipt=False):
    try:
        ol = _win_outlook()
        mail = ol.CreateItem(0)  # olMailItem
        mail.To = send["email"]
        mail.Subject = send["subject"]
        # GetInspector forces the account's default signature into HTMLBody; prepend the body
        # so the user's Outlook signature is preserved (COM otherwise clobbers it).
        _ = mail.GetInspector
        sig = mail.HTMLBody or ""
        mail.HTMLBody = _win_body_html(send["body"]) + sig
        mail.Attachments.Add(os.path.abspath(flyer))
        if receipt:
            mail.ReadReceiptRequested = True
        # best-effort: send from the account whose SMTP matches `sender`
        try:
            for acct in ol.Session.Accounts:
                if str(getattr(acct, "SmtpAddress", "")).lower() == sender.lower():
                    mail.SendUsingAccount = acct
                    break
        except Exception:
            pass
        mail.Display(False)  # opens a reviewable compose window; does NOT send
        return True, ""
    except Exception as e:
        return False, str(e)[:140]


def _win_cleanup(subject, day, account, all_dates=False):
    try:
        import datetime
        ol = _win_outlook()
        ns = ol.GetNamespace("MAPI")
        drafts = ns.GetDefaultFolder(16)  # olFolderDrafts
        target = datetime.date.fromisoformat(day)
        gone = 0
        # iterate a static snapshot; deleting while enumerating live shifts the collection
        items = list(drafts.Items)
        for it in items:
            try:
                if subject.lower() in str(it.Subject).lower():
                    if all_dates:
                        it.Delete()
                        gone += 1
                        continue
                    ct = it.CreationTime
                    if datetime.date(ct.year, ct.month, ct.day) == target:
                        it.Delete()
                        gone += 1
            except Exception:
                pass
        return str(gone)
    except Exception as e:
        return f"ERR {str(e)[:120]}"


# --------------------------------------------------------------------------- Graph
def _graph():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lo_graph
    return lo_graph


def _graph_open_one(send, flyer, sender, receipt=False):
    g = _graph()
    try:
        g.create_draft(send["email"], send["subject"], send["body"], flyer, receipt=receipt)
        return True, ""
    except Exception as e:
        return False, str(e).replace("\n", " ")[:140]


def _graph_cleanup(subject, day, account, all_dates=False):
    g = _graph()
    try:
        gone = 0
        for d in (g.drafts_on(None) if all_dates else g.drafts_on(day)):
            if subject.lower() in (d.get("subject") or "").lower():
                g.delete_message(d["id"])
                gone += 1
        return str(gone)
    except Exception as e:
        return f"ERR {str(e)[:120]}"


# ------------------------------------------------------------------------ follow-ups
# A nudge is a REPLY on the original thread, never a fresh email: the recipient's mail app
# then shows the first pitch right under it. `send` is a blast-log entry (lo_blasts.py) and
# must carry `sent_mid`, the Message-ID of the original as it left the Sent folder.

def _mac_followup(send, text, sender, flyer=None):
    """Mail's `reply` keeps In-Reply-To/References, so the draft threads. Quirks, verified
    2026-09-29 and 2026-10-05: a scripted reply to your own sent mail is addressed to YOU (so
    the recipient is swapped in); Mail's quoted original is not reachable from AppleScript —
    replacing `content` drops it, and so does inserting a paragraph above it; and the
    signature always re-lands at the very end. So nothing of the original survives in the
    body: the nudge has to carry the pitch itself, and the flyer is attached again."""
    mid = (send.get("sent_mid") or "").strip().strip("<>")
    if not mid:
        return False, "original not found in Sent"
    attach = ""
    if flyer:
        # inside `tell r`: addressed as `content of r` from outside, Mail loses the reply
        # ("Can't get outgoing message id N")
        attach = f'''
  tell r
    tell content
      make new attachment with properties {{file name:(POSIX file {_mac_asq(flyer)} as alias)}} at after the last paragraph
    end tell
  end tell'''
    # The Sent search can outrun AppleScript's default 2-minute wait on a big mailbox.
    script = f'''
with timeout of 600 seconds
tell application "Mail"
  set orig to missing value
  -- Each account's own Sent folder first: one indexed lookup (seconds). The unified
  -- `sent mailbox` walk below is the slow fallback that was timing out.
  repeat with acct in (every account)
    repeat with nm in {"Sent Items", "Sent Messages", "Sent", "Sent Mail"}
      try
        set orig to first message of mailbox (nm as string) of acct whose message id is {_mac_asq(mid)}
        exit repeat
      end try
    end repeat
    if orig is not missing value then exit repeat
  end repeat
  if orig is missing value then
  repeat with mb in (every mailbox of sent mailbox)
    try
      set hits to (messages of mb whose message id is {_mac_asq(mid)})
      if (count of hits) > 0 then
        set orig to item 1 of hits
        exit repeat
      end if
    end try
  end repeat
  end if
  if orig is missing value then
    try
      set orig to first message of sent mailbox whose message id is {_mac_asq(mid)}
    end try
  end if
  if orig is missing value then return "ERR original not found in Sent"
  set r to reply orig opening window true
  delay 1
  delete every to recipient of r
  make new to recipient at end of to recipients of r with properties {{address:{_mac_asq(send["to"])}}}
  set content of r to {_mac_asbody(text)} & return{attach}
  return "ok"
end tell
end timeout'''
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    out = p.stdout.strip()
    if p.returncode != 0 or out != "ok":
        return False, (out or p.stderr.strip())[:140].replace("ERR ", "")
    return True, ""


def _win_followup(send, text, sender, flyer=None):
    try:
        ol = _win_outlook()
        sent = ol.GetNamespace("MAPI").GetDefaultFolder(5)   # olFolderSentMail
        want = send["to"].lower()
        items = sent.Items
        items.Sort("[SentOn]", True)
        orig = None
        for it in items:
            try:
                if send["subject"].lower() in str(it.Subject).lower() and \
                        any(want == (r.Address or "").lower() or
                            want == (r.AddressEntry.GetExchangeUser().PrimarySmtpAddress or "").lower()
                            for r in it.Recipients):
                    orig = it
                    break
            except Exception:
                continue
        if orig is None:
            return False, "original not found in Sent Items"
        r = orig.Reply()
        while r.Recipients.Count:
            r.Recipients.Remove(1)
        r.Recipients.Add(send["to"])
        r.Recipients.ResolveAll()
        r.HTMLBody = _win_body_html(text) + (r.HTMLBody or "")
        if flyer:
            r.Attachments.Add(os.path.abspath(flyer))
        r.Display(False)
        return True, ""
    except Exception as e:
        return False, str(e)[:140]


def _graph_followup(send, text, sender, flyer=None):
    g = _graph()
    try:
        made = g.create_followup(send.get("sent_mid") or "", send["to"], text, flyer)
        return (True, "") if made else (False, "original not found in Sent Items")
    except Exception as e:
        return False, str(e).replace("\n", " ")[:140]


# ----------------------------------------------------------------------------- API
def backend():
    """Which backend to use: explicit config, else Graph if set up, else the platform."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")) as f:
            chosen = (json.load(f).get("mail") or {}).get("backend")
    except Exception:
        chosen = None
    if chosen in ("graph", "apple-mail", "outlook-com"):
        return chosen
    try:
        if _graph().configured():
            return "graph"
    except Exception:
        pass
    if IS_MAC:
        return "apple-mail"
    if IS_WIN:
        return "outlook-com"
    return None


OPENERS = {"graph": _graph_open_one, "apple-mail": _mac_open_one, "outlook-com": _win_open_one}
CLEANERS = {"graph": _graph_cleanup, "apple-mail": _mac_cleanup, "outlook-com": _win_cleanup}
FOLLOWERS = {"graph": _graph_followup, "apple-mail": _mac_followup, "outlook-com": _win_followup}


def _unsupported():
    print(f"No mail backend available on {platform.system()}. Set up Outlook "
          f"(listing-outreach setup) to draft through Microsoft Graph.", file=sys.stderr)


def open_drafts(sends, flyer, sender, receipts=False):
    which = backend()
    opener = OPENERS.get(which)
    if not opener:
        _unsupported()
        return 0, len(sends)
    # Check the sign-in once. Otherwise a stale token fails identically on all 30 sends.
    if which == "graph":
        g = _graph()
        try:
            who = g.me()["email"]
        except g.GraphError as e:
            print(f"\n{e}", file=sys.stderr)
            return 0, len(sends)
        # Graph drafts from whichever mailbox signed in; say so rather than quietly disagreeing.
        if who and sender and who.lower() != sender.lower():
            print(f"  note: signed in as {who}, but config says {sender}. "
                  f"Drafts will come from {who}.")
    ok = fail = 0
    for s in sends:
        good, err = opener(s, flyer, sender, receipts)
        if good:
            ok += 1
            print(f"  drafted {s['tenant']} -> {s['email']}")
        else:
            fail += 1
            print(f"  FAILED  {s['tenant']} ({s['email']}): {err}")
    if ok and which == "graph":
        print(f"\n  {ok} draft(s) are in your Outlook Drafts folder — review and send there.")
    return ok, fail


SENDERS = {"apple-mail": _mac_send_one}


def send_now(sends, flyer, sender, log_path):
    """Opt-in: SEND each message instead of drafting it, one at a time, flyer attached.

    Every address is written to `log_path` (JSON) the moment it goes, and read back first, so a
    crash or a re-run can never send twice — an address already marked sent is skipped. Stops at
    the first failure rather than ploughing through a broken session. Apple Mail only for now;
    the other backends keep the draft-and-review path. Returns (sent, skipped, failed)."""
    import time
    fn = SENDERS.get(backend())
    if not fn:
        print(f"--send isn't available on the {backend()} backend yet — drafting is.",
              file=sys.stderr)
        return 0, 0, len(sends)
    log = json.load(open(log_path)) if os.path.exists(log_path) else {}
    sent = skipped = 0
    for s in sends:
        key = (s["email"] or "").strip().lower()
        if log.get(key, {}).get("sent"):
            skipped += 1
            print(f"  already sent  {s['tenant']} -> {s['email']}")
            continue
        good, err = fn(s, flyer, sender)
        log[key] = {"tenant": s["tenant"], "contact": s.get("contact"), "sent": good,
                    "at": time.time(), "err": "" if good else err}
        with open(log_path, "w") as f:
            json.dump(log, f, indent=1)
        if not good:
            print(f"  FAILED  {s['tenant']} ({s['email']}): {err}")
            return sent, skipped, 1
        sent += 1
        print(f"  sent    {s['tenant']} -> {s['email']}")
        time.sleep(6)
    return sent, skipped, 0


def cleanup_drafts(subject, day, account, all_dates=False):
    cleaner = CLEANERS.get(backend())
    if not cleaner:
        _unsupported()
        return "0"
    return cleaner(subject, day, account, all_dates)


def draft_followup(send, text, sender, flyer=None):
    """Draft one nudge as a reply on the original thread, flyer re-attached when given.
    Never sends. Returns (ok, err)."""
    fn = FOLLOWERS.get(backend())
    if not fn:
        _unsupported()
        return False, "no mail backend"
    return fn(send, text, sender, flyer)
