# Migadu behaviour worth knowing

Findings from a real migration and ongoing management. Several of these look
like bugs in your own code until you know the cause.

## ManageSieve

- Endpoint is `imap.migadu.com:4190` — the same host as IMAP, not a separate
  `sieve.` or `manage.` hostname (neither resolves).
- The greeting advertises `"SASL" ""` — **no mechanisms** — until STARTTLS
  completes. Authentication before STARTTLS is impossible, not merely unwise.
- Implementation identifies as "Sora ManageSieve Proxy".
- Available extensions: `fileinto`, `envelope`, `encoded-character`,
  `imap4flags`, `variables`, `relational`, `vacation`, `copy`, `regex`, `date`,
  `index`, `mailbox`, `subaddress`, `body`, `editheader`, plus the standard
  comparators.
- `CHECKSCRIPT` validates server-side before you store anything. Use it every
  time. It catches missing `require` lines, which otherwise produce a script
  that stores and activates fine but silently misfiles mail.

## Two Sieve scripts, one active

Migadu's webmail (Rainloop) manages its own script named `rainloop.user`,
carrying base64 `BEGIN:HEADER` blocks it parses to render its rules UI.

If you activate your own script, the webmail UI still displays `rainloop.user`
and no longer reflects reality. Worse, **saving any rule from the webmail
reactivates `rainloop.user`**, silently displacing yours. Check with
`bin/sieve-pull` before assuming your rules are live.

## Folder names

- Migadu requires IMAP modified UTF-7 (RFC 3501 §5.1.3) and **rejects** literal
  UTF-8: creating `A & B` fails with
  `BAD [CLIENTBUG] Syntax error: invalid mailbox name: utf7: invalid UTF-7`.
- Its webmail does **not** decode UTF-7 for display, so a correctly-encoded
  `Sales & Orders` shows as `Sales &- Orders` there. Other clients decode it
  properly. The practical fix is to avoid `&` in folder names.
- `INBOX` is spelled uppercase; subfolders hang off it as `INBOX/Name` with `/`
  as the delimiter.

## Plus-addressing (subaddressing)

Migadu auto-creates a folder named after the tag when mail arrives for
`user+tag@domain`. That is why folders appear that nobody created.

To keep everything in INBOX instead, intercept with Sieve:

```sieve
require ["fileinto", "subaddress", "variables", "imap4flags", "envelope"];

if envelope :matches :detail "to" "*" {
    set :lower "tag" "${1}";
    addflag "tag-${tag}";
    fileinto "INBOX";
    stop;
}
```

Deleting an auto-created folder is a reset, not a permanent removal — it
reappears on the next matching message unless a rule intercepts.

**Each envelope recipient is processed separately.** Mail addressed to both
`user@` and `user+tag@` delivers **two** copies, one tagged and one not.

## Filing mail into folders hides it

Not a Migadu quirk -- a design finding, recorded because the measurement was
the surprising part.

A mailbox filing incoming mail into eleven `INBOX/<Theme>` folders was measured
before changing it:

| Location | Unread |
|---|---|
| INBOX | 111 |
| eleven theme subfolders | 170 |

**More unread mail was hidden than visible.** Filing does not reduce the
amount to deal with, it splits it across places that must each be remembered
and opened. Nothing in any status output makes that obvious, because per-folder
unread counts are only visible if you go looking for them.

The alternative costs nothing extra in Sieve. Replace

```sieve
fileinto :create "INBOX/Tech";
```

with

```sieve
addflag "tag-tech";
fileinto "INBOX";
```

The grouping survives as an IMAP keyword, searchable as `KEYWORD tag-tech` and
usable as a saved search or smart mailbox that looks like a folder in the
client. Mail stays in one place.

Two details worth keeping:

- Tag known noise (newsletters, social) with `addflag "\\Seen"` as well, so it
  lands silently. Without this, collapsing folders into INBOX just moves the
  pile rather than shrinking it, and the unread count stops meaning anything.
- Genuine fire-and-forget alerts are the one case where filing away *is*
  right -- they are never acted on individually.

