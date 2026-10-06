#!/usr/bin/env python3
"""One log per outreach blast — who was sent what, and what happened after.

Why this exists: the original send-manifest.json was a single file that every blast
overwrote. Reply matching only ever needed the latest batch, but follow-ups need every
open batch at once — the Westview South nudges are due while the Cathedral Commons ones
are still out. So each blast gets its own file under ~/.listing-outreach/blasts/, and the
legacy manifest is still written alongside for anything that reads it.

A blast log carries, per recipient:
  sent_at / sent_mid     confirmed from the Sent folder, not from when the draft was made
  read_at / not_read_at  from a read receipt, when the blast asked for them
  replied_at             any reply on the thread — this is what stops the follow-ups
  followups[]            {n, drafted_at, sent_at} for each nudge

Dates are ISO strings with a UTC offset, so comparisons survive a machine changing zone.
"""
import datetime
import json
import os
import re

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".listing-outreach")
DIR = os.path.join(BASE, "blasts")
LEGACY = os.path.join(BASE, "send-manifest.json")

DEFAULT_CADENCE = [3, 10]      # business days after the original send: nudge 1, nudge 2


FLYERS = os.path.join(BASE, "flyers")


def keep_flyer(slug, path):
    """Copy the blast's flyer to ~/.listing-outreach/flyers/<slug>/<its own name> and return
    that path. The file name is what the recipient sees on the attachment, so it is kept.
    Nudges re-attach it, and the 7 AM job can't count on the original: Dropbox online-only
    placeholders and launchd's CloudStorage block both leave it unreadable at run time."""
    import shutil
    if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    folder = os.path.join(FLYERS, slug)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, os.path.basename(path))
    if os.path.abspath(path) != os.path.abspath(dest):
        shutil.copyfile(path, dest)
    return dest


def flyer_for(blast):
    """The blast's kept flyer, if it is still there."""
    f = blast.get("flyer")
    return f if f and os.path.isfile(f) and os.path.getsize(f) > 0 else None


def now():
    return datetime.datetime.now().astimezone()


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def parse(s):
    """ISO string -> aware datetime. A naive one is taken as local time."""
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "blast"


def norm_subj(s):
    return re.sub(r"^((re|fwd|fw|aw)\s*:\s*)+", "", s or "", flags=re.I).strip().lower()


# ------------------------------------------------------------------ business days
def add_business_days(d, n):
    """The date n business days after d (weekends skipped; holidays are not modelled)."""
    step = 0
    while step < n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            step += 1
    return d


def business_days_between(a, b):
    """Whole business days from date a to date b (0 if b is not after a)."""
    n, d = 0, a
    while d < b:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


# ------------------------------------------------------------------ store
def path_for(slug):
    return os.path.join(DIR, f"{slug}.json")


def load(slug):
    with open(path_for(slug)) as f:
        return json.load(f)


def save(blast):
    os.makedirs(DIR, exist_ok=True)
    tmp = path_for(blast["slug"]) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blast, f, indent=1)
    os.replace(tmp, path_for(blast["slug"]))     # never leave a half-written log behind


def all_blasts():
    if not os.path.isdir(DIR):
        return []
    out = []
    for name in sorted(os.listdir(DIR)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(DIR, name)) as f:
                    out.append(json.load(f))
            except Exception:
                pass
    return out


def open_blasts():
    return [b for b in all_blasts() if not b.get("closed")]


def find(name_or_slug):
    """A blast by slug, or by a case-insensitive fragment of its listing name."""
    want = slugify(name_or_slug)
    hits = [b for b in all_blasts() if b["slug"] == want]
    if not hits:
        hits = [b for b in all_blasts() if want in b["slug"]]
    return hits[0] if len(hits) == 1 else None


def new_send(to, contact="", firm="", subject="", body="", tenants=None):
    return {
        "to": to, "contact": contact, "firm": firm, "subject": subject, "body": body,
        "tenants": tenants or [],
        "sent_at": None, "sent_mid": None,
        "read_at": None, "not_read_at": None,
        "replied_at": None,
        "followups": [],
    }


# ------------------------------------------------------------------ syncing against mail
RECEIPT_READ = re.compile(r"^\s*read\s*:", re.I)
RECEIPT_NOT_READ = re.compile(r"^\s*not\s+read\s*:", re.I)


def receipt_kind(subject):
    """'read', 'not_read' or None. Exchange/Outlook receipts are 'Read: <subject>'."""
    if RECEIPT_NOT_READ.match(subject or ""):
        return "not_read"
    if RECEIPT_READ.match(subject or ""):
        return "read"
    return None


def subject_matches(want, got):
    """Does message subject `got` belong to the thread whose subject is `want`?"""
    w = norm_subj(want)
    g = norm_subj(re.sub(r"^\s*(not\s+)?read\s*:\s*", "", got or "", flags=re.I))
    return bool(w) and w in g


