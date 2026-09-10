# Setting up your email

Your email has moved to a new provider. Your address has not changed, and all
your old mail is still there.

You need to update the settings on each device you read mail on. This guide
covers Outlook on Windows, and Mail on an iPhone or iPad.

It takes about five minutes per device.

---

## Before you start

You need two things:

1. **Your email address** — the full thing, including the part after the `@`.
2. **Your password** — either from the settings email that was sent to you, or
   one you chose yourself after following an invitation link.

Your email address is also your username. There is nothing else to remember.

> **One password for everything.** The same password works for Outlook, your
> iPhone, and webmail. If you change it in one place, it changes everywhere and
> you will need to update your other devices.

---

## The settings

You may not need these — the steps below walk you through it. Keep them to hand
in case a screen asks for something unexpected.

| | Server | Port | Security |
|---|---|---|---|
| **Incoming (IMAP)** | `imap.migadu.com` | 993 | SSL/TLS |
| **Outgoing (SMTP)** | `smtp.migadu.com` | 465 | SSL/TLS |

Username: **your full email address**
Password: **your mail password**

Webmail, if you just want to read mail in a browser:
**https://webmail.migadu.com**

---

## iPhone and iPad

### Remove the old account first

If your email is already on your phone, remove it before adding it again.
Otherwise you will end up with two copies of everything.

1. Open **Settings**
2. Tap **Apps**, then **Mail** *(on older iOS: scroll to **Mail** directly)*
3. Tap **Mail Accounts**
4. Tap the old account, then **Delete Account**

Deleting the account removes it from the phone only. Your mail is safe on the
server.

### Add the account

1. In the same **Mail Accounts** screen, tap **Add Account**
2. Tap **Other** at the bottom of the list
3. Tap **Add Mail Account**
4. Fill in:
   - **Name** — how you want your name to appear to people you email
   - **Email** — your full email address
   - **Password** — your mail password
   - **Description** — anything you like, e.g. "Home email"
5. Tap **Next**

Your phone will try to work out the settings on its own. This takes a few
seconds. If it succeeds, skip to step 9. If it asks for more detail, carry on
below — that is normal and not a problem.

6. If a screen appears with **IMAP** and **POP** at the top, make sure **IMAP**
   is selected.

7. Fill in **Incoming Mail Server**:
   - Host Name: `imap.migadu.com`
   - User Name: your full email address
   - Password: your mail password

8. Fill in **Outgoing Mail Server**:
   - Host Name: `smtp.migadu.com`
   - User Name: your full email address
   - Password: your mail password

   > The outgoing username and password are **not** optional here, even though
   > the phone labels them that way. Leave them blank and sending will fail.

9. Tap **Next**. Verification takes up to a minute.
10. Tap **Save**.

### Check it works

Send yourself an email from the phone. If it arrives, both sending and
receiving are working.

If verification fails, the most likely cause is a typo in the password. Tap
back and retype it — do not paste it if it might have picked up a space.

---

## Outlook on Windows

### Remove the old account first

1. Open Outlook
2. **File** → **Account Settings** → **Account Settings**
3. Select the old account, click **Remove**, confirm

### Add the account

1. **File** → **Add Account**
2. Type your full email address
3. Click **Advanced options**, tick **Let me set up my account manually**,
   then **Connect**
4. Choose **IMAP**
5. Fill in:

   **Incoming mail**
   - Server: `imap.migadu.com`
   - Port: `993`
   - Encryption method: `SSL/TLS`

   **Outgoing mail**
   - Server: `smtp.migadu.com`
   - Port: `465`
   - Encryption method: `SSL/TLS`

6. Click **Next**, enter your password, click **Connect**

If Outlook offers to set things up automatically and it works, that is fine —
you can skip the manual settings.

### New Outlook

If your Outlook looks different and says "New Outlook" with a toggle in the
corner, the steps are similar but under **Settings** (the gear icon) →
**Accounts** → **Add account**. Choose **IMAP** if asked, and use the same
servers, ports and encryption as above.

---

## Your folders

You may see folders you did not create, such as **Archive**, **Junk** or
folders grouping mail by subject. These are normal. Mail is sorted into them
automatically as it arrives.

Anything important stays in your **Inbox**.

---

## Common problems

**"Cannot verify account information" or the password is rejected**
Almost always a mistyped password. Retype it slowly rather than pasting.
Passwords are case sensitive.

**Mail arrives but I cannot send**
The outgoing server needs your username and password too. Go back into the
account settings and check the outgoing (SMTP) section has both filled in.

**I have two copies of every email**
The old account is still set up alongside the new one. Remove the old one.

**Old mail is missing**
Some apps only download recent messages to save space. Scroll to the bottom of
a folder and look for "Load More Messages", or check webmail to confirm the
mail is on the server.

**Nothing works and I want to check my mail now**
Go to **https://webmail.migadu.com** in any browser and sign in with your email
address and password. This always works and needs no setup.

---

## Changing your password

1. Go to **https://webmail.migadu.com** and sign in
2. Open **Settings**, then **Change Password**

Remember to update the password on every device afterwards.
