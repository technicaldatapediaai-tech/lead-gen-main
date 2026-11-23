# Leadnius go-live checklist

Everything needed to put Leadnius live on Render: the API (`lead-gen-backend`), the web app (`lead-gen-frontend`,
which also runs the SEO / GEO / AEO job worker) and two Postgres databases. Prepared 2026-11-17.

Run this whenever values change; it reads both env files, says what blocks the launch and prints every OAuth / webhook
URL to register:

```bash
python3 ops/golive_check.py --backend <api env file> --frontend <web env file> --strict
```

Templates: `lead-gen-backend/.env.production.example`, `lead-gen-frontend/.env.production.example`.

## 1. Accounts and keys (owner: you)

| Needed for | What to get | Where it goes |
|---|---|---|
| **Launch blocker** — signup verification, password reset | Resend account + verified sending domain (`RESEND_API_KEY`, `EMAIL_FROM`) | API |
| **Launch blocker** — hosting | Render account (blueprint below), domain DNS access | — |
| AI writing (ideas, copy, scripts, messages, scans) | Anthropic API key (`ANTHROPIC_API_KEY`) — already have one | API |
| SEO AI answers + Content Studio AI images | OpenRouter key (`OPENROUTER_API_KEY`) — already have one | Web app |
| SEO emails (monthly reports, alerts) | SMTP login (already set locally) or Resend | Web app |
| SEO keyword / ranking data | DataForSEO login | Web app |
| Trend analyser | Apify token — each workspace pastes its own in Content Settings | (in app) |
| Google sign-in, Gmail inboxes, YouTube posting, Search Console | Google Cloud OAuth client; enable Gmail, YouTube Data v3, Search Console APIs; publish the consent screen (Gmail and YouTube scopes need Google verification for outside users) | API + Web app |
| Outlook / 365 inboxes | Microsoft Entra app (`MICROSOFT_CLIENT_ID/SECRET`) | API |
| LinkedIn sign-in + posting | LinkedIn app with "Sign In with LinkedIn using OpenID Connect" and "Share on LinkedIn" | API |
| Instagram + Facebook posting | Meta app (Facebook Login for Business), App Review for `pages_manage_posts`, `instagram_content_publish` | API |
| WhatsApp agent | Meta WhatsApp Business: verified business, phone number, approved template (entered per workspace in the app) | (in app) |
| X posting | X developer app with OAuth 2.0 and a plan that allows posting | API |
| Reddit posting (+ lead capture) | Reddit app of type "web app" at reddit.com/prefs/apps (`REDDIT_CLIENT_ID/SECRET`) | API |
| LinkedIn / WhatsApp sending without the Chrome extension; LinkedIn + Instagram posting | Unipile subscription (`UNIPILE_API_KEY`, webhook secret) | API |

## 2. Deploy on Render (owner: you, ~20 minutes)

