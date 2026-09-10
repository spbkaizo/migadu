"""Send a mailbox's connection settings to its user.

Sends via authenticated SMTP submission as the operator's own mailbox, so the
message comes from a real address the recipient recognises rather than from
something that will be filed as spam.
"""

import os
import re
import secrets
import smtplib
import string
import subprocess
import tempfile
from email.message import EmailMessage

from . import creds

HOST = "smtp.migadu.com"
PORT = 465

GUIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "user-guide.md",
)

# Ambiguous glyphs removed: someone will read this off a screen and retype it.
ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)


def generate_password(length=24):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


HEADING = "Mail settings for {address}\n"

# Shown first for an invitation: the settings below are unusable until the
# password is set, so leading with them puts the steps out of order.
INVITE_BLOCK = """
FIRST: a separate email from Migadu has a link to set your own password. Use
that link before anything below.
"""

# Leads the message: it is the one thing the reader needs before anything else
# here is usable, and the one thing they will come back to find.
PASSWORD_BLOCK = """
Your sign-in details:

    Email address   {address}
    Password        {password}

Your email address is also your username, everywhere.

Please change this password once you are set up: sign in at
https://webmail.migadu.com, then Settings, then Change Password. Once you
have, this message is worth deleting.
"""

# POP3 and ManageSieve are deliberately omitted. Nobody sets up ManageSieve by
# hand, and choosing POP3 by mistake pulls mail off the server.
SETTINGS = """
Server settings, if your mail app asks for them:

  IMAP   imap.migadu.com   port 993   TLS
  SMTP   smtp.migadu.com   port 465   TLS

Use your full email address as the username for both. One password covers mail
and webmail -- there is no separate "app password".

Webmail:  https://webmail.migadu.com

Your mail app may offer to configure itself once you enter the address and
password. If it does not, or if it fails, enter the two servers above by hand
-- that always works.

Step-by-step instructions for iPhone, iPad and Outlook are attached as a PDF,
and repeated below if you would rather not open an attachment.
"""

# Used when no password is included, so SETTINGS does not open mid-sentence.
SETTINGS_NO_PASSWORD = """
Your email address is also your username, everywhere.
""" + SETTINGS

def _plain(markdown):
    """Flatten the guide's markdown into something readable as plain text.

    The guide is written for GitHub as well as for email, so it carries syntax
    that reads as noise in a mail client.
    """
    out = []
    for line in markdown.splitlines():
        if line.strip() in ("---", "***"):
            out.append("-" * 68)
            continue
        # Table rows: drop the alignment separator, render the rest as columns.
        if re.fullmatch(r"\s*\|[\s|:-]+\|\s*", line):
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = "  " + "   ".join(c for c in cells if c)
        line = re.sub(r"^(#+)\s*", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"^>\s?", "  ", line)
        out.append(line)
    return "\n".join(out).strip("\n")


def load_guide(path=None):
    """Return the user guide as plain text, or None when it is unavailable."""
    try:
        with open(path or GUIDE_PATH) as f:
            return _plain(f.read())
    except OSError:
        return None


def guide_pdf(text=None):
    """Render the guide to PDF bytes, or None if this system cannot.

    Uses cupsfilter, which ships with macOS, so there is no dependency to
    install. Returns None rather than raising: a missing PDF should not stop
    the settings email going out.
    """
    text = text or load_guide()
    if not text:
        return None
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "Email setup guide.txt")
        with open(src, "w") as f:
            f.write(text)
        try:
            # cupsfilter writes progress to stderr and the PDF to stdout.
            r = subprocess.run(
                ["cupsfilter", src],
                capture_output=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
    return r.stdout if r.stdout.startswith(b"%PDF") else None


def build(address, password=None, invited=False, guide=True, pdf=True):
    body = HEADING.format(address=address)
    if invited:
        body += INVITE_BLOCK
    if password:
        body += PASSWORD_BLOCK.format(address=address, password=password)
        body += SETTINGS.format(address=address)
    else:
        body += SETTINGS_NO_PASSWORD.format(address=address)

    text = (load_guide() if guide is True else guide) if guide else None
    if text:
        body += "\n" + "=" * 68 + "\n\n" + text + "\n"

    msg = EmailMessage()
    msg["Subject"] = f"Mail settings for {address}"
    msg.set_content(body)

    if pdf:
        data = guide_pdf(text)
        if data:
            msg.add_attachment(
                data,
                maintype="application",
                subtype="pdf",
                filename="Email setup guide.pdf",
            )
    return msg


def send(to_address, msg, sender=None, password=None):
    """Send msg, authenticating as the operator's mailbox."""
    if sender is None or password is None:
        sender, password = creds.imap()
    msg["From"] = sender
    msg["To"] = to_address
    with smtplib.SMTP_SSL(HOST, PORT, timeout=30) as s:
        s.login(sender, password)
        s.send_message(msg)
    return to_address
