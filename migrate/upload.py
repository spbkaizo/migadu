"""Upload the classified sync tree to Migadu over IMAP.

Resumable: a per-folder set of already-uploaded Message-IDs is checkpointed, so
an interrupted run does not create duplicates. Existing server messages are read
first and treated as already present.
"""

import email
import imaplib
import json
import os
import sys
import time

SYNC = os.path.expanduser(os.environ.get("MAIL_SYNC", "~/mail-archive/mailbox-sync"))
STATE = os.path.expanduser(os.environ.get("MIGADU_UPLOAD_STATE", "./.upload-state.json"))
SECRET = os.path.expanduser(os.environ.get("MIGADU_SECRET", "~/.migadu-secret"))
HOST = "imap.migadu.com"

imaplib._MAXLINE = 10_000_000

# Local maildir name -> Migadu folder. Anything unmapped is created under the
# archive root so the original structure survives.
DIRECT = {
    "Inbox": "INBOX",
    "Sent": "Sent",
    "Drafts": "Drafts",
    "Archive": "Archive",
}


def creds():
    raw = open(SECRET, "rb").read().decode().rstrip("\n")
    user, pw = raw.split(" ", 1)
    return user, pw


def connect():
    user, pw = creds()
    M = imaplib.IMAP4_SSL(HOST, 993)
    M.login(user, pw)
    return M


def utf7_encode(name):
    """Unicode -> IMAP modified UTF-7 (RFC 3501). '&' and non-ASCII must be
    encoded or the server rejects the mailbox name."""
    out = []
    i = 0
    while i < len(name):
        c = name[i]
        if c == "&":
            out.append("&-")
            i += 1
        elif 0x20 <= ord(c) <= 0x7E:
            out.append(c)
            i += 1
        else:
            run = []
            while i < len(name) and not (0x20 <= ord(name[i]) <= 0x7E):
                run.append(name[i])
                i += 1
            import base64

            b = "".join(run).encode("utf-16-be")
            out.append("&" + base64.b64encode(b).decode().rstrip("=").replace("/", ",") + "-")
    return "".join(out)


def target_folder(local):
    if local in DIRECT:
        return DIRECT[local]
    # Inbox.Systems.nas -> Inbox/Systems/nas ; keep everything else as-is
    if local.startswith("Inbox."):
        name = "INBOX/" + local[len("Inbox.") :].replace(".", "/")
    else:
        name = local.replace(".", "/")
    return utf7_encode(name)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, STATE)


def ensure_folder(M, name):
    try:
        ok, _ = M.select(f'"{name}"')
        if ok == "OK":
            return True
    except imaplib.IMAP4.error:
        pass
    try:
        M.create(f'"{name}"')
        M.subscribe(f'"{name}"')
    except imaplib.IMAP4.error as e:
        print(f"    cannot create {name}: {e}")
        return False
    try:
        ok, _ = M.select(f'"{name}"')
    except imaplib.IMAP4.error:
        return False
    return ok == "OK"


def server_msgids(M):
    """Message-IDs already on the server for the selected folder."""
    out = set()
    ok, d = M.search(None, "ALL")
    if ok != "OK" or not d[0]:
        return out
    uids = d[0].split()
    for i in range(0, len(uids), 500):
        chunk = b",".join(uids[i : i + 500]).decode()
        ok, resp = M.fetch(chunk, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
        if ok != "OK":
            continue
        for item in resp:
            if isinstance(item, tuple) and item[1]:
                t = item[1].decode(errors="replace")
                if ":" in t:
                    out.add(t.split(":", 1)[1].strip())
    return out


def upload_folder(M, local, st):
    cur = os.path.join(SYNC, local, "cur")
    if not os.path.isdir(cur):
        return 0
    files = sorted(os.listdir(cur))
    if not files:
        return 0

    remote = target_folder(local)
    if not ensure_folder(M, remote):
        print(f"  SKIP {local}: cannot select/create {remote}")
        return 0

    done = set(st.get(remote, []))
    if not done:
        done = server_msgids(M)

    print(f"  {local} -> {remote}: {len(files)} local, {len(done)} already on server", flush=True)

    sent = 0
    for n, fn in enumerate(files, 1):
        p = os.path.join(cur, fn)
        try:
            with open(p, "rb") as fh:
                raw = fh.read()
            msg = email.message_from_bytes(raw)
        except Exception:
            continue
        mid = str(msg.get("Message-ID") or "").strip()
        if mid and mid in done:
            continue

        idate = None
        try:
            idate = imaplib.Time2Internaldate(os.path.getmtime(p))
        except Exception:
            pass

        try:
            ok, _ = M.append(f'"{remote}"', "\\Seen", idate, raw)
        except (imaplib.IMAP4.error, OSError) as e:
            print(f"\n    append failed ({e}); will resume")
            break
        if ok != "OK":
            continue
        sent += 1
        if mid:
            done.add(mid)
        if sent % 25 == 0:
            st[remote] = sorted(done)
            save_state(st)
            print(f"    {n}/{len(files)}", end="\r", flush=True)

    st[remote] = sorted(done)
    save_state(st)
    print(" " * 60, end="\r")
    return sent


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    st = load_state()
    M = connect()
    print(f"connected to {HOST}\n")

    folders = sorted(d for d in os.listdir(SYNC) if os.path.isdir(os.path.join(SYNC, d)))
    if only:
        folders = [f for f in folders if f == only]

    total = 0
    for f in folders:
        try:
            total += upload_folder(M, f, st)
        except (imaplib.IMAP4.abort, OSError) as e:
            print(f"\nreconnecting after {e}")
            try:
                M.logout()
            except Exception:
                pass
            time.sleep(3)
            M = connect()
            total += upload_folder(M, f, st)

    print(f"\nuploaded {total} messages this run")
    try:
        M.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
