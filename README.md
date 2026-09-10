# migadu

Tools for managing a [Migadu](https://migadu.com) mail service from the command
line, and for migrating to it from outlook.com.

Python 3, standard library only. No dependencies to install.

## What it does

**Manage an existing Migadu mailbox**

- Filter rules as version-controlled Sieve files, validated server-side before
  they go live
- Folder and message-count overview
- Read-only queries against Migadu's admin API — mailboxes, aliases,
  identities, rewrites, and real storage usage

**Migrate from outlook.com**

- OAuth2 device-code sign-in (no Azure app registration needed)
- Read-only mailbox survey — sizes and counts per folder and per year
- Resumable download to maildir
- Tier-based classification: decide what belongs on the server versus a local
  archive
- IMAP upload to Migadu

## Supported source provider

**outlook.com only.** The migration tooling is built around Microsoft's OAuth2
device-code flow and Outlook's particular IMAP quirks. Other providers may work
with modification, but are not supported or tested here.

The management tooling is provider-independent — it only talks to Migadu.

## Quickstart

```sh
git clone <this-repo> ~/src/migadu
cd ~/src/migadu

# credentials
cp .migadu-secret.example ~/.migadu-secret
chmod 600 ~/.migadu-secret
$EDITOR ~/.migadu-secret        # one line: user@example.com yourpassword

bin/status                       # folders, filters, usage
```

To manage filter rules:

```sh
cp -r mailboxes/example mailboxes/you
$EDITOR mailboxes/you/filters.sieve

bin/sieve-push you --dry-run     # validate server-side
bin/sieve-push you               # store and activate
bin/sieve-pull you               # confirm server matches local
```

## Credentials

Two different secrets:

| Purpose | Credential | Supplied via |
|---|---|---|
| IMAP / SMTP / ManageSieve | mailbox password | `MIGADU_USER` + `MIGADU_PASS`, or `~/.migadu-secret` |
| Admin REST API | account email + API key | `MIGADU_API_USER` + `MIGADU_API_KEY`, or `~/.migadu-api-secret` |

The API key comes from My Account → API Keys and is **not** your mailbox
password. Everything except `bin/status`'s usage section works without it.

Migadu has no "app password" concept — one mailbox password serves IMAP, SMTP,
POP3 and webmail.

## A warning about the webmail

Migadu's webmail owns a Sieve script called `rainloop.user`. Saving any rule
through the webmail UI reactivates that script and silently displaces the one
managed here. Run `bin/sieve-pull` to check before assuming your rules are
live.

## Documentation

- [`docs/migadu-facts.md`](docs/migadu-facts.md) — Migadu behaviour worth
  knowing, including several things that look like bugs in your own code
- [`docs/migration-guide.md`](docs/migration-guide.md) — the outlook.com
  migration end to end, and the traps in it
- [`docs/runbook.md`](docs/runbook.md) — common tasks

## Licence

BSD 2-Clause. See [LICENSE](LICENSE).
