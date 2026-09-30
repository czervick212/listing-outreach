#!/usr/bin/env python3
"""Read receipts for Apple Mail — a mailbox-wide switch, held open only while a blast sends.

Graph and classic Outlook set a read-receipt flag on each draft. Apple Mail has no such
flag: its only lever is the hidden `UserHeaders` preference, which adds a header to every
message Mail sends while it is set. Tested 2026-09-29 against Exchange:

  * Mail stamps the header at the moment of SENDING, not when the draft is created —
    turning it off before pressing Send leaves the email without it.
  * Mail reads the preference live. No relaunch needed in either direction.

So for a blast with receipts the switch goes ON when the drafts open and must stay on until
they have all been sent. Anything ELSE the user sends in that window also asks for a
receipt, so it comes off the moment the blast is fully in Sent (`watch`), after a hard
deadline regardless, or on demand (`off`).

    python3 lo_receipts.py status
    python3 lo_receipts.py on <blast-slug> [--hours 6]
    python3 lo_receipts.py off
    python3 lo_receipts.py watch <blast-slug>     # started in the background by make_drafts
"""
import datetime
import json
import os
import plistlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lo_blasts  # noqa: E402

DOMAIN = "com.apple.mail"
HEADER = "Disposition-Notification-To"
STATE = os.path.join(lo_blasts.BASE, "receipts-on.json")
LOG = os.path.join(lo_blasts.BASE, "receipts.log")
DEFAULT_HOURS = 6
POLL_SECONDS = 180


def _log(msg):
    os.makedirs(lo_blasts.BASE, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{lo_blasts.iso(lo_blasts.now())}  {msg}\n")


def _headers():
    """Mail's current UserHeaders dict (empty if unset)."""
    p = subprocess.run(["defaults", "export", DOMAIN, "-"], capture_output=True)
    if p.returncode != 0:
        return {}
    try:
        return dict(plistlib.loads(p.stdout).get("UserHeaders") or {})
    except Exception:
        return {}


def _write_headers(h):
    """Replace UserHeaders, keeping whatever other custom headers the user already had."""
    if not h:
        subprocess.run(["defaults", "delete", DOMAIN, "UserHeaders"], capture_output=True)
        return
    frag = plistlib.dumps(h, fmt=plistlib.FMT_XML).decode()
    frag = frag[frag.index("<dict>"):frag.rindex("</dict>") + len("</dict>")]
    subprocess.run(["defaults", "write", DOMAIN, "UserHeaders", frag], check=True)


def is_on():
    return HEADER in _headers()


def state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return None


def on(slug, address, hours=DEFAULT_HOURS):
    h = _headers()
    h[HEADER] = address
    _write_headers(h)
    deadline = lo_blasts.now() + datetime.timedelta(hours=hours)
    with open(STATE, "w") as f:
        json.dump({"slug": slug, "address": address,
                   "since": lo_blasts.iso(lo_blasts.now()),
                   "deadline": lo_blasts.iso(deadline)}, f, indent=1)
    _log(f"ON  for {slug} until {deadline:%H:%M}")
    return deadline


def off(reason="by hand"):
    was = is_on()
    h = _headers()
    h.pop(HEADER, None)
    _write_headers(h)
    if os.path.exists(STATE):
        os.remove(STATE)
    if was:
        _log(f"OFF ({reason})")
    return was


def unsent(slug):
    """Recipients in the blast not yet seen in the Sent folder."""
    import lo_scan
    blast = lo_blasts.load(slug)
    me = _address()
    rows = lo_scan.gather(days=2, sent_only=True, backend="apple-mail", bodies=False)
    lo_blasts.sync(blast, rows, me)
    lo_blasts.save(blast)
    return [s["to"] for s in blast["sends"] if not s.get("sent_at")]


def _address():
    try:
        with open(os.path.join(lo_blasts.BASE, "config.json")) as f:
            return json.load(f)["user"]["email"]
    except Exception:
        return ""


def watch(slug):
    """Poll Sent until the blast is out, then switch receipts off. Always ends by the deadline."""
    st = state() or {}
    deadline = lo_blasts.parse(st.get("deadline")) or (
        lo_blasts.now() + datetime.timedelta(hours=DEFAULT_HOURS))
    _log(f"watching {slug}")
    while True:
        if not is_on():
            _log("watch: already off, exiting")
            return
        try:
            left = unsent(slug)
        except Exception as e:
            left = None
            _log(f"watch: couldn't read Sent ({e})")
        if left == []:
            off(f"{slug} fully sent")
            return
        if lo_blasts.now() >= deadline:
            off(f"deadline reached, {len(left) if left else '?'} still unsent")
            return
        # wake at the deadline rather than overshooting it by up to a poll interval
        time.sleep(max(1, min(POLL_SECONDS, (deadline - lo_blasts.now()).total_seconds())))


def start_watcher(slug):
    """Detach a watcher so it outlives the Claude session that opened the drafts."""
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "watch", slug],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def _cli():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    if cmd == "status":
        st = state()
        if is_on():
            print(f"Read receipts: ON  ({(st or {}).get('slug', 'unknown blast')}, "
                  f"auto-off by {(st or {}).get('deadline', '?')})")
            print("Every email Apple Mail sends right now asks for a read receipt.")
        else:
            print("Read receipts: off")
        return 0
    if cmd == "on" and len(args) > 1:
        hours = float(args[args.index("--hours") + 1]) if "--hours" in args else DEFAULT_HOURS
        d = on(args[1], _address(), hours)
        print(f"Read receipts ON until the blast is sent (by {d:%-I:%M %p} at the latest).")
        return 0
    if cmd == "off":
        print("Read receipts off." if off() else "Read receipts were already off.")
        return 0
    if cmd == "watch" and len(args) > 1:
        watch(args[1])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
