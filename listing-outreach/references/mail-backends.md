# Mail backends

The email half of this toolkit has three ways to reach a mailbox. Which one runs is
`mail.backend` in `~/.listing-outreach/config.json` when it is set; otherwise Graph if it is
configured, otherwise the platform default (Apple Mail on macOS, Outlook COM on Windows).

| backend | reaches | drafts appear | reads the inbox |
|---|---|---|---|
| `graph` | **any Outlook**, Mac or Windows, new app or classic | Outlook Drafts folder | ✅ |
| `apple-mail` | Mail.app | compose windows on screen | ✅ local `.emlx` store |
| `outlook-com` | **classic** Outlook desktop only | compose windows on screen | ✅ COM |

## Why Graph exists

Microsoft's **New Outlook** — now the default on both platforms — cannot be automated locally.

- **On the Mac** it still publishes an AppleScript dictionary, but it is wired to a vestigial
  local store: `exchange accounts`, `imap accounts` and `pop accounts` all return 0, `inbox`
  reports 0 messages, and `save`, `delete`, `close … saving no` and `move to deleted items` all
  silently do nothing. Creating a message does open a real compose window, but there is no way
  to clean up afterwards, and no way to read a reply.
- **On Windows** it dropped COM entirely — `Dispatch("Outlook.Application")` fails.

There is no local database to read either: New Outlook keeps mail in `HxStore.hxd`, a
proprietary binary, where classic Outlook for Mac kept a readable `Outlook.sqlite`.

Microsoft Graph is the API Outlook itself talks to. Nothing is scripted locally, so it works on
either platform, on either app, and with no mail client installed at all.

## Setting Graph up

One five-minute app registration, then a sign-in. The registration lives in the user's own
Microsoft 365 organization — this toolkit ships no app id and holds no credentials of anyone's.

1. **portal.azure.com** → search **App registrations** → **New registration**
2. Name it anything (`Listing Outreach`), leave it single-tenant, **Register**
3. **Authentication** → **Add a platform** → **Mobile and desktop applications** → tick the
   `https://login.microsoftonline.com/common/oauth2/nativeclient` box → **Configure**
4. Same page, **Advanced settings** → **Allow public client flows: Yes** → **Save**
5. **Overview** → copy the **Application (client) ID**

Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.graph.client_id <application-id>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_config.py" set mail.backend graph
python3 "${CLAUDE_PLUGIN_ROOT}/lib/lo_graph.py" login
```

`login` prints a short code and a URL. They open it, enter the code, sign in with their work
email, approve the permission list once. `lo_graph.py status` confirms who is signed in;
`lo_graph.py logout` forgets it.

No API permissions need configuring in the portal — the scopes (`Mail.ReadWrite`, `User.Read`,
`offline_access`) are requested at sign-in.

## When it won't sign in

The script translates Microsoft's error codes, but the three that actually happen:

- **"Allow public client flows"** was left off (`AADSTS7000218`) — step 4 above.
- **The org won't recognise the app id** (`AADSTS700016`) — the ID was mistyped, or the
  registration lives in a different Microsoft 365 organization than the account signing in.
- **An administrator has to approve it** (`AADSTS65001`, `AADSTS90094`) — the tenant requires
  admin consent for new apps. Send IT the registration and ask them to grant it. Some
  organizations also block users from registering apps at all, in which case IT has to create
  the registration and hand back the client ID.

Either way the fallback is real: set `mail.backend` to `apple-mail` if Mail.app is configured,
or work the target sheet's contact list by hand. The VTS half is unaffected.

## No registration? Replies still work

Reply tracking does not need Graph at all if Claude can reach the mailbox through a **Microsoft
365 connector**. That connector is read-only for mail — it can search and read, but cannot
create a draft, attach a file, or delete anything — so it covers the reply half and not the
drafting half.

It also cannot be called from a script, only from inside a Claude session. So the flow is:
Claude searches Outlook per recipient, writes the hits to JSON, and `scan_replies.py --messages
<file>` does the matching. Full instructions live in the main skill's Step 10.

That leaves a connector-only user with the target sheet, the VTS writes and reply tracking —
everything except automated drafting, which they do by hand from the sheet's contact list until
someone sets up a registration.

## Where the token lives

`~/.listing-outreach/graph-token.json`, mode `600`. It holds a refresh token for that one
mailbox — treat it like a password, and run `lo_graph.py logout` before handing a machine on.
Nothing is sent anywhere except Microsoft.

## Behavior differences worth knowing

- **From address**: Graph sends from the mailbox that signed in. `user.email` in config still
  signs the body; if the two disagree, `make_drafts.py` says so before drafting.
- **Signatures**: a Graph draft carries no Outlook signature (the classic-COM path pulls one in
  via `GetInspector`). Keep the sign-off in the email template.
- **Attachments**: under 3 MB go in one request; anything larger uploads in 3.125 MB chunks
  through an upload session. If an attachment fails, the draft is deleted rather than left to be
  sent without the flyer.
- **`mail.account`** is an Apple Mail concept (which account holds Drafts). Both Outlook
  backends ignore it.
- **Draft cleanup** on Graph filters by the day the draft was created, then matches the subject
  fragment in the toolkit rather than in the query — Graph's `$filter` has no `contains()` for
  `subject`.
