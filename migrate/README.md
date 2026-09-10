# outlook.com -> Migadu migration

One-time tooling. Once your mail is moved, nothing here runs again.

See [`../docs/migration-guide.md`](../docs/migration-guide.md) for the full
walkthrough, including why outlook.com needs OAuth2 and the traps in its IMAP
implementation.

## Order

```sh
python3 login.py                            # OAuth2 device-code sign-in
python3 report.py you@example.com           # read-only survey
MAIL_DEST=~/mail-archive/you python3 download.py you@example.com
MAIL_DEST=~/mail-archive/you python3 classify.py
MAIL_DEST=~/mail-archive/you python3 classify.py --apply
MAIL_SYNC=~/mail-archive/you-sync python3 upload.py
```

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `MAIL_DEST` | maildir archive root | `~/mail-archive/mailbox` |
| `MAIL_SYNC` | tree to upload to Migadu | `~/mail-archive/mailbox-sync` |
| `MAIL_REPORT` | classification report path | `./classification-report.txt` |
| `MIGADU_SECRET` | credentials file | `~/.migadu-secret` |

## Safety

`report.py`, `download.py` and `classify.py` never modify the source mailbox —
every IMAP `SELECT` is read-only, and no message is deleted from Outlook.

`classify.py --purge-courier` is the one exception: it permanently deletes
courier-tracking mail from your **local archive** (never the server). It is a
separate flag from `--apply` precisely so it cannot happen by accident.

Outputs (`classification-report.txt`, `*.log`, `.upload-state.json`) contain
real addresses and Message-IDs. They are gitignored. Keep it that way.