For the backlog already filed away, `bin/inbox-reflow` tags unread messages and
moves them back to INBOX. It leaves read mail and the folders themselves alone,
and dry-runs by default.

## A rule that nearly matches is silently dead

Sieve `header :contains` is a plain substring test with no feedback. A rule
listing a domain the mail does not actually come from never fires, never errors
and never appears in any status output -- it simply does nothing, and the mail
lands untagged as though no rule existed.

Three real cases found in one mailbox, each a rule that had looked correct for
months:

| Rule listed | Mail actually came from |
|---|---|
| `@members.ebay.co.uk` | `members.ebay.com` |
| `@grafana.com` | `<instance>.grafana.net` (self-hosted) |
| `_substack_com_` (relay form only) | `substack.com` direct |

The pattern: a ccTLD assumed from a UK-facing brand, a vendor's SaaS subdomain
rather than its corporate one, and a relay-encoded form listed without the
direct form alongside it. The self-hosted case is the easiest to miss, since
the brand name is right there in the rule.

Audit by asking what is *not* tagged rather than by reading the rules, which is
the check that finds this:

```
SEARCH UNSEEN            # then subtract each KEYWORD you expect
```

Group the remainder by sender domain. A domain appearing in quantity with no
keyword is either a missing rule or a near-miss in an existing one. Reading the
ruleset will not show it, because the rule looks right.

## UID SEARCH with a charset argument silently under-returns

`imaplib`'s two search methods differ in signature, and the difference is easy
to miss because only one of them errors:

```python
M.search(None, "UNSEEN")          # charset first -- correct
M.uid("SEARCH", None, "UNSEEN")   # WRONG: None is sent as a search argument
M.uid("SEARCH", "UNSEEN")         # correct
```

`uid()` takes no charset, so the `None` goes to the server as part of the
command. Migadu answers `OK` with a **partial** result set rather than `BAD`:
observed returning 0 UIDs where 401 messages matched, and on a smaller folder
returning the correct set, which is what makes this survive testing.

The failure mode is a script that selects too few messages and reports success.
Anything that subtracts one search from another -- "which messages have no
keyword" -- then over-reports the remainder instead of crashing.

Verified against the live server 2026-10-06. Both `bin/untagged` and
`bin/inbox-reflow` use the no-charset form.

The same charset argument corrupts sequence-number `SEARCH` with multiple
criteria. `M.search(None, "KEYWORD", "tag-x")` was observed returning an
identical count for *every* keyword tried, including ones no message carried --
fetching those messages showed none had the flag. Single-criterion
`M.search(None, "UNSEEN")` is fine, which is what makes the broken form look
plausible.

Trust `M.uid("SEARCH", ...)` without a charset. When a count has to be right,
verify it by fetching `(FLAGS)` per message and reading the keywords, which
cannot be fudged by the search implementation:

```python
ok, data = M.uid("FETCH", chunk, "(FLAGS)")
```

That is how the figures above were confirmed.

Even the single-criterion form is not reliable for counting across many folders
in one session. Walking every folder and running `UID SEARCH ALL` in each
returned an identical count for all eight -- a figure matching none of them.
The symptom is a suspiciously uniform column.

**For "how many messages are in this folder", read the `EXISTS` response that
`SELECT` returns.** It comes from a different code path and has been correct
every time:

```python
ok, d = M.select(f'"{utf7_encode(name)}"', readonly=True)
count = int(d[0])          # EXISTS
```

`imap.counts()` already does this; `bin/status` is therefore trustworthy where
an ad-hoc `SEARCH` loop is not. Treat a count that decides whether to delete
something as needing `EXISTS` corroboration first.

## Migrated mail is all the same age to IMAP

`BEFORE`/`SINCE` match INTERNALDATE -- when the server received the message --
not the `Date:` header. Mail imported in bulk therefore carries the import date,
not the date it was sent.

Measured on a mailbox holding seven months of mail, all imported in one month:

| | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct |
|---|---|---|---|---|---|---|---|---|
| `Date:` header | 143 | 188 | 257 | 232 | 204 | 144 | 429 | 180 |
| INTERNALDATE | 0 | 0 | 0 | 0 | 0 | 0 | 1594 | 182 |

So `BEFORE 06-Sep-2026` matched **nothing** in a mailbox whose oldest message
was sent in March. Any age-based cleanup written against `BEFORE` silently does
nothing to migrated mail while working correctly on mail that arrived live --
which is the worst way round, since the migrated backlog is what needs it.

`SENTBEFORE`/`SENTSINCE` match the `Date:` header instead. Prefer them for
anything about how old the *mail* is; `BEFORE` answers only how long it has been
on this server. Note `Date:` is sender-supplied and occasionally absent or
nonsense, so a tool that must not skip anything should fall back rather than
assume it parses.

`bin/alert-prune` uses `BEFORE` deliberately: its alerts arrive live, verified
by comparing INTERNALDATE with `Date:` across every alert in the mailbox and
finding a zero gap on all of them.

## Authentication

- No "app password" concept *by that name*. One mailbox password serves IMAP,
  SMTP, POP3 and webmail. Migadu's autoconfig specifies `password-cleartext`
  with `%EMAILADDRESS%` as the username — "cleartext" meaning inside the TLS
  tunnel. **Identities** do provide a revocable per-device credential, for
  sending as well as reading; see below.
- Unlike Google/Microsoft/Apple, there is no MFA-driven need for a separate
  per-application credential.
- The **admin REST API** is different: HTTP Basic with your Migadu *account*
  email and an API key from My Account → API Keys.

## Identities

An identity is an address *under* a mailbox carrying its own password and its
own per-protocol permissions. It is the feature that fills the app-password gap
above: a credential you can revoke alone, without changing the password every
other device is using.

It is not an alias, and the two are easy to confuse:

| | Alias | Identity |
|---|---|---|
| Scope | domain | one mailbox |
| Endpoint | `/v1/domains/{d}/aliases` | `/v1/domains/{d}/mailboxes/{lp}/identities` |
| Own password | no | **yes** |
| Can log in | no | **yes** — `may_access_imap`, `may_access_pop3`, `may_access_managesieve`, each separately |
| Can send as | no | **yes** — `may_send` |
| Receives mail | forwards elsewhere | delivers into the parent mailbox |

Read-only fields are `local_part`, `domain` and `address`. `password` is
write-only — the API never returns it, so a generated one that is not recorded
at creation time is gone.

### `name` is required on create

`POST .../identities` without a `name` fails with a bare
`400 {"error":"bad request"}`. The response names no field, and `name` reads
like the optional display-name field it is on every other resource.
`migadu/admin.py` defaults it to the local part.

### A password is ignored unless `password_use` says otherwise

Sending `password` on create or update **is not enough**. The write returns
200, every field reads back correctly, and the identity still has
`password_use: "none"` — meaning no password is set and every login is
rejected. Nothing in the response says the password was discarded.

The symptom is an identity that looks perfect in the API and in the webmail
while `Authentication failed` comes back from IMAP, which reads as a wrong
password or a permissions mistake rather than a field you did not send.

Send `password_use: "custom"` alongside it:

```json
{"password_use": "custom", "password": "..."}
```

Verified against the live API 2026-09-11. `migadu/admin.py` sets this for you
in both `create_identity()` and `update_identity()`.

Confirmed at the same time: an identity granted `may_access_imap` logs in at
`imap.migadu.com:993` with its own address as the username and lands in the
**parent mailbox's** INBOX — the same messages, not a separate store. The
parent password keeps working throughout, and deleting the identity revokes
only that credential.

One more surprise on revocation: a deleted identity's login is refused with
`[UNAVAILABLE] Backend server temporarily unavailable`, not an authentication
error. That reads like a Migadu outage rather than a credential that no longer
exists. Check the identity still exists before treating it as one.

### SMTP: identity passwords work, but a refusal can be Migadu's side

