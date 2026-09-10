"""Classify the local mail archive into sync vs cold-archive tiers.

Default mode writes a report and touches nothing. --apply builds hardlinked
sync/ and cold/ trees from the approved rules. The source archive is only ever
read.
"""

import argparse
import collections
import email
import email.policy
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

SRC = os.path.expanduser(os.environ.get("MAIL_DEST", "~/mail-archive/mailbox"))
SYNC = SRC + "-sync"
COLD = SRC + "-cold"
REPORT = os.path.expanduser(os.environ.get("MAIL_REPORT", "./classification-report.txt"))

WINDOW_DAYS = 183
BULK_CAP = 2 * 1024 * 1024
BIG = 3 * 1024 * 1024

AUTO_RE = re.compile(r"no-?reply|donotreply|notification|alert|automated|mailer", re.I)

# Domain-anchored so it cannot match substrings in unrelated addresses.
COURIER_RE = re.compile(
    r"@([\w.-]*\.)?(evri\.com|royalmail\.com|dpd\.co\.uk|yodel\.co\.uk"
    r"|parcelforce\.co\.uk|dhlecommerce\.co\.uk|dhl\.com|ups\.com|fedex\.com"
    r"|inpost\.co\.uk)|no-?reply_at_(royalmail|parcelforce)_",
    re.I,
)

# Machine-generated notifications that carry no lasting value.
DROP_SENDERS = re.compile(r"@kierfiold\.grafana\.net|@ebay\.com|@members\.ebay\.com", re.I)

# Folders never synced to the new provider.
NO_SYNC_FOLDERS = {"Junk", "Deleted"}
RECEIPT_RE = re.compile(
    r"receipt|invoice|order #|your order|payment|dispatch|delivery|booking|confirmation", re.I
)

SYNC_TIERS = {"1-correspondence", "2-receipts", "2-other"}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def hv(msg, header):
    v = msg.get(header)
    return str(v) if v is not None else ""


def addr(text):
    m = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text.lower())
    return m[0] if m else ""


def norm_subject(s):
    return re.sub(r"^(re|fw|fwd)\s*:\s*", "", s.strip(), flags=re.I).lower()


def attachment_digest(msg):
    """SHA-256 over each attachment payload, for spotting re-quoted copies."""
    out = []
    for part in msg.walk():
        if part.get_filename():
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload and len(payload) > 32 * 1024:
                out.append(hashlib.sha256(payload).hexdigest())
    return frozenset(out)


class Msg:
    __slots__ = (
        "path", "folder", "size", "date", "frm", "subject", "msgid",
        "bulk", "thread", "auto", "receipt", "tier", "atts", "reason", "courier",
    )


def load(src):
    msgs = []
    for folder in sorted(os.listdir(src)):
        cur = os.path.join(src, folder, "cur")
        if not os.path.isdir(cur):
            continue
        for fn in os.listdir(cur):
            p = os.path.join(cur, fn)
            try:
                with open(p, "rb") as fh:
                    m = email.message_from_binary_file(fh)
            except Exception:
                continue
            o = Msg()
            o.path = p
            o.folder = folder
            o.size = os.path.getsize(p)
            try:
                d = parsedate_to_datetime(hv(m, "Date"))
                o.date = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
            except Exception:
                o.date = None
            o.frm = addr(hv(m, "From"))
            o.subject = hv(m, "Subject")
            o.msgid = hv(m, "Message-ID").strip()
            o.bulk = bool(hv(m, "List-Unsubscribe")) or hv(m, "Precedence").lower().startswith(
                ("bulk", "list")
            )
            o.thread = bool(hv(m, "In-Reply-To") or hv(m, "References"))
            o.auto = bool(AUTO_RE.search(hv(m, "From")))
            o.courier = bool(COURIER_RE.search(hv(m, "From")))
            o.receipt = bool(RECEIPT_RE.search(o.subject))
            o.atts = attachment_digest(m) if o.size >= 256 * 1024 else frozenset()
            o.tier = None
            o.reason = ""
            msgs.append(o)
    return msgs


