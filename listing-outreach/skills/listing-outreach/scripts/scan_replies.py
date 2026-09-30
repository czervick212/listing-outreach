#!/usr/bin/env python3
"""Find replies to an outreach batch and split them per tenant.

Matches each reply against ~/.listing-outreach/send-manifest.json on (sender address + subject),
which for mail WE sent is a deterministic key back to the exact tenant set — so a reply covering
several tenants ("no for three, yes for one") becomes one row per tenant in reply-queue.json,
each with an `outcome` field to classify before writing to VTS.

    python scan_replies.py                       # replies in the last 30 days
    python scan_replies.py --days 14
    python scan_replies.py --show                # print the queue, write nothing
    python scan_replies.py --messages msgs.json  # match messages fetched some other way

Which mailbox it reads follows `mail.backend` in config.json, same as the drafting half:
graph       -> the Outlook Inbox over Microsoft Graph (any Outlook, either platform)
apple-mail  -> the local Apple Mail .emlx store
outlook-com -> the Outlook Inbox via COM (pywin32), classic Outlook desktop only

`--messages` reads no mailbox at all — it takes messages already gathered and only does the
matching. That is the route for someone whose Outlook is reachable through Claude's Microsoft
365 connector but who has no Graph registration: Claude searches Outlook, dumps the results to
JSON, and this does the (recipient + subject) -> tenant split. The connector cannot be called
from a script, so it has to arrive this way. Accepts the connector's own field names
(sender/subject/receivedDateTime/internetMessageId/body|summary|bodyPreview) or this script's
internal ones (frm/subj/body/date/mid), as a bare list or under a "messages"/"value" key.
"""
import json
import sys
import os
import re
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import lo_mail  # noqa: E402  -- for the shared backend choice

BASE = os.path.join(os.path.expanduser("~"), ".listing-outreach")
MANIFEST = f"{BASE}/send-manifest.json"
QUEUE = f"{BASE}/reply-queue.json"

DAYS = 30
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days") + 1])
SHOW_ONLY = "--show" in sys.argv
MSG_FILE = None
if "--messages" in sys.argv:
    MSG_FILE = sys.argv[sys.argv.index("--messages") + 1]

if not os.path.exists(MANIFEST):
    print("No send manifest yet — there is no outreach batch to match replies against.\n"
          "Freeze one at send time with:\n"
          "  build_send_manifest.py <targets.xlsx> <vts_property_id> \"<Listing Name>\"",
          file=sys.stderr)
    raise SystemExit(2)
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


# A quoted original usually starts on its own line. But a preview from Microsoft's connector
# has its newlines collapsed to spaces, so the attribution arrives mid-sentence:
#   "...get inside?  On Mon, Aug 31, 2026 at 1:18 PM Spencer Ward <sward@...> wrote:  Hey Mike,"
# Left in, the broker's reply carries our own outbound text and gets classified as theirs.
FLAT_QUOTE = re.compile(
    r"\s(?:On\s.{5,120}?\swrote:"          # Gmail / Apple Mail attribution
    r"|-{2,}\s*Original Message"            # Outlook's separator
    r"|From:\s.{1,120}?\sSent:)",          # Outlook header block, newlines flattened
    re.S)   # deliberately case-SENSITIVE: with re.I, "...checking on it, he wrote: yes" matches

# An attribution line unambiguously opens the quoted block, so cut there as soon as there is any
# real text in front of it — broker replies are short ("Pass.", "Not for us right now") and a
# 40-character floor left exactly those carrying the whole history. A bare "> " prefix is
# different: people answer interleaved between quoted lines, so keep the high floor there.
ATTRIBUTION = ["\nOn ", "\nFrom: ", "\n-----Original", "\n________"]
INTERLEAVED = "\n> "


def strip_quoted(t):
    cut = len(t)
    for marker in ATTRIBUTION:
        k = t.find(marker)
        if k >= 2:                    # >= 2 so a message that IS a quote keeps its content
            cut = min(cut, k)
    k = t.find(INTERLEAVED)
    if k > 40:
        cut = min(cut, k)
    m = FLAT_QUOTE.search(t, 2)
    if m:
        cut = min(cut, m.start())
    return t[:cut].strip()


# --------------------------------------------------------- gather
# The per-backend readers live in lib/lo_scan.py, shared with followups.py.
import lo_scan  # noqa: E402
import lo_blasts  # noqa: E402


def gather_file(path):
    """Messages someone else already fetched — the Microsoft 365 connector, usually.

    Normalizes to this script's row shape, and is strict about the two fields the match depends
    on: a sender address and a subject. A message missing either can never match, so it is
    reported rather than silently dropped.
    """
    with open(path) as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("messages") or raw.get("value") or raw.get("rows") or []
    if not isinstance(raw, list):
        raise ValueError('expected a list of messages, or {"messages": [...]}')

    out, skipped = [], 0
    for m in raw:
        if not isinstance(m, dict):
            skipped += 1
            continue
        frm = m.get("frm") or m.get("sender") or m.get("from") or ""
        if isinstance(frm, dict):                    # Graph nests it; the connector does not
            frm = (frm.get("emailAddress") or frm).get("address", "")
        subj = m.get("subj") or m.get("subject") or ""
        body = (m.get("body") or m.get("summary") or m.get("bodyPreview")
                or m.get("reply_text") or "")
        if isinstance(body, dict):                   # Graph's {contentType, content}
            body = body.get("content", "")
        if not frm or not subj:
            skipped += 1
            continue
        out.append({
            "frm": str(frm).lower(),
            "subj": subj,
            "body": body,
            "date": m.get("date") or m.get("receivedDateTime") or m.get("sentDateTime") or "",
            "mid": m.get("mid") or m.get("internetMessageId") or m.get("id") or f"{frm}:{subj}",
        })
    if skipped:
        print(f"  ({skipped} entr{'y' if skipped == 1 else 'ies'} skipped — no sender or no "
              f"subject, so nothing to match on)")
    return out


GATHERERS = lo_scan.GATHERERS
LABELS = lo_scan.LABELS

if MSG_FILE:
    print(f"matching ({os.path.basename(MSG_FILE)}) against {len(by_addr)} recipient(s)")
    try:
        messages = gather_file(MSG_FILE)
    except Exception as e:
        print(f"\nCouldn't read {MSG_FILE}: {e}", file=sys.stderr)
        raise SystemExit(2)
    print(f"  {len(messages)} message(s) to match")
else:
    BACKEND = lo_mail.backend()
    if BACKEND not in GATHERERS:
        print("No mailbox to read — run listing-outreach setup to connect Outlook, or pass "
              "--messages with results fetched another way.", file=sys.stderr)
        raise SystemExit(2)
    print(f"scanning ({LABELS[BACKEND]}) against {len(by_addr)} recipient(s)")
    try:
        messages = [m for m in GATHERERS[BACKEND](DAYS) if m.get("folder") != "sent"]
    except Exception as e:
        print(f"\nCouldn't read the mailbox: {e}", file=sys.stderr)
        raise SystemExit(2)

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
    if lo_blasts.receipt_kind(msg["subj"]):
        continue                                   # a read receipt, not an answer — followups.py logs it
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
