# Windows notes

This toolkit was built and tested on macOS. The Windows paths below are written carefully but
**have not been tested on a real Windows machine** — prefer the actual error text over any
assumption here. When Claude is helping a Windows user, this file is the support map.

## What works cross-platform vs. macOS-only

| Part | Windows | How |
|---|---|---|
| Build target sheet (`build_vts_plan`, `build_send_manifest`) | ✅ | pure Python + openpyxl |
| Write to VTS (`emit_vts_js` in Chrome) | ✅ | browser automation, OS-independent |
| Draft emails w/ flyer (`make_drafts`) | ✅ classic Outlook | `lib/lo_mail.py` COM backend |
| Clear drafts (`cleanup_drafts`) | ✅ classic Outlook | COM, deletes from Drafts folder |
| Scan replies (`scan_replies`) | ✅ classic Outlook | COM, reads the Inbox |

## Python

- Use **`python`** on Windows, `python3` on macOS/Linux. Try one; if it reports
  "command not found" (or opens the Microsoft Store), use the other.
- The **Microsoft Store `python.exe` stub**: typing `python` may open the Store and look like
  nothing happened. Fix needs a real install from python.org **and** turning off the
  app-execution alias in Settings → Apps → Advanced app settings → App execution aliases.

## Dependencies

```
python -m pip install --user openpyxl pywin32
```

`pywin32` is what provides `win32com.client`. It is Windows-only; on macOS it isn't installed
and isn't needed (the Mail.app AppleScript path is used instead).

## Outlook: classic vs. New

The email features drive **classic Outlook desktop** through COM automation. The **New Outlook**
(the Store/webview app) does **not** expose COM — `Dispatch("Outlook.Application")` fails. A user
on New Outlook must either switch classic Outlook back on (toggle in New Outlook's title bar), or
send manually from the target sheet's contact list. The VTS-write half is unaffected either way.

## Behavior differences to expect

- **Signatures**: the COM draft uses `GetInspector` to pull the account's default signature into
  the message, then prepends the body, so the user's normal Outlook signature is preserved.
- **From address**: `make_drafts` best-effort matches `user.email` to an Outlook account and sets
  `SendUsingAccount`; if there's only one account this is moot.
- **Drafts window**: `mail.Display(False)` opens a normal compose window for review. It does not
  send. Closing it prompts to save like any Outlook draft.
- **`cleanup_drafts`** ignores the `mail.account` config on Windows and uses the default Outlook
  profile's Drafts folder.

## Paths

- `~` is expanded via `os.path.expanduser` everywhere, so config at `~/.listing-outreach` resolves
  to `C:\Users\<name>\.listing-outreach`.
- The flyer path passed to `make_drafts` should be a normal filesystem path; forward or back
  slashes both work through Python. Keep it out of any mail-app-managed folder.