def correspondents(msgs, src):
    """Addresses the mailbox owner actually wrote to -- the strongest
    'this matters' signal available without reading message bodies."""
    out = set()
    cur = os.path.join(src, "Sent", "cur")
    if not os.path.isdir(cur):
        return out
    for fn in os.listdir(cur):
        try:
            with open(os.path.join(cur, fn), "rb") as fh:
                m = email.message_from_binary_file(fh)
        except Exception:
            continue
        for a in re.findall(
            r"[\w.+-]+@[\w.-]+\.\w+", (hv(m, "To") + " " + hv(m, "Cc")).lower()
        ):
            out.add(a)
    return out


def classify(msgs, corr, cutoff):
    for o in msgs:
        if o.courier:
            o.tier, o.reason = "5-courier", "courier tracking (purgeable)"
        elif o.folder in NO_SYNC_FOLDERS:
            o.tier, o.reason = "4-junk", f"{o.folder} folder"
        elif DROP_SENDERS.search(o.frm):
            o.tier, o.reason = "3-bulk-auto", "notification-only sender"
        elif o.bulk:
            o.tier, o.reason = "3-bulk-auto", "List-Unsubscribe/Precedence"
        elif o.folder == "Sent" or (o.frm in corr and o.frm):
            o.tier, o.reason = "1-correspondence", "known correspondent"
        elif o.thread:
            o.tier, o.reason = "1-correspondence", "in a thread"
        elif o.receipt:
            o.tier, o.reason = "2-receipts", "receipt-like subject"
        elif o.auto:
            o.tier, o.reason = "3-bulk-auto", "automated sender"
        else:
            o.tier, o.reason = "2-other", "unclassified"


def suppress_sent_dupes(msgs, cutoff):
    """Route Sent copies that merely re-quote Inbox attachments to cold."""
    inbox_atts = collections.defaultdict(set)
    for o in msgs:
        if o.folder != "Sent" and o.atts and in_window(o, cutoff):
            inbox_atts[norm_subject(o.subject)] |= o.atts

    suppressed = []
    for o in msgs:
        if o.folder == "Sent" and o.atts and in_window(o, cutoff):
            seen = inbox_atts.get(norm_subject(o.subject), set())
            if o.atts and o.atts <= seen:
                o.reason = "Sent copy re-quotes Inbox attachments"
                suppressed.append(o)
    return suppressed


def in_window(o, cutoff):
    return o.date is not None and o.date >= cutoff


def selected(o, cutoff, suppressed):
    if id(o) in suppressed:
        return False
    if not in_window(o, cutoff):
        return False
    if o.tier not in SYNC_TIERS:
        return False
    return True


