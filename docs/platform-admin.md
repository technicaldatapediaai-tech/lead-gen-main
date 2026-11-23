# Platform admin (Leadnius staff console)

`/admin` in the Lead Gen app. Only users with `is_platform_admin` can open it; they see a **Platform admin** link at
the bottom of the app sidebar. Every `/api/admin/*` call checks the flag on the server too.

Code: `lead-gen-backend/api/admin.py`, `models/admin.py` (`admin_audit_log`), `scripts/platform_admin.py`;
frontend `app/admin/*`, `lib/admin.ts`, `components/admin/ViewAsBanner.tsx`.

## Who is an admin

```
cd ~/Desktop/Lead\ Gen
lead-gen-backend/venv/bin/python -m backend.scripts.platform_admin create admin@leadnius.in --password '…' --name 'Leadnius Admin'
lead-gen-backend/venv/bin/python -m backend.scripts.platform_admin grant  someone@leadnius.in   # existing account
lead-gen-backend/venv/bin/python -m backend.scripts.platform_admin revoke someone@leadnius.in
lead-gen-backend/venv/bin/python -m backend.scripts.platform_admin list
```

`create` also gives the admin a "Leadnius HQ" workspace, so the normal app works for them. There is deliberately no
UI to make someone an admin.

## Pages

| Page | What it shows / does |
| --- | --- |
| Overview | customers (active / suspended), users (signed in this week, new), messages sent in 30 days per channel, replies, plans, credits used, sign-ups per day, channel health (accounts, connected, with errors, paused), accounts reporting errors |
| Customers | every workspace with plan, credits, members, 30-day sends and replies, accounts and errors, last activity, status; search by company, domain or a member's email; filter by status and plan |
| Customer | members (suspend / reactivate a user), connected inboxes / LinkedIn profiles / WhatsApp numbers with their errors, campaigns, **plan & credits**, **suspend / reactivate**, **view as customer**, admin history |
| Users | every login with its workspaces; suspend / reactivate |
| Audit log | every admin change and support view |

## Suspending

- **Workspace**: `organization.status = suspended` with a reason. Its members get "This workspace is suspended" on
  every workspace API call (`agent_deps.get_current_org`, `content_deps`), operator tokens stop working, and the
  background email / WhatsApp senders, IMAP reply polling and LinkedIn drafting skip it. Nothing is deleted;
  reactivating resumes everything. Admins can't suspend the workspace they're signed in to.
- **User**: `user.is_active = false` (already enforced at sign-in and on every request). Platform admins and yourself
  can't be suspended from the console.

## Plan & credits

`PATCH /api/admin/orgs/{id}/billing {plan?, creditsDelta?, note}`. Credits are added or removed as a delta and can't
go below zero. Each change is logged with before / after and the note.

## View as customer (support view)

`POST /api/admin/orgs/{id}/view-as` returns a 30-minute access token carrying `view_as_org`. The frontend parks the
admin's own tokens, opens `/dashboard` with the view token and shows an amber banner with **Exit support view**.

- The token is **read-only**: middleware in `main.py` rejects any non-GET request that carries it.
- `get_current_user` points the (detached) admin user at the customer's workspace for that request only, so the
  admin's own account is never changed.
- No refresh token is kept during the view. When it expires, the app returns to `/admin` instead of signing out.
- The admin console itself refuses view tokens.
- Each support view is written to the audit log.

## Edit as admin (2026-10-30)

Besides the read-only support view, `POST /api/admin/orgs/{id}/view-as` with `{"mode": "edit"}` returns a 30-minute
token whose writes are allowed (`view_as_mode: "edit"` claim; the read-only middleware lets it through) and whose role
inside the workspace is `admin`. The admin console's customer page has **Edit as admin** plus two cards, **GTM
playbook** (documents, company, ICP, personas) and **Signals** (every type with tier, on/off, origin and 30-day count),
each with **Open & edit**, which starts an edit session and lands on the customer's Account → GTM playbook tab or Signal
Agent page. The dashboard shows a red "Editing <org> as a Leadnius admin" banner until **Finish editing**. Every session
is logged in the audit (`view_as.start` with `mode`). `GET /api/admin/orgs/{id}` now includes `playbook`, `signalTypes`
and `signals30d`.

## Usage & cost (2026-10-30)

Every Claude call is metered in `ai_usage` (`services/ai_usage.py`): organisation (from the request's workspace or the
background job's org), feature (`message_writer`, `signal_scan`, `signal_strategy`, `signal_feeds`, `playbook_suggest`,
`content_*`), model, input / output / cache-write / cache-read tokens, web searches and the cost in USD at Anthropic
list prices (`PRICING` in the service; Haiku 5.5 prompts over 100k tokens 5x; web search $10 per 1,000). Update
`PRICING` when the price list changes.

- `GET /api/admin/usage?days=30` → totals, per organisation (with plan, credits and credits used), per feature, per
  model, and the price table. Console page **Usage & cost**.
- `GET /api/admin/orgs/{id}` → `aiUsage` (30 days: totals, by feature, by model, last 25 calls). Console card
  **AI usage & cost** on the customer page.
- `GET /api/admin/overview` → `aiCost30d`, `aiCalls30d`.

Credits (the plan allowance, one per message sent) and AI cost (what the Claude calls cost Leadnius) are shown side
by side so each customer's gross margin is visible.

## Leads

`/admin/leads` (nav "Leads"; each customer page has "See leads (n)"). Shows the actual leads, not just counts: name,
title, company, contact routes (LinkedIn, X or Reddit profile, email), signal with tier and unique/basic, what happened
and the evidence link, fit score, platform and how it was found (Chrome scout, company website, Stack Exchange, …),
found date and status. Filters: workspace, search (name, title, company), signal, platform, tier, found today / 7 / 30
days. "Found today" counts against the 30-a-day target (IST day). Export CSV downloads the filtered list (newest 500).
API: `GET /api/admin/leads?orgId=&q=&signal=&platform=&tier=&since=today|7d|30d|all&page=&pageSize=` (platform admins
only). Opening a workspace's leads is written to the audit log (`org.view_leads`).
