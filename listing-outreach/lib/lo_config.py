#!/usr/bin/env python3
"""Config for the Listing Outreach toolkit — everything account-specific lives here,
never in the skill prose or the scripts, so a plugin update never clobbers a user's setup.

Stored at ~/.listing-outreach/config.json. Shape:

{
  "user": {
    "name": "Jane Broker",              # signs the emails; deal lead on VTS writes
    "email": "jbroker@example.com",     # From: address on the outreach mail
    "vts_user_id": 12345                # OPTIONAL — only to log submittals to VTS
  },
  "contact_index": "",                  # optional; path to a contact_index.json, which
                                        # gives the contact cascade its two free rungs
                                        # before Lusha. Unset = start the cascade at Lusha.
  "vts": {                              # OPTIONAL — the VTS logging steps only
    "tenant_industry_id": 122,          # "Retail (General)" on most accounts
    "deal_type_id": 1,                  # "New Deal"
    "dead_deal_reasons": { "requirement_dead": 35, ... }
  },
  "mail": {                             # optional; the email half only
    "backend": "graph",                 # graph | apple-mail | outlook-com. Unset = decide:
                                        #   Graph if configured, else the platform default
    "account": "Exchange",              # Apple Mail account holding Drafts (that path only)
    "graph": {
      "client_id": "<application-id>",  # their own Azure app registration — see lo_graph.py
      "tenant": "organizations"         # or their tenant id, if they were given one
    }
  }
}

The `vts` block is identical to what the VTS Leasing Toolkit already discovers, so if that
plugin is set up, `import-from-vts` copies it over instead of asking again.

    python3 lib/lo_config.py show
    python3 lib/lo_config.py set user.name "Jane Broker"
    python3 lib/lo_config.py import-from-vts
"""
import json, os, sys

HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(HOME, ".listing-outreach")
CFG = os.path.join(CFG_DIR, "config.json")
VTS_CFG = os.path.join(HOME, ".vts-toolkit", "vts-config.json")


def load():
    if not os.path.exists(CFG):
        return {}
    with open(CFG) as f:
        return json.load(f)


def save(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(cfg, f, indent=2)


def _dig(cfg, dotted):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(cfg, dotted, value):
    keys = dotted.split(".")
    cur = cfg
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    # coerce ints
    try:
        value = int(value)
    except (ValueError, TypeError):
        pass
    cur[keys[-1]] = value


def is_ready(cfg):
    """Enough to run an outreach pass. VTS is NOT required.

    Outreach has two halves: building a target list and mailing it, which need only
    an identity; and logging submittals back to VTS, which needs the VTS block. A
    canvass of local operators -- dentists, vets, a regional chain with no corporate
    real estate team -- never touches VTS at all, and demanding vts_user_id up front
    stopped that user before they started.
    """
    return bool(_dig(cfg, "user.name") and _dig(cfg, "user.email"))


def contact_index(cfg):
    """Path to the user's contact index, or "" -- rungs 1-2 of the contact cascade.

    Entirely optional. With it, the free rungs answer most of a chain list before any
    Lusha credit is spent; without it the cascade simply starts at Lusha. Nobody needs
    to build an index to run an outreach pass.
    """
    return _dig(cfg, "contact_index") or ""


def vts_ready(cfg):
    """Enough to write submittals back to VTS -- checked only by the VTS steps."""
    return bool(_dig(cfg, "user.vts_user_id") and _dig(cfg, "vts"))


def main():
    args = sys.argv[1:]
    cfg = load()
    if not args or args[0] == "show":
        if not cfg:
            print("NOT SET UP — run /listing-outreach-setup", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(cfg, indent=2))
        if not is_ready(cfg):
            print("\n(incomplete — user.name and user.email are required; "
                  "user.vts_user_id + vts.* only if you log submittals to VTS)",
                  file=sys.stderr)
            sys.exit(2)
        return
    if args[0] == "set" and len(args) >= 3:
        _set(cfg, args[1], " ".join(args[2:]))
        save(cfg)
        print(f"set {args[1]}")
        return
    if args[0] == "import-from-vts":
        if not os.path.exists(VTS_CFG):
            print("no VTS toolkit config at ~/.vts-toolkit/vts-config.json — set the "
                  "vts.* values manually or run VTS setup first", file=sys.stderr)
            sys.exit(1)
        v = json.load(open(VTS_CFG))
        cfg.setdefault("vts", {})
        if "ids" in v:
            cfg["vts"]["tenant_industry_id"] = v["ids"].get("tenant_industry_retail_general", 122)
            cfg["vts"]["deal_type_id"] = v["ids"].get("deal_type_id", 1)
            cfg["vts"]["dead_deal_reasons"] = v["ids"].get("dead_deal_reasons", {})
        if "user" in v:
            cfg.setdefault("user", {})
            cfg["user"].setdefault("name", v["user"].get("name"))
            cfg["user"].setdefault("email", v["user"].get("email"))
            cfg["user"].setdefault("vts_user_id", v["user"].get("id"))
        save(cfg)
        print("imported user + vts taxonomy from the VTS toolkit config")
        return
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
