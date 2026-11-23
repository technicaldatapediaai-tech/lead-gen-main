# Email deliverability (Email Agent)

Built 2026-11-20, when email went live for the first workspace (`EMAIL_DRY_RUN=false`).

**Where:** Email Agent → **Deliverability** tab.
**Code:** `services/email_deliverability.py`, wired into `services/email_channel.py`.
**Tests:** `tests/test_email_deliverability.py`.

## What it does

### Bounces
- Delivery-failure notices that land in a connected inbox are read during the reply check.
- **Hard bounce** (the address doesn't exist):
  - the lead's email is marked invalid (`profile.emailBounced`);
  - their email sequences stop;
  - the address is never emailed again.
- **Soft bounce** (mailbox full, try later): only counted.
- Bounces are stored as `email_message` rows with `direction="bounce"` (`subject` = `hard` or `soft`, `body` = the reason).
- Campaigns show their hard-bounce count (`CampaignOut.bounced`).

### Bounce guard
- An inbox pauses itself when 5% or more of its last 7 days' emails hard-bounced, once it has sent at least 20.
- The pause reason is shown on the inbox.

### Ramp (the "warm-up")
- The daily limit grows automatically: start 5, +2 a day, up to 40 (30 for personal Gmail / Outlook addresses).
- New inboxes get it by default.
- Stored in `sender_account.settings.ramp` (migration 0012).
- This is a volume ramp. The mail exchange between your own inboxes is the warm-up below.

### Domain check
- Checks MX, SPF, DKIM (common selectors) and DMARC for the inbox's domain, with what to add when one is missing.
- Personal mailboxes (gmail.com and others) are reported as provider-managed.

### Sending engine
- **Window:** the campaign's send window is read on the workspace's clock (organisation timezone, else the content
  profile's), not UTC.
- **Pacing:** after a real send, an inbox rests a random 3–8 minutes (`settings.nextSendAt`).
- **Same sender:** a lead's follow-ups go from the inbox that sent the first email, so the thread stays together. The
  lead waits if that inbox is at its limit.
- **Provider matching:** with inboxes on different providers, a new lead gets an inbox on the recipient's provider
  (Gmail to Gmail, Outlook to Outlook) when one is free. It never waits for a match.
- **Format:** emails are plain text, plus an HTML version only when the workspace tracks opens or clicks.
- **Replies:** a reply stops the sequence.

### A/Z testing (built 2026-11-20)
- An email step can have up to 4 extra versions (`step.variants`: subject + body). The step's own text is version A.
- Each lead gets one version, chosen by a stable hash of lead and step, so the split is even and never changes on a retry.
- The version is stored on `email_message.variant` (migration 0015).
- Results per step and version (sent, leads who replied, hard bounces): `GET /api/campaigns/{id}/variants`, shown in
  the campaign builder as "Version results".
- Write versions in the campaign builder: set the step to "Fixed template with variables", then "Add a version to test".

### Warm-up and placement tests between your own inboxes (built 2026-11-20)
**Code:** `services/email_warmup.py`, table `email_check` (migration 0018). **Tests:** `tests/test_email_warmup.py`.

- **Needs 2 or more connected inboxes** that can send and be read (IMAP). There is no shared pool with other customers.
- **Placement test** ("Run test" on an inbox):
  - One plain email goes to each of the workspace's other inboxes.
  - Each receiving inbox is read: was it in the Inbox or in Spam / Junk? The spam folder is the one flagged `\Junk`, else a
    well-known name such as `[Gmail]/Spam` or `Junk Email`.
  - Gmail's Promotions and Updates tabs count as Inbox.
  - Results show under "Inbox placement tests". "Check now" reads them at once; otherwise the background pass does it
    every 10 minutes (`EMAIL_WARMUP_INTERVAL_S`).
  - Not found after 30 minutes means "Didn't arrive".
- **Warm-up** (switch per inbox, off by default):
  - A few plain emails a day go to your other inboxes, from 2 a day, +1 a day, up to the target (default 10, max 30).
  - The receiving inbox marks them read and moves them out of spam (IMAP MOVE, else copy + delete).
  - It answers about a third of them.
  - Last 7 days per inbox: sent, landed in inbox / spam, rescued, answered.
- **Never leads or replies:** warm-up and test mail never become leads or Sales Leads replies. Reply matching only
  takes mail from leads, and the email-lead sync treats every inbox of the workspace as "us". Before this, a second
  inbox could have been imported as a lead.
- Nothing runs in email test mode (`EMAIL_DRY_RUN`).

### Open and click tracking (built 2026-11-20)
**Code:** `services/email_tracking.py`, public routes `api/tracking.py`, columns on `email_message` (migration 0018).

- **Switches:** off by default. Two switches in the Deliverability tab, "Track opens" and "Track link clicks", stored
  in `org.settings.emailTracking`.
- **Needs a public `BACKEND_URL`.** On localhost the switches are disabled and the reason is shown, because mail apps
  can't reach the server.
- **Opens:** a tracked email also gets an HTML version with a 1×1 image, `GET /api/t/o/{token}.gif`. Apple Mail Privacy
  Protection loads every image, so open counts are rough.
- **Clicks:** links go through `GET /api/t/c/{token}?u=…&s=…`.
  - The link is signed (HMAC with `SECRET_KEY`), so it can't be used as an open redirect. An unsigned or changed link
    gets a 400.
  - A click also counts as an open.
- **Stored per email:** `track_token`, `opens`, `opened_at`, `clicks`, `clicked_at`.
- **30-day rates** (tracked emails only) show in the tracking card.
- Tracking can lower cold-email placement. The UI says so next to the switches.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/accounts/email/deliverability` | per inbox: status, today's limit, ramp, warm-up, sent / bounced / replies (7 days and all time); `readableInboxes`, `placement` (latest tests), `tracking` (switches, availability, 30-day open / click rates) |
| GET | `/api/accounts/{id}/email/dns` | MX / SPF / DKIM / DMARC checks |
| PUT | `/api/accounts/{id}/email/ramp` | `{enabled, start, step, target, restart}` |
| PUT | `/api/accounts/{id}/email/warmup` | `{enabled, target?}`; 400 with fewer than 2 inboxes |
| POST | `/api/accounts/{id}/email/placement-test` | sends the test from this inbox; 400 with fewer than 2 inboxes or in test mode |
| POST | `/api/accounts/email/placement/check` | read the receiving inboxes now |
| PUT | `/api/accounts/email/tracking` | `{opens, clicks}`; 400 when the server isn't public |
| GET | `/api/t/o/{token}.gif`, `/api/t/c/{token}` | public, no login (the recipient's mail app calls them) |

## Not built yet (compared with tools like Instantly)

| Thing | Why not yet |
|---|---|
| A shared warm-up pool across customers | Warm-up runs only between a workspace's own inboxes |
| Custom tracking domain | Tracking links use `BACKEND_URL`; a per-workspace domain needs DNS + TLS per customer |
| Separate sending domains, redirect to the main site | Set up by the user at their domain registrar. The domain check then verifies the records |
| Step conditions on opens and clicks | Not added back yet; replies drive the sequence |