An identity with `password_use: "custom"` authenticates SMTP submission at
`smtp.migadu.com` with its own address and password, so one identity covers a
phone's incoming and outgoing servers. There is no `may_access_smtp` flag;
`may_send` defaults to true and is all it needs.

On 2026-11-12, though, every identity — made in the admin UI or through the
API, with or without a password reset — logged in to IMAP fine while SMTP
refused it:

```
535 5.7.8 Authentication credentials invalid
```

Migadu support put this down to a brief connectivity issue on their side, and
afterwards an identity that had been refused authenticated (`235`). One
identity in another domain was still refused after the fix and was left with
support.

So a `535` from SMTP for an identity whose password works on IMAP is not a
wrong password and not a missing API field. Don't send the parent password
to work around it: stop retrying (after several failures one
attempt drew `454 4.7.0 temporary authentication failure`), and report it to
Migadu support.

Two distinct uses, needing opposite settings:

- **Per-device credential.** One identity per client, with only the protocols
  that client needs. A leaked phone password is revoked by deleting that one
  identity.
- **Send-as persona.** Sending from `billing@` out of your own mailbox. Here
  Migadu's guide notes "the password of the identity is irrelevant and does not
  have to be used" — set every `may_access_*` false and the credential is
  never a liability.

Note the overlap with existing mechanisms is smaller than it looks:
plus-addressing tags *inbound* mail and grants no sending identity; aliases
forward and cannot authenticate, so an alias can never be the From of an
authenticated submission. Identities are the only one of the three that yields
a credential.

## Service endpoints

| Service | Host | Port |
|---|---|---|
| IMAP | `imap.migadu.com` | 993 (TLS) |
| SMTP submission | `smtp.migadu.com` | 465 (TLS) |
| POP3 | `pop.migadu.com` | 995 (TLS) |
| ManageSieve | `imap.migadu.com` | 4190 (STARTTLS) |
| Admin API | `api.migadu.com` | 443 |

Inbound MX: `aspmx1.migadu.com` (10), `aspmx2.migadu.com` (20).

## Autoconfig over your own domain fails TLS (harmlessly)

`autoconfig.yourdomain.com` CNAMEd to `autoconfig.migadu.com` returns a
certificate for **`admin.migadu.com`**, so HTTPS fails with a hostname
mismatch:

```
$ openssl s_client -connect autoconfig.example.com:443 \
    -servername autoconfig.example.com </dev/null |
  openssl x509 -noout -subject -ext subjectAltName
subject=CN=admin.migadu.com
    DNS:admin.migadu.com
```

The cause is server-side, not a DNS mistake: `autoconfig.migadu.com`,
`admin.migadu.com` and your CNAME all resolve to the same IP, and that server
has no vhost for your domain, so it falls back to its default certificate.
`autoconfig.migadu.com` requested by its own name has a perfectly valid cert.
Nothing in your DNS can fix this.

**It does not break client setup.** Thunderbird tries several URLs in order,
and the plain-HTTP one succeeds:

| URL | Result |
|---|---|
| `https://autoconfig.<domain>/mail/config-v1.1.xml` | fails (TLS mismatch) |
| `https://<domain>/.well-known/autoconfig/...` | 404 |
| `http://autoconfig.<domain>/mail/config-v1.1.xml` | **200, correct settings** |

The HTTP response is a valid `clientConfig` naming `imap.migadu.com:993` and
`smtp.migadu.com:465`, with the user's address pre-filled. Autoconfig therefore
works in practice — verified against a live domain.

Outlook autodiscovery uses the `_autodiscover._tcp` SRV record and
`autodiscover.migadu.com`, which has a valid certificate for its own name, so
that path is unaffected.

Still document manual settings in any user-facing guide: they always work, they
are needed for clients with no autoconfig support, and they do not depend on a
plaintext HTTP fetch succeeding. `docs/user-guide.md` does this — it walks
through manual setup and treats any automatic configuration as a bonus.

## Storage

Quota is shared across **all** mailboxes on the account, not per mailbox. Query
the real figure rather than guessing:

```
GET /v1/domains/{domain}/usage
```

`bin/status` prints it when the admin API is configured.
