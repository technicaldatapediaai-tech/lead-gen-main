# Leads from your inbox (Lead Agent → source "Email")

Built 2026-11-19. When an email inbox is connected, Leadnius turns the people you've been in touch with by email into
leads, tagged with where they came from.

## When it runs

- **On connect:** right after an inbox is connected (Google or Microsoft sign-in, or IMAP / SMTP), in the background.
  The `EMAIL_LEAD_SYNC_ON_CONNECT` setting turns this off; tests turn it off.
- **Lead Agent → Sync email:** syncs every connected inbox. A toast shows how many leads were added or updated, or why
  an inbox couldn't be read.
- **Account → Connected IDs → Email:** the inbox's ⋯ menu has "Sync leads from this inbox".

Syncing again never duplicates anyone: people already in Lead Agent are updated.

## Who becomes a lead

Only message headers (From, To, Cc, Date, Subject and bulk-mail markers) from the last 12 months are read, up to
3,000 newest messages per folder. No message bodies are read or stored.

- **Included:** everyone you wrote to, from the Sent folder (To and Cc). That covers past contacts and the people
  you're talking to now.
- **Counted, not added:** replies from them in the Inbox add to their "received" count. People who only wrote to you
  (cold pitches, vendors) are not added.
- **Skipped:**
  - your own addresses and aliases;
  - your other inboxes that use the same name;
  - colleagues on your company domain;
  - no-reply, notification and calendar addresses;
  - newsletter "unsubscribe" addresses (beehiiv, ConvertKit, customer.io and others);
  - anyone on the do-not-contact list.
- **People already in Lead Agent:** they keep their original source and gain the email history.

## What a lead gets

- **Name:** from the email's display name ("Smith, Jane" becomes "Jane Smith"; lowercase names are capitalised), or
  from the address ("laxmi.m1774" becomes "Laxmi M"). If neither works, the address itself.
- **Company:** from the email domain ("kite.co.uk" becomes "Kite"). Personal webmail addresses get no company.
- **Profile:**
  - `channel: "email"` (Source = Email);
  - `sourceDetail`: the inbox it came from;
  - `emailHistory: {inbox, sent, received, firstAt, lastAt, lastSubject, lastDirection}`.
- **Score:** how warm the relationship is, not ICP fit. Base 50, +10 if they replied, +10 if you spoke in the last
  30 days.
- **Persona:** none is shown for leads without a job title. Message drafts still fall back to the workspace's first
  persona.

## Lead Agent

- **Source column:** where the lead came from (Email, LinkedIn, X, Reddit, Slack, Signal Agent, added by hand…). Email
  leads also show the inbox and "N sent · N received · last contact".
- **Source filter:** the first filter. With more than one inbox it can narrow to a single inbox (`email|address`).

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/leads/email-sync` | `{accounts: [{id, inbox, status, lastError, sync: {status, scanned, contacts, added, updated, blocked, error, note, startedAt, finishedAt}}], running}` |
| POST | `/api/leads/email-sync` | `{accountId?}`: starts in the background; 422 if no inbox is connected |

## Code

- **Service:** `services/email_leads.py`, with `collect()` (who counts), `import_contacts()` and the IMAP header scan.
- **Run state:** stored in `org.settings.emailLeadSync`.
- **Tests:** `tests/test_email_leads.py` (fake mailbox).

First real run (2026-11-19): 3,217 headers scanned in about 20 seconds, giving 86 leads.
