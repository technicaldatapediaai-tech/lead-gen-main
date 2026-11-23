# WhatsApp channel

The WhatsApp Agent sends and receives through **Meta's WhatsApp Cloud API**, the official business API. It does not
automate a phone or WhatsApp Web; numbers that do that get banned.

Code: `lead-gen-backend/services/whatsapp_channel.py`, `api/whatsapp.py`, WhatsApp routes in `api/accounts.py`.

## What the client needs from Meta

1. A Meta Business account with a **WhatsApp Business Account (WABA)** and a phone number added in WhatsApp Manager.
   The number cannot also be used in the normal WhatsApp or WhatsApp Business app.
2. A Meta app with the WhatsApp product. From **WhatsApp → API Setup** copy the **Phone number ID** and the
   **WhatsApp Business Account ID**.
3. A **permanent access token**: Business Settings → System users → add a system user → assign the app and the WABA →
   Generate token with `whatsapp_business_messaging` and `whatsapp_business_management`. The temporary 24-hour token
   from API Setup works for testing only.
4. The **App secret** (App settings → Basic). It signs webhook calls, so the backend can tell real Meta calls from fakes.
5. An approved **message template** for opening conversations (WhatsApp Manager → Message templates). Recommended
   (category Marketing, language English):

   ```
   Hi {{1}}, {{2}}

   If this isn't relevant, reply STOP and I won't message again.
   ```

   `{{1}}` is the first name and `{{2}}` is the personalised message from the writer (docs/personalised-messages.md).

## Rules WhatsApp enforces, and how the backend follows them

| Rule | What the backend does |
| --- | --- |
| A business can only start a conversation with an approved template | Every campaign step sends a template. Its variables carry the personalised text. |
| Free text only within 24 hours of the person's last message | `POST /api/whatsapp/reply` checks the window and returns 409 outside it. |
| Recipients must have opted in to messages from the business | Leads need `whatsappOptIn: true` (set on import or with `POST /api/leads/whatsapp-opt-in`). The sender skips the rest and reports how many. `WHATSAPP_REQUIRE_OPT_IN=false` turns this off; do that only if opt-in is recorded elsewhere. |
| Template variables can't contain newlines, tabs or 4+ spaces | `_param_text()` flattens them. |
| Messaging limits and quality rating | Per-number `dailyLimit` (starts at 50, status `warming`); quality (GREEN/YELLOW/RED) is stored when the number is checked. |

## Connecting a number

```
POST /api/accounts/whatsapp/test   {phoneNumberId, businessAccountId, accessToken, templateName?, templateLang?}
POST /api/accounts/whatsapp        same + appSecret, label?, dailyLimit?
GET  /api/accounts/{id}/whatsapp   details + webhook settings
PATCH /api/accounts/{id}/whatsapp  {templateName?, templateLang?, accessToken?, appSecret?}  (re-verified before saving)
```

The test call never saves anything. It reports the number's display name and quality, and whether the template exists,
is APPROVED in that language, and how many variables it has. Connecting runs the same check and refuses a wrong
token, an unknown number, or an unapproved template. The token and app secret are stored encrypted and never returned.

The connect response includes `webhook.callbackUrl` and `webhook.verifyToken`. In the Meta app: **WhatsApp →
Configuration → Webhook** → paste both → Verify and save → subscribe to the **messages** field.
Meta must be able to reach the URL, so the backend needs a public HTTPS address (deployed, or a tunnel such as ngrok
with `BACKEND_URL` set to it). `webhook.public` is false while the backend is on localhost.

## Sending

A WhatsApp campaign's steps are `type: "message"` (or `"template"`). Optional per-step keys:

- `templateName`, `templateLang`: override the number's default template
- `templateParams`: the variables in order, default `["firstName", "message"]`. Tokens: `firstName`, `name`, `company`,
  `title`, `signal`, `message` (the writer's personalised text), or literal text with `{{company}}`-style variables.
- `mode: "template"` with a `body` uses that text as the `message` variable; otherwise the writer writes it.

The sender runs every `WHATSAPP_SENDER_INTERVAL_S` (60 s) and on `POST /api/campaigns/{id}/send-due`: running campaign,
inside the send window, due enrolments only, round-robin across the campaign's numbers within their daily limits, up to
10 per pass. Every message is logged in `whatsapp_message`. With `WHATSAPP_DRY_RUN` (default on while `DEV_MODE`) it logs
instead of calling Meta.

## Receiving

`POST /api/webhooks/whatsapp`: each change is matched to a number by `metadata.phone_number_id` and verified with that
number's app secret (`X-Hub-Signature-256`); a payload that fails is rejected with 401. Then:

- **messages** go through `reply_ingest` exactly like email replies: the lead's sequence stops, opt-out words ("stop",
  "unsubscribe", ...) add the number to Do Not Contact, the reply appears in Sales Leads with its campaign. Redelivered
  messages are recorded once.
- **statuses** (sent → delivered → read, or failed with Meta's reason) update the logged message.

## Settings (`lead-gen-backend/.env`)

```
WHATSAPP_DRY_RUN=false        # actually send (default: on in DEV_MODE)
WHATSAPP_REQUIRE_OPT_IN=true
WHATSAPP_GRAPH_VERSION=v23.0
BACKEND_URL=https://api.example.com   # public URL used for the webhook callback
```
