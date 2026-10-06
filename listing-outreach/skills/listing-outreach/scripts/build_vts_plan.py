#!/usr/bin/env python3
"""Build the VTS write plan from the target sheet.

    python3 build_vts_plan.py <targets.xlsx> <vts_property_id> [out_dir] [--send-log <log.json>]

--send-log (from make_drafts.py --send) limits section A to the emails that actually landed:
a row that was never sent, or that bounced, is left out — a bounce gets no VTS comment. The
bounced rows are listed at the end so they can be re-sourced.

Produces, in out_dir (default ~/.listing-outreach):
  vts_plan.json  - machine-readable plan the JS runner consumes
  vts_plan.txt   - human preview to review before anything is written

Sections:
  A. submitted   - one deal PER TENANT that actually got an email, commented
                   "Submitted site." or "Submitted potential relo opportunity."
  B. dead        - tenants who passed / were ruled out; created then marked dead with a reason
  C. stage       - any tenant with a non-default stage recorded in the "VTS stage" note
                   (e.g. a tour), applied after creation

User identity + VTS taxonomy come from ~/.listing-outreach/config.json.
Relocation vs. fresh submittal is read from the sheet: a row whose Category or Notes marks it
as a relo (or that carries a relo line in the draft) is logged as a relo opportunity.
"""
import json, os, sys, openpyxl

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(1)

args = sys.argv[1:]
SEND_LOG = None
if "--send-log" in args:
    i = args.index("--send-log")
    SEND_LOG = args[i + 1]
    args = args[:i] + args[i + 2:]
SHEET = args[0]
PROP = int(args[1])
OUT = args[2] if len(args) > 2 else os.path.join(os.path.expanduser("~"), ".listing-outreach")
SENT = json.load(open(SEND_LOG)) if SEND_LOG else None
skipped_bounce, skipped_unsent = [], []
os.makedirs(OUT, exist_ok=True)

CFG = os.path.join(os.path.expanduser("~"), ".listing-outreach", "config.json")
try:
    cfg = json.load(open(CFG))
    UID = cfg["user"]["vts_user_id"]
    UNAME = cfg["user"]["name"]
    IND = cfg.get("vts", {}).get("tenant_industry_id", 122)
    DT = cfg.get("vts", {}).get("deal_type_id", 1)
except Exception:
    print("Not configured — run /listing-outreach-setup first.", file=sys.stderr)
    raise SystemExit(2)

ws = openpyxl.load_workbook(SHEET)["Targets"]
H = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}


def cell(r, name):
    return ws.cell(row=r, column=H[name]).value if name in H else None


def is_relo(r):
    """A relo pitch is flagged in the draft body or the Notes column."""
    body = (cell(r, "Email Draft") or "").lower()
    notes = (cell(r, "Notes") or "").lower()
    return "need a relo" in body or "relo opportunity" in notes or "relo" in (cell(r, "Category") or "").lower()


submitted = []
for r in range(2, ws.max_row + 1):
    email = (cell(r, "Email") or "").strip()
    if not email:
        continue                      # no email = nothing sent = nothing to log
    if SENT is not None:
        rec = SENT.get(email.lower())
        if not rec or not rec.get("sent"):
            skipped_unsent.append(cell(r, "Tenant"))
            continue
        if rec.get("bounced"):
            skipped_bounce.append(f"{cell(r, 'Tenant')} <{email}>")
            continue
    contact = cell(r, "Broker / Contact") or ""
    first, _, last = contact.partition(" ")
    submitted.append({
        "tenant": cell(r, "Tenant"),
        "comment": "Submitted potential relo opportunity." if is_relo(r) else "Submitted site.",
        # carried through for emit_tim_js.py -- Handbook Steps 4/5 need the category to set
        # the requirement's "Main; Sub" description and guess its size block
        "category": cell(r, "Category") or "",
        "contact": {"first_name": first, "last_name": last, "email": email,
                    "company_name": cell(r, "Firm") or "", "type": "broker"},
    })

plan = {
    "property_id": PROP, "user_id": UID, "user_name": UNAME,
    "tenant_industry_id": IND, "deal_type_id": DT,
    "submitted": submitted,
    "dead": [],       # populate from the Ruled out tab / your notes before running (see SKILL.md)
    "stage": [],
    "bryan_comments": [],
}
with open(os.path.join(OUT, "vts_plan.json"), "w") as f:
    json.dump(plan, f, indent=1)

n_relo = sum(1 for s in submitted if "relo" in s["comment"])
lines = [f"VTS WRITE PLAN — property {PROP}, as {UNAME}\n",
         f"A. CREATE + COMMENT  ({len(submitted)} deals)",
         f"   {len(submitted)-n_relo} x 'Submitted site.'   |   {n_relo} x 'Submitted potential relo opportunity.'\n"]
for s in sorted(submitted, key=lambda x: (x["tenant"] or "").lower()):
    tag = "RELO" if "relo" in s["comment"] else "site"
    lines.append(f"   [{tag}] {s['tenant']:<38} {s['contact']['email']}")
lines.append("\nB/C. dead deals and stage moves are empty — fill them from the Ruled out tab")
lines.append("     and your notes before running the writer (see SKILL.md Step 9).")
if SENT is not None:
    lines.append(f"\nLeft out (send log): {len(skipped_bounce)} bounced, {len(skipped_unsent)} not sent")
    for b in skipped_bounce:
        lines.append(f"   BOUNCED  {b}")
txt = "\n".join(lines)
open(os.path.join(OUT, "vts_plan.txt"), "w").write(txt)
print(txt)
print(f"\nwrote {OUT}/vts_plan.json")
