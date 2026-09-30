#!/usr/bin/env python3
"""Read recent mail — both directions — from whichever backend is configured.

Shared by scan_replies.py (who answered) and followups.py (who was actually sent, who
read it, who still needs a nudge). Every backend returns the same row shape:

    {frm, to: [addr, ...], subj, body, date: ISO-8601 with offset, mid, folder}

`folder` is 'sent' for mail the user sent and 'inbox' for everything they received —
including mail already filed out of the Inbox, because a reply that got filed is still
a reply. Drafts, Outbox, Junk and Deleted are never read: a draft sitting in Drafts is
exactly the thing that must NOT count as sent.
"""
import datetime
import email
import email.parser
import email.utils
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lo_mail  # noqa: E402

MAC_ROOT = os.path.expanduser("~/Library/Mail")
MAC_SKIP = ("drafts", "outbox", "sendlater", "scheduled", "deleted", "junk", "trash",
            "sync issues", "conversation history")
MAC_SENT = ("sent items.mbox", "sent messages.mbox", "sent mail.mbox", "sent.mbox")


def _iso(dt):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def _addrs(*headers):
    return [a.lower() for _, a in email.utils.getaddresses([h for h in headers if h]) if a]


# ----------------------------------------------------------------------------- macOS
def _mac_folder(path):
    """'sent', 'inbox', or None to skip — judged by the .mbox the file lives in."""
    parts = [p.lower() for p in path.split(os.sep) if p.lower().endswith(".mbox")]
    if not parts:
        return None
    if any(p in MAC_SENT for p in parts):
        return "sent"
    if any(any(k in p for k in MAC_SKIP) for p in parts):
        return None
    return "inbox"


def _mac_read(path, want_body=True):
    try:
        with open(path, "rb") as f:
            raw = f.read() if want_body else f.read(16384)   # headers live at the top
        raw = raw[raw.find(b"\n") + 1:]               # .emlx starts with a byte-count line
        if want_body:
            m = email.message_from_bytes(raw)
        else:
            m = email.parser.BytesHeaderParser().parsebytes(raw.split(b"\n\n", 1)[0] + b"\n\n")
    except Exception:
        return None
    body = ""
    if want_body:
        for part in m.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", "ignore")
                    break
                except Exception:
                    pass
    try:
        when = email.utils.parsedate_to_datetime(m.get("Date"))
    except Exception:
        when = None
    return {"frm": email.utils.parseaddr(m.get("From") or "")[1].lower(),
            "to": _addrs(m.get("To"), m.get("Cc")),
            "subj": str(m.get("Subject") or "").replace("\n", " ").strip(),
            "body": body, "date": _iso(when),
            "mid": (m.get("Message-ID") or path).strip()}


def _mac_index():
    """Path to Mail's Envelope Index — its own SQLite catalogue of every message."""
    hits = sorted(glob.glob(os.path.join(MAC_ROOT, "V*", "MailData", "Envelope Index")))
    return hits[-1] if hits else None


def _mac_folder_url(url):
    """Classify a mailbox by its URL (ews://…/Sent%20Items, imap://…/INBOX, …)."""
    import urllib.parse
    tail = urllib.parse.unquote(url or "").lower().rstrip("/")
    last = tail.rsplit("/", 1)[-1]
    if last in ("sent items", "sent messages", "sent mail", "sent"):
        return "sent"
    if any(k in last for k in MAC_SKIP):
        return None
    return "inbox"


def gather_mac_index(days, sent_only=False):
    """Headers only, straight from the Envelope Index: ~0.1 s where reading .emlx files
    takes a minute (filing mail rewrites files, so tens of thousands look 'recent').
    Opened read-only; SQLite readers never block Mail's own writes."""
    import sqlite3
    path = _mac_index()
    if not path:
        raise FileNotFoundError("no Envelope Index")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
        rows = con.execute("""
            select m.ROWID, lower(a.address), coalesce(m.subject_prefix,'') || coalesce(s.subject,''),
                   coalesce(m.date_sent, m.date_received), mb.url, g.message_id_header
            from messages m
            join mailboxes mb on mb.ROWID = m.mailbox
            left join subjects s on s.ROWID = m.subject
            left join addresses a on a.ROWID = m.sender
            left join message_global_data g on g.ROWID = m.global_message_id
            where m.date_received >= ? and m.deleted = 0""", (cutoff,)).fetchall()
        keep = {}
        for rid, frm, subj, ts, url, mid in rows:
            folder = _mac_folder_url(url)
            if folder is None or (sent_only and folder != "sent"):
                continue
            keep[rid] = {"frm": frm or "", "to": [], "subj": subj.strip(), "body": "",
                         "date": _iso(datetime.datetime.fromtimestamp(ts).astimezone()) if ts else "",
                         "mid": (mid or f"rowid:{rid}").strip(), "folder": folder}
        if keep:
            con.execute("create temp table want(id integer primary key)")
            con.executemany("insert into want values (?)", [(k,) for k in keep])
            for rid, addr in con.execute("""
                    select r.message, lower(a.address) from recipients r
                    join want w on w.id = r.message
                    join addresses a on a.ROWID = r.address"""):
                keep[rid]["to"].append(addr)
        return list(keep.values())
    finally:
        con.close()


