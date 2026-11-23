# Email channel: real sending and reply detection

Status: built 2026-10-23. Extends `docs/agent-api-contract.md` (Accounts / Campaigns / Replies). camelCase JSON.

## What it does

1. **Connect an inbox (SMTP/IMAP).** Any provider: Gmail/Workspace with an app password, Zoho, Outlook, own domain.
   The app verifies both logins before saving. Credentials are encrypted at rest (Fernet key derived from `SECRET_KEY`).
2. **Send sequences.** A background sender runs every 60 s: for each running email campaign it picks enrolled leads
   whose next step is due, personalises the step (`services/personalize.py` for template steps), sends through one of the
   campaign's connected inboxes (round-robin, daily limit per inbox, send window honoured, ~random 20-90 s pacing),
   records the send, advances the step. After the last step the enrolment is `finished`.
3. **Detect replies.** Every 2 min the app polls each inbox over IMAP for new mail since the last check, keeps mail that
   answers a message we sent (`In-Reply-To`/`References` match, or sender is an enrolled lead), and hands it to
   `services/reply_ingest.ingest_reply` so it lands in Sales Leads with sentiment, stops the sequence and honours opt-outs.
   Bounces / auto-replies are ignored.

Dev mode: with `EMAIL_DRY_RUN=true` (default in `DEV_MODE`), the sender does everything except the real SMTP send,
and logs the message instead; set `EMAIL_DRY_RUN=false` to send for real.

## Data

`sender_account` (existing) gains, for email accounts:

| column | meaning |
| --- | --- |
| `smtp_host`, `smtp_port`, `smtp_security` (`ssl` \| `starttls`) | outgoing server |
| `imap_host`, `imap_port` | incoming server (IMAP over SSL) |
| `username` | login (usually the address) |
| `secret_enc` | encrypted password / app password |
| `from_name` | display name on sent mail |
| `verified_at`, `last_error` | last successful check / last failure text |
| `last_imap_check_at`, `imap_last_uid` | reply polling cursor |

New table `email_message`: one row per sent email (`org_id, campaign_id, lead_id, account_id, step, message_id, subject,
body, sent_at`) and per detected reply (`direction='in'`, `in_reply_to`). Used for threading and the activity counters.

`campaign_lead` gains `next_due_at` (when the current step may be sent) and `last_sent_at`.

## API (additions)

| Method | Path | Body → Response |
| --- | --- | --- |
| POST | `/api/accounts/email/test` | `EmailAccountInput` → `{ ok, smtp: {ok, error?}, imap: {ok, error?} }` (nothing saved) |
| POST | `/api/accounts/email` | `EmailAccountInput` → `AccountOut` (verifies first; 400 with the provider's error if a login fails) |
| PATCH | `/api/accounts/{id}/email` | partial `EmailAccountInput` (password optional) → `AccountOut` |
| GET | `/api/accounts/{id}/email` | → `EmailAccountOut` (settings without the password) |
| POST | `/api/accounts/{id}/check-replies` | poll this inbox now → `{ found: number }` |
| POST | `/api/campaigns/{id}/send-due` | run one sender pass for this campaign now → `{ sent, skipped, reason? }` |
| GET | `/api/accounts/email/presets` | `[{ key, name, smtpHost, smtpPort, smtpSecurity, imapHost, imapPort, help }]` |

```ts
type EmailAccountInput = {
  email: string; fromName?: string; password: string;
  smtpHost: string; smtpPort: number; smtpSecurity: 'ssl' | 'starttls';
  imapHost: string; imapPort: number; dailyLimit?: number; label?: string;
};
type EmailAccountOut = AccountOut & { email: string; fromName: string; smtpHost: string; smtpPort: number;
  smtpSecurity: string; imapHost: string; imapPort: number; verifiedAt: string | null; lastError: string;
  lastImapCheckAt: string | null };
```

`AccountOut` (all channels) also gains `verifiedAt: string | null` and `lastError: string`.

## Presets

Gmail / Google Workspace (smtp.gmail.com 465 ssl, imap.gmail.com 993; needs 2-step verification + an App password),
Zoho Mail (smtp.zoho.com 465 / imap.zoho.com 993; app-specific password if 2FA), Outlook / Microsoft 365
(smtp.office365.com 587 starttls / outlook.office365.com 993; needs an app password or SMTP AUTH enabled), Custom.

## Guardrails kept

Daily limit per inbox (`daily_limit`, `sent_today` reset at UTC midnight), paused/disconnected inboxes never send,
`one_campaign_at_a_time`/`stop_all_on_reply`/DNC are enforced by the existing enrolment and reply code, the campaign
send window (`window.from/to/days`, UTC) is honoured, a step with `only_if_no_reply` is skipped once the lead replied.

## OAuth connect (Gmail / Google Workspace, Outlook / Microsoft 365)

Added 2026-10-30 (`services/email_oauth.py`, `api/email_oauth.py`). Instead of an app password, the user signs in with
the provider from **Integrations → Gmail / Outlook → Sign in to connect**:

1. `GET /api/integrations/{google|outlook}/oauth/start` (admin) → `{ url }`; the browser goes there. `503` until the
   server has the provider's client ID/secret.
2. The provider redirects to `GET /api/integrations/oauth/callback/{provider}?code&state`. `state` is a 10-minute
   signed token (org + user). We exchange the code, read the mailbox address from the `id_token`, and save a
   `SenderAccount(channel="email", auth_type="oauth", oauth_provider=…)`: refresh token encrypted in `secret_enc`,
   cached access token in `oauth_access_enc` / `oauth_expires_at`, SMTP/IMAP hosts from the provider preset. The
   integration is marked connected and the browser is sent to `/dashboard/integrations?connected=…&inbox=…`
   (or `?error=…`).
3. Sending and reply polling use the same SMTP/IMAP code with SASL **XOAUTH2** (`email_channel._credential`): the access
   token is refreshed 3 minutes before expiry; a revoked grant (`invalid_grant`) marks the inbox `disconnected`.
4. `POST /api/integrations/{google|outlook}/disconnect` drops the tokens and sets the inboxes `disconnected`;
   `.../connect` answers `400` (OAuth is the only way in).

Server setup:
- **Google:** Cloud Console → APIs & Services → Credentials → the same OAuth client used for Sign in with Google. Add the
  redirect URI `{BACKEND_URL}/api/integrations/oauth/callback/google`. The `https://mail.google.com/` scope is
  *restricted*: in testing mode only listed test users can connect; production use needs Google's app verification.
  Env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
- **Microsoft:** Entra admin center → App registrations → new app (accounts in any org + personal, or your tenant), redirect
  URI `{BACKEND_URL}/api/integrations/oauth/callback/outlook` (type Web), client secret, delegated permissions
  `SMTP.Send`, `IMAP.AccessAsUser.All`, `offline_access`, `openid`, `email`, `profile`. The mailbox (or tenant) must have
  **SMTP AUTH** enabled. Env: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT` (`common` or tenant ID).
