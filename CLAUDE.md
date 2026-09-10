# Context for Claude

## What this repo is

Tooling to manage a Migadu mail service, plus the one-time tooling used to
migrate to it from outlook.com. It is **public**, so two rules override
convenience everywhere:

1. **No personal data in commits.** No real addresses, domains, Message-IDs,
   message counts from a live mailbox, or credentials — not in code, not in
   docs, not in commit messages. The `.gitignore` enforces this — do not relax
   those patterns. Live mailbox directories (`mailboxes/*@*/`) are gitignored
   entirely. Use placeholders (`user@example.com`, `example.com`) everywhere.
2. **No hardcoded identities in code.** Everything takes a CLI argument or an
   env var. A grep for any real username or domain must stay empty.

## Scope boundary — read before editing

DNS is **not** managed here. The zone's records (MX, SPF, DKIM, DMARC,
autoconfig, SRV) are managed in a separate infrastructure repo and deployed
from there. If a task involves DNS records, it belongs in that repo, not this
one.

This repo covers the Migadu *service*: filter rules, folders, mailboxes,
aliases, identities.

## Credentials

Two **different** secrets. Confusing them wastes time.

| Purpose | Credential | Where |
|---|---|---|
| IMAP / SMTP / ManageSieve | mailbox password | `MIGADU_USER`+`MIGADU_PASS`, else `~/.migadu-secret` |
| Admin REST API | account email + API key | `MIGADU_API_USER`+`MIGADU_API_KEY`, else `~/.migadu-api-secret` |

The API key is generated at My Account → API Keys. It is not the mailbox
password. Migadu has no "app password" concept — one mailbox password serves
IMAP, SMTP, POP3 and webmail.

File format is `<user> <secret>` on one line. **Split on the first space only**
— the password may itself contain spaces. Getting this wrong looks exactly like
a wrong password.

## Deployment shape

The account can hold more than one domain, and the same local part (`admin@`,
say) can exist in several of them. That is why mailbox directories and every
CLI argument use the **full address**, never the bare username — see
`mailboxes/README.md`.

A managed mailbox typically has:

- `INBOX` plus themed subfolders, including nested ones (`Finance/Banking`)
- Sieve scripts: `custom` (the one managed here, kept ACTIVE) and
  `rainloop.user` (inactive, owned by Migadu's webmail)
- Rules in `mailboxes/<address>/filters.sieve` (**gitignored**), ordered as
  four passes: system alerts, importance tags that keep mail in INBOX, theme
  filing, then the plus-address catch-all — which must stay last

To manage a mailbox, add a directory named for its full address under
`mailboxes/`. `mailboxes/example/` is the starting point and the only one
tracked.

## Before changing filter rules

Migadu's webmail owns `rainloop.user`. **If the user saves a rule in the
webmail UI, it reactivates that script and silently displaces `custom`.** So:

```
bin/sieve-pull user@example.com                  # confirm server matches local first
# edit mailboxes/user@example.com/filters.sieve
bin/sieve-push user@example.com --dry-run        # server-side CHECKSCRIPT
bin/sieve-push user@example.com                  # store + activate
```

Never skip the dry run. `CHECKSCRIPT` catches missing `require` lines that
would otherwise break mail filing silently.

To verify plus-address tagging end to end, send to `user+sometag@example.com`
and check it lands in INBOX with the keyword `tag-sometag`.

## Layout

```
migadu/      library: creds, sieve (ManageSieve), imap, admin (REST),
             mailbox (address/domain resolution), notify (settings email)
migrate/     one-time outlook.com -> Migadu tooling
mailboxes/   per-mailbox filter rules, named <user>@<domain>; example/ is the
             starting point and the only one tracked
bin/         status, sieve-push, sieve-pull, mailbox-setup
docs/        migadu-facts.md, migration-guide.md, runbook.md
```

`docs/migadu-facts.md` records behaviour that cost real time to discover. Read
it before assuming how Migadu works — several of its entries are things that
look like bugs in your own code until you know better.

## Where the mail lives

Only configuration lives in this repo. The live mailbox is on Migadu; the bulk
archive is a local maildir plus a checksum-verified mbox tarball, mirrored to
separate storage; the migration's output records (reports, logs, state files)
sit in their own directory outside the repo. None of that is tracked here, and
none of it should be. The previous provider's account and its OAuth token are
likewise kept outside the repo as a fallback path for refetching mail.

Note that `Admin().usage()` reports consumed storage, not the plan's quota
ceiling — a near-zero reading is normal when mail is archived off-server. The
ceiling lives on Migadu's billing page, not in the API.

## Things that will bite you

- Migadu **rejects** literal UTF-8 in folder names; use `imap.utf7_encode()`.
  Its webmail does not decode UTF-7 for display, so avoid `&` in folder names
  entirely rather than encoding it correctly.
- ManageSieve needs STARTTLS before it advertises any SASL mechanism.
- Migadu auto-creates a folder per plus-address tag unless a rule intercepts.
  Deleting such a folder is a reset, not a permanent removal.
- Mail addressed to both `user@` and `user+tag@` delivers **twice** — each
  envelope recipient is processed separately.
