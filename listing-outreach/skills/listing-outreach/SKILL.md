---
name: listing-outreach
description: Blast a new retail listing to maximum coverage — build a vetted tenant/broker target list, write one personalized email per broker with the flyer attached, open them as reviewable Mail.app windows, and log every send back to VTS as "Submitted site." Use when the user picks up a new listing and wants full market coverage, says "blast this listing", "who should we send this to", "run outreach on <property>", "canvass the market for <site>", "maximum coverage on the new listing", or hands over a flyer and asks who to pitch. Also use to refresh outreach on an existing listing.
---

# New Listing Outreach

Turn a new listing into a canvass: every plausible tenant, the right broker for each, one
email per person, and a VTS record of every submittal. The notes below are what actually goes
wrong doing this by hand — follow the reasoning, not just the letter.

**Config first.** User identity and VTS taxonomy live in `~/.listing-outreach/config.json`.
Run `python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" show` — exit code 2 means it's never been
set up; stop and run `/listing-outreach-setup`. Scripts take the listing's paths and property id
as arguments; nothing about any one user's filesystem is baked in.

## Inputs to collect first

1. **The listing** — address, pad/space sizes, deal structure (sale, ground lease, or both).
2. **Target tenant categories** — coffee drive-thru, QSR, car wash, quick lube, banks, early
   education, EV, vet, medical. Ask; do not assume from the address.
3. **The flyer** — a path. Copy it somewhere normal (next to the listing); a file under the
   Mail container's Downloads cannot be reliably attached by AppleScript.
4. **The email they want** — ask them to write it, or draft one and have them rewrite it. Expect
   two or three passes, and keep it short: the common note is "too much info."

## Step 1 — Seed the target list from a comparable VTS property

**Highest-leverage step, and not obvious.** Don't start from a blank tenant list. Find a
property in their VTS with a live pipeline in the same product type — a pad site, a ground
lease, a similar trade area — and pull every deal off it:

```
GET /api/horse/deals?activity_report_filter[properties][]=<ID>
    &activity_report_filter[page]=1&activity_report_filter[page_size]=100
    &properties[]=<ID>&page=1&page_size=100
```

Every address on that pipeline was used on a real deal recently — a better contact set than any
roster scrape. Each deal carries `deal_name`, `status`, `tenant_contact{full_name,company_name,
email,phone}` and `latest_comment`. The comment is gold: it records *why* each tenant passed,
which drives the ruled-out logic below. **The response is an object, not an array** — rows are
under `.activity_logs`. Drive it with `javascript_tool` on a logged-in VTS tab in Chrome.

## Step 2 — Get the landlord's own exclusions

Reconstruct the ruled-out list: tenants carved out of the listing agreement by name, categories
that can't physically fit, competitors already in the node. **Carve-outs are contractual, never
a judgment call.** Keep these on a **Ruled out** tab with the reason — never delete silently.
Give the tab a `Your call` dropdown (Keep out / Pitch anyway) and a `Why` column so the user can
overturn any of them, and re-read that tab on the next pass.

## Step 3 — Proximity: use the barrier, not a radius

The naive rule is "already operating within two miles → cannibalization → skip." Wrong often
enough to matter. **Ask what barrier the market actually uses** — e.g. "which side of the
interstate is their store on?" The interchange, not the mileage, separates the trade areas.

