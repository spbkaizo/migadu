"""Client for the Migadu admin REST API (https://api.migadu.com/v1/).

HTTP Basic: username is the Migadu *account* email, password is an API key
generated at My Account > API Keys. That key is a separate credential from any
mailbox password.

Mostly read operations. The API supports create/update/delete for every resource
here, but those change live mail service, so add them deliberately rather than
by reflex. The only writes implemented are the two password paths on an existing
mailbox -- see set_password() and invite().
"""

import base64
import json
import urllib.error
import urllib.request

from . import creds

BASE = "https://api.migadu.com/v1"


class NotConfigured(Exception):
    """No API key available."""


class Admin:
    def __init__(self, user=None, key=None):
        if user is None or key is None:
            pair = creds.admin()
            if not pair:
                raise NotConfigured(
                    "set MIGADU_API_USER and MIGADU_API_KEY (My Account > API Keys), "
                    "or write '<account-email> <api-key>' to ~/.migadu-api-secret"
                )
            user, key = pair
        self._auth = base64.b64encode(f"{user}:{key}".encode()).decode()

    def _request(self, path, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
        req.add_header("Authorization", f"Basic {self._auth}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"{e.code} {e.reason} for {method} {path}: {body}") from None

    def _get(self, path):
        return self._request(path)

    def domains(self):
        return self._get("/domains")

    def mailboxes(self, domain):
        return self._get(f"/domains/{domain}/mailboxes")

    def identities(self, domain, local_part):
        return self._get(f"/domains/{domain}/mailboxes/{local_part}/identities")

    def aliases(self, domain):
        return self._get(f"/domains/{domain}/aliases")

    def rewrites(self, domain):
        return self._get(f"/domains/{domain}/rewrites")

    def usage(self, domain):
        return self._get(f"/domains/{domain}/usage")

    def diagnostics(self, domain):
        return self._get(f"/domains/{domain}/diagnostics")

    def mailbox(self, domain, local_part):
        return self._get(f"/domains/{domain}/mailboxes/{local_part}")

    # --- writes ---------------------------------------------------------
    #
    # Both change a live mailbox's credentials. Everything else in this class
    # is read-only; keep it that way unless there is a clear reason.

    def set_password(self, domain, local_part, password, activate=True):
        """Set a mailbox password directly.

        A mailbox left awaiting an invitation is `is_active: false` and cannot
        be used, so setting a password reactivates it by default.

        The caller is then holding a live credential and is responsible for
        delivering it safely.
        """
        payload = {"password": password}
        if activate:
            payload["is_active"] = True
        return self._request(
            f"/domains/{domain}/mailboxes/{local_part}",
            method="PUT",
            payload=payload,
        )

    def invite(self, domain, local_part, recovery_email):
        """Set the invitation fields on an existing mailbox.

        WARNING: Migadu documents `password_method: "invitation"` only for
        mailbox *creation* (POST). Sending it via PUT to an existing mailbox is
        accepted -- the recovery address is stored and the mailbox is set
        `is_active: false` -- but **no invitation email is sent**. The mailbox
        is then unusable until a password is set another way.

        Verified against the live API 2026-09-10. Use set_password(), or
        Migadu's own webmail password-reset flow, to give an existing user
        access.
        """
        return self._request(
            f"/domains/{domain}/mailboxes/{local_part}",
            method="PUT",
            payload={
                "password_method": "invitation",
                "password_recovery_email": recovery_email,
            },
        )
