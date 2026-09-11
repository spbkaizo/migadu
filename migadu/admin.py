"""Client for the Migadu admin REST API (https://api.migadu.com/v1/).

HTTP Basic: username is the Migadu *account* email, password is an API key
generated at My Account > API Keys. That key is a separate credential from any
mailbox password.

Mostly read operations. The API supports create/update/delete for every resource
here, but those change live mail service, so add them deliberately rather than
by reflex. The writes implemented are the two password paths on an existing
mailbox -- see set_password() and invite() -- and identity create/update/delete,
which manage per-device credentials under a mailbox.
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

    def identity(self, domain, local_part, identity_local_part):
        return self._get(
            f"/domains/{domain}/mailboxes/{local_part}/identities/{identity_local_part}"
        )

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

    # --- identities -----------------------------------------------------
    #
    # An identity is an address under a mailbox with its own password and its
    # own per-protocol permissions -- Migadu's answer to an app password. See
    # docs/migadu-facts.md#identities.

    def create_identity(
        self,
        domain,
        local_part,
        identity_local_part,
        password=None,
        name=None,
        may_send=True,
        may_receive=True,
        may_access_imap=False,
        may_access_pop3=False,
        may_access_managesieve=False,
    ):
        """Create an identity under an existing mailbox.

        Login access defaults to OFF for every protocol: an identity that only
        needs to send (a `billing@` persona, say) should not also be a way in.
        Pass the individual may_access_* flags to grant a device real access.

        `password` is write-only -- the API never returns it afterwards, so a
        generated one not recorded now cannot be recovered. Without it the
        identity exists but has no usable credential, which is the right shape
        for send-only use.

        Two undocumented API requirements, both verified against the live API
        2026-09-11 -- see docs/migadu-facts.md#identities:

        `name` is REQUIRED on create. Without it the POST fails with a bare
        `400 {"error":"bad request"}` naming no field, so it defaults to the
        local part here rather than leaving callers to discover that.

        A password is ONLY stored when `password_use` is sent as "custom".
        Sending `password` alone is accepted, returns 200, and silently leaves
        `password_use: "none"` -- an identity that looks correct in every field
        but rejects every login.
        """
        payload = {
            "local_part": identity_local_part,
            # Required by the API; a bare 400 is the only complaint otherwise.
            "name": name if name is not None else identity_local_part,
            "may_send": may_send,
            "may_receive": may_receive,
            "may_access_imap": may_access_imap,
            "may_access_pop3": may_access_pop3,
            "may_access_managesieve": may_access_managesieve,
        }
        if password is not None:
            payload["password_use"] = "custom"
            payload["password"] = password
        return self._request(
            f"/domains/{domain}/mailboxes/{local_part}/identities",
            method="POST",
            payload=payload,
        )

    def update_identity(self, domain, local_part, identity_local_part, **fields):
        """Change fields on an existing identity.

        Accepts any writable field: name, password, may_send, may_receive,
        may_access_imap, may_access_pop3, may_access_managesieve. Only the
        fields passed are sent, so the rest keep their current values.

        Setting every may_* false leaves the identity in place but inert --
        useful to suspend a device without deleting the address.

        As in create_identity(), a `password` is only stored alongside
        `password_use: "custom"`, which is added here when omitted. Without it
        the write succeeds and changes nothing.
        """
        if not fields:
            raise ValueError("update_identity needs at least one field to change")
        if "password" in fields:
            fields.setdefault("password_use", "custom")
        return self._request(
            f"/domains/{domain}/mailboxes/{local_part}/identities/{identity_local_part}",
            method="PUT",
            payload=fields,
        )

    def delete_identity(self, domain, local_part, identity_local_part):
        """Delete an identity, revoking its credential immediately.

        Only that identity is affected: the parent mailbox password and every
        other identity under it keep working. That is the whole point of the
        feature.

        Mail already delivered through the identity stays in the parent
        mailbox -- an identity is a way in, not a separate store.
        """
        return self._request(
            f"/domains/{domain}/mailboxes/{local_part}/identities/{identity_local_part}",
            method="DELETE",
        )
