# Connected accounts (Account → Connected IDs)

Sidebar → **Account** → **Connected IDs** tab (`/dashboard/account?tab=ids`), built 2026-11-17 (first as a separate
page; the old `/dashboard/accounts` address now forwards here with its query). Each workspace connects its own
accounts here; owners and admins can connect and disconnect.

Layout (2026-11-18):
- **Banners.** A test-mode strip and a "needs attention" list come first. The list holds disconnected, expired or
  failing accounts, each with a Reconnect button that reruns the matching sign-in (Gmail → Google, Unipile → Unipile…).
- **Sections.** Three cards: **Messaging & outreach** (LinkedIn, Email, WhatsApp), **Publishing** (Instagram,
  Facebook, X, YouTube, Reddit) and **Data & research** (Apify, Apollo, Hunter).
- **Platform rows.** One row per platform, with what it's used for and a single Connect / Add button. The button
  becomes a menu when there are several ways to connect; ways the server can't offer yet are disabled, with the reason.
  "Not available yet" means none is set up.
- **Account lines.** Under a row, each connected account shows its name, how it's connected, the usage bar (sent
  today / daily limit), its status (Active, Warming up, Disconnected…) and a ⋯ menu: Reconnect, Post as a company
  page, Disconnect.

Code: `components/settings/ConnectedAccounts.tsx`, `ConnectionRow.tsx` (row and account-line layout) and
`DataProviders.tsx` (Data & research).

| Platform | Ways to connect | Used for |
|---|---|---|
| LinkedIn | Unipile sign-in (one sign-in = DMs + posting; then "Company page" to post as a page) · LinkedIn API | DMs, comments, posting |
| Instagram | Unipile sign-in (any account) · Meta API (business / creator account linked to a Page) | posting |
| Facebook | Meta API (Pages you manage; also adds their Instagram accounts) | posting |
| X | X API | posting (comments / DMs: Claude in Chrome, X Agent). Not via Unipile: its docs list X as deprecated in v1, "coming soon" in v2 (checked 2026-11-18) |
| YouTube | Google sign-in | video uploads |
| Reddit | Reddit sign-in (new) | posting to your profile or a subreddit (comments / DMs: Reddit Agent) |
| Email | Google sign-in (Gmail) · Microsoft sign-in (Outlook) · any inbox over SMTP / IMAP | Email Agent sending + reply tracking |
| WhatsApp | Unipile QR scan · Meta Cloud API (set up in WhatsApp Agent) | DMs |

LinkedIn and WhatsApp cards also choose how DMs go out (Claude in Chrome extension, Unipile, Meta Cloud API) through
`PUT /api/delivery/{platform}`.

## How the sign-ins come back

- Unipile (`POST /api/connections/unipile/connect`): hosted sign-in on auth.unipile.com; Unipile sends the browser to
  `/dashboard/account?tab=ids&unipile=<platform>&account_id=acc_…&provider=…&state=…` (failure: `error_title`). The page calls
  `POST /api/connections/unipile/claim`; the signed state (`conn:<platform>`, 1 hour) proves the sign-in started in
  this workspace. LinkedIn becomes a DM sender and a posting account, WhatsApp a DM sender, Instagram a posting account.
- Platform APIs: `/api/studio/oauth/{platform}/start` (posting) and `/api/integrations/{google|outlook}/oauth/start?ret=accounts`
  (inboxes) come back to this page with `?connected=` or `?error=`.
- SMTP / IMAP: the existing connect form (tests the login before saving).

Disconnect (`DELETE /api/connections/{unipile|posting|sender}/{id}`): a Unipile account is removed with its DM and
posting sides and deleted from Unipile (stops billing for it); the DM sending method falls back when it was the last one.

## Reddit posting (new)

Content Studio cards can now target Reddit: text = self post, graphic = link to the image, video = link to the Drive
file. The card has "Reddit title" and "Subreddit" (empty = the user's own profile, `u_<name>`). API:
`POST https://oauth.reddit.com/api/submit` with a descriptive User-Agent; tokens refresh hourly. Needs a Reddit app of
type "web app" with redirect `{BACKEND_URL}/api/studio/oauth/callback/reddit`. Check each subreddit's self-promotion
rules before posting there.

Code: `lead-gen-backend/api/connections.py`, `services/publishers.py` (Reddit), `lead-gen-frontend/app/dashboard/accounts`,
`components/settings/ConnectedAccounts.tsx`, `lib/agent/connections.ts`; tests `tests/test_connections.py`.
