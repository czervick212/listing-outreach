#!/usr/bin/env python3
"""Find replies to an outreach batch and split them per tenant.

Reads the local Apple Mail store (.emlx) — never the Outlook MCP, which is unusable
headlessly. Matches each reply against data/send-manifest.json on (sender address +
subject), which for mail WE sent is a deterministic key back to the exact tenant set.

Emits data/reply-queue.json: one entry per (thread, tenant) with the reply text, so a
downstream pass can classify each tenant separately. A single "no for three, yes for
one" reply becomes four rows.

    python3 scan_replies.py                 # replies since the manifest was built
    python3 scan_replies.py --days 14
    python3 scan_replies.py --show          # print the queue, write nothing
"""
import json, sys, os, re, email, email.utils, datetime, subprocess, glob

BASE = os.path.join(os.path.expanduser("~"), ".listing-outreach")
MANIFEST = f"{BASE}/send-manifest.json"
QUEUE = f"{BASE}/reply-queue.json"
MAILROOT = os.path.expanduser("~/Library/Mail")

DAYS = 30
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days") + 1])
SHOW_ONLY = "--show" in sys.argv

man = json.load(open(MANIFEST))
# recipient address -> the send record (its tenant list is what a reply must be split across)
by_addr = {s["to"].lower(): s for s in man["sends"]}
def norm_subj(s):
    return re.sub(r"^((re|fwd|fw):\s*)+", "", s or "", flags=re.I).strip().lower()

# each send carries its own subject — match per-send, not against one global key
subject_by_addr = {s["to"].lower(): norm_subj(s["subject"]) for s in man["sends"]}

if SHOW_ONLY and os.path.exists(QUEUE):
    q = json.load(open(QUEUE))
    for r in q["rows"]:
        print(f"[{r['outcome'] or 'unclassified':<12}] {r['tenant']:<34} {r['from']}")
    print(f"\n{len(q['rows'])} row(s) from {len(set(x['thread'] for x in q['rows']))} thread(s)")
    raise SystemExit

cutoff = datetime.datetime.now() - datetime.timedelta(days=DAYS)

# Only scan recently-modified .emlx — the archive is ~67k files and a full walk is slow.
found = subprocess.run(
    ["find", MAILROOT, "-name", "*.emlx", "-mtime", f"-{DAYS}"],
    capture_output=True, text=True).stdout.split("\n")
files = [f for f in found if f.strip()]
print(f"scanning {len(files)} recent message file(s) against {len(by_addr)} recipient(s)")


def parse(path):
    try:
        raw = open(path, "rb").read()
        raw = raw[raw.find(b"\n") + 1:]          # .emlx starts with a byte-count line
        return email.message_from_bytes(raw)
    except Exception:
        return None


def body_of(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            try:
                return part.get_payload(decode=True).decode("utf-8", "ignore")
            except Exception:
                pass
    return ""


def strip_quoted(t):
    for marker in ["\nOn ", "\nFrom: ", "\n-----Original", "\n________", "\n> "]:
        k = t.find(marker)
        if k > 40:
            t = t[:k]
    return t.strip()


rows, seen = [], set()
for path in files:
    msg = parse(path)
    if not msg:
        continue
    subj = (msg.get("Subject") or "").strip()
    norm = norm_subj(subj)
    frm = email.utils.parseaddr(msg.get("From") or "")[1].lower()
    send = by_addr.get(frm)
    if not send:
        continue                                   # not one of our recipients
    want = subject_by_addr.get(frm, "")
    if want and want not in norm:
        continue                                   # right person, different thread
    mid = msg.get("Message-ID") or path
    if mid in seen:
        continue
    seen.add(mid)
    text = strip_quoted(body_of(msg))
    if not text:
        continue
    dt = msg.get("Date") or ""
    for t in send["tenants"]:
        rows.append({
            "thread": mid,
            "from": frm,
            "contact": send["contact"],
            "firm": send["firm"],
            "date": dt,
            "tenant": t["tenant"],
            "vts_deal_id": t.get("vts_deal_id"),
            "reply_text": text[:1500],
            "covers": [x["tenant"] for x in send["tenants"]],
            "outcome": None,        # yes | no | later  -- set by the classify pass
            "vts_comment": None,    # drafted comment text, reviewed before posting
            "posted": False,
        })

out = {
    "built": datetime.datetime.now().isoformat(timespec="seconds"),
    "vts_property_id": man["vts_property_id"],
    "rows": rows,
}
if rows:
    json.dump(out, open(QUEUE, "w"), indent=1)

threads = len(set(r["thread"] for r in rows))
print(f"{threads} reply thread(s) -> {len(rows)} (thread, tenant) row(s)")
for r in rows:
    flag = "  [SPLIT]" if len(r["covers"]) > 1 else ""
    print(f"  {r['contact'] or r['from']:<18} {r['tenant']:<34}{flag}")
if rows:
    print(f"\nwrote {QUEUE} — classify each row, then post to VTS on approval")
else:
    print("no replies yet")