def sync(blast, messages, me):
    """Fold mailbox rows into the blast log. Returns a list of human-readable changes.

    `messages` rows: {frm, to:[...], subj, date (ISO), mid, folder: 'sent'|'inbox'}.
    Only fills fields that are still empty, so re-running is harmless.
    """
    me = (me or "").lower()
    built = parse(blast.get("built")) or now() - datetime.timedelta(days=30)
    changes = []
    rows = [m for m in messages if parse(m.get("date"))]
    rows.sort(key=lambda m: parse(m["date"]))

    for s in blast["sends"]:
        r = s["to"].lower()
        sent_at = parse(s.get("sent_at"))

        # 1. The original going out: first sent message to them on this subject after the build.
        if not sent_at:
            for m in rows:
                if (m["folder"] == "sent" and r in m["to"] and parse(m["date"]) >= built
                        and subject_matches(s["subject"], m["subj"])):
                    s["sent_at"], s["sent_mid"] = m["date"], m["mid"]
                    sent_at = parse(m["date"])
                    changes.append(f"sent      {s['to']}")
                    break
        if not sent_at:
            continue

        # 2. Follow-ups going out: a later sent message on the thread after that nudge was drafted.
        used = {s.get("sent_mid")} | {f.get("sent_mid") for f in s["followups"]}
        for fu in s["followups"]:
            if fu.get("sent_at") or not fu.get("drafted_at"):
                continue
            drafted = parse(fu["drafted_at"]) - datetime.timedelta(minutes=5)
            for m in rows:
                if (m["folder"] == "sent" and r in m["to"] and m["mid"] not in used
                        and parse(m["date"]) >= drafted
                        and subject_matches(s["subject"], m["subj"])):
                    fu["sent_at"], fu["sent_mid"] = m["date"], m["mid"]
                    used.add(m["mid"])
                    changes.append(f"nudge {fu['n']}   {s['to']}")
                    break

        # 3. What came back: receipts and replies, from them, on this thread, after the send.
        for m in rows:
            if m["folder"] != "inbox" or m["frm"] != r or parse(m["date"]) < sent_at:
                continue
            if not subject_matches(s["subject"], m["subj"]):
                continue
            kind = receipt_kind(m["subj"])
            if kind == "read" and not s.get("read_at"):
                s["read_at"] = m["date"]
                changes.append(f"read      {s['to']}")
            elif kind == "not_read" and not s.get("not_read_at"):
                s["not_read_at"] = m["date"]
                changes.append(f"not read  {s['to']}")
            elif kind is None and not s.get("replied_at"):
                s["replied_at"] = m["date"]
                changes.append(f"replied   {s['to']}")
    return changes


# ------------------------------------------------------------------ what's due
def state(s):
    """One short status for a recipient."""
    if s.get("replied_at"):
        return "replied"
    if not s.get("sent_at"):
        return "not sent"
    sent_fus = [f for f in s["followups"] if f.get("sent_at")]
    pending = [f for f in s["followups"] if not f.get("sent_at")]
    if pending:
        return f"nudge {pending[-1]['n']} drafted"
    if sent_fus:
        return f"nudged x{len(sent_fus)}"
    return "waiting"


def due(blast, today=None):
    """[(send, n)] — recipients whose nudge n should be drafted today."""
    today = today or now().date()
    cadence = blast.get("cadence") or DEFAULT_CADENCE
    messages = blast.get("followup") or {}
    out = []
    for s in blast["sends"]:
        if s.get("replied_at") or not s.get("sent_at"):
            continue
        sent = parse(s["sent_at"]).date()
        done = {f["n"] for f in s["followups"]}
        for n, days in enumerate(cadence, start=1):
            if n in done:
                continue
            if not (messages.get(str(n)) or "").strip():
                break                                   # no message written for this nudge
            prev = [f for f in s["followups"] if f["n"] == n - 1]
            if n > 1 and not (prev and prev[0].get("sent_at")):
                break                                   # nudge 2 waits for nudge 1 to go out
            if today >= add_business_days(sent, days):
                out.append((s, n))
            break
    return out


ORG_WORDS = {"hospitality", "family", "llc", "inc", "co", "company", "restaurants",
             "restaurant", "team", "partners", "management", "owners", "office"}


# Shared inboxes: whoever reads info@ is rarely the name on the sheet, so they get "there".
ROLE_INBOXES = {"info", "hello", "hi", "contact", "contactus", "mail", "email", "inquiries",
                "inquiry", "enquiries", "reservations", "reservation", "reserve", "events",
                "event", "catering", "office", "admin", "team", "general", "support", "sales",
                "marketing", "leasing", "realestate", "development", "expansion", "booking",
                "bookings", "host", "manager", "management", "careers", "jobs", "press"}


def first_name(contact, email=None):
    """A first name to greet, or "there" when the contact is a company rather than a person,
    or the address is a shared inbox (info@, reservations@ ...).
    'Villagio Hospitality Group' and 'Lina family' are not people; 'Carlos Delgado group'
    still names one, so a trailing 'group' is dropped when two words are left."""
    local = re.sub(r"[^a-z]", "", (email or "").split("@")[0].lower())
    if local in ROLE_INBOXES:
        return "there"
    words = [w.strip(".,") for w in (contact or "").split()]
    if words and words[-1].lower() == "group" and len(words) >= 3:
        words = words[:-1]
    if not words or "@" in words[0] or any(w.lower() in ORG_WORDS | {"group"} for w in words):
        return "there"
    return words[0]


def fill(template, s, blast):
    """Placeholders: {first_name} {contact} {tenant} {listing}."""
    first = first_name(s.get("contact"), s.get("to"))
    tenants = [t.get("tenant") for t in s.get("tenants") or [] if t.get("tenant")]
    tenant = (tenants[0] if len(tenants) == 1
              else ", ".join(tenants[:-1]) + " and " + tenants[-1] if tenants else "")
    return (template.replace("{first_name}", first)
                    .replace("{contact}", s.get("contact") or first)
                    .replace("{tenant}", tenant)
                    .replace("{listing}", blast.get("listing") or ""))
