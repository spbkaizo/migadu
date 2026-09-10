"""Minimal ManageSieve client for Migadu (RFC 5804).

Enough to list, download, upload and activate filter scripts. STARTTLS is
mandatory here -- the server advertises no SASL mechanisms until the connection
is encrypted, so authentication before STARTTLS is impossible.
"""

import base64
import re
import socket
import ssl

from . import creds

HOST = "imap.migadu.com"
PORT = 4190


class Sieve:
    def __init__(self, host=HOST, port=PORT):
        self.sock = socket.create_connection((host, port), timeout=30)
        self.f = self.sock.makefile("rwb")
        self._banner = self._read()
        self._cmd("STARTTLS")
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(self.sock, server_hostname=host)
        self.f = self.sock.makefile("rwb")
        self._read()  # post-TLS capability banner

    def _read(self):
        lines = []
        while True:
            line = self.f.readline()
            if not line:
                break
            s = line.decode(errors="replace").rstrip("\r\n")
            lines.append(s)
            if s.startswith(("OK", "NO", "BYE")):
                break
            # literal payload: {NNN}
            m = re.search(r"\{(\d+)\}$", s)
            if m:
                lines.append(self.f.read(int(m.group(1))).decode(errors="replace"))
                self.f.readline()
        return lines

    def _cmd(self, text, literal=None):
        if literal is not None:
            payload = literal.encode()
            self.f.write(f"{text} {{{len(payload)}+}}\r\n".encode())
            self.f.write(payload + b"\r\n")
        else:
            self.f.write((text + "\r\n").encode())
        self.f.flush()
        return self._read()

    def login(self):
        user, pw = creds.imap()
        blob = base64.b64encode(f"\0{user}\0{pw}".encode()).decode()
        r = self._cmd(f'AUTHENTICATE "PLAIN" "{blob}"')
        if not any(x.startswith("OK") for x in r):
            raise SystemExit(f"sieve auth failed: {r}")
        return r

    def listscripts(self):
        return self._cmd("LISTSCRIPTS")

    def getscript(self, name):
        return self._cmd(f'GETSCRIPT "{name}"')

    def putscript(self, name, body):
        return self._cmd(f'PUTSCRIPT "{name}"', literal=body)

    def setactive(self, name):
        return self._cmd(f'SETACTIVE "{name}"')

    def checkscript(self, body):
        return self._cmd("CHECKSCRIPT", literal=body)

    def logout(self):
        try:
            self._cmd("LOGOUT")
        except Exception:
            pass