def gather_mac(days, sent_only=False, bodies=True):
    """The local Apple Mail store. Header-only reads go through the Envelope Index; the
    .emlx walk below is the fallback, and the only route when bodies are needed.
    """
    if not bodies:
        try:
            return gather_mac_index(days, sent_only)
        except Exception:
            pass
    return _gather_mac_files(days, sent_only, bodies)


def _gather_mac_files(days, sent_only=False, bodies=True):
    """The local Apple Mail store. `find -mtime` keeps it to recent files; the Sent-only
    mode scans just the Sent mailboxes, which is cheap enough to poll every few minutes."""
    if sent_only:
        roots = [p for p in glob.glob(os.path.join(MAC_ROOT, "V*", "*", "*.mbox"))
                 if os.path.basename(p).lower() in MAC_SENT]
    else:
        roots = [MAC_ROOT]
    found = []
    for root in roots:
        found += subprocess.run(["find", root, "-name", "*.emlx", "-mtime", f"-{days}"],
                                capture_output=True, text=True).stdout.split("\n")
    out = []
    for path in (f for f in found if f.strip()):
        folder = _mac_folder(path)
        if folder is None:
            continue
        row = _mac_read(path, want_body=bodies and folder == "inbox")
        if row:
            row["folder"] = folder
            out.append(row)
    return out


# --------------------------------------------------------------------------- Windows
def gather_win(days, sent_only=False, bodies=True):
    import win32com.client
    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    out = []
    folders = [(5, "sent")] if sent_only else [(6, "inbox"), (5, "sent")]  # Inbox, Sent Items
    for num, label in folders:
        items = ns.GetDefaultFolder(num).Items
        field = "[SentOn]" if label == "sent" else "[ReceivedTime]"
        items.Sort(field, True)
        for it in items:
            try:
                t = it.SentOn if label == "sent" else it.ReceivedTime
                when = datetime.datetime(t.year, t.month, t.day, t.hour, t.minute, t.second)
                if when < cutoff:
                    break
                frm = ""
                try:
                    frm = (it.SenderEmailAddress or "").lower()
                    if frm.startswith("/o="):           # Exchange DN, not SMTP
                        frm = (it.Sender.GetExchangeUser().PrimarySmtpAddress or "").lower()
                except Exception:
                    pass
                to = []
                try:
                    for rcp in it.Recipients:
                        a = rcp.Address or ""
                        if a.startswith("/o="):
                            a = rcp.AddressEntry.GetExchangeUser().PrimarySmtpAddress or ""
                        if a:
                            to.append(a.lower())
                except Exception:
                    pass
                mid = ""
                try:   # PR_INTERNET_MESSAGE_ID
                    mid = it.PropertyAccessor.GetProperty(
                        "http://schemas.microsoft.com/mapi/proptag/0x1035001F")
                except Exception:
                    mid = getattr(it, "EntryID", "") or f"{it.Subject}:{t}"
                out.append({"frm": frm, "to": to, "subj": it.Subject or "",
                            "body": (it.Body or "") if bodies and label == "inbox" else "",
                            "date": _iso(when), "mid": mid, "folder": label})
            except Exception:
                continue
    return out


# --------------------------------------------------------------------------- Graph
def gather_graph(days, sent_only=False, bodies=True):
    import lo_graph
    return lo_graph.messages_since(days, sent_only=sent_only, bodies=bodies)


GATHERERS = {"graph": gather_graph, "apple-mail": gather_mac, "outlook-com": gather_win}
LABELS = {"graph": "Outlook via Graph", "apple-mail": "Apple Mail",
          "outlook-com": "Outlook COM"}


def gather(days=30, sent_only=False, backend=None, bodies=True):
    """`bodies=False` reads headers only — all follow-up tracking needs, and far faster."""
    which = backend or lo_mail.backend()
    fn = GATHERERS.get(which)
    if not fn:
        raise RuntimeError("No mailbox to read — run listing-outreach setup to connect mail.")
    return fn(days, sent_only=sent_only, bodies=bodies)
