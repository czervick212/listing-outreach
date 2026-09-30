#!/usr/bin/env python3
"""Microsoft Graph mail backend — Outlook without scripting the Outlook app.

Why this exists: New Outlook (Mac *and* Windows) cannot be automated locally. On the Mac
its AppleScript dictionary is still published but wired to a vestigial local store — no
accounts, an empty Inbox, and save/delete/close silently do nothing. On Windows the New
Outlook app dropped COM entirely. Graph is what Outlook itself talks to, so it works on
either platform, on the new app or the classic one, with no mail client installed at all.

Auth is the OAuth **device code** flow against the user's own app registration: they sign
in once in a browser, we keep the refresh token. Scopes are requested at token time, so
their registration needs no API permissions configured — only "Allow public client flows".

Deliberately stdlib-only. This plugin has no venv and no dependency bootstrap (its
requirements.txt is documentation, nothing reads it), so a `msal` dependency would mean
building install machinery for one file's worth of HTTP.

    python3 lib/lo_graph.py login     # sign in, store the token
    python3 lib/lo_graph.py status    # who am I signed in as
    python3 lib/lo_graph.py logout    # forget the token
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".listing-outreach")
CFG = os.path.join(BASE, "config.json")
TOKEN = os.path.join(BASE, "graph-token.json")

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "offline_access User.Read Mail.ReadWrite"
DEFAULT_TENANT = "organizations"        # any work/school account; not personal Outlook.com

SIMPLE_LIMIT = 3 * 1024 * 1024          # Graph's cap for a one-shot attachment upload
CHUNK = 3276800                         # 10 x 320 KB — upload sessions demand a 320 KB multiple


class GraphError(Exception):
    """The API said no, with a message worth showing the user."""


class NeedsLogin(GraphError):
    """No usable token. The caller should tell them to run `lo_graph.py login`."""


# ------------------------------------------------------------------ config
def _cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except Exception:
        return {}


def _graph_cfg():
    return (_cfg().get("mail") or {}).get("graph") or {}


def client_id():
    return _graph_cfg().get("client_id") or ""


def tenant():
    return _graph_cfg().get("tenant") or DEFAULT_TENANT


def configured():
    """True when there's an app registration to authenticate against."""
    return bool(client_id())


def signed_in():
    return configured() and os.path.exists(TOKEN)


