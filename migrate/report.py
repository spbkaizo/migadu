"""Read-only survey of an Outlook.com mailbox over IMAP.

Reports message counts and sizes per folder and per year so the migration
cutoff can be chosen against real numbers. Opens folders read-only and writes
nothing to the server.
"""

import collections
import imaplib
import sys

import oauth

HOST = "outlook.office365.com"
SIZE_BUCKETS = [(5, "5MB+"), (10, "10MB+"), (25, "25MB+")]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def connect(user):
    M = imaplib.IMAP4_SSL(HOST, 993)
    tok = oauth.get_token()
    M.authenticate("XOAUTH2", lambda _: f"user={user}\x01auth=Bearer {tok}\x01\x01".encode())
    return M


def folders(M):
    ok, data = M.list()
    if ok != "OK":
        raise SystemExit("LIST failed")
    out = []
    for raw in data:
        if not raw:
            continue
        line = raw.decode(errors="replace")
        if "\\Noselect" in line:
            continue
        # LIST reply: (flags) "delim" name -- the name is quoted only when it
        # contains spaces, and may itself contain the delimiter, so take
        # everything after the delimiter field and unquote if needed.
        after_flags = line.split(")", 1)[1].strip()
        parts = after_flags.split(None, 1)
        if len(parts) != 2:
            continue
        name = parts[1].strip()
        if len(name) > 1 and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]
        out.append(name)
    return out


def survey(M, folder):
    """Return (count, total_bytes, per_year, big_counts) for one folder."""
    try:
        ok, d = M.select(f'"{folder}"', readonly=True)
    except imaplib.IMAP4.error:
        return None
    if ok != "OK":
        return None
    n = int(d[0])
    if n == 0:
        return 0, 0, {}, {}

    ok, d = M.search(None, "ALL")
    if ok != "OK" or not d[0]:
        return 0, 0, {}, {}
    uids = d[0].split()

    total = 0
    per_year = collections.defaultdict(lambda: [0, 0])  # year -> [count, bytes]
    big = collections.Counter()

    # Fetch metadata only -- no message bodies.
    for i in range(0, len(uids), 500):
        chunk = b",".join(uids[i : i + 500]).decode()
        ok, resp = M.fetch(chunk, "(RFC822.SIZE INTERNALDATE)")
        if ok != "OK":
            continue
        for item in resp:
            if not isinstance(item, bytes):
                item = item[0] if isinstance(item, tuple) else b""
            s = item.decode(errors="replace")
            size = year = None
            if "RFC822.SIZE" in s:
                try:
                    size = int(s.split("RFC822.SIZE")[1].split()[0].strip(" )"))
                except (ValueError, IndexError):
                    pass
            if "INTERNALDATE" in s:
                # INTERNALDATE format: "05-Sep-2026 09:45:05 +0000"
                try:
                    ds = s.split('INTERNALDATE "')[1].split('"')[0]
                    year = int(ds.split("-")[2].split()[0])
                except (ValueError, IndexError):
                    pass
            if size is None:
                continue
            total += size
            if year:
                per_year[year][0] += 1
                per_year[year][1] += size
            for mb, label in SIZE_BUCKETS:
                if size >= mb * 1024 * 1024:
                    big[label] += 1
        print(f"    {folder}: {min(i + 500, len(uids))}/{len(uids)}", end="\r", flush=True)

    print(" " * 70, end="\r")
    return len(uids), total, dict(per_year), dict(big)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: report.py <email-address>")
    user = sys.argv[1]

    print(f"Connecting to {HOST} as {user} ...", flush=True)
    M = connect(user)
    print("Connected.\n", flush=True)

    fl = folders(M)
    print(f"{len(fl)} selectable folders\n", flush=True)

    grand_n = grand_b = 0
    year_tot = collections.defaultdict(lambda: [0, 0])
    big_tot = collections.Counter()
    rows = []

    skipped = []
    for f in fl:
        r = survey(M, f)
        if not r:
            skipped.append(f)
            continue
        n, b, py, big = r
        if n:
            rows.append((f, n, b))
            grand_n += n
            grand_b += b
            for y, (c, sz) in py.items():
                year_tot[y][0] += c
                year_tot[y][1] += sz
            big_tot.update(big)

    print("=" * 62)
    print(f"{'FOLDER':<34}{'MSGS':>8}{'SIZE':>12}")
    print("=" * 62)
    for f, n, b in sorted(rows, key=lambda r: -r[2]):
        print(f"{f[:33]:<34}{n:>8}{human(b):>12}")
    print("-" * 62)
    print(f"{'TOTAL':<34}{grand_n:>8}{human(grand_b):>12}")

    print("\n" + "=" * 62)
    print(f"{'YEAR':<34}{'MSGS':>8}{'SIZE':>12}")
    print("=" * 62)
    cum = 0
    for y in sorted(year_tot, reverse=True):
        c, sz = year_tot[y]
        cum += sz
        print(f"{y:<34}{c:>8}{human(sz):>12}   (cumulative {human(cum)})")

    print("\n" + "=" * 62)
    print("LARGE MESSAGES")
    print("=" * 62)
    for _, label in SIZE_BUCKETS:
        print(f"  {label:<10}{big_tot.get(label, 0):>8} messages")
    if skipped:
        print("\n" + "=" * 62)
        print(f"UNREADABLE FOLDERS ({len(skipped)})")
        print("=" * 62)
        for f in skipped:
            print(f"  {f}")

    print(f"\nMigadu quota is 5GB across ALL mailboxes.")
    try:
        M.logout()
    except Exception:
        pass


if __name__ == "__main__":
    main()
