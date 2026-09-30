---
name: listing-outreach-setup
description: First-run setup and health check for the Listing Outreach toolkit — install the one dependency, capture the user's identity (name, sending email, VTS deal-lead id) and VTS taxonomy, connect their mail (Outlook or Apple Mail), and verify Chrome + VTS are reachable. Use when someone installs the plugin, says "set up listing outreach", "configure the outreach tool", "get /listing-outreach working", or when the main skill reports config is missing.
---

# Listing Outreach — Setup

The main skill needs three things about the user, none of which can be assumed: who they are
(to sign the emails and be the VTS deal lead), what address the outreach sends from, and their
VTS account's taxonomy ids. This captures all of it into `~/.listing-outreach/config.json` so
plugin updates never clobber it.

Config commands (paths use `${CLAUDE_PLUGIN_ROOT}`; substitute the real path if the plugin
isn't loaded into this session yet):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" show
```

## Step 1 — Dependency

The scripts need `openpyxl`. Check and install:

```bash
python3 -c "import openpyxl" 2>/dev/null && echo ok || python3 -m pip install --user openpyxl
# Windows: python -m pip install --user openpyxl pywin32
```

Cross-platform. `pywin32` is only needed for the **classic Outlook COM** path on Windows — skip
it if they'll use Outlook via Graph (Step 4), which is stdlib-only. Apple Mail needs no extra
dependency either. The VTS-write half (Chrome) works everywhere. See `references/windows.md`.

## Step 2 — Identity

Ask the user for their name and the email address the outreach should send from. Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set user.name "Their Name"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set user.email "them@firm.com"
```

## Step 3 — VTS taxonomy and deal-lead id

**If they already use the VTS Leasing Toolkit**, everything needed is already discovered —
import it in one call:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" import-from-vts
```

That copies their VTS user id, the retail-industry id, the new-deal type id, and the
dead-deal reason ids from `~/.vts-toolkit/vts-config.json`.

**If they don't**, discover it from an open, logged-in VTS tab in Chrome (connect first —
`list_connected_browsers` → `select_browser` → `tabs_context_mcp`; a "not connected" error
almost always means no browser is selected, not a broken extension). Run in `javascript_tool`:

```js
const v = window.vts || {};
const H={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'};
const ref = v.reference_data || {};
({ user_id: v.user && v.user.id,
   industries: (ref.tenant_industries||[]).filter(i=>/retail/i.test(i.name)).map(i=>`${i.id}:${i.name}`),
   deal_types: (ref.deal_types||[]).map(t=>`${t.id}:${t.name}`),
   dead_reasons: (ref.dead_deal_reasons||ref.activity_log_iteration_reasons||[]).map(r=>`${r.id}:${r.name}`) })
```

Then set the values (retail-general industry id, "new" deal-type id, and the deal-lead id):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set user.vts_user_id 12345
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set vts.tenant_industry_id 122
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set vts.deal_type_id 1
```

The dead-deal reason ids are needed to mark passes dead. Store them under
`vts.dead_deal_reasons` (import-from-vts does this automatically); at minimum capture
`requirement_dead` and `cannibalization_risk`.

## Step 4 — Mail

**Ask which mail client they actually use for work.** Don't infer it from the operating system —
plenty of Mac users have never opened Apple Mail, and New Outlook is now the default on both
platforms. Full detail in `references/mail-backends.md`.

**Outlook (either platform, new or classic) → the Graph backend.** This is the answer for most
people. It needs a one-time app registration in their own Microsoft 365 organization; walk them
through it rather than pasting the whole list at once:

> portal.azure.com → **App registrations** → **New registration** → name it `Listing Outreach`,
> **Register** → **Authentication** → **Add a platform** → **Mobile and desktop applications** →
> tick the `nativeclient` box → **Configure** → **Advanced settings** → **Allow public client
> flows: Yes** → **Save** → **Overview** → copy the **Application (client) ID**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.graph.client_id <application-id>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.backend graph
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_graph.py" login      # prints a code; they sign in
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_graph.py" status     # confirm the account
```

If their organization blocks user app registrations, or requires an admin to approve the
sign-in, **say so plainly and don't fight it** — the error text in `lo_graph.py` names which
one it is. IT can either grant the app or create the registration and hand back the client ID.
Until then they send from the target sheet by hand; everything else in the toolkit still works.

**One registration covers a whole firm.** A single-tenant app registered once serves every
colleague in that Microsoft 365 organization — they each just sign in to it. Only someone
outside the organization needs their own.

**No registration at all?** If a Microsoft 365 connector is available in the session, reply
tracking still works — Claude searches their Outlook and feeds the results to
`scan_replies.py --messages`, per the main skill's Step 10. Drafting is the only half that
truly requires Graph. Leave `mail.backend` unset in that case.

**Apple Mail →** nothing to configure, it's the macOS default. `cleanup_drafts.py` deletes from
an account named `Exchange` unless told otherwise:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.backend apple-mail
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.account "Work"
```

**Classic Outlook on Windows →** `set mail.backend outlook-com`, and `pywin32` from Step 1.

## Step 5 — Follow-ups

Ask: *"Want me to draft follow-ups automatically? Every weekday at 7 AM I check your open
blasts, and anyone who hasn't replied after 3 business days (then 10) gets a nudge drafted
as a reply on the original email, ready for you to review and send."* If yes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/listing-outreach/scripts/followups.py" schedule install
```

Optional: a copy of the daily due list somewhere they'll see it, e.g. a note their daily
note embeds (Obsidian: `![[Outreach Follow-ups]]`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set followups.due_note "<path/to/Outreach Follow-ups.md>"
```

On a Mac using Apple Mail, the first scheduled run may ask to let `python3` control Mail (to
open the reply drafts) — they allow it once. The scheduled job runs with `/usr/bin/python3`;
if it can't read Mail it logs that to `~/.listing-outreach/followups.log`, and granting
`/usr/bin/python3` Full Disk Access fixes it.

## Step 6 — Auto-update

**Do not skip this, and do not decide it silently — ask.** Auto-update is OFF by default for
third-party marketplaces, so without this the user is frozen at the version they installed and
bug fixes never reach them.

Ask plainly: *"Want the toolkit to update itself when I ship fixes? Otherwise you stay on this
version until you ask for an update."* If they say yes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_autoupdate.py" enable
```

That flips one flag in Claude Code's own marketplace store. If they'd rather not, leave it —
`status` reports the current state, and they can update by hand whenever:

```bash
claude plugin marketplace update outreach-tools && claude plugin update listing-outreach
```

## Step 7 — Confirm

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" show
```

A clean `show` (exit 0) means ready. Then tell them how to run it: "hand me a new listing —
the address, the tenant categories you're chasing, and the flyer — and say *blast this
listing*." The main skill (`/listing-outreach`) drives the rest.
