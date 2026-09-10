"""Credential resolution for Migadu.

Two distinct secrets are involved:

  mailbox password  -- IMAP, SMTP and ManageSieve
  admin API key     -- the REST API at api.migadu.com, generated at
                       My Account > API Keys. This is NOT the mailbox password.

Environment variables win over the file, so CI or another machine can supply
credentials without writing them to disk.
"""

import os

SECRET_FILE = os.path.expanduser(os.environ.get("MIGADU_SECRET", "~/.migadu-secret"))


class MissingCredentials(Exception):
    pass


def _from_file(path=None):
    """Parse 'user password' from the secret file.

    The password may itself contain spaces, so only the first space separates
    the fields. Getting this wrong produces an authentication failure that
    looks like a wrong password.
    """
    path = path or SECRET_FILE
    try:
        with open(path, "rb") as f:
            raw = f.read().decode().rstrip("\n")
    except OSError:
        return None
    if " " not in raw:
        return None
    user, password = raw.split(" ", 1)
    return user, password


def imap():
    """(user, password) for IMAP, SMTP and ManageSieve."""
    user = os.environ.get("MIGADU_USER")
    password = os.environ.get("MIGADU_PASS")
    if user and password:
        return user, password

    pair = _from_file()
    if pair:
        return pair

    raise MissingCredentials(
        f"set MIGADU_USER and MIGADU_PASS, or write '<user> <password>' to {SECRET_FILE}"
    )


def admin():
    """(account_email, api_key) for the REST admin API.

    Returns None when no API key is configured, so callers can degrade rather
    than fail -- most of this toolkit works without admin API access.
    """
    user = os.environ.get("MIGADU_API_USER")
    key = os.environ.get("MIGADU_API_KEY")
    if user and key:
        return user, key

    pair = _from_file(os.path.expanduser("~/.migadu-api-secret"))
    if pair:
        return pair

    return None
