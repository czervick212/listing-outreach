#!/usr/bin/env python3
"""Turn on auto-update for the marketplace this plugin ships in.

Third-party marketplaces have auto-update OFF by default, so a user who installs
the plugin once stays frozen at that version — bug fixes never reach them. The
setting is a per-marketplace flag in Claude Code's own known_marketplaces.json;
there is no CLI subcommand for it, so we edit the file.

Only ever called after the user says yes. `status` reports without touching it.

    python3 lo_autoupdate.py status
    python3 lo_autoupdate.py enable
"""
import json
import pathlib
import sys

MARKETPLACE = "outreach-tools"
STORE = pathlib.Path.home() / ".claude/plugins/known_marketplaces.json"


def load():
    if not STORE.exists():
        sys.exit(f"No marketplace store at {STORE} — is Claude Code installed?")
    try:
        return json.loads(STORE.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{STORE} is not valid JSON ({e}) — leaving it alone.")


def entry(data):
    if MARKETPLACE not in data:
        known = ", ".join(sorted(data)) or "none"
        sys.exit(
            f"Marketplace '{MARKETPLACE}' is not installed (found: {known}).\n"
            "Run: claude plugin marketplace add czervick212/listing-outreach"
        )
    return data[MARKETPLACE]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    data = load()
    on = bool(entry(data).get("autoUpdate"))

    if cmd == "status":
        print("on" if on else "off")
        return

    if cmd != "enable":
        sys.exit(f"Unknown command '{cmd}' — use 'status' or 'enable'.")

    if on:
        print(f"Auto-update was already on for {MARKETPLACE}.")
        return

    data[MARKETPLACE]["autoUpdate"] = True
    # Write via a temp file in the same dir so a crash can't truncate the store.
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(STORE)
    print(f"Auto-update is now on for {MARKETPLACE}. Fixes arrive on their own.")


if __name__ == "__main__":
    main()
