---
name: listing-outreach
description: Blast any retail listing to maximum coverage — inline space, junior box, second-gen restaurant, pad site or ground lease. Builds a vetted target list from whichever source fits the tenant you are chasing (a comparable VTS pipeline, web research on expanding chains, or the local operators actually trading near the site), finds the right contact for each, writes one personalized email per person with the flyer attached, opens them as reviewable drafts (Outlook either platform, or Mail.app), logs every send back to VTS when VTS is in play, and follows up: optional read receipts, and nudges drafted as replies on the original thread for anyone who hasn't answered after 3 and 10 business days. Use when the user picks up a listing and wants market coverage, says "blast this listing", "who should we send this to", "run outreach on <property>", "canvass the market for <site>", "find every <use> near <address>", "maximum coverage on the new listing", or hands over a flyer and asks who to pitch. Also use for "who opened / read my email", "any follow-ups due", "follow up on the <listing> blast", "which brokers haven't replied". Works for national chains and for local operators — dentists, vets, salons, restaurants — and runs with or without VTS.
---

# New Listing Outreach

Turn a new listing into a canvass: every plausible tenant, the right broker for each, one
email per person, and a VTS record of every submittal. The notes below are what actually goes
wrong doing this by hand — follow the reasoning, not just the letter.

**Config first.** User identity and VTS taxonomy live in `~/.listing-outreach/config.json`.
Run `python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" show` — exit code 2 means it's never been
set up; stop and run `/listing-outreach-setup`. Scripts take the listing's paths and property id
as arguments; nothing about any one user's filesystem is baked in.

**VTS is optional.** Only Steps 1a and 9 touch it. A canvass of local operators never does, so
`is_ready()` asks for name and email only — don't send someone to VTS setup to email twelve
dentists. Check `vts_ready(cfg)` before the VTS steps and skip them cleanly if it's false.

**Auto-update, once.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_autoupdate.py" status`. If it
prints `off`, the user is frozen on their installed version and fixes never reach them — catches
anyone who installed before setup started asking. Say so **once, after the run is finished**, and
offer `lo_autoupdate.py enable`. Never interrupt an outreach pass for it, and if they decline,
drop it — don't raise it again next run.

## Inputs to collect first

1. **The listing** — address, the space (SF for inline or a box, acreage for a pad), and the
   deal structure: lease, sale, ground lease, or several on offer. "Pad" is one case, not the
   default; plenty of these listings are an inline suite or a second-gen restaurant.
2. **Target tenant categories** — coffee drive-thru, QSR, car wash, quick lube, banks, early
   education, EV, vet, medical, dental, salon, fitness. Ask; do not assume from the address.
   **The answer decides which list source to use in Step 1** — a national-chain category and a
   local-operator category are gathered completely differently.
3. **The flyer** — a path. Copy it somewhere normal (next to the listing); a file under the
   Mail container's Downloads cannot be reliably attached by AppleScript.
4. **The email they want** — ask them to write it, or draft one and have them rewrite it. Expect
   two or three passes, and keep it short: the common note is "too much info."
