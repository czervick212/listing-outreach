---
name: listing-outreach-setup
description: First-run setup and health check for the Listing Outreach toolkit — install the one dependency, capture the user's identity (name, sending email, VTS deal-lead id) and VTS taxonomy, and verify Mail + Chrome + VTS are reachable. Use when someone installs the plugin, says "set up listing outreach", "configure the outreach tool", "get /listing-outreach working", or when the main skill reports config is missing.
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

Cross-platform. On **Windows** also install `pywin32` (provides Outlook COM) — the command
above becomes `python -m pip install --user openpyxl pywin32`, and the user needs **classic
Outlook** (New Outlook has no COM). On **macOS** the email half drives Mail.app and needs no
extra dependency. The VTS-write half (Chrome) works everywhere. See `references/windows.md`.

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

## Step 4 — Mail account (optional)

`cleanup_drafts.py` deletes leftover drafts from a named Mail account, defaulting to
`Exchange`. If the user's work mail sits under a differently-named account, set it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.account "Work"
```

## Step 5 — Confirm

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" show
```

A clean `show` (exit 0) means ready. Then tell them how to run it: "hand me a new listing —
the address, the tenant categories you're chasing, and the flyer — and say *blast this
listing*." The main skill (`/listing-outreach`) drives the rest.
