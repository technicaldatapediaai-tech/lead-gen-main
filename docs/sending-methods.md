# Sending methods: Claude in Chrome, Unipile, Meta

Each workspace chooses, per platform, how approved messages leave the app (agent page → **Sending method** tab;
X and Reddit: agent → Settings). Stored in `organization.settings.delivery`. Approval, daily caps and spacing are the
same whichever method is used.

| Platform | Claude in Chrome (operator runbook) | Unipile (automatic, server) | Meta Cloud API |
|---|---|---|---|
| LinkedIn | default: `linkedin-outbound`, `linkedin-send-approved`, `social-outbound` | campaign visits / connection requests / DMs, Posts-agent DMs and connection notes, post comments | n/a |
| WhatsApp | `whatsapp-web-send` (WhatsApp Web), drafts in Actions to approve | campaign messages as plain text from the linked number | default: templates from an official business number |
| X | default: `social-outbound` | not available: Unipile's X support is deprecated in v1, "coming soon" in v2 | n/a |
| Reddit | default: `social-outbound` | not available: Unipile doesn't support Reddit | n/a |

Checked against developer.unipile.com on 2026-11-16 (v2 API). When Unipile ships X, add it in `services/delivery.py`
(`UNSUPPORTED`) and `services/unipile.py`.

## Unipile setup (once, platform level)

1. Unipile subscription (per connected account: about €49/month covers up to 10 accounts, then about €5 per account; check unipile.com/pricing).
2. Backend env: `UNIPILE_API_KEY` (header `X-API-KEY`), `UNIPILE_BASE_URL=https://api.unipile.com`.
   `UNIPILE_DRY_RUN` defaults to on in DEV_MODE: sends are logged and no LinkedIn-visible action happens (not even profile views).
3. Webhook (replies, account status): create an endpoint in Unipile for `{API}/api/webhooks/unipile` with events
   `account.add`, `account.reconnect`, `account.status.*`, `account.locked`, `account.unlocked`, `account.remove`, `message.new`;
   put its secret in `UNIPILE_WEBHOOK_SECRET` (requests are checked against `unipile-signature: t=…,v0=…`).

## Linking an account (each workspace)

Sending method tab → **Link a LinkedIn account / a WhatsApp number** → `POST /api/unipile/connect` returns Unipile's
hosted login link (`POST /v2/auth/link`, `redirect_uri` = the agent page, `state` = signed org + channel, 1 h).
The person signs in on Unipile's page (LinkedIn login / WhatsApp QR); we never see the password. Unipile redirects
back with `account_id` and `state`; the page calls `POST /api/unipile/claim`, which checks the state signature and
workspace, reads `GET /v2/accounts/{id}` (provider must match) and creates a `SenderAccount` with `unipile_account_id`
(migration 0009). One Unipile account can belong to one workspace. The webhook's `account.add` does the same server-side.
**Unlink** removes the account from Unipile (stops billing) and falls back to the default method if it was the last one.
Seats count against the plan (`plan.ensure_seat`).

## How Unipile sends (`services/unipile_sender.py`, every `UNIPILE_SENDER_INTERVAL_S` = 120 s)

Per workspace on Unipile, at most one LinkedIn send per pass, only when `content_safety.safety_status` allows it
(daily DM / connection caps, spacing, working hours, pause), in this order: approved campaign action → approved
Posts-agent message → approved post comment (`social_outbound.safety` for LinkedIn comments).

- Profile id: `GET /v2/{acc}/users/{slug}?variant=linkedin_classic` → `id` (ACo…), cached in `lead.profile.linkedinId`.
  This is a profile view on LinkedIn, so a visit step always calls it.
- Connection request: `POST /v2/{acc}/users/me/relation-requests {user_id, message}` (note ≤300 chars on paid
  accounts, 200 free; LinkedIn's limit returns 422 `cannot_resend_yet`).
- DM: `POST /v2/{acc}/inboxes/CLASSIC_PRIMARY/chats/send {text, users_ids}`. Not a relation → outcome `not_connected`
  (the step retries daily for 14 days, as with the operator).
- Comment: `GET /v2/{acc}/posts/{activity id | urn}` then `POST /v2/{acc}/posts/{id}/comments {text}`.
  The URL-to-post-id step is the least verified part; check it on the first real comment.
- WhatsApp (`whatsapp_channel.send_due` with method `unipile`): `POST /v2/{acc}/chats/send {text, users_ids: "<digits>@s.whatsapp.net"}`,
  10-20 s apart, opt-in still required.

Send-once: each item is claimed before the call (campaign actions and comments flip to `uncertain`, Posts-agent
messages are marked `sent_by=unipile:sending`); a timeout or provider 5xx is recorded `uncertain` and never retried;
Unipile's own 429 puts the item back. With LinkedIn on Unipile the operator queues (`/api/content/queue`,
`/api/social/linkedin/queue`) stay empty except public replies to comments, so nothing goes out twice.

Replies: `message.new` with `is_sender: false` on a linked account → `reply_ingest` when the sender is a lead
(LinkedIn: `profile.linkedinId`; WhatsApp: the phone number).

Unipile's recommended LinkedIn limits (v2 docs): invitations 80-100/day (~200/week) on paid accounts, profile
retrievals ~100/day, other actions ~100/day. Our defaults are well below that.

## API

- `GET /api/delivery` → `{platforms: {linkedin|whatsapp|x|reddit: {method, options[{key, available, reason}], accounts[]}}, unipile: {configured, dryRun}}`
- `PUT /api/delivery/{platform} {method}` (admin; Unipile needs a linked account)
- `POST /api/unipile/connect {channel}`, `POST /api/unipile/claim {accountId, state}`, `DELETE /api/unipile/accounts/{id}` (admin)
- `POST /api/webhooks/unipile` (signed)
- `GET /api/outbound/actions?channel=whatsapp`, `GET /api/outbound/whatsapp/queue` (operator CLI `whatsapp-queue`)

Tests: `tests/test_sending_methods.py` (Unipile faked).
