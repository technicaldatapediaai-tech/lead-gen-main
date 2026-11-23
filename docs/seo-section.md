# SEO / GEO / AEO section (Inbound)

Leadnius' Inbound → **SEO / GEO / AEO** is the former RankSignal product (`~/Downloads/seoaeogeowebsite`), moved
into the Leadnius frontend on 2026-11-16. There is no separate app, login or website any more: the pages live inside
the Leadnius dashboard, the API routes inside the Leadnius Next.js server, and the job worker runs in that server.

## Where things are (lead-gen-frontend)

| What | Path |
|---|---|
| Pages (websites, report, AI answers, to-do, audit, fixes, monthly, prospect report, settings, onboarding) | `app/dashboard/inbound/seo/**` |
| API routes (was `/api/*`) | `app/api/seo/**` |
| SEO back-office for Leadnius staff (customers, AI usage, jobs, flags…) | `app/admin/seo/**` (Admin → SEO / GEO / AEO) |
| Public shared report / score badge | `app/seo-report/[token]`, `app/seo-badge/[file]` |
| Server code | `lib/seo/**` (crawler, audit, visibility, providers, connectors, jobs, billing limits, …) |
| Components | `components/seo/**` |
| Database schema + migrations | `prisma/schema.prisma`, `prisma/migrations` (database `leadnius_seo`) |
| Request gate (CSRF, API session, view-as read-only) | `proxy.ts` → `lib/seo/proxy.ts` |
| Job worker boot | `instrumentation.ts` (`RUN_WORKER_IN_APP=true`), or `npm run seo:worker` |
| Tests (1,051, vitest) | `tests/seo/**`, `npm run test:seo` |
| Colours | `app/seo-theme.css` (rs-* tokens mapped to the Leadnius palette; imported by `app/globals.css`) |

## Sign-in

No SEO login. `/dashboard/inbound/seo/connect` (where pages without an SEO session redirect) and a sync on every
section load call `POST /api/seo/auth/leadnius` with the browser's Leadnius access token. The server asks the Leadnius
API (`/api/users/me`, `/api/workspace`) who it is and maps (`lib/seo/leadnius.ts`):

- Leadnius workspace → one SEO `Organization` (`leadniusOrgId`), plan starter→starter, growth→growth, scale→agency;
  a `Subscription` row with provider `leadnius` (billing is Leadnius'; Razorpay was removed).
- Leadnius user → SEO `User` by email (no usable password); Leadnius platform admins are SEO staff.
- Leadnius role → membership role. Switching workspace in Leadnius re-issues the session.
- Leadnius "view as customer" → SEO staff support session (read-only when Leadnius' is).

Team, account (name, password, deletion) and billing are managed in Leadnius; the SEO settings page says so.

## Removed with RankSignal's standalone app

Marketing site, sign-up / login / Google login / password reset / invites, Razorpay checkout, free check and contact
forms, its robots / sitemap / llms.txt, and the global CSP (would block the Leadnius backend calls; the SEO paths keep
nosniff, referrer, permissions and no-framing headers via `next.config.ts`).

## Setup lives in the business profile; the section shows results (2026-11-16)

- **Business profile** (`/dashboard/profile`, linked from the sidebar's "Profile N% complete"): one Leadnius
  questionnaire. Steps: your business (name, website or "we don't have a website yet", what you sell, industry,
  model, stage) → your customers (who, job titles, department, industries, size, locations, city / country / language,
  where you're active) → competitors (AI suggestions + your own) → customer questions (AI-written + your own) → review.
  Saves the organisation profile (all 8 sidebar completion fields), the agents' workspace company / ICP, and the SEO
  project (create or PATCH, add ticked / remove unticked questions; first website + AI checks for a new or changed site).
- **SEO / GEO / AEO** shows results only: Leadnius page header + tabs Overview · Fixes · AI answers · Progress ·
  Monthly reports · Full report; website switcher, "Business profile" and settings in the header. The old in-section
  setup wizard (`/onboarding`) and customer-question editor (`/prompts`) redirect to the profile.
- **No website**: project `websiteUrl ""` (schemas accept it). Website checks are refused (`no_website`) and never
  scheduled; the Overview (`components/seo/leadnius/no-website-overview.tsx`) shows what AI says about the business
  by name and a "get found without a website" plan from `STARTER_LISTINGS` (Google Business Profile, Maps, directories,
  reviews), tracked on the Get listed tab. Tabs: Overview · AI answers · Get listed · Progress · Monthly reports.
- Look: rs type scale and Card / PageHeader / Stat / Button match Leadnius (`components/agent/ui`); page content is
  full width under the header (no centred 960px column, no second sidebar).

## Config (`lead-gen-frontend/.env.local`)

`DATABASE_URL` / `DIRECT_URL` (local `leadnius_seo`), `SESSION_SECRET`, `CREDENTIALS_KEY` (new for this database),
`APP_URL`, `RUN_WORKER_IN_APP`, `LEADNIUS_API_URL`, and the provider keys moved from RankSignal with the owner's OK:
OpenAI, OpenRouter, DataForSEO, SMTP, `AI_DAILY_BUDGET_USD`, `ALLOW_SIMULATED_PROVIDER`.
Migrations: `npm run seo:migrate` (reads `DATABASE_URL`; export it from `.env.local` first).

The old RankSignal folder and its Neon database are untouched (archive); nothing in Leadnius points at them.

## Fixes from the 2026-11-17 platform test

- **Admin back-office sign-in**: platform admins are sent away from `/dashboard`, so `/admin/seo/*` without an SEO
  session now goes to `/admin/seo-connect` (same bridge; `connectPathFor` in `lib/seo/dashboard/server.ts`, proxy too).
  The back-office renders inside the Leadnius admin console as a tab strip (`components/seo/admin/shell.tsx`), not a
  second app shell.
- **First visit layout**: the connect page now does a full page load to the target (a client redirect kept the bare,
  session-less layout: no padding, toasts or plan banner).
- **Boot check**: `instrumentation.ts` no longer crashes every Leadnius page when `assertProductionEnv` fails; it logs
  `[seo] SEO / GEO / AEO background jobs are OFF …` and skips the worker. Locally with `next start` (APP_URL is
  localhost) run `npm run seo:worker` alongside.
- **Notifications**: a check whose job was marked failed after it finished (worker restarts) now notifies "ready",
  not "didn't finish"; fresh results mark older "didn't finish" notices read; the analyze run's per-change approval
  notices are off (`requestApproval(..., { notify: false })`, the run summary covers them) and the per-change wording
  is plain English; "55 of 50 answers" no longer appears after a resumed run.
