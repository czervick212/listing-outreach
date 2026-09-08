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

## Notes

- `claude plugin ...` are ordinary shell commands, so Claude can install/update the plugin
  itself; only the `/plugin` slash UI needs the user.
- Account-specific data lives in `~/.listing-outreach/config.json`, never in the repo — updates
  never clobber a user's setup.
- Keep user-facing strings written for a broker, not a programmer.