5. **The follow-up** — draft it alongside the email, one message for the whole blast, so the
   user approves both at once. Nudge 1 goes 3 business days after the original, nudge 2 at 10
   (a short "last note" is fine; leave it out and there is only one nudge). Placeholders:
   `{first_name}` (falls back to "there", and always "there" for shared inboxes like info@ /
   reservations@), `{tenant}`, `{listing}`. **Write it to stand on its own**: one line that
   names the space (size + what it is + where), one line with the ask for `{tenant}`. Never a
   bare "just checking in" — on Apple Mail the original is NOT quoted underneath (Mail's quote
   can't be scripted), and on a shared inbox the reader may never have seen the first email.
   The flyer is re-attached to every nudge automatically. Example:
   "Hi {first_name}, following up on the 4,169 SF second-generation restaurant space at
   Cathedral Commons in upper NW DC. Still available. Any interest for {tenant}?"
6. **Read receipts?** Ask, yes or no, per blast. Be straight about what they are: most
   recipients' mail apps ask "send a receipt?" (many say no), Gmail and Apple Mail never send
   one, so silence means nothing. On Apple Mail the switch is mailbox-wide while the blast
   sends — see Step 8.

## Step 0 — Read the listing's rules file first

Look for `outreach-rules.md` in the listing's own folder (next to the flyer). It holds what
the user has already decided for this property: exclusives, category screens ("no fitness"),
geographic disqualifiers, broker rules per category, landlord preferences, pitch points
that go in every email, a never-contact list, VTS comment wording. **Screen against it while
building the list, not after** — researching 20 brands and having the user cut 15 of them is
the slowest possible loop. When the user adds or changes a rule mid-run, write it into the
file before moving on. No file yet? Create one from what they tell you in this run.

## Step 1 — Build the target list

Three sources. Which one (or two) applies follows from the category the user named in the
inputs, not from a mode they pick. Getting this wrong wastes the whole pass: national chains
and local operators live in completely different places.

| chasing | use | why |
|---|---|---|
| national/regional chains | **1a** VTS pipeline, then **1b** web research | they have a real estate department and deal history |
| local operators — dentists, vets, salons, independent F&B | **1c** who trades nearby | no corporate RE team, no deal history, not on any roster |

### Step 1a — Seed from a comparable VTS property *(chains; needs VTS)*

**Highest-leverage step for a chain, and not obvious.** Don't start from a blank tenant list. Find a
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

### Step 1b — Extend with web research *(chains)*

The VTS pipeline only reaches tenants who have already done a deal with this shop. For a
category it has never traded, research who is actually expanding — and **verify anything whose
fit depends on a current prototype or expansion push** (e.g. "X just launched a smaller
drive-thru-only building for tight lots") with a search before you put it on the sheet. That
kind of claim goes stale fast and training data alone is not good enough to state as current
fact. Cite what you find, and keep confirmed ideas visibly separate from speculative ones.

### Step 1c — The operators already trading nearby *(local)*

Neither source above finds a three-office dental group. Read the operators out of OSM:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/find_local_operators.py" \
  "<site address>" --uses dentist --radius-mi 5 [--exclude-chains] [--csv out.csv]
```

Uses: dentist, medical, vet, pharmacy, fitness, childcare, carwash, auto, salon, grocery,
liquor, pet, coffee, bank, food. Several at once is fine. It returns name, distance, address,
phone and website where OSM has them, and marks each row local or chain by how many sites that
brand has in the area — no brand list to maintain.

Two honest limits, and say them to the user rather than letting the list look complete:

- **OSM is volunteer-mapped**, and it maps chains better than independents — the opposite of
  what you want here. Good start on a canvass, never the whole market.
- **A state licensing roster is the complete source** where one exists (dental board, vet board,
  ABC). Use it when the canvass has to be exhaustive rather than quick.

It returns no contacts at all, by design: OSM carries a business, not a person. Those rows go
through Step 5 exactly like a chain with nobody on file.

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
bbox Overpass query and filter names client-side — **a regex-over-area `name~"..."` query times
out.** `--uses` sets which OSM tags to look for and shares its vocabulary with Step 1c, so the
two can never disagree about what a dentist is. It defaults to food and banks, which was once
hardcoded: on a dental or salon canvass that found zero competitors and read every target as a
fresh market.

`classify_proximity.py` does all of this (stdlib only, no keys):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/classify_proximity.py" \
  "<site address>" --brands "Chipotle,Panera,Wendy's" [--barrier "I 270"] [--radius-mi 3] \
  [--uses food,coffee]
```

Per brand it returns distance, which side of the barrier, the OSM drive-through flag, and a
suggested verdict — SKIP (same side, close, has a drive-through), RELO (across the barrier, or a
store with no drive-through the pad can offer), VERIFY (same side & close but OSM has no
drive-through data — check the store), or a fresh-submittal note when no nearby store exists.
Verdicts are advisory; confirm on the Ruled out tab. OSM drive-through tagging is sparse, so
VERIFY is common and honest — don't let a missing tag assert a relo.

## Step 4 — A tenant already in the market is a relocation, not a dead end

If a tenant trades nearby but their store lacks the format the pad offers — no drive-thru, wrong
side of the barrier — that's a *relo pitch*, not an exclusion. Check the brand's own location
page for the drive-thru feature before assuming. Two email variants:

- **Fresh submittal** — "We just picked up the listing at X so you may have already looked at
  this, but would <tenant> consider doing a deal at either of the pads?"
- **Relo** — "...so you may have already looked at this. I know <tenant> is already in the market
  but wanted to check if they need a relo. <one line on why>."

## Step 5 — Find the contact: cheapest evidence first, and never invent an address

**Stop and get the list signed off before this step.** Contacts are where the money and the
time go — Lusha burns credits, web research burns minutes — and the list always changes on
first read. Show the user the targets, let them drop categories, add names and flag concepts
they have already tried. Expect a couple of rounds; it is cheap here and expensive after.

Then work down the rungs, taking the first answer you can stand behind. This is a cost order
as well as a quality order:

| rung | source | cost | reaches |
|---|---|---|---|
| 1 | a contact already on a deal with us | free | anyone we have traded with |
| 2 | our own mail archive | free | anyone we have corresponded with |
| 3 | Lusha | credits | corporate site-selection roles |
| 4 | public web search | minutes | local operators — the only rung that does |

Rungs 1–2 come from the contact index if the user has one — `contact_index.json` and
`resolve.py`, pointed at by `contact_index` in config. No index, start at rung 3. Either way,
**run rungs 1–2 over the whole list before spending a single credit**, then let Lusha work the
short list of what is left. Say how many credits a Lusha pass will cost before running it, and
the total spent after.

**Don't trust the index's "newest" address blindly.** It orders a person's addresses by deal
date, and a mis-dated row (a year in the future) makes an old firm's address look current —
that sent a pitch to a broker's former employer. `vet_contacts.py` (Step 7b) flags it; when
in doubt, check the firm's current team page.

A local operator will fall to rung 4 every time, and that is correct, not a failure. Their
contact is usually the owner behind a front-desk `info@`, which is a lower hit rate than broker
outreach — say so rather than letting the sheet look fuller than it is.

**Title rules:** prefer Real
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
Targets columns, in order: Tenant · Tier · Category · **Space** · Broker / Contact · Firm ·
Email · Email source · Status · Subject · Email Draft · Send Email · **Your notes** · Where
this came from · Notes. The scripts find columns by these header names, so keep them.

**`Space`** says which part of the listing this target is being pitched — "Pad A", "Suite 210",
"the 4,169 SF restaurant box", "whole building". It was called `Pad` when this only did pad
sites; a one-word rename, but do not revert it and do not leave a `Pad` header behind, or a
sheet built today and a script from yesterday disagree silently.

**`Email source`** carries which rung the address came from, and it earns its place: a Lusha
guess and a broker you emailed last week are not the same confidence, and the person deciding
whether to send needs to see which is which. Mark a constructed address as derived, never as
found.

- **`Your notes` is the user's column.** Read it back on every rebuild and re-apply it, matched
  on tenant name, or you destroy their work. Freeze panes at `B2`.
- **Notes** carries the source VTS stage + last comment — what makes the sheet auditable.
- Cap mailto links well under 2,000 chars or Excel silently truncates them. (The short email
  template keeps them ~500.)

## Step 7b — Vet every address before anything opens or sends

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/vet_contacts.py" <targets.xlsx>
```

Checks each address for an MX record, against `~/.listing-outreach/people_moves.json` (who
left a firm, who moved where, do-not-contact), and — with a contact index — for a "newest"
date that's in the future (a mis-dated row) or more than two years old. **Exit 1 = a row is
blocked; fix it before Step 8.** When the user corrects a contact ("she left three years
ago", "he's at X now"), add it to `people_moves.json` on the spot — it's the only check that
remembers. Also confirm each target is still OPEN; a closed business never goes out.

## Step 8 — Open the emails with the flyer attached

`mailto:` **cannot carry an attachment** — that's the protocol. So the drafts are made directly,
through whichever backend is set up (`lib/lo_mail.py` picks it; `references/mail-backends.md`
explains all three):

| backend | where the drafts appear |
|---|---|
| `graph` | the **Outlook Drafts folder** — any Outlook, Mac or Windows, new app or classic |
| `apple-mail` | compose windows on screen (macOS default when Outlook isn't set up) |
| `outlook-com` | compose windows on screen (Windows, **classic** Outlook only) |

**Freeze the blast log first** — follow-ups and receipts both run from it, and the receipts
watcher needs it before the first draft opens:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/build_send_manifest.py" <targets.xlsx> <vts_property_id|0> "<Listing Name>" \
    --followup "<nudge 1>" [--followup2 "<nudge 2>"] [--receipts]
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/make_drafts.py" <targets.xlsx> <flyer.pdf> [--receipts --blast "<Listing Name>"]
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/make_drafts.py" <targets.xlsx> <flyer.pdf> 0 10   # a batch
```

**Read receipts by backend.** Graph and classic Outlook flag each draft. **Apple Mail has no
per-message flag** — `--receipts` switches on Mail's receipt header for the whole mailbox and
starts a background watcher (`lib/lo_receipts.py`) that switches it off the moment every email
in the blast shows in Sent, or after 6 hours regardless. Mail stamps the header at *send* time
(tested), so it must stay on until they're sent — **anything else the user sends in that window
also asks for a receipt. Tell them that in one line when you open the drafts.** `lo_receipts.py
off` ends it instantly; `lo_receipts.py status` says whether it's on.

(`python3` on macOS/Linux, `python` on Windows.) **Nothing is sent** — every draft is reviewed
and sent by hand. On Graph they queue up in Drafts, which is what you want for a 30-broker
blast; on the two local backends each one opens as a visible window. The From: address comes
from config, except on Graph, where mail comes from the mailbox that signed in (the script says
so if the two disagree). Signatures are whatever the client applies — Graph drafts carry none,
so keep the sign-off in the template.

### `--send`: send it now *(Apple Mail; opt-in)*

Drafting stays the default. When the user has approved the list and says to send, use
`--send` instead of opening drafts:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/make_drafts.py" <targets.xlsx> <flyer.pdf> --send   # waits 5 min for bounces
```

It sends one at a time, logs each address to `~/.listing-outreach/sends/<sheet>.json` as it
goes (a re-run never sends twice), then **waits 5 minutes and reads the bounces from Mail**
(`lib/lo_bounces.py`), marking each address delivered or bounced. Then Step 9 with
`--send-log`, so VTS is written for delivered rows only. Bounces come back as a list to
re-source — they get no VTS comment.

Claude Code's auto-mode classifier blocks scripted bulk sends unless the user has allowed this
command. If it's refused, say so plainly and give them the exact command to run — don't hunt
for another route. The one-time fix is a Bash permission rule for `make_drafts.py`, added from
an interactive `claude` terminal.

After sending, `cleanup_drafts.py "<subject fragment>"` clears the leftovers. Graph deletes them
server-side. Apple Mail saves any open windows first, then deletes by subject+date, and still
throttles scripted deletes unpredictably — if it stalls, do it by hand: Drafts → search →
select all → Delete.

## Step 9 — Log every send back to VTS *(only if they use VTS)*

Every email sent becomes a deal on the listing's VTS property with a comment — **"Submitted
site."** or **"Submitted potential relo opportunity."** One deal **per tenant**, not per email.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/build_vts_plan.py" <targets.xlsx> <property_id> [--send-log ~/.listing-outreach/sends/<sheet>.json]
# review ~/.listing-outreach/vts_plan.txt, then fill the dead[] and stage[] arrays in vts_plan.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/emit_vts_js.py" counts
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/emit_vts_js.py" submitted 0 12   # paste into javascript_tool
```

**Never log before the bounces are in.** After a `--send`, pass its log: rows that bounced or
never went are left out of the plan. After hand-sent drafts, wait ~5 minutes and run
`python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_bounces.py" 1 <addresses…>` first. A comment posted on a
bounce has to be found and deleted again — the round trip this rule exists to avoid.

`emit_vts_js.py` reads **every page** of the property's deals before writing and refuses to
write on a partial read. A big property (180+ deals) spans pages; a one-page read made its
duplicate check blind and would have created duplicates.

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

## Step 10 — Follow-ups

`followups.py` runs from the blast logs in `~/.listing-outreach/blasts/` — one per listing, so
several blasts are followed up at once.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/followups.py" schedule install   # once per machine
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/followups.py" status [listing]   # where every blast stands
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/followups.py" run --dry-run      # what today's run would draft
```

The scheduled run (weekdays 7:00 AM) reads recent mail in both directions and, per recipient:
confirms the original actually left (Sent folder, not draft time); logs read receipts ("Read:"
/ "Not read:" messages — never treated as replies); stops for good at any reply; and drafts the
nudge that's due **as a reply on the original thread** — Graph via `createReply`, classic
Outlook via `.Reply()`, Apple Mail via Mail's own `reply` (threads correctly, but Mail's
quoted original isn't scriptable, so on Apple Mail the body is only the nudge + signature —
which is why the nudge text must carry the pitch). The blast's flyer is re-attached to every
nudge; `make_drafts.py` keeps a copy in `~/.listing-outreach/flyers/` the first time it runs. Nudge 2 waits until nudge 1 was actually sent. **Nothing is ever sent.** It then
writes `~/.listing-outreach/followups-due.md` (and a copy at `followups.due_note` in config — a
note the user can embed in a daily note), updates a narrow `Tracking` column on the Targets
sheet when the workbook isn't open, and shows a notification.

- Change the messages later: `followups.py set "<listing>" --followup "..." --followup2 "..."`.
- Give an older blast its flyer: `followups.py set "<listing>" --flyer <flyer.pdf>`.
- Stop a blast: `followups.py close "<listing>"`. Blasts close themselves once everyone has
  replied or had every nudge plus a week.
- A blast made before v0.7.0 only has `send-manifest.json`: `followups.py import-legacy`.
- On Apple Mail the reader uses Mail's Envelope Index (headers only, well under a second); if
  it's unreadable it falls back to walking `.emlx` files, which can take a minute.

## Step 11 (optional) — Track the replies for VTS

Reply tracking works with or without VTS; only the final write-back needs it.

The join table was frozen in Step 8 (`build_send_manifest.py`), so a reply covering several
tenants ("no for three, yes for one") routes back to the exact deals. It reads the most recent
blast's `send-manifest.json`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/scan_replies.py"    # as replies land
```

For mail *we* sent, `(recipient + subject)` is a deterministic key back to the tenant set —
which sidesteps the ambiguity of brokers who span multiple properties. `scan_replies.py` reads
the Inbox through the same backend as the drafting half — Graph, the local `.emlx` store, or
Outlook COM — splits each reply per tenant into `reply-queue.json`, and leaves an `outcome`
field to classify before writing to VTS.

### If they have no mail backend but Claude has their Outlook

Someone on Outlook with **no Graph registration** still gets reply tracking, as long as a
Microsoft 365 connector is available to *you* in this session. The connector can't be called
from a script, so fetch the mail yourself and hand it over:

1. Read `~/.listing-outreach/send-manifest.json` for the recipient addresses and the send date.
2. For **each recipient**, search their Outlook: `sender: <that address>`,
   `afterDateTime: <the send date>`. Per-sender keeps it bounded — never pull a whole inbox.
3. Write the hits to a JSON file. The connector's own field names work as-is; the only two that
   must be present are the sender address and the subject.
4. Match them with the script — same split, same output, no mailbox needed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/scan_replies.py" --messages <replies.json>
```

The search result's `summary` is a ~200-character preview. That is usually enough to classify a
pass, but for anything you are about to write to VTS as a real outcome, read the full message
first — a preview can cut off mid-sentence and reverse the meaning.

**Do the matching in the script, not by eye.** One broker reply legitimately becomes four rows
when that broker was pitched four tenants; that fan-out is exactly what the script exists for.

## Things that will bite you

- **Check who else at the firm is already working the property** — pull the listing's own VTS
  property before sending, and watch for parent-company aliases (a Bridgestone deal is the same
  company as a Firestone row). Near-miss names that are *not* duplicates: Mavis vs Discount Tire,
  AutoZone vs O'Reilly.
- **Master-broker conflict** — if the firm represents a target, the listing agreement may require
  the landlord's prior written consent and cut the commission. Flag those rows.
- **Bulk writes get blocked in auto mode** — a loop creating dozens of drafts or VTS deals
  trips the permission classifier. Ask for a Bash permission rule; don't chunk the batch to slip
  past it.
- **0-byte `.xlsx`** = an online-only cloud placeholder, not corruption. Materialize it first.
- **Attachment size** — a heavy flyer (6 MB+) can stall Mail's Outbox mid-batch and trip
  corporate size gateways on cold sends. If sends stall, quit/reopen Mail; consider a link if it
  recurs. Graph uploads big flyers in chunks and doesn't stall, but the recipient's gateway
  still might.
- **A Graph draft with no flyer is never left behind** — if the attachment upload fails the
  draft is deleted, so a flyerless email can't be sent by accident. Re-run the batch.
