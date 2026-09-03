#!/usr/bin/env python3
"""Cross-platform mail backend for Listing Outreach.

Two operations, two platforms:
  * open_drafts(sends, flyer, sender)         -> reviewable compose windows, flyer attached
  * cleanup_drafts(subject, day, account)     -> save any open windows, delete drafts by subject+day

macOS  -> Mail.app via AppleScript (tested).
Windows-> classic Outlook desktop via COM / pywin32 (win32com). Written carefully but NOT
          tested on real Windows — the honest caveat, same as the VTS toolkit. New Outlook
          (the store/web app) does NOT expose COM; users on it must use classic Outlook, or
          fall back to the .csv the caller can also emit.

`sends` is a list of dicts: {tenant, contact, email, subject, body}.
The compose window is opened for REVIEW — never sent automatically, on either platform.
"""
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


def _mac_open_one(send, flyer, sender):
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


def _mac_cleanup(subject, day, account):
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
    r = subprocess.run(["osascript", "-e", f'''
tell application "Mail"
  {daydef}
  set a to first account whose name is "{account}"
  set dm to first mailbox of a whose name is "Drafts"
  set gone to 0
  repeat 400 times
    try
      delete (first message of dm whose subject contains "{subject}" and date received >= d0 and date received < d1)
      set gone to gone + 1
      delay 0.15
    on error
      exit repeat
    end try
  end repeat
  return gone
end tell'''], capture_output=True, text=True)
    return r.stdout.strip() or "0"


# --------------------------------------------------------------------------- Windows
def _win_outlook():
    import win32com.client  # from pywin32
    return win32com.client.Dispatch("Outlook.Application")


def _win_body_html(body):
    import html
    return "".join(f"<div>{html.escape(line) if line else '&nbsp;'}</div>"
                   for line in str(body).rstrip().split("\n"))


def _win_open_one(send, flyer, sender):
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


def _win_cleanup(subject, day, account):
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
                    ct = it.CreationTime
                    if datetime.date(ct.year, ct.month, ct.day) == target:
                        it.Delete()
                        gone += 1
            except Exception:
                pass
        return str(gone)
    except Exception as e:
        return f"ERR {str(e)[:120]}"


# ----------------------------------------------------------------------------- API
def open_drafts(sends, flyer, sender):
    if IS_MAC:
        opener = _mac_open_one
    elif IS_WIN:
        opener = _win_open_one
    else:
        print(f"Unsupported platform: {platform.system()}", file=sys.stderr)
        return 0, len(sends)
    ok = fail = 0
    for s in sends:
        good, err = opener(s, flyer, sender)
        if good:
            ok += 1
            print(f"  opened  {s['tenant']} -> {s['email']}")
        else:
            fail += 1
            print(f"  FAILED  {s['tenant']} ({s['email']}): {err}")
    return ok, fail


def cleanup_drafts(subject, day, account):
    if IS_MAC:
        return _mac_cleanup(subject, day, account)
    if IS_WIN:
        return _win_cleanup(subject, day, account)
    print(f"Unsupported platform: {platform.system()}", file=sys.stderr)
    return "0"
