require ["fileinto", "subaddress", "variables", "imap4flags", "envelope", "mailbox"];

# Starter rules. Copy this directory to mailboxes/<your-mailbox>/ and edit.
# Validate before activating:  bin/sieve-push <your-mailbox> --dry-run

# File automated alerts from your own infrastructure, marked read so they do
# not compete for attention. :create makes the folder on first use.
#
# if allof(
#     header :contains ["From"] "alerts@example.com",
#     header :contains ["Subject"] "SomeAlertName"
# )
# {
#     addflag "\\Seen";
#     fileinto :create "INBOX/system";
#     stop;
# }

# Plus-addressed mail (you+tag@example.com) stays in INBOX rather than being
# auto-filed into a folder per tag, which is Migadu's default. The tag is kept
# as an IMAP keyword, so it remains searchable:
#
#     KEYWORD tag-shopping
#
# That is how you find out which signup leaked or sold an address -- mail
# tagged for one service arriving from another is the evidence.
if envelope :matches :detail "to" "*"
{
    set :lower "tag" "${1}";
    addflag "tag-${tag}";
    fileinto "INBOX";
    stop;
}