1. Push the repo to GitHub (it isn't a git repository yet; `_backup/`, `.env`, `.env.local` and `venv/` must stay out).
2. Render → **New → Blueprint** → pick the repo. `render.yaml` creates:
   - `leadnius-db`, `leadnius-seo-db` (Postgres 16)
   - `leadnius-api` (Docker, `/health`, 1 GB disk at `/var/data` for uploaded / AI images)
   - `leadnius-web` (Node 20, `npm ci && npm run build`, migrations as the pre-deploy step, `/api/seo/health`)
   Generated for you: `SECRET_KEY`, `INBOUND_WEBHOOK_SECRET`, `SESSION_SECRET`.
3. Fill every value marked `sync: false` in the Render dashboard (the table above). Generate `CREDENTIALS_KEY` with
   `openssl rand -hex 32`. Never change `SECRET_KEY` or `CREDENTIALS_KEY` after launch: that logs everyone out and
   breaks every saved connection.
4. Custom domains: `api.leadnius.in` → `leadnius-api`, `app.leadnius.in` → `leadnius-web` (Render shows the CNAME
   records). Then set `BACKEND_URL`, `FRONTEND_URL`, `APP_URL`, `NEXT_PUBLIC_API_URL`, `LEADNIUS_API_URL` to the https
   addresses and redeploy the web app (`NEXT_PUBLIC_API_URL` is baked in at build time).
5. Copy the production values into two local files (never commit them) and run the preflight with `--strict` until it
   reports 0 blockers.

Notes: the web app runs on `standard` (the build and the website crawler need more than 512 MB). Keep it at one
instance while the SEO worker runs inside it; to scale out, set `RUN_WORKER_IN_APP=false` and add a Render worker with
`npm run seo:worker:prod`. Vercel can host the web pages, but not the SEO worker, so it would still need that Render
worker.

## 3. Register URLs with each provider (owner: you)

`ops/golive_check.py` prints them with your domains. With `api.leadnius.in` / `app.leadnius.in`:

| Provider | URL |
|---|---|
| Google (sign-in) | `https://api.leadnius.in/api/auth/google/callback` |
| Google (Gmail inbox) | `https://api.leadnius.in/api/integrations/oauth/callback/google` |
| Google (YouTube posting) | `https://api.leadnius.in/api/studio/oauth/callback/google` |
| Google (Search Console) | `https://app.leadnius.in/api/seo/integrations/google/callback` |
| Microsoft (Outlook) | `https://api.leadnius.in/api/integrations/oauth/callback/outlook` |
| LinkedIn (sign-in) | `https://api.leadnius.in/api/auth/linkedin/callback` |
| LinkedIn (posting) | `https://api.leadnius.in/api/studio/oauth/callback/linkedin` |
| Meta (Instagram + Facebook) | `https://api.leadnius.in/api/studio/oauth/callback/meta` |
| X | `https://api.leadnius.in/api/studio/oauth/callback/x` |
| Reddit | `https://api.leadnius.in/api/studio/oauth/callback/reddit` |
| Meta WhatsApp webhook | `https://api.leadnius.in/api/webhooks/whatsapp` |
| Unipile webhook | `https://api.leadnius.in/api/webhooks/unipile` |

## 4. What the apps enforce themselves (done)

- The API refuses to start with `DEV_MODE=false` and a weak or default `SECRET_KEY`, logs a warning for localhost URLs,
  the default webhook secret and channels left in test mode (`services/golive.py`), and rejects the shipped
  `INBOUND_WEBHOOK_SECRET` in production.
- The API accepts the deployed web app's address (`FRONTEND_URL`, `*.onrender.com`, `*.leadnius.in`) for CORS and for
  the "a person clicked" AI approval; an explicit `BACKEND_URL` (custom domain) wins over Render's default URL for OAuth.
- The web app's SEO config check no longer takes every page down: a bad SEO setting switches only the SEO jobs off,
  with a log line `[seo] SEO / GEO / AEO background jobs are OFF …`.
- `lead-gen-frontend/.npmrc` (`legacy-peer-deps`) and a pinned `sharp` make `npm ci` work on a clean machine.

## 5. Launch day (owner: you, with me)

1. Preflight with production values: 0 blockers.
2. Open `https://app.leadnius.in`, sign up with a real address, confirm the verification email arrives.
3. Business profile → save → SEO / GEO / AEO opens and its first check runs (watch the bell).
4. Connect one inbox, one LinkedIn sender (Chrome extension or Unipile), one posting account; schedule a test post to
   your own account; approve one message to yourself.
5. Admin console (`/admin`, platform admin login) → SEO back-office → System shows the worker running and no failed jobs.
6. Turn on Render's daily Postgres backups for both databases and add an uptime check on `/health` and
   `/api/seo/health`.

## 6. After launch

- Keep `AI_REQUIRE_APPROVAL=true` (default): no Claude call without a person's click.
- The daily lead job and the Claude in Chrome scout stay off until you turn them back on.
- Admin console → Usage & cost shows AI spend per workspace; SEO back-office → AI usage shows SEO spend.