def write_report(msgs, corr, cutoff, suppressed, path):
    sup = set(id(x) for x in suppressed)
    L = []
    w = L.append

    total_n = len(msgs)
    total_b = sum(o.size for o in msgs)
    w("=" * 78)
    w("MAIL ARCHIVE CLASSIFICATION REPORT")
    w("=" * 78)
    w(f"source        : {SRC}")
    w(f"total         : {total_n} messages, {human(total_b)}")
    w(f"window        : last {WINDOW_DAYS} days (since {cutoff.date()})")
    w(f"correspondents: {len(corr)} addresses extracted from Sent")
    w("")

    tn = collections.Counter()
    tb = collections.Counter()
    for o in msgs:
        tn[o.tier] += 1
        tb[o.tier] += o.size
    w("ALL MAIL BY TIER")
    w("-" * 78)
    for t in sorted(tn):
        w(f"  {t:20} {tn[t]:6} msgs  {human(tb[t]):>10}")
    w(f"  {'TOTAL':20} {sum(tn.values()):6} msgs  {human(sum(tb.values())):>10}")
    w("")

    inw = [o for o in msgs if in_window(o, cutoff)]
    wn = collections.Counter()
    wb = collections.Counter()
    for o in inw:
        wn[o.tier] += 1
        wb[o.tier] += o.size
    w(f"IN WINDOW ({len(inw)} msgs, {human(sum(o.size for o in inw))})")
    w("-" * 78)
    for t in sorted(wn):
        mark = "SYNC" if t in SYNC_TIERS else "cold"
        w(f"  [{mark}] {t:20} {wn[t]:6} msgs  {human(wb[t]):>10}")
    w("")

    sel = [o for o in msgs if selected(o, cutoff, sup)]
    w("=" * 78)
    w(f"=> WOULD SYNC: {len(sel)} messages, {human(sum(o.size for o in sel))}")
    w(f"=> suppressed Sent duplicates: {len(suppressed)} messages, "
      f"{human(sum(o.size for o in suppressed))}")
    w("=" * 78)
    w("")

    w("REVIEW BUCKET -- '2-other' senders in window (decide tier for each)")
    w("-" * 78)
    oc = collections.Counter()
    ob = collections.Counter()
    for o in inw:
        if o.tier == "2-other":
            oc[o.frm] += 1
            ob[o.frm] += o.size
    for a, c in oc.most_common(40):
        w(f"  {c:5}  {human(ob[a]):>9}  {a}")
    w("")

    w(f"LARGE MESSAGES IN WINDOW (>= {human(BIG)})")
    w("-" * 78)
    big = sorted((o for o in inw if o.size >= BIG), key=lambda o: -o.size)
    for o in big:
        flag = "SYNC" if selected(o, cutoff, sup) else "cold"
        w(f"  [{flag}] {human(o.size):>8}  {o.date.date()}  {o.folder[:20]:22} "
          f"{o.subject[:40]:42} {o.frm[:28]}")
        if id(o) in sup:
            w(f"           ^-- {o.reason}")
    w("")

    w("CROSS-FOLDER DUPLICATES (same Message-ID in >1 folder)")
    w("-" * 78)
    byid = collections.defaultdict(list)
    for o in msgs:
        if o.msgid:
            byid[o.msgid].append(o)
    dupes = [(k, v) for k, v in byid.items() if len(v) > 1]
    pair = collections.Counter()
    wasted = 0
    for _, v in dupes:
        pair[tuple(sorted(set(x.folder for x in v)))] += 1
        wasted += sum(x.size for x in v[1:])
    w(f"  {len(dupes)} duplicated Message-IDs, {human(wasted)} redundant")
    for p, c in pair.most_common(8):
        w(f"    {c:5}  {' + '.join(p)}")
    w("")

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return "\n".join(L)


def apply_split(msgs, cutoff, suppressed):
    sup = set(id(x) for x in suppressed)
    n_sync = n_cold = 0
    for o in msgs:
        dest = SYNC if selected(o, cutoff, sup) else COLD
        out = os.path.join(dest, o.folder, "cur")
        os.makedirs(out, exist_ok=True)
        target = os.path.join(out, os.path.basename(o.path))
        if not os.path.exists(target):
            os.link(o.path, target)
        if dest is SYNC:
            n_sync += 1
        else:
            n_cold += 1
    return n_sync, n_cold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="build sync/ and cold/ trees")
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument(
        "--purge-courier",
        action="store_true",
        help="permanently delete tier 5-courier messages from the source archive",
    )
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"reading {SRC} ...", flush=True)
    msgs = load(SRC)
    print(f"  {len(msgs)} messages", flush=True)

    corr = correspondents(msgs, SRC)
    print(f"  {len(corr)} correspondents", flush=True)

    classify(msgs, corr, cutoff)
    suppressed = suppress_sent_dupes(msgs, cutoff)
    print(f"  {len(suppressed)} Sent duplicates suppressed", flush=True)

    text = write_report(msgs, corr, cutoff, suppressed, REPORT)
    print("\n".join(text.splitlines()[:40]))
    print(f"\nfull report: {REPORT}")

    if args.purge_courier:
        doomed = [o for o in msgs if o.tier == "5-courier"]
        freed = sum(o.size for o in doomed)
        print(f"\npurging {len(doomed)} courier messages ({human(freed)}) from {SRC}")
        for o in doomed:
            os.remove(o.path)
        msgs = [o for o in msgs if o.tier != "5-courier"]
        print(f"archive now {len(msgs)} messages")

    if args.apply:
        ns, nc = apply_split(msgs, cutoff, suppressed)
        print(f"\nsync tree: {ns} messages -> {SYNC}")
        print(f"cold tree: {nc} messages -> {COLD}")


if __name__ == "__main__":
    main()
