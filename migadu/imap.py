"""IMAP helpers for Migadu."""

import imaplib

from . import creds

HOST = "imap.migadu.com"
PORT = 993

imaplib._MAXLINE = 10_000_000


def connect(user=None, password=None):
    if user is None or password is None:
        user, password = creds.imap()
    M = imaplib.IMAP4_SSL(HOST, PORT)
    M.login(user, password)
    return M


def utf7_encode(name):
    """Unicode -> IMAP modified UTF-7 (RFC 3501 section 5.1.3).

    Migadu rejects literal UTF-8 in mailbox names, so '&' and any non-ASCII
    character must be encoded. Note its webmail does not decode this for
    display, so a folder named 'A & B' shows up as 'A &- B' there -- prefer
    names without '&'.
    """
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


def utf7_decode(name):
    """IMAP modified UTF-7 -> unicode."""
    out = []
    i = 0
    while i < len(name):
        if name[i] == "&":
            j = name.find("-", i)
            if j == -1:
                out.append(name[i:])
                break
            chunk = name[i + 1 : j]
            if chunk == "":
                out.append("&")
            else:
                import base64

                pad = "=" * (-len(chunk) % 4)
                try:
                    out.append(
                        base64.b64decode(chunk.replace(",", "/") + pad).decode("utf-16-be")
                    )
                except Exception:
                    out.append(name[i : j + 1])
            i = j + 1
        else:
            out.append(name[i])
            i += 1
    return "".join(out)


def folders(M):
    """Selectable folder names, decoded from modified UTF-7."""
    ok, data = M.list()
    if ok != "OK":
        return []
    out = []
    for raw in data:
        if not raw:
            continue
        line = raw.decode(errors="replace")
        if "\\Noselect" in line:
            continue
        # LIST reply: (flags) "delim" name -- the name is quoted only when it
        # contains spaces, and may itself contain the delimiter.
        after_flags = line.split(")", 1)[1].strip()
        parts = after_flags.split(None, 1)
        if len(parts) != 2:
            continue
        name = parts[1].strip()
        if len(name) > 1 and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]
        out.append(utf7_decode(name))
    return out


def counts(M, names=None):
    """{folder: message_count}. Selects read-only, so nothing is modified."""
    out = {}
    for name in names if names is not None else folders(M):
        try:
            ok, d = M.select(f'"{utf7_encode(name)}"', readonly=True)
            out[name] = int(d[0]) if ok == "OK" else None
        except imaplib.IMAP4.error:
            out[name] = None
    return out
