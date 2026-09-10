"""Download an Outlook.com mailbox to maildir, resumably.

Writes one maildir per IMAP folder under DEST. Progress is checkpointed per
folder so an interrupted run (dropped SMB mount, expired token, closed laptop)
resumes without re-fetching. Server is opened read-only throughout.
"""

import email
import email.utils
import imaplib
import json
import os
import socket
import sys
import time

import oauth
import report

DEST = os.environ.get("MAIL_DEST", os.path.expanduser("~/mail-archive/mailbox"))
STATE = os.path.join(DEST, ".download-state.json")
BATCH = 100
imaplib._MAXLINE = 10_000_000


def decode_folder(name):
    """IMAP modified-UTF7 -> unicode (e.g. 'Sales &- Orders' -> 'Sales & Orders')."""
    try:
        out, i = [], 0
        while i < len(name):
            if name[i] == "&":
                j = name.index("-", i)
                chunk = name[i + 1 : j]
                if chunk == "":
                    out.append("&")
                else:
                    import base64

                    pad = "=" * (-len(chunk) % 4)
                    out.append(base64.b64decode(chunk.replace(",", "/") + pad).decode("utf-16-be"))
                i = j + 1
            else:
                out.append(name[i])
                i += 1
        return "".join(out)
    except Exception:
        return name


def safe_path(name):
    return decode_folder(name).replace("/", ".").replace(os.sep, ".")


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, STATE)


def maildir(base):
    for sub in ("cur", "new", "tmp"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)


def write_msg(base, uid, raw, internaldate):
    ts = int(time.time())
    if internaldate:
        try:
            ts = int(time.mktime(imaplib.Internaldate2tuple(internaldate)))
        except Exception:
            pass
    # Filename is keyed on UID only -- no timestamp -- so refetching a folder
    # overwrites rather than duplicating. UIDs are stable per folder in IMAP.
    fn = f"U{uid}.{socket.gethostname()}:2,S"
    path = os.path.join(base, "cur", fn)
    if os.path.exists(path):
        return False
    # Written directly into cur/ rather than via tmp/: nothing reads this
    # archive concurrently, and the rename doubles cost on network storage.
    with open(path, "wb") as f:
        f.write(raw)
    try:
        os.utime(path, (ts, ts))
    except OSError:
        pass
    return True


def fetch_folder(M, folder, st):
    key = folder
    done = set(st.get(key, {}).get("uids", []))
    base = os.path.join(DEST, safe_path(folder))

    try:
        ok, d = M.select(f'"{folder}"', readonly=True)
    except imaplib.IMAP4.error as e:
        print(f"  SKIP {folder}: {e}")
        return 0
    if ok != "OK":
        print(f"  SKIP {folder}: select failed")
        return 0

    ok, d = M.uid("SEARCH", None, "ALL")
    if ok != "OK" or not d[0]:
        return 0
    uids = [u.decode() for u in d[0].split()]
    todo = [u for u in uids if u not in done]
    if not todo:
        print(f"  {decode_folder(folder)}: complete ({len(uids)})")
        return 0

    maildir(base)
    print(f"  {decode_folder(folder)}: {len(todo)} to fetch ({len(done)} already)", flush=True)

    got = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        try:
            ok, resp = M.uid("FETCH", ",".join(chunk), "(RFC822 INTERNALDATE)")
        except (imaplib.IMAP4.error, OSError) as e:
            print(f"    fetch error, will resume: {e}")
            break
        if ok != "OK":
            break

        # Outlook returns each message as a (head, body) tuple followed by a
        # bytes element carrying UID and INTERNALDATE, so metadata must be read
        # from the trailing element rather than the tuple head.
        pending = None
        for item in resp:
            if isinstance(item, tuple):
                pending = (item[0].decode(errors="replace"), item[1])
                continue

            meta = item.decode(errors="replace") if isinstance(item, bytes) else ""
            if pending is None:
                continue
            head, raw = pending
            pending = None

            blob = head + " " + meta
            uid = idate = None
            if "UID " in blob:
                try:
                    uid = blob.split("UID ")[1].split()[0].strip(" )")
                except IndexError:
                    pass
            if 'INTERNALDATE "' in blob:
                try:
                    idate = '"' + blob.split('INTERNALDATE "')[1].split('"')[0] + '"'
                except IndexError:
                    pass

            if uid and raw:
                if write_msg(base, uid, raw, idate):
                    got += 1
                done.add(uid)

        # A batch that returns nothing means the response shape was not
        # understood; stop rather than checkpoint UIDs that were never written.
        if not any(isinstance(x, tuple) for x in resp):
            print(f"\n    no messages parsed in batch -- stopping {folder}")
            return got

        st.setdefault(key, {})["uids"] = sorted(done)
        save_state(st)
        print(f"    {min(i + BATCH, len(todo))}/{len(todo)}", end="\r", flush=True)

    print(" " * 60, end="\r")
    return got


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: download.py <email-address>  (MAIL_DEST sets the destination)")
    user = sys.argv[1]
    print(f"Destination: {DEST}")
    os.makedirs(DEST, exist_ok=True)

    st = load_state()
    M = report.connect(user)
    fl = report.folders(M)
    print(f"{len(fl)} folders\n", flush=True)

    total = 0
    for f in fl:
        try:
            total += fetch_folder(M, f, st)
        except (imaplib.IMAP4.abort, OSError) as e:
            print(f"\nconnection lost ({e}); reconnecting ...", flush=True)
            try:
                M.logout()
            except Exception:
                pass
            M = report.connect(user)
            total += fetch_folder(M, f, st)

    print(f"\nDownloaded {total} new messages this run.")
    print(f"Archive: {DEST}")
    try:
        M.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
