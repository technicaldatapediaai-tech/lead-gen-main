# Content Studio (sidebar → Content)

Built 2026-11-17. Replaces the old Content group (LinkedIn Posts, "Blog & SEO" / "Video Script" placeholders). The
LinkedIn Posts agent code is still in the repo (`/dashboard/agents/linkedin-posts`, `/api/content/*`) because its
engager ingest feeds lead capture; it is just no longer in the sidebar.

| Sidebar item | Route | What it does |
|---|---|---|
| Idea & Script Generation | `/dashboard/content/studio` | Notion-style board + trend analyser |
| Channel Posting | `/dashboard/content/posting` | Every scheduled post, one row per platform; publishes them |
| *(no settings page)* | Account → Connected IDs | Apify token and posting accounts; `/dashboard/content/settings` forwards there. Template graphics use the default brand colours (the Brand tab was removed 2026-11-19 at the user's request; the API `PUT /api/studio/settings/brand` still exists) |

## The board

Cards are `studio_item` rows. Drag between columns (native HTML5 drag and drop); columns a card can't use dim while it
is dragged.

```
text / graphic:  Ideas → Approved → Creative ready → Scheduled → Posted
video:           Ideas → Approved (= Shoot & edit) → Uploaded to Drive → Scheduled → Posted
```

Guards (`services/studio.py: move_problem`): Creative ready needs copy or a graphic; Uploaded needs a Google Drive
link; Scheduled needs a time + platforms (dropping a card on Scheduled opens it on the schedule section). Posted is
reached only when every post of the card went out (or was marked posted). Leaving Scheduled cancels its pending posts.

Open a card to: pick the format (text / graphic / video), edit idea + hook, and then

- **Text**: "Write with AI" → main copy + X and Instagram versions (skills linkedin-copywriter, linkedin-hook-writer,
  x-copywriter).
- **Graphic**: three modes.
  - *Branded template* (default): quote / list / stat / carousel. "Design with AI" writes the slides, caption and an
    image prompt (skill graphics-designer). Rendered by `app/api/content-graphic/[id]/[slide]` (next/og, 1080 px;
    `?format=jpeg` via sharp for Instagram) with the stored (default) brand colours + handle. The link is
    signed (`graphic_sig`), because platforms fetch it without a login.
  - *AI image*: `app/api/content-image` — OpenRouter's Image API (`POST /api/v1/images`) with the frontend's
    `OPENROUTER_API_KEY` (OpenAI Images as a fallback when only `OPENAI_API_KEY` is set). Default model
    `openai/gpt-image-1-mini` (about 1¢ a square image at list price; `CONTENT_IMAGE_MODEL` overrides, e.g.
    `google/gemini-3.1-flash-image`). Checks the Leadnius login before any paid call, converts to JPEG (sharp) and
    stores the image on the card through the backend. Failed generations aren't billed by OpenRouter.
  - *Upload*: PNG / JPEG / WebP up to 8 MB (`POST /api/studio/items/{id}/media`, stored in `CONTENT_MEDIA_DIR`,
    served at `/api/studio/media/{file}`). Instagram only takes JPEG.
- **Video**: "Write script with AI" → hook, script with B-roll / on-screen notes, shot list, caption, YouTube title
  (skills youtube-script, linkedin-hook-writer). Then shoot + edit, upload the final file to Google Drive shared as
  "Anyone with the link", paste the link, press Uploaded. Publishing downloads it from
  `drive.google.com/uc?export=download&id=…` (large files can hit Drive's virus-scan page; then post it yourself).

**Generate ideas** (board or Trends tab): Claude with content-strategy, content-waterfall and linkedin-hook-writer,
over the latest trend report + top 15 outlier posts + the business profile; skips titles already on the board.

Every Claude / OpenAI call is a button click labelled "uses AI credits" (the AI_REQUIRE_APPROVAL rule holds: no
background AI). Without a Claude key the AI buttons return 503.

## Trend analyser (Trends tab)

`services/trends.py`, through the workspace's **own Apify token** (Content Settings). Runs only from "Pull posts".

| Platform | Actor | Watches | ≈ price / 1k |
|---|---|---|---|
| Instagram | `apify~instagram-scraper` | accounts, hashtags | $1.5–2.7 |
| Facebook | `apify~facebook-posts-scraper` | page URLs / names | $2–5 |
| Reddit | `trudax~reddit-scraper-lite` | subreddits (top of week / month) | $3.4–4 |
| X | `apidojo~tweet-scraper` | keywords, accounts (needs a paid Apify plan) | $0.40 |
| LinkedIn | `harvestapi~linkedin-post-search` | keywords, profile URLs | $1.5–2 |

Limits per workspace: posts per source (5–100), look-back days, max Apify spend per pull (split across platforms,
passed to Apify as `maxTotalChargeUsd`). Posts land in `trend_post` with engagement
(likes + 2×comments + 3×shares + views/100) and **outlier** = engagement ÷ the author's median (3+ posts) or the
platform batch median. "Find trends" (Claude, skills researcher + content-strategy) reads the top 40 outliers of the
last 30 days into a `trend_report`: themes, why they work, hook patterns, best formats. "+ Idea" puts one post on the
board without AI.

## Channel Posting

Scheduling a card creates one `channel_post` per platform, using the workspace's first active account for that
platform (changeable per post). `services/publishers.py: run_loop` publishes due posts every 60 s; a post is claimed
(`scheduled → posting`) before sending so it can't go out twice. Per post: Post now / Retry, I posted it (with link),
Reschedule, switch account, Cancel. **Test mode**: `CONTENT_POST_DRY_RUN` (defaults to `DEV_MODE`) logs instead of
publishing and returns a `dryrun-…` id.

| Platform | Text | Graphic | Video |
|---|---|---|---|
| LinkedIn | ✓ | ✓ (one image; carousel → first slide via API, all slides via Unipile) | ✓ |
| Facebook Page | ✓ | ✓ | ✓ (`file_url`) |
| Instagram | – | ✓ (single or carousel, JPEG) | ✓ (Reels) |
| X | ✓ (280) | ✓ (up to 4 images) | ✓ |
| YouTube | – | – | ✓ |

## Posting accounts: platform API or Unipile

Each platform's own API (OAuth; tokens encrypted in `publish_account`):

| Platform | Server env | Redirect URI to register | Notes |
|---|---|---|---|
| Instagram + Facebook | `META_APP_ID`, `META_APP_SECRET` (`META_GRAPH_VERSION` v27.0) | `{BACKEND_URL}/api/studio/oauth/callback/meta` | One login adds every Page + its linked Instagram business/creator account. Scopes `pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish, business_management`; App Review for client accounts. |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` (already set), `LINKEDIN_VERSION` 202610 | `{BACKEND_URL}/api/studio/oauth/callback/linkedin` | App needs the "Share on LinkedIn" product (`w_member_social`) + "Sign In with LinkedIn using OpenID Connect". 60-day token; reconnect when it expires. |
| X | `X_CLIENT_ID`, `X_CLIENT_SECRET` | `{BACKEND_URL}/api/studio/oauth/callback/x` | OAuth 2.0 PKCE, confidential client; posting needs an X API plan with write access. |
| YouTube | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (already set) | `{BACKEND_URL}/api/studio/oauth/callback/google` | Enable YouTube Data API v3; `youtube.upload` is a sensitive scope (Google verification for production; unverified apps upload as private). |

**Unipile** (LinkedIn + Instagram only; same `UNIPILE_API_KEY` as LinkedIn DMs, docs/sending-methods.md):
`POST /v2/{account_id}/posts {text, attachments[{content base64, content_type, filename}], post_as}`.

- "Unipile" button → hosted login → back to Content Settings with `account_id` + `state` → claimed as a posting
  account (`publish_account.meta.via = "unipile"`). The signed state is `post:<platform>`, so a DM-linking state can't
  create a posting account and vice versa.
- The LinkedIn account already linked through Unipile for DMs can be reused ("Use it for posting"), no second login.
- "Company page" on a Unipile LinkedIn account lists its pages (`GET /v2/{account_id}/linkedin/company/pages`) and adds
  one as its own posting account (posts with `post_as`).
- Unipile does not post to Facebook Pages, X or YouTube; those use their own APIs.
- Disconnecting a Unipile posting account removes it from Unipile too, unless DMs or another posting account use it.

## Data

Migration `0010` (idempotent): `trend_run`, `trend_post` (unique org + url), `trend_report`, `studio_item`,
`publish_account`, `channel_post`. Workspace settings live in `organization.settings.contentStudio`
(`apifyTokenEnc`, `apifyUser`, `apifyPlan`, `sources`, `limits`, `brand`).

## Code

Backend: `models/studio.py`, `services/{trends,studio,publishers}.py`, `services/unipile.py` (`create_post`,
`company_pages`), `api/studio.py`, tests `tests/test_content_studio.py`.
Frontend: `lib/agent/studio.ts`, `components/content/{StudioBoard,CardDrawer,TrendsPanel,ContentSettings,shared}.tsx`,
`app/dashboard/content/{studio,posting,settings}`, `app/api/content-graphic`, `app/api/content-image`.

## Ideas: sources, pillars and scores (2026-11-20)

`studio.generate_ideas` no longer depends on trends alone.

- **Sources** (`studio.idea_sources`, no AI, nothing paid):
  - the buyer profile (pains, objections, value props, proof);
  - buying signals from the last 45 days;
  - what leads said in replies (their words, no names);
  - what leads post about (lead activity);
  - the latest trend read and top posts.

  The Generate dialog shows how much each source has (`GET /api/studio/ideas/sources`).
- **Pillars:** up to 6 themes per workspace (`contentStudio.pillars`, `PUT /api/studio/settings/pillars`, edited from
  the "Pillars" button on the board). Ideas are spread across them; one pillar can be picked when generating. Cards
  carry `pillar`, and the board filters by it.
- **Scores:** each idea is rated 1-5 for fit with the buyer, timeliness and originality.
  - `score` = 0-100, with fit counting double.
  - `meta.reason` says why; `meta.source` and `meta.basedOn` say what inspired it.
  - New ideas are placed best-first.
  - Stored on `studio_item.pillar / score / meta` (migration 0013).

Tests: `tests/test_content_ideas_v2.py`.

Not built yet:
- learning from published posts' results;
- accounts to watch;
- a weekly batch;
- voice from past posts.

