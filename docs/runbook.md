# Runbook

## Check current state

```sh
bin/status
```

Folders with message counts, which Sieve script is active, and domain storage
usage if the admin API is configured.

## Change filter rules

```sh
bin/sieve-pull you@example.com           # confirm server matches local FIRST
$EDITOR "mailboxes/you@example.com/filters.sieve"
bin/sieve-push you@example.com --dry-run # server-side CHECKSCRIPT
bin/sieve-push you@example.com           # store + activate
```

Mailbox directories are named for the full address. A bare local part works
when unambiguous, but is refused when it exists in several domains.

The pull step matters: Migadu's webmail can replace the active script without
warning. If `sieve-pull` reports a difference you did not make, someone saved a
rule through the webmail UI.

## Recover after the webmail hijacks your rules

Symptom: rules stop working, and `bin/status` shows `rainloop.user` as ACTIVE.

```sh
bin/sieve-push you@example.com     # re-activates 'custom'
```

Your script was never deleted, only deactivated.

## Onboard a user

Send someone their connection settings, and optionally set their password.
`docs/user-guide.md` is the non-technical walkthrough to send alongside it.

```sh
# Safest: Migadu emails an invitation, the user picks their own password.
bin/mailbox-setup alice --invite --recovery alice@elsewhere.example

# No change to the account, just resend the settings.
bin/mailbox-setup alice --settings-only

# Generate a password, set it, and email it. Prompts for confirmation --
# this resets a live password and puts it in a mailbox in plaintext.
bin/mailbox-setup alice --send-password
```

Add `--dry-run` to any of these to see what would happen. Prefer `--invite`
where the user has another working address: the password then never exists
outside Migadu.

The message carries `docs/user-guide.md` twice — attached as a PDF and repeated
inline — so it works whether or not the recipient opens attachments. Edit the
guide and both update; there is no second copy to keep in step. The PDF is
produced by `cupsfilter`, which ships with macOS. On a machine without it the
send still succeeds, inline-only, with a warning. Suppress either with
`--no-pdf` or `--no-guide`.

Note `bin/mailbox-setup` uses the **admin API** credentials to change the
account, and the **mailbox** credentials to send the mail. Both must be
configured.

## Add a mailbox

```sh
cp -r mailboxes/example "mailboxes/other@example.com"
$EDITOR "mailboxes/other@example.com/filters.sieve"
MIGADU_USER=other@example.com MIGADU_PASS='...' bin/sieve-push other@example.com
```

Each mailbox has its own password, so supply credentials via environment
variables when acting on a mailbox other than the one in `~/.migadu-secret`.
The sieve tools check this and refuse rather than pushing one mailbox's rules
onto another.

## Trace a leaked address

Plus-addressed mail is tagged with an IMAP keyword. Search for it in any
client, or:

```python
from migadu import imap
M = imap.connect()
M.select('"INBOX"', readonly=True)
print(M.search(None, "KEYWORD", "tag-shopping"))
```

Mail tagged for one service arriving from another is your evidence that the
address was sold or leaked. Block it by adding a rule ahead of the catch-all:

```sieve
if envelope :detail "to" "shopping" { discard; stop; }
```

## Query the admin API

```python
from migadu.admin import Admin
a = Admin()
print(a.usage("example.com"))       # real storage figures
print(a.mailboxes("example.com"))
print(a.aliases("example.com"))
print(a.diagnostics("example.com")) # Migadu's own DNS checks
```

`diagnostics` is useful after DNS changes — it reports what Migadu sees for
MX, SPF, DKIM and DMARC.

## Check DNS is still correct

DNS is managed elsewhere (see CLAUDE.md), but to verify what the world sees —
and bypass a local resolver that may be serving stale answers:

```sh
curl -s -H 'accept: application/dns-json' \
  'https://dns.google/resolve?name=example.com&type=MX' | python3 -m json.tool
```

Querying an authoritative nameserver by name is not sufficient: an intercepting
local resolver can answer on its behalf.
