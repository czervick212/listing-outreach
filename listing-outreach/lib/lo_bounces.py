#!/usr/bin/env python3
"""Which of a blast's recipients bounced — Apple Mail only.

    import lo_bounces
    lo_bounces.bounced(["a@x.com", "b@y.com"], since_epoch)   -> {"a@x.com"}

Why this exists: VTS was being logged ("Submitted site.") the moment a send left the Outbox,
and bounces land one to five minutes later. On 2026-10-05 that meant posting comments on
four deals and then deleting them again. The send path now waits, asks this module, and only
logs the rows that landed — a bounce gets no VTS comment at all.

How it reads Mail: the Envelope Index is a live SQLite db (WAL mode), so it is COPIED with its
-wal/-shm files first and the copy is queried — never the original. A bounce is any message
received since the blast started whose sender is a mailer-daemon / postmaster / Exchange system
sender, or whose subject reads Undeliverable / Delivery Status / Returned mail / failure. The
bounce's own .emlx is then searched for the addresses we sent to; only those count. (A bounce
names the failed recipient in its body, not in its headers.)
"""
import glob
import os
import shutil
import sqlite3
import tempfile

MAIL = os.path.join(os.path.expanduser("~"), "Library", "Mail")

SENDER_HINTS = ("mailer-daemon", "postmaster", "microsoftexchange")
SUBJECT_HINTS = ("undeliverable", "delivery status", "returned mail", "delivery failure",
                 "failure notice", "not delivered", "could not be delivered")


def _envelope_index():
    hits = sorted(glob.glob(os.path.join(MAIL, "V*", "MailData", "Envelope Index")))
    return hits[-1] if hits else None


def _copy(db):
    tmp = tempfile.mkdtemp(prefix="lo-envidx-")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db + suffix):
            shutil.copy2(db + suffix, os.path.join(tmp, "Envelope Index" + suffix))
    return os.path.join(tmp, "Envelope Index"), tmp


def _bounce_rowids(db, since):
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "select m.ROWID, lower(a.address), lower(s.subject) from messages m "
            "join addresses a on m.sender = a.ROWID join subjects s on m.subject = s.ROWID "
            "where m.date_received >= ?", (int(since),)).fetchall()
    finally:
        con.close()
    return [rid for rid, sender, subj in rows
            if any(h in (sender or "") for h in SENDER_HINTS)
            or any(h in (subj or "") for h in SUBJECT_HINTS)]


def _emlx_paths(rowids):
    want = {str(r) for r in rowids}
    found = {}
    if not want:
        return found
    for root, _dirs, files in os.walk(MAIL):
        for f in files:
            if not f.endswith(".emlx"):
                continue
            stem = f.split(".")[0]
            if stem in want and stem not in found:
                found[stem] = os.path.join(root, f)
        if len(found) == len(want):
            break
    return found


def bounced(addresses, since):
    """The subset of `addresses` (lower-cased) that bounced since `since` (epoch seconds).
    Returns None when Mail's index can't be read (not a Mac, no Full Disk Access...), so a
    caller can tell "no bounces" from "couldn't check"."""
    db = _envelope_index()
    if not db:
        return None
    addrs = {a.strip().lower() for a in addresses if a}
    try:
        copy, tmp = _copy(db)
    except OSError:
        return None
    try:
        rowids = _bounce_rowids(copy, since)
    except sqlite3.Error:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = set()
    for path in _emlx_paths(rowids).values():
        try:
            text = open(path, "rb").read().decode("utf-8", "ignore").lower()
        except OSError:
            continue
        out |= {a for a in addrs if a in text}
    return out


if __name__ == "__main__":
    import sys
    import time
    if len(sys.argv) < 2:
        print("usage: lo_bounces.py <hours back> <address> [<address> ...]")
        raise SystemExit(1)
    hrs = float(sys.argv[1])
    res = bounced(sys.argv[2:], time.time() - hrs * 3600)
    print("could not read Mail's index" if res is None else (sorted(res) or "no bounces"))
