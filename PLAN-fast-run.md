# Plan: fast outreach runs (v0.8.0)

Agreed 2026-10-05 after a 2.5-hour Cathedral Commons night (36 emails, 23 VTS deals) that should
have taken 30–40 minutes. The time went to round trips, re-screening, bad contacts and undoing VTS
comments — not to writing or logging. Goal: **Spencer approves a screened list once; send, bounce
handling and VTS logging finish without him running anything.**

## Decisions
- **Drafts stay the default.** Headless send is an opt-in flag (`--send`).
- **Bounce wait: 5 minutes** before any VTS write.
- **Rules live with the listing**: `<listing folder>/outreach-rules.md`
  (first one: `Landlords/Bozzuto/Cathedral Commons/outreach-rules.md`).

## Work, in order

### 1. Fix: VTS writer reads only 100 deals  *(ship first, on its own)*
`skills/listing-outreach/scripts/emit_vts_js.py` → `DEALS()` fetches page 1, page_size 100.
Cathedral Commons has 180 → duplicate check blind to 80 → duplicate deals. Walk every page and
fail closed if the count disagrees with `total_count` (same loop the VTS toolkit uses).

### 2. Per-listing rules file
`outreach-rules.md` read at Step 1 so the list is screened *before* research, not after.
Sections: exclusives (as category bans), geographic disqualifiers, category screens (e.g. no
fitness; apparel only if not in Georgetown/Bethesda), broker rule per category (restaurants:
skip brokered; non-food: OK), landlord preferences (Bozzuto: high-end if N12 goes non-food),
pitch points (2 hrs free validated parking; ~23,000 cars/day on Wisconsin; no food talk in
non-food emails), and a "never contact" list.

### 3. Stronger contact vetting before send
- MX check (already done ad hoc) becomes a hard gate.
- Flag a contact whose newest index record is old or **future-/mis-dated** (the Matt Alexander
  case: index ranked his old Cushman address as newer off a "08/31/28" row).
- A known-moves file (`~/.listing-outreach/people_moves.json`): Amanda left DochAlex ~2023;
  Matt Alexander = DochAlex, not Cushman. Applied to every list.
- Fill gaps index → Lusha → web; print the Lusha credit cost before spending.
- Check the target is OPEN; closed businesses never reach the list or VTS.

### 4. `--send` mode
Headless Mail.app send, one at a time, flyer attached, per-address JSON log so a crash or
re-run can never double-send (tonight's `s3_send.py` shape). Drafts path unchanged.

### 5. Bounce gate before VTS
After the last send: wait 5 min, read bounces from the Mail Envelope Index (copy with -wal/-shm;
match recipients inside the bounce .emlx). Then create deals with contacts attached, comment
"Submitted site." only on delivered rows, and list bounces for re-sourcing. No comment on a bounce.

### 6. One permission rule (Spencer, once)
Allow the plugin's send command from an interactive `claude` terminal so the auto-mode
classifier stops blocking it. Everything else stays gated.

## End state
"Run outreach on N12, high-end non-food, 5 targets" → screened + contacted list → "go" →
one summary: sent / bounced / logged.

## Notes
- `lib/lo_blasts.py` and `lib/lo_graph.py` have uncommitted changes in the repo as of this plan —
  look before touching them.
- Releasing = bump `version` in `.claude-plugin/plugin.json`, commit, push (see RELEASING.md).
  Pushing reaches every user of the plugin; confirm with Spencer before each push.
