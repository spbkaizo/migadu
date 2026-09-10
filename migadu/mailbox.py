"""Resolve a mailbox argument to an address, domain and rules directory.

The account hosts more than one domain, and a local part can exist in several
of them -- `admin@` typically exists in all. So a bare local part is only
usable when it is unambiguous, and the tools ask for a full address otherwise
rather than guessing and acting on the wrong mailbox.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAILBOXES = os.path.join(ROOT, "mailboxes")


class Ambiguous(Exception):
    """A bare local part exists in more than one domain."""


class Unknown(Exception):
    """No such mailbox on the account."""


def directory(address):
    """Rules directory for an address. Named for the full address."""
    return os.path.join(MAILBOXES, address)


def filters_path(address):
    return os.path.join(directory(address), "filters.sieve")


def resolve(arg, admin=None, default_domain=None):
    """Turn a CLI argument into (address, local_part, domain).

    Accepts a full address, or a bare local part when that is unambiguous.
    With an Admin client, the local part is checked against the live account so
    a typo fails immediately rather than at the first write. Without one, the
    local directories are used instead, so the sieve tools keep working when
    the admin API is not configured.
    """
    if "@" in arg:
        local, _, domain = arg.partition("@")
        return arg, local, domain

    # An explicit domain settles it, so never report ambiguity over it.
    if default_domain:
        return f"{arg}@{default_domain}", arg, default_domain

    candidates = []
    if admin is not None:
        for d in admin.domains().get("domains", []):
            name = d["name"]
            for m in admin.mailboxes(name).get("mailboxes", []):
                if m["local_part"] == arg:
                    candidates.append(name)
    else:
        if os.path.isdir(MAILBOXES):
            for entry in os.listdir(MAILBOXES):
                local, sep, domain = entry.partition("@")
                if sep and local == arg:
                    candidates.append(domain)

    if len(candidates) == 1:
        domain = candidates[0]
        return f"{arg}@{domain}", arg, domain

    if not candidates:
        raise Unknown(f"no mailbox '{arg}' found -- give the full address")

    raise Ambiguous(
        f"'{arg}' exists in {len(candidates)} domains ({', '.join(sorted(candidates))}); "
        f"use the full address, e.g. {arg}@{sorted(candidates)[0]}"
    )