# ------------------------------------------------------------------ HTTP
def _request(url, method="GET", data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()
    except urllib.error.URLError as e:
        raise GraphError(f"Could not reach Microsoft ({e.reason}). Check the network.")


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return {}


def _post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    status, _, raw = _request(url, "POST", body,
                              {"Content-Type": "application/x-www-form-urlencoded"})
    return status, _json(raw)


# ------------------------------------------------------------------ auth
def _auth_base():
    return f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0"


def _save_token(tok, account=None):
    os.makedirs(BASE, exist_ok=True)
    keep = {
        "refresh_token": tok.get("refresh_token"),
        "access_token": tok.get("access_token"),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
        "account": account or _peek_account(tok.get("access_token")),
        "client_id": client_id(),
        "tenant": tenant(),
    }
    # Written before the chmod, so create it closed rather than fixing it afterwards.
    fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(keep, f, indent=2)
    return keep


def _peek_account(access_token):
    """Read the account name out of the token's own payload — one less API round trip."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get("preferred_username") or claims.get("upn") or ""
    except Exception:
        return ""


def _load_token():
    try:
        with open(TOKEN) as f:
            return json.load(f)
    except Exception:
        return {}


def login(print_=print):
    """Device code flow. Prints the code, waits for the user to finish in the browser."""
    if not configured():
        raise NeedsLogin(
            "No Microsoft app registration configured yet.\n"
            "Run listing-outreach setup, or set it by hand:\n"
            "  python3 lib/lo_config.py set mail.graph.client_id <application-id>")

    status, r = _post_form(f"{_auth_base()}/devicecode",
                           {"client_id": client_id(), "scope": SCOPES})
    if status != 200:
        raise GraphError(_login_hint(r))

    print_("")
    print_(f"  Open {r['verification_uri']} and enter code:  {r['user_code']}")
    print_("")
    print_("  Sign in with your work email. Waiting…")

    interval = int(r.get("interval", 5))
    deadline = time.time() + int(r.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = _post_form(f"{_auth_base()}/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id(),
            "device_code": r["device_code"],
        })
        if status == 200:
            saved = _save_token(tok)
            print_(f"\n  Signed in as {saved['account']}")
            return saved
        err = tok.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise GraphError(_login_hint(tok))
    raise GraphError("The sign-in code expired before it was used. Run login again.")


def _login_hint(r):
    """Turn Microsoft's error codes into something a broker can act on."""
    err = r.get("error", "")
    desc = (r.get("error_description") or "").split("\r\n")[0]
    if err == "authorization_declined":
        return "Sign-in was cancelled in the browser."
    if err == "invalid_client" or "AADSTS7000218" in desc:
        return ("That app registration isn't set up for this kind of sign-in.\n"
                "In the Azure portal open your registration -> Authentication -> "
                "Advanced settings, and set 'Allow public client flows' to Yes.")
    if err == "unauthorized_client" or "AADSTS700016" in desc:
        return (f"Your organization doesn't recognise app id {client_id()}.\n"
                "Check the Application (client) ID was copied correctly, and that the "
                "registration lives in the same Microsoft 365 organization you sign in to.")
    if "AADSTS65001" in desc or "AADSTS90094" in desc or err == "consent_required":
        return ("Your organization requires an administrator to approve this app before it "
                "can read your mailbox. Send your IT admin the app registration and ask them "
                "to grant it. Until then, send from Outlook by hand.")
    return desc or f"Sign-in failed ({err or 'unknown error'})."


def token():
    """A valid access token, refreshing silently when the old one has aged out."""
    if not configured():
        raise NeedsLogin(
            "Microsoft Outlook isn't set up yet — run listing-outreach setup.")
    t = _load_token()
    if not t.get("refresh_token"):
        raise NeedsLogin("Not signed in to Outlook yet. Run:  python3 lib/lo_graph.py login")
    if t.get("client_id") and t["client_id"] != client_id():
        raise NeedsLogin("The app registration changed. Run:  python3 lib/lo_graph.py login")
    if t.get("access_token") and time.time() < t.get("expires_at", 0):
        return t["access_token"]

    status, tok = _post_form(f"{_auth_base()}/token", {
        "grant_type": "refresh_token",
        "client_id": client_id(),
        "refresh_token": t["refresh_token"],
        "scope": SCOPES,
    })
    if status != 200:
        raise NeedsLogin("Your Outlook sign-in expired. Run:  python3 lib/lo_graph.py login")
    # A refresh normally returns a new refresh token; keep the old one if it doesn't.
    tok.setdefault("refresh_token", t["refresh_token"])
    return _save_token(tok, t.get("account"))["access_token"]


def logout():
    if os.path.exists(TOKEN):
        os.remove(TOKEN)
        return True
    return False


# ------------------------------------------------------------------ API
def api(path, method="GET", body=None, headers=None, tries=3):
    """One Graph call. `path` is either a /v1.0-relative path or a full nextLink URL."""
    url = path if path.startswith("http") else GRAPH + path
    h = {"Authorization": f"Bearer {token()}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})

    for attempt in range(tries):
        status, resp_headers, raw = _request(url, method, data, h)
        if status == 429 or status >= 500:
            if attempt == tries - 1:
                break
            time.sleep(int(resp_headers.get("Retry-After") or (2 ** attempt)))
            continue
        break

    if status in (200, 201, 202):
        return _json(raw)
    if status == 204:
        return {}
    if status == 401:
        raise NeedsLogin("Outlook rejected the sign-in. Run:  python3 lib/lo_graph.py login")
    detail = (_json(raw).get("error") or {}).get("message") or raw[:200].decode("utf-8", "replace")
    raise GraphError(f"Microsoft Graph error {status}: {detail}")


def me():
    r = api("/me?$select=displayName,mail,userPrincipalName")
    return {"name": r.get("displayName", ""), "email": r.get("mail") or r.get("userPrincipalName", "")}


# ------------------------------------------------------------------ drafts
def create_draft(to, subject, body, attachment=None, receipt=False):
    """Create a draft in the signed-in mailbox. Never sends. Returns {id, webLink}.
    `receipt` asks the recipient's mail app for a read receipt on this one message."""
    msg = api("/me/messages", "POST", {
        "subject": subject,
        "body": {"contentType": "Text", "content": (body or "").rstrip() + "\n"},
        "toRecipients": [{"emailAddress": {"address": to}}],
        "isReadReceiptRequested": bool(receipt),
    })
    if attachment:
        try:
            attach(msg["id"], attachment)
        except Exception:
            # A draft with no flyer is worse than no draft — don't leave it to be sent.
            try:
                api(f"/me/messages/{msg['id']}", "DELETE")
            except Exception:
                pass
            raise
    return {"id": msg["id"], "webLink": msg.get("webLink", "")}


def attach(message_id, path):
    """Attach a file, taking the upload-session route for anything Graph won't inline."""
    size = os.path.getsize(path)
    name = os.path.basename(path)
    if size < SIMPLE_LIMIT:
        with open(path, "rb") as f:
            api(f"/me/messages/{message_id}/attachments", "POST", {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentBytes": base64.b64encode(f.read()).decode(),
            })
        return

    session = api(f"/me/messages/{message_id}/attachments/createUploadSession", "POST", {
        "AttachmentItem": {"attachmentType": "file", "name": name, "size": size},
    })
    url = session["uploadUrl"]
    with open(path, "rb") as f:
        sent = 0
        while sent < size:
            block = f.read(CHUNK)
            last = sent + len(block) - 1
            # The upload URL carries its own auth; sending ours over it is rejected.
            status, _, raw = _request(url, "PUT", block, {
                "Content-Length": str(len(block)),
                "Content-Range": f"bytes {sent}-{last}/{size}",
            }, timeout=300)
            if status not in (200, 201, 202):
                detail = (_json(raw).get("error") or {}).get("message") or ""
                raise GraphError(f"Attaching {name} failed ({status}). {detail}".strip())
            sent = last + 1


def drafts_on(day):
    """Every draft created on `day` (YYYY-MM-DD), or every draft in the folder when `day`
    is None. Graph's $filter has no contains() for subject, so callers match the subject
    themselves on what comes back."""
    url = "/me/mailFolders/drafts/messages?$select=id,subject,createdDateTime&$top=100"
    if day:
        url += (f"&$filter=createdDateTime ge {day}T00:00:00Z"
                f" and createdDateTime lt {day}T23:59:59Z")
    out = []
    while url:
        page = api(url)
        out.extend(page.get("value", []))
        url = page.get("@odata.nextLink")
    return out


def delete_message(message_id):
    api(f"/me/messages/{message_id}", "DELETE")


def create_followup(original_mid, to, text):
    """A real reply on the thread of a message we sent, addressed back to its recipient.

    createReply on our own sent message addresses the reply to ourselves, so the recipient
    is set explicitly. `comment` puts the text above Outlook's own quoted original. Returns
    {id, webLink}, or None when the original can't be found (e.g. it has been deleted)."""
    mid = original_mid.replace("'", "''")
    hits = api(f"/me/messages?$filter=internetMessageId eq '{mid}'&$select=id&$top=1")
    if not hits.get("value"):
        return None
    reply = api(f"/me/messages/{hits['value'][0]['id']}/createReply", "POST", {
        "message": {"toRecipients": [{"emailAddress": {"address": to}}]},
        "comment": text,
    })
    return {"id": reply["id"], "webLink": reply.get("webLink", "")}


# ------------------------------------------------------------------ inbox
def inbox_since(days):
    """Inbox messages from the last `days`, shaped like the other backends' rows."""
    import datetime
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"/me/mailFolders/inbox/messages"
           f"?$select=subject,from,receivedDateTime,internetMessageId,body&$top=50"
           f"&$filter=receivedDateTime ge {cutoff}&$orderby=receivedDateTime desc")
    # Ask for text bodies, so replies arrive the same shape the .emlx reader produces.
    headers = {"Prefer": 'outlook.body-content-type="text"'}
    out = []
    while url:
        page = api(url, headers=headers)
        for m in page.get("value", []):
            addr = (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
            out.append({
                "frm": addr,
                "subj": m.get("subject") or "",
                "body": (m.get("body") or {}).get("content") or "",
                "date": m.get("receivedDateTime") or "",
                "mid": m.get("internetMessageId") or m.get("id") or "",
            })
        url = page.get("@odata.nextLink")
    return out


def messages_since(days, sent_only=False, bodies=True):
    """Recent mail in both directions — every folder, so a reply already filed away still
    counts — shaped like the other backends' rows (see lo_scan.py). Drafts are skipped."""
    import datetime
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    me_addr = (me().get("email") or "").lower()
    base = "/me/mailFolders/sentitems/messages" if sent_only else "/me/messages"
    url = (f"{base}?$select=subject,from,toRecipients,ccRecipients,receivedDateTime,"
           f"sentDateTime,internetMessageId,isDraft{',body' if bodies else ''}&$top=50"
           f"&$filter=receivedDateTime ge {cutoff}&$orderby=receivedDateTime desc")
    headers = {"Prefer": 'outlook.body-content-type="text"'}
    out = []
    while url:
        page = api(url, headers=headers)
        for m in page.get("value", []):
            if m.get("isDraft"):
                continue
            frm = (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
            sent = frm == me_addr
            to = [((r.get("emailAddress") or {}).get("address") or "").lower()
                  for r in (m.get("toRecipients") or []) + (m.get("ccRecipients") or [])]
            out.append({
                "frm": frm, "to": [a for a in to if a],
                "subj": m.get("subject") or "",
                "body": "" if sent else (m.get("body") or {}).get("content") or "",
                "date": (m.get("sentDateTime") if sent else m.get("receivedDateTime")) or "",
                "mid": m.get("internetMessageId") or m.get("id") or "",
                "folder": "sent" if sent else "inbox",
            })
        url = page.get("@odata.nextLink")
    return out


# ------------------------------------------------------------------ CLI
def _cli():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "login":
        login()
        return 0
    if cmd == "logout":
        print("Signed out." if logout() else "Wasn't signed in.")
        return 0
    if cmd == "status":
        if not configured():
            print("Outlook (Graph): not configured — no app registration set.")
            print("  python3 lib/lo_config.py set mail.graph.client_id <application-id>")
            return 2
        print(f"app id : {client_id()}")
        print(f"tenant : {tenant()}")
        if not os.path.exists(TOKEN):
            print("signed in: no —  python3 lib/lo_graph.py login")
            return 2
        who = me()
        print(f"signed in: {who['name']} <{who['email']}>")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except GraphError as e:
        print(f"\n{e}", file=sys.stderr)
        raise SystemExit(2)
