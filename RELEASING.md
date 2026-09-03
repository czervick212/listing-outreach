# Releasing

Users only receive updates when the `version` in `listing-outreach/.claude-plugin/plugin.json`
is bumped. Bump it on **every** release, or your changes reach no one.

1. Make the change.
2. Bump `version` in `listing-outreach/.claude-plugin/plugin.json` (semver).
3. Commit and push to the GitHub repo backing this marketplace.
4. Users update with: "ask Claude to update the listing outreach plugin," or
   `claude plugin marketplace update outreach-tools && claude plugin update listing-outreach`.

Auto-update is OFF by default for third-party marketplaces. Each user enables it once via
`/plugin` → Marketplaces → `outreach-tools` → Enable auto-update.

## Notes

- `claude plugin ...` are ordinary shell commands, so Claude can install/update the plugin
  itself; only the `/plugin` slash UI needs the user.
- Account-specific data lives in `~/.listing-outreach/config.json`, never in the repo — updates
  never clobber a user's setup.
- Keep user-facing strings written for a broker, not a programmer.
