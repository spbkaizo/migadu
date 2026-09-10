# Mailbox configuration

One directory per mailbox, containing `filters.sieve`. **Directories are named
for the full address**, because the account hosts several domains and a local
part such as `admin` usually exists in all of them.

- `example/` — starter rules, documented. Copy it to begin.
- `<user>@<domain>/` — a live configuration. Gitignored: real rules name real
  correspondents, and this is a public repository.

```sh
cp -r mailboxes/example "mailboxes/you@example.com"
$EDITOR "mailboxes/you@example.com/filters.sieve"
bin/sieve-push you@example.com --dry-run
bin/sieve-push you@example.com
```

A bare local part also works when it is unambiguous — `bin/sieve-push you` —
but the tools refuse it when the name exists in more than one domain rather
than guessing which you meant.

Each mailbox authenticates with its own password, and the sieve tools refuse to
act on a mailbox whose credentials you are not using. To manage another
mailbox, supply its password:

```sh
MIGADU_USER=other@example.com MIGADU_PASS='...' bin/sieve-push other@example.com
```

Only mailboxes with a directory here are managed. Migadu mailboxes with no
directory are left entirely alone.