To test it: geocode the site and every competitor store to **rooftop** (ArcGIS
`findAddressCandidates`, `Addr_type: PointAddress` — never Census centerline); pull the barrier
geometry from Overpass (`way["ref"="I 270"]["highway"="motorway"]`); do a nearest-segment
point-side test (sign of the 2D cross product vs. the site's own sign). A latitude comparison is
wrong wherever the road runs diagonally, which it usually does. Find competitor stores with one
bbox Overpass query on `amenity~"fast_food|restaurant|cafe|bank"` and filter names client-side —
**a regex-over-area `name~"..."` query times out.**

## Step 4 — A tenant already in the market is a relocation, not a dead end

If a tenant trades nearby but their store lacks the format the pad offers — no drive-thru, wrong
side of the barrier — that's a *relo pitch*, not an exclusion. Check the brand's own location
page for the drive-thru feature before assuming. Two email variants:

- **Fresh submittal** — "We just picked up the listing at X so you may have already looked at
  this, but would <tenant> consider doing a deal at either of the pads?"
- **Relo** — "...so you may have already looked at this. I know <tenant> is already in the market
  but wanted to check if they need a relo. <one line on why>."

## Step 5 — Fill contact gaps, never invent an address

For tenants with no contact, use an enrichment tool (Lusha, etc.). **Title rules:** prefer Real
Estate, Site Selection, Development, Franchise Development, and — at banks/credit unions —
**Facilities**, which usually owns branch real estate. Reject **Construction** (builds after the
site is picked), **Property Management** (manages existing), and especially **Commercial Real
Estate _Lending_** — at banks, most "Commercial Real Estate" titles are lenders, not site
pickers. If nothing fits, leave the row with no button and say so. A guessed address burns the
contact.

## Step 6 — One email per broker, not per tenant

**Group sends by contact email.** A broker with four listings on the sheet gets one email naming
all four, not four emails. Keep one row per tenant (the user tracks tenants, and notes are
per-tenant), but put the Send button only on the group's first row and mark the others
`in <first name>'s email`. Sort so each group sits together.

- 1 tenant: "Would X consider…"  ·  2: "Would X or Y consider…"  ·  3+: "Would any of these
  have interest?" + a bulleted list.
- Mixed relo/fresh in one group: ask the fresh ones first, then "And I know Y is already in the
  market — wanted to check if they need a relo."

## Step 7 — The workbook

Three tabs: **Targets**, **Site** (the facts, so nobody re-derives them), **Ruled out**.
Targets columns, in order: Tenant · Tier · Category · Pad · Broker / Contact · Firm · Email ·
Email source · Status · Subject · Email Draft · Send Email · **Your notes** · Where this came
from · Notes. The scripts find columns by these header names, so keep them.

- **`Your notes` is the user's column.** Read it back on every rebuild and re-apply it, matched
  on tenant name, or you destroy their work. Freeze panes at `B2`.
- **Notes** carries the source VTS stage + last comment — what makes the sheet auditable.
- Cap mailto links well under 2,000 chars or Excel silently truncates them. (The short email
  template keeps them ~500.)

## Step 8 — Open the emails with the flyer attached

`mailto:` **cannot carry an attachment** — that's the protocol. Script Mail.app instead:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/make_drafts.py" <targets.xlsx> <flyer.pdf>
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/make_drafts.py" <targets.xlsx> <flyer.pdf> 0 10   # a batch
```

Opens each as a **visible compose window** — reviewed, then sent by hand; nothing is saved or
sent. AppleScript gotchas: `POSIX file … as alias` (bare `file:` → -1701); the flyer can't live
in the Mail container; Drafts is nested under the account, not top-level. The From: address
comes from config. After sending, `cleanup_drafts.py "<subject fragment>"` clears any leftover
drafts (it saves open windows first, then deletes by subject+date — Mail throttles scripted
deletes, so if it stalls, do it by hand: Drafts → search → ⌘A → Delete).

## Step 9 — Log every send back to VTS

Every email sent becomes a deal on the listing's VTS property with a comment — **"Submitted
site."** or **"Submitted potential relo opportunity."** One deal **per tenant**, not per email.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/build_vts_plan.py" <targets.xlsx> <property_id>
# review ~/.listing-outreach/vts_plan.txt, then fill the dead[] and stage[] arrays in vts_plan.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/emit_vts_js.py" counts
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/emit_vts_js.py" submitted 0 12   # paste into javascript_tool
```

Also log the negatives: tenants who passed get created and marked `dead_deal` with a reason id.
That's what stops the next canvass re-pitching them.

**The stage-change contract — the one non-obvious API detail, learned the hard way:**

- The iteration POST (`/activity_logs/<id>/activity_log_iterations`) **requires `date` AND an
  inline `comment`.** With just `{status, reason_ids}` it returns 200 but the stage silently
  does NOT move (the iteration is appended as history, never adopted). No comment → 422.
- **That inline comment is validation-only — it does NOT persist.** The visible comment is a
  separate `/activity_log_iteration_comments` POST. So a dead-deal log is: create → flip stage
  (throwaway inline comment) → post the real comment. Never delete the "duplicate" — the inline
  one was never saved.
- `dead_deal` requires a reason id; other stages reject one.
- **"Cannot change deal stage to the same stage" (422)** = already there internally from a
  failed retry — bounce via `initial_inquiry`, then set the target.
- **VTS normalizes new tenant names** (EVgo→EVGo, IONNA→Ionna, Cook Out→Cook out) — match
  created deals back by a NORMALIZED (lowercase-alphanumeric) key, never the exact string.

`emit_vts_js.py`'s `setStage()` and name-matching encode all of this — use it rather than
hand-rolling the calls.

## Step 10 (optional) — Track the replies

Freeze the join table at send time, so a reply covering several tenants ("no for three, yes for
one") routes back to the exact deals:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/build_send_manifest.py" <targets.xlsx> <property_id> "<Listing Name>"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/scan_replies.py"    # later, as replies land
```

For mail *we* sent, `(recipient + subject)` is a deterministic key back to the tenant set —
which sidesteps the ambiguity of brokers who span multiple properties. `scan_replies.py` reads
the local `.emlx` store (never the Outlook MCP — unusable headlessly), splits each reply per
tenant into `reply-queue.json`, and leaves an `outcome` field to classify before writing to VTS.

## Things that will bite you

- **Check who else at the firm is already working the property** — pull the listing's own VTS
  property before sending, and watch for parent-company aliases (a Bridgestone deal is the same
  company as a Firestone row). Near-miss names that are *not* duplicates: Mavis vs Discount Tire,
  AutoZone vs O'Reilly.
- **Master-broker conflict** — if the firm represents a target, the listing agreement may require
  the landlord's prior written consent and cut the commission. Flag those rows.
- **Bulk writes get blocked in auto mode** — a loop creating dozens of Mail drafts or VTS deals
  trips the permission classifier. Ask for a Bash permission rule; don't chunk the batch to slip
  past it.
- **0-byte `.xlsx`** = an online-only cloud placeholder, not corruption. Materialize it first.
- **Attachment size** — a heavy flyer (6 MB+) can stall Mail's Outbox mid-batch and trip
  corporate size gateways on cold sends. If sends stall, quit/reopen Mail; consider a link if it
  recurs.
