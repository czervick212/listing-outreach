#!/usr/bin/env python3
"""Find replies to an outreach batch and split them per tenant.

Matches each reply against ~/.listing-outreach/send-manifest.json on (sender address + subject),
which for mail WE sent is a deterministic key back to the exact tenant set — so a reply covering
several tenants ("no for three, yes for one") becomes one row per tenant in reply-queue.json,
each with an `outcome` field to classify before writing to VTS.

    python scan_replies.py                 # replies in the last 30 days
    python scan_replies.py --days 14
    python scan_replies.py --show          # print the queue, write nothing

macOS  -> reads the local Apple Mail .emlx store (never the Outlook MCP — unusable headlessly).
Windows-> reads the Outlook Inbox via COM (pywin32), classic Outlook desktop.
"""
import json
import sys
import os
import re
import datetime
import platform

BASE = os.path.join(os.path.expanduser("~"), ".listing-outreach")
MANIFEST = f"{BASE}/send-manifest.json"
QUEUE = f"{BASE}/reply-queue.json"
IS_WIN = platform.system() == "Windows"

DAYS = 30
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days") + 1])
SHOW_ONLY = "--show" in sys.argv

man = json.load(open(MANIFEST))
by_addr = {s["to"].lower(): s for s in man["sends"]}


def norm_subj(s):
    return re.sub(r"^((re|fwd|fw):\s*)+", "", s or "", flags=re.I).strip().lower()


subject_by_addr = {s["to"].lower(): norm_subj(s["subject"]) for s in man["sends"]}

if SHOW_ONLY and os.path.exists(QUEUE):
    q = json.load(open(QUEUE))
    for r in q["rows"]:
        print(f"[{r['outcome'] or 'unclassified':<12}] {r['tenant']:<34} {r['from']}")
    print(f"\n{len(q['rows'])} row(s) from {len(set(x['thread'] for x in q['rows']))} thread(s)")
    raise SystemExit


def strip_quoted(t):
    for marker in ["\nOn ", "\nFrom: ", "\n-----Original", "\n________", "\n> "]:
        k = t.find(marker)
        if k > 40:
            t = t[:k]
    return t.strip()


# --------------------------------------------------------- gather (mac .emlx | win Outlook COM)
def gather_mac():
    import email
    import email.utils
    import subprocess
    root = os.path.expanduser("~/Library/Mail")
    found = subprocess.run(["find", root, "-name", "*.emlx", "-mtime", f"-{DAYS}"],
                           capture_output=True, text=True).stdout.split("\n")
    msgs = []
    for path in (f for f in found if f.strip()):
        try:
            raw = open(path, "rb").read()
            raw = raw[raw.find(b"\n") + 1:]                 # .emlx starts with a byte-count line
            m = email.message_from_bytes(raw)
        except Exception:
            continue
        body = ""
        for part in m.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", "ignore")
                    break
                except Exception:
                    pass
        msgs.append({"frm": email.utils.parseaddr(m.get("From") or "")[1].lower(),
                     "subj": m.get("Subject") or "", "body": body,
                     "date": m.get("Date") or "", "mid": m.get("Message-ID") or path})
    return msgs


def gather_win():
    import win32com.client
    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    inbox = ns.GetDefaultFolder(6)  # olFolderInbox
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=DAYS)
    msgs = []
    for it in items:
        try:
            rt = it.ReceivedTime
            if datetime.datetime(rt.year, rt.month, rt.day) < cutoff:
                break
            # resolve the sender's SMTP address (Exchange senders need PropertyAccessor)
            frm = ""
            try:
                frm = (it.SenderEmailAddress or "").lower()
                if frm.startswith("/o="):               # Exchange DN, not SMTP
                    frm = (it.Sender.GetExchangeUser().PrimarySmtpAddress or "").lower()
            except Exception:
                pass
            msgs.append({"frm": frm, "subj": it.Subject or "", "body": it.Body or "",
                         "date": str(it.ReceivedTime),
                         "mid": getattr(it, "EntryID", None) or f"{it.Subject}:{it.ReceivedTime}"})
        except Exception:
            continue
    return msgs


print(f"scanning ({'Outlook COM' if IS_WIN else 'Apple Mail .emlx'}) "
      f"against {len(by_addr)} recipient(s)")
messages = gather_win() if IS_WIN else gather_mac()

rows, seen = [], set()
for msg in messages:
    frm = msg["frm"]
    send = by_addr.get(frm)
    if not send:
        continue                                   # not one of our recipients
    want = subject_by_addr.get(frm, "")
    if want and want not in norm_subj(msg["subj"]):
        continue                                   # right person, different thread
    if msg["mid"] in seen:
        continue
    seen.add(msg["mid"])
    text = strip_quoted(msg["body"])
    if not text:
        continue
    for t in send["tenants"]:
        rows.append({
            "thread": msg["mid"], "from": frm, "contact": send["contact"], "firm": send["firm"],
            "date": msg["date"], "tenant": t["tenant"], "vts_deal_id": t.get("vts_deal_id"),
            "reply_text": text[:1500], "covers": [x["tenant"] for x in send["tenants"]],
            "outcome": None, "vts_comment": None, "posted": False,
        })

out = {"built": datetime.datetime.now().isoformat(timespec="seconds"),
       "vts_property_id": man["vts_property_id"], "rows": rows}
if rows:
    json.dump(out, open(QUEUE, "w"), indent=1)

threads = len(set(r["thread"] for r in rows))
print(f"{threads} reply thread(s) -> {len(rows)} (thread, tenant) row(s)")
for r in rows:
    flag = "  [SPLIT]" if len(r["covers"]) > 1 else ""
    print(f"  {r['contact'] or r['from']:<18} {r['tenant']:<34}{flag}")
print(f"\nwrote {QUEUE} — classify each row, then post to VTS on approval" if rows else "no replies yet")
