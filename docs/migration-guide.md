# Migrating from outlook.com to Migadu

What actually worked, including the parts that wasted the most time. This is
the only source provider supported here.

## The blocker nobody mentions

outlook.com has **disabled IMAP password authentication**. The capability
banner says it plainly:

```
* CAPABILITY IMAP4 IMAP4rev1 AUTH=XOAUTH2 LOGINDISABLED ...
```

`LOGINDISABLED` means no password will ever work, app password or not. Every
tool needs an OAuth2 bearer token.

Meanwhile the export routes have closed too:

- The privacy portal (`account.microsoft.com/privacy`) no longer offers mail
  export.
- PST export requires **classic** Outlook desktop. The new Outlook app and the
  web interface cannot do it.

That leaves IMAP with OAuth2.

## Getting a token without registering an Azure app

Thunderbird's registered public client id works with Microsoft's device-code
flow, so no Azure app registration or admin consent is needed:

```
client_id = 9e5f94bc-e8a4-4e73-b8be-63364c29d753
scope     = https://outlook.office.com/IMAP.AccessAsUser.All offline_access
tenant    = consumers
```

`migrate/oauth.py` implements it. You get a URL and a short code, sign in with
your own browser and MFA, and the token lands locally. No password reaches the
tooling.

Run the sign-in as its own step — the device code expires in 15 minutes, and
you do not want it printed at the start of a long-running survey:

```
python3 migrate/login.py
```

## Order of operations

```
python3 migrate/login.py                       # sign in once
python3 migrate/report.py you@example.com      # read-only survey
MAIL_DEST=~/mail-archive/you \
  python3 migrate/download.py you@example.com  # maildir, resumable
MAIL_DEST=~/mail-archive/you \
  python3 migrate/classify.py                  # report: what to sync
MAIL_DEST=~/mail-archive/you \
  python3 migrate/classify.py --apply          # build sync/ and cold/ trees
MAIL_SYNC=~/mail-archive/you-sync \
  python3 migrate/upload.py                    # push to Migadu
```

`report.py` opens folders read-only and fetches only `RFC822.SIZE` and
`INTERNALDATE`. Run it first: it tells you how much mail you have per folder
and per year, so the sync cutoff is chosen against real numbers.

## Four traps in Outlook's IMAP

**1. FETCH responses are split.** Outlook returns the message as a
`(head, body)` tuple followed by a *separate* bytes element carrying `UID` and
`INTERNALDATE`:

```
TUPLE head: b'1 (RFC822 {2137}'
body bytes: 2137
BYTES:      b' INTERNALDATE "16-May-2026 06:34:03 +0100" UID 13862)'
```

Parsing metadata from the tuple head finds no UID and silently discards every
message — while still marking them fetched. Read the trailing element.

**2. Folder names are inconsistently quoted.** `LIST` returns bare names
(`Inbox/Finance`) but quotes any containing spaces (`"Inbox/Mailing Lists"`).
Splitting on the last token yields the delimiter `/` rather than the name.

**3. Filenames must key on UID alone.** Embedding a fetch timestamp means a
refetch writes new files instead of matching existing ones, silently doubling
the archive. `U<uid>.<host>:2,S` is idempotent.

**4. Never deduplicate by content hash.** Byte-identical messages legitimately
exist in several folders — the same receipt filed twice, a message and its Sent
copy. Hash-based dedup deletes real mail. Use `Message-ID` or UID.

## Storage: measure before deciding

Intuition is wrong here. In a 28,381-message archive:

- 8,553 messages carried `List-Unsubscribe` — but only 0.43 GB total
- 348 messages (1.2%) held **58%** of all bytes
- Median message: 15.7 KB

Filtering marketing barely helps a quota problem. Large attachments and
re-quoted threads do. And the large mail is often the *most* valuable —
solicitor documents, signed contracts — so a flat size cap discards legal
records while keeping trivia. Cap by category, not globally.

## Local disk first, network storage second

Writing maildir straight to an SMB share was measured at **19 files/s**. The
same writes locally: **7,348 files/s** — 385x faster. Over half the SMB cost
was the maildir `tmp/`→`cur/` rename, whose atomicity guarantee is pointless
when nothing else reads the archive.

Download locally, then bulk-rsync to network storage once.

## Do not delete the old account yet

Keep outlook.com as a fallback until the new mailbox has been in real use for a
few weeks. The OAuth token stays valid for refetching anything missed.
