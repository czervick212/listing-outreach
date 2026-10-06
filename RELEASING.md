# Releasing

Users only receive updates when the `version` in `listing-outreach/.claude-plugin/plugin.json`
is bumped. Bump it on **every** release, or your changes reach no one.

1. Make the change.
2. Bump `version` in `listing-outreach/.claude-plugin/plugin.json` (semver).
3. Commit and push to the GitHub repo backing this marketplace.
4. Users update with: "ask Claude to update the listing outreach plugin," or
   `claude plugin marketplace update outreach-tools && claude plugin update listing-outreach`.

Auto-update is OFF by default for third-party marketplaces — so a released fix reaches
nobody who hasn't turned it on. Setup Step 5 now asks every new user and, on a yes, runs
`lib/lo_autoupdate.py enable` (it sets the `autoUpdate` flag in Claude Code's
`known_marketplaces.json`; there's no CLI subcommand for it). The main skill checks `status`
and nudges once for anyone who installed before that step existed. The `/plugin` →
Marketplaces → `outreach-tools` menu route still works if a user prefers it.

## Version history

| version | change |
|---|---|
| 0.8.0 | fast runs: VTS writer reads every page (was 100 deals — blind duplicate check) and no longer crashes on a stray `%`; per-listing `outreach-rules.md`; `vet_contacts.py` (MX, people moves, mis-dated index rows); opt-in `--send` with a 5-minute bounce gate; `build_vts_plan.py --send-log` logs delivered rows only; plus the shared-inbox greeting and kept-flyer fixes |
| 0.7.0 | follow-ups + read receipts: per-listing blast logs, nudges at 3/10 business days drafted as thread replies, daily 7 AM schedule, receipts per blast (Apple Mail via a watched mailbox-wide switch) |
| 0.6.0 | any listing type, and local operators as a list source |
| 0.5.0 | Outlook backend over Microsoft Graph — works on New Outlook, Mac or Windows |
| 0.4.0 | ask every user to turn on auto-update at install |
| 0.3.1 | release the VTS timestamp fix |
| 0.3.0 | script the proximity / relocation classifier (Step 3+4) |
| 0.2.0 | Windows support for the email half |
| 0.1.0 | first release |

## Notes

- `claude plugin ...` are ordinary shell commands, so Claude can install/update the plugin
  itself; only the `/plugin` slash UI needs the user.
- Account-specific data lives in `~/.listing-outreach/config.json`, never in the repo — updates
  never clobber a user's setup.
- Keep user-facing strings written for a broker, not a programmer.
