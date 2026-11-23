# Leadnius Agent platform — API contract

This is the contract between `lead-gen-backend` (FastAPI, Postgres) and `lead-gen-frontend` (Next.js) for the
outbound-agent features ported from AgentHQ (`~/Gudpals/agent-saas` + `agent-saas-backend`). Both sides are built
against this document; if something here is ambiguous, follow the AgentHQ backend's behaviour
(`~/Gudpals/agent-saas-backend/src`).

## Conventions

- **Base:** every path below is prefixed `/api`. Routes are registered **without** a trailing slash. The frontend
  `lib/api.ts` `normalizeEndpoint` must not append a slash to these prefixes: `/api/workspace`, `/api/accounts`,
  `/api/campaigns`, `/api/leads`, `/api/replies`, `/api/signal-types`, `/api/signals`, `/api/personas`, `/api/queue`,
  `/api/integrations`, `/api/dnc`, `/api/billing`, `/api/analytics`, `/api/webhooks`.
- **Auth:** `Authorization: Bearer <access_token>` (existing JWT from `/api/auth/login`). Use `get_current_user`.
- **Workspace = organisation.** Every row is scoped by `org_id = current_user.current_org_id`. If the user has no
  current org → `400 {"detail": "No active organisation"}`. Another org's id → `404`.
- **Roles:** from `OrganizationMember.role` for the current org. `owner`/`admin` ⇒ admin. Member-only routes return
  `403 {"detail": "Admin role required"}`. Admin-only: `PATCH /workspace`, `POST /integrations/{key}/{action}`,
  `DELETE /dnc` entries (not needed now).
- **JSON is camelCase** for all new endpoints, both request and response (pydantic `alias_generator=to_camel`,
  `populate_by_name=True`, `by_alias=True`). Existing auth/users/organizations endpoints stay snake_case.
- **IDs** are UUID strings. **Timestamps** are ISO-8601 strings (UTC, naive `datetime.utcnow()` on the backend,
  serialised with a trailing `Z`-less ISO string is fine; frontend treats as UTC).
- **Errors:** FastAPI style `{"detail": "..."}`; validation errors are the standard 422 list (frontend flattens them).
- **Enums** (string literals):
  - `Channel` = `whatsapp | linkedin | email`
  - `Sentiment` = `positive | neutral | negative`
  - `StepType` = `message | connect | visit | inmail | email | template | handoff`
  - `AccountStatus` = `active | warming | paused | disconnected`
  - `CampaignStatus` = `running | paused | draft | completed`
  - `LeadStatus` = `new | in_sequence | replied | opted_out`
  - `EnrolmentStatus` = `queued | active | replied | stopped | finished`
  - `QueueStatus` = `pending | approved | rejected`
  - `DncKind` = `email | phone | domain`
  - `Plan` = `starter | growth | scale`

## Shared shapes (TypeScript notation = JSON wire format)

```ts
type SequenceStep = {
  id: string; type: StepType; delayDays: number; delayHours: number; // 0-23
  subject?: string; body: string; onlyIfNoReply: boolean; condition?: string;
  handoffTo?: Channel; mode?: "ai" | "template"; instructions?: string; inputs?: string[];
};
type SendWindow = { from: string; to: string; days: string[] };          // "HH:MM", ["Mon",...]
type LeadProfile = { headline: string; tenure: string; location: string; recentActivity: string;
  hook: string; companyNote: string; signalDetail: string; signalHook: string };
type WorkspaceSettings = {
  company: { name: string; website: string; industry: string; size: string; offering: string;
             geographies: string; dealSize: string; caseStudies: string };
  icp: { titles: string; companySize: string; industries: string; fundingStage: string; pains: string;
         valueProps: string; objections: string; tone: string; cta: string };
  guardrails: { oneCampaignAtATime: boolean; stopAllOnReply: boolean; skipCustomers: boolean;
                companyCooldown: boolean; approveFirst20: boolean; pauseUnhealthySenders: boolean };
  optOutKeywords: string[];
};
type ConnectedAccount = { id: string; channel: Channel; handle: string; label: string; status: AccountStatus;
  dailyLimit: number; sentToday: number; health: number; createdAt: string };
type Campaign = { id: string; channel: Channel; name: string; status: CampaignStatus; accountIds: string[];
  leadList: string; leads: number; sent: number; replies: number; positive: number; steps: SequenceStep[];
  window: SendWindow; createdAt: string };
type Lead = { id: string; name: string; title: string; company: string; email: string; phone: string;
  linkedin: string; signal: string; score: number; status: LeadStatus; profile: LeadProfile | null;
  week: string; createdAt: string; persona?: string | null };          // persona = matched persona name
type Reply = { id: string; leadId: string | null; campaignId: string | null; channel: Channel;
  sentiment: Sentiment; name: string; title: string; company: string; campaign: string; message: string;
  aiSummary: string; email: string; phone: string; linkedin: string; unread: boolean; receivedAt: string };
type Signal = { id: string; type: string; company: string; detail: string; score: number; source: string;
  contacts: number; detectedAt: string };
type SignalType = { key: string; name: string; desc: string; enabled: boolean; count: number };
type Persona = { id: string; name: string; plural: string; titles: string[]; pains: string[]; cares: string;
  value: string; proof: string; tone: string; cta: string; leads: number; reply: number };
type Segment = { text: string; src?: "signal" | "profile" | "persona" | "cta" };
type Draft = { persona: string; subject?: string; segments: Segment[] };
type QueueItem = { id: string; leadId: string; channel: Channel; step: number; status: QueueStatus;
  createdAt: string; lead: Lead; persona: string | null; draft?: Draft; text: string };
type Integration = { key: string; name: string; desc: string; category: "Channels" | "CRM" | "Data" | "Productivity";
  connected: boolean; connectedAt: string | null };
type Workspace = { id: string; name: string; plan: Plan; credits: number; creditsUsed: number;
  settings: WorkspaceSettings; createdAt: string };
```

## Endpoints

### Workspace (`api/workspace.py`, prefix `/api/workspace`, plus `/api/dnc`, `/api/billing`)

| Method & path | Role | Body / query | Response & rules |
|---|---|---|---|
| `GET /workspace` | any | – | `Workspace` (from the current Organization: `name`, `plan`, `credits`, `credits_used`, `settings`) |
| `PATCH /workspace` | admin | `{ name?, company?: Partial<company>, icp?: Partial<icp>, guardrails?: Partial<guardrails>, optOutKeywords?: string[] }` | Shallow-merge each section; `optOutKeywords` replaced wholesale; returns `Workspace` |
| `GET /dnc` | any | – | `{ emails: number, phones: number, domains: number }` |
| `POST /dnc` | any | `{ entries: {kind: DncKind, value: string}[] }` **or** `{ csv: string }` | CSV split on newline/comma; kind inferred (`@`→email, `/^[+\d][\d\s()-]+$/`→phone, else domain); phone normalised to `[\d+]` only, others trimmed+lowercased; insert ignore-duplicates; returns `{ added: number }` |
| `GET /billing` | any | – | `{ plan, price: string, usage: {label, used, total}[] }` with rows `Credits`, `WhatsApp numbers`, `LinkedIn seats`, `Email inboxes`. Limits: starter 1/1/3 "₹4,999", growth 5/5/10 "₹14,999", scale 50/50/100 "Custom". Senders counted per channel where status ≠ disconnected |
| `POST /workspace/seed-demo` | admin, `DEV_MODE` only (else 403) | – | Loads the AgentHQ demo dataset (QuantPM-style: 10 senders, 6 campaigns, 10 leads with profiles, 5 enrolments, 8 replies, 7 signals, signal-type counts, 8 connected integrations, queue items, 2 DNC rows, 14 days activity + 7-week trend) into the current org, replacing existing agent data for that org. Returns `{ ok: true }` |

Team management uses the existing `/api/organizations/{id}/members`, `/invite`, `PATCH/DELETE members/{user_id}`.

### Sender accounts (`api/accounts.py`, prefix `/api/accounts`)

| Method & path | Body / query | Rules |
|---|---|---|
| `GET /accounts?channel=` | – | List for org (invalid channel ignored), ordered by `created_at` |
| `POST /accounts` | `{ channel, handle, label?="New account", dailyLimit? }` | Status forced `warming`, health 100, sentToday 0; default limit whatsapp 50 / linkedin 20 / email 20. 201 `ConnectedAccount` |
| `PATCH /accounts/{id}` | `{ label?, status?, dailyLimit? }` | Returns row |
| `POST /accounts/{id}/toggle` | – | `paused`→`active`; any other → `paused` |
| `DELETE /accounts/{id}` | – | 204; also removes the id from every campaign's `accountIds` |

### Campaigns (`api/campaigns.py`, prefix `/api/campaigns`)

`CampaignInput = { channel, name, status?="draft", accountIds?=[], leadList?="", steps: SequenceStep[] (min 1), window: SendWindow }`.

`validate()` → 400 in this order: LinkedIn `connect` step body > 300 chars; `handoff` step without `handoffTo`;
`status=running` with no accounts; account not in org ("unknown sender account"); account channel ≠ campaign
channel; any account `disconnected`.

| Method & path | Body / query | Rules |
|---|---|---|
| `GET /campaigns?channel=` | – | `Campaign[]`, `created_at` desc |
| `GET /campaigns/sent?campaign_id=&channel=&limit=500` | – | What went out, newest first, for one campaign, one channel's campaigns, or all: `{ items: SentMessage[], total, leads, counted }`. Sources: LinkedIn `outbound_action` done with outcome ok (connect / message; visits excluded), `email_message` and `whatsapp_message` with direction out. `SentMessage = { id, campaignId, campaignName, channel, leadId, leadName, leadTitle, leadCompany, leadLinkedin, leadStatus, step, kind: connect\|message\|email\|whatsapp, subject, text, to, status, sentAt, link, via }`. `counted` = sum of the campaigns' `sent` counters (higher than `total` when older sends have no stored record). 404 for a campaign outside the org. UI: every Sent number / "Messages sent" tile opens it (components/agent/SentMessages.tsx) |
| `GET /campaigns/{id}` | – | `Campaign` |
| `POST /campaigns` | `CampaignInput` | validate; 201 `Campaign` (counters 0) |
| `PUT /campaigns/{id}` | `CampaignInput` | full replace + validate |
| `PATCH /campaigns/{id}/status` | `{ status }` | if → running, require ≥1 account; also promote this campaign's `queued` enrolments to `active` |
| `DELETE /campaigns/{id}` | – | 204; cascades `campaign_leads`; replies keep `campaignId` nulled |
| `GET /campaigns/{id}/leads` | – | `{ lead: Lead, status: EnrolmentStatus, currentStep: number, addedAt: string }[]` |
| `POST /campaigns/{id}/leads` | `{ leadIds: string[] (min 1) }` | per id: not in org → skip "not found"; lead `opted_out` or DNC-blocked → "do not contact"; guardrail `oneCampaignAtATime` and lead has queued/active enrolment in another campaign → "already in another active campaign"; else enrol (`active` if campaign running else `queued`, ignore if already enrolled). `new` lead → `in_sequence`; `campaign.leads += 1` per real insert. Returns `{ added: number, skipped: {leadId, reason}[] }` (`added` = real inserts) |

### Leads (`api/leads.py`, prefix `/api/leads`)

`LeadInput = { name, company, title?="", email?="", phone?="", linkedin?="", signal?="", score?=0 (0-100), week?, profile?: LeadProfile }`.

| Method & path | Body / query | Rules |
|---|---|---|
| `GET /leads?week=&status=&ids=` | `ids` comma-separated | `Lead[]` with `persona` name, score desc |
| `GET /leads/weeks` | – | `string[]` distinct ISO weeks desc (`"2026-W43"`) |
| `GET /leads/stats?week=` | – | `{ total, withEmailPct, withPhonePct, avgScore }` rounded ints, denominator floored at 1 |
| `GET /leads/export.csv?week=&status=` | – | `text/csv` attachment `leads.csv`; columns name,title,company,email,phone,linkedin,signal,score,status,week |
| `GET /leads/{id}` | – | `Lead & { personaObj: Persona | null }` |
| `POST /leads` | `{ leads: LeadInput[] (1..5000) }` | week defaults to current ISO week, status `new`; 201 `{ added, ids }` |
| `GET /leads/{id}/personalize?channel=&step=0` | – | 400 bad channel; 409 "create a persona first" if org has no personas; step clamped 0-2; returns `Draft` |

### Agents (`api/agents.py`: `/api/signal-types`, `/api/signals`, `/api/personas`, `/api/queue`, `/api/integrations`)

| Method & path | Role | Body / query | Rules |
|---|---|---|---|
| `GET /signal-types` | any | – | `SignalType[]` (ensure provisioned) |
| `PATCH /signal-types/{key}` | any | `{ enabled }` | returns row |
| `GET /signals?minScore=` | any | – | `Signal[]` detected_at desc, score ≥ min |
| `GET /personas` | any | – | `Persona[]` (ensure provisioned) |
| `POST /personas` | any | `PersonaInput = { name, plural, titles: string[] (≥1), pains?: string[], cares?, value?, proof?, tone?, cta? }` | 201 |
| `PUT /personas/{id}` | any | `PersonaInput` | |
| `DELETE /personas/{id}` | any | – | 204 |
| `GET /queue` | any | – | pending `QueueItem[]` joined to lead, with `draft`/`text` from personalize (undefined if no personas) |
| `POST /queue` | any | `{ leadId, channel, step?=0 }` | lead must be in org; 201 `QueueItem` |
| `POST /queue/{id}/{decision}` | any | decision `approve|reject`; id may be `all` | only pending items change; `{ updated: number }` |
| `GET /integrations` | any | – | `Integration[]` (ensure provisioned) |
| `POST /integrations/{key}/{action}` | admin | action `connect|disconnect` | sets `connected`, `connectedAt` (null on disconnect); returns row |

### Replies & inbound webhook (`api/replies.py`: `/api/replies`, `/api/webhooks`)

| Method & path | Auth | Body / query | Rules |
|---|---|---|---|
| `POST /webhooks/inbound` | header `x-webhook-secret` == `settings.INBOUND_WEBHOOK_SECRET` (timing-safe) else 401 | `{ workspaceId, channel, message, from: {email?, phone?, linkedin?, name?}, campaignId? }` | 404 unknown workspace. Runs `ingest_reply` (below). 201 `Reply` |
| `GET /replies?sentiment=&channel=` | JWT | – | `Reply[]` received_at desc |
| `GET /replies/counts` | JWT | – | `{ all, positive, neutral, negative, unread }` |
| `PATCH /replies/{id}` | JWT | `{ sentiment?, unread? }` | returns row |

`ingest_reply` (service): (1) match lead by email (case-insensitive) → phone (spaces stripped) → linkedin exact;
(2) attribute campaign: lead's enrolment whose campaign id == `campaignId` if given, else same channel, first match;
(3) opt-out = case-insensitive substring of `settings.optOutKeywords`; sentiment via `classify_reply`;
(4) in one transaction: insert reply (snapshot name/title/company/contacts from lead else `from`; name fallback
`from.name` → email → phone → "Unknown"); lead status `opted_out` or `replied`; enrolments → `replied` (all of the
lead's if opt-out or `guardrails.stopAllOnReply` or no attributed campaign, else only the attributed one); on opt-out
add email+phone to DNC reason `opt-out`; `campaign.replies += 1` (+`positive`); upsert `activity.replies += 1` for today.

`classify_reply(message, opt_out_keywords) -> (sentiment, ai_summary)` on lowercased text, first match wins:
1. opt-out → `negative`, "Opted out. Auto-added to do-not-contact."
2. `not interested`, `\bno thanks\b`, `don'?t (message|contact|email)`, `unsubscribe`, `\bstop\b`, `remove me` → `negative`, "Not interested."
3. `not the right time|later|next quarter|q[1-4]\b|budget freeze` → `neutral`, "Timing is off. Follow up later."
4. `\byes\b`, `interested`, `let'?s (talk|chat)`, `\bslots?\b`, `\bcall\b`, `\bmeet(ing)?\b`, `send (me|over)`, `\bloop in\b`, `sounds good`, `timing is` → `positive`, "Shows interest. Follow up quickly."
5. else `neutral`, summary = message truncated to 117 chars + "…" if > 120.

### Analytics (`api/analytics.py`, prefix `/api/analytics`)

`pct(a,b) = round(a/b*100, 1)` or 0 when b = 0.

| Method & path | Response |
|---|---|
| `GET /analytics/overview?channel=` | `{ totals: { sent, replies, positive, leadsInSequence, replyRate, activeCampaigns, activeSenders, sentToday, capacityToday }, byChannel: { channel, campaigns, sent, replies, positive, replyRate, positiveRate }[] (always 3), campaigns: { id, name, channel, status, sent, replies, positive, replyRate }[] }`. Channel filter applies to campaigns only. `capacityToday` sums `dailyLimit` of senders not disconnected/paused |
| `GET /analytics/weekly-activity` | always 7 entries `{ day: "Mon", date: "YYYY-MM-DD", whatsapp, linkedin, email, replies }` for today−6..today |
| `GET /analytics/trend?weeks=7` | weeks clamped 1-26; activity grouped by ISO week → `{ week: "W43", leads, replies, meetings }[]`, last N |

## Personalisation (`services/personalize.py`)

- `persona_for(lead, personas)`: first persona where any persona title is a case-insensitive substring of the lead
  title, else `personas[0]`.
- Fallback profile when `lead.profile` is null: `hook = "what {company} is building"`, `signalHook = "the recent
  {signal.lower()} news"` if signal else `"{company}'s growth"`, other fields "".
- `personalize(lead, persona, channel, step) -> Draft` builds `Segment[]` (`n` = first name, `pain = pains[0]` or
  "outbound doesn't scale", first letter lowercased):
  - **Step 0 LinkedIn:** `"Hi {n} — "`, `"congrats on {signalHook}"` (signal), `". Enjoyed "`, `hook` (profile),
    `". I work with {plural} on "`, `pain` (persona), `" — would love to connect."`
  - **Step 0 WhatsApp/email:** `"Hi {n} 👋 "` (WhatsApp) / `"Hi {n}, "` (email); `"congrats on {signalHook}!"`
    (signal); `" Saw "`; `hook` (profile); `" — "`; `"most {plural} we talk to at this stage say {pain}."` (persona);
    `" We help teams like {company} with "`; `value` (persona); `". "`; `cta` (cta). Email subject:
    `"{signalHook minus leading the/your} → pipeline"`.
  - **Step 1:** `"{n}, quick follow-up — "`; `proof` (persona); `". Given "`; `signalHook` (signal); `", the timing
    felt relevant for {company}. "`; `"Want the 1-page breakdown?"` (cta). Email subject `"Re: {company}"`.
  - **Step 2:** `"Last note from me, {n}. "`; `"If {pains[1] or pain} isn't a priority right now"` (persona);
    `" while you're "`; `"settling into the new role"` if tenure matches `week|month` else `"heads-down on
    {company}'s next phase"` (profile); `", just say \"later\" and I'll circle back next quarter."`. Email subject
    `"Close the loop?"`.
- `to_text(segments)` joins `text`.

## Provisioning (`services/provision.py`)

`ensure_provisioned(org)` is idempotent and is called from `OrganizationService.create_organization` and lazily
by `GET /signal-types`, `/integrations`, `/personas`, `/workspace`:
- `org.settings` defaults: company `{industry: "B2B SaaS", size: "1-10", name: org.name, website: org.domain or "", others ""}`,
  icp `{tone: "Friendly & direct", others ""}`, guardrails all `true` except `approveFirst20: false`,
  `optOutKeywords: ["STOP","unsubscribe","not interested","remove me","don't message"]`.
- 10 signal types (disabled, count 0): `funding, hiring, job_change, tech, intent, social, news, visitors, competitor, events`
  with the names/descs from `agent-saas-backend/src/db/defaults.ts`.
- 15 integrations (disconnected): Channels `whatsapp, linkedin, google, outlook, smtp`; CRM `hubspot, salesforce,
  zoho, pipedrive`; Data `apollo, clay, crunchbase`; Productivity `calendly, slack, webhooks` (names/descs from defaults.ts).
- 4 starter personas: "Founder / CEO", "Sales leader", "Finance leader", "Marketing / Growth" (fields from
  `agent-saas-backend/src/db/demo/personalize.ts`), stats zeroed.

## Database (Postgres, SQLModel)

Organization gains: `plan: str = "growth"`, `credits_used: int = 0`, `settings: JSONB` (WorkspaceSettings; default
`{}` then filled by provisioning). `database.py`'s ALTER block adds these three with `IF NOT EXISTS`.

New tables (all with `org_id UUID FK organization.id`, indexed):
`sender_account`, `agent_campaign`, `campaign_lead` (PK campaign_id+lead_id, cascade), `agent_lead`, `reply`
(lead_id/campaign_id nullable, `ON DELETE SET NULL`), `signal_type` (PK org_id+key), `signal`, `agent_persona`,
`approval_queue` (lead cascade), `workspace_integration` (PK org_id+key), `do_not_contact` (PK org_id+kind+value),
`activity_daily` (PK org_id+date; columns whatsapp, linkedin, email, replies, leads, meetings).
Table names are prefixed where they would collide with removed lead-gen tables (`lead`, `campaign`, `persona`,
`integration`) so a dev DB with old tables still works; the removed tables are simply left orphaned.

## Frontend routes (all under the protected `/dashboard` shell)

| Route | Page |
|---|---|
| `/dashboard` | AgentHQ dashboard (overview, weekly activity, sentiment, latest replies, running campaigns, trend) |
| `/dashboard/sales-leads`, `/dashboard/sales-leads/analytics` | Replies inbox; agent analytics |
| `/dashboard/integrations` | Integrations |
| `/dashboard/account` | Account: Connected IDs, Business profile, GTM playbook, Guardrails, Team & billing (team from org members; "Manage organisation" links to `/dashboard/organisation`) |
| `/dashboard/agents`, `/agents/signal`, `/agents/leads`, `/agents/messaging`, `/agents/[channel]`, `/agents/[channel]/campaigns/[id]` | Agent pages |
| kept: `/dashboard/organisation`, `/dashboard/privacy`, `/dashboard/terms`, `/dashboard/affiliate-program` | unchanged |

### Signal feeds (free sources) and scans

`POST /api/signal-types/{key}/scan` works for custom signals (AI web scan, `services/signal_scan.py`) **and** for the
built-in `hiring`, `funding` and `news` types (`services/signal_feeds.py`): Google News RSS searches built from the
ICP industries and the company's geography, last 30 days, deduped by article URL and company. With a server
`ANTHROPIC_API_KEY`, Haiku (`MESSAGE_AI_MODEL`, low effort) names the company and scores ICP fit; without one the
company is parsed from the headline and `score` is 50. Every signal carries the article `url`. Enabled feed-backed
types are also rescanned in the background every `SIGNAL_FEED_SCAN_INTERVAL_S` (default daily). The other built-in
types (job changes, tech stack, visitors, ...) need a data provider and answer `400`.

### Plan limits (enforced since 2026-10-30, `services/plan.py`)

- **Seats:** `PLAN_LIMITS[plan]` caps connected sender accounts per channel (starter 1/1/3, growth 5/5/10, scale
  50/50/100 for WhatsApp / LinkedIn / email). `POST /api/accounts`, `/api/accounts/email`, `/api/accounts/whatsapp` and
  the Gmail/Outlook OAuth connect answer `402` with a plain message when the cap is reached; disconnected accounts
  don't count.
- **Credits:** `organization.credits` (allowance; `0` = unlimited) and `credits_used`. One credit per outbound message:
  email send, WhatsApp template send, LinkedIn connect/DM reported `ok`. When spent, email/WhatsApp `send-due`
  answers `reason: "no message credits left on this plan"` and the LinkedIn operator queue is empty. Shown on
  `GET /api/billing` as the "Credits" row.
- `PLAN_LIMITS_ENFORCED=false` disables both (self-hosted / demo).

### Signal strategy (2026-10-30, `services/signal_strategy.py`)

Every workspace's signals are derived from its own GTM playbook and ICP, tiered by timing and chosen for uniqueness:

| Tier | Meaning | Treatment |
|---|---|---|
| `intent` | the buyer is already looking for this kind of help (asked, RFP, hired or hiring someone to own it, evaluating) | contact within days |
| `hot` | something broke or changed in the last 90 days that creates the pain now | full sequence |
| `warm` | context that makes them a likely fit soon: new leader, growth, a date on the calendar | LinkedIn + email |
| `cool` | fit only, no timing | nurture |

`SignalType` gained `tier`, `rationale` (why it predicts a deal and why competitors don't watch it, plus how to find it)
and `origin` (`manual` | `playbook` | `catalog`). `POST /api/signal-types/strategy` (admin, one Opus call) returns
`{ summary, created: SignalType[], updated: key[] }`: every existing type gets a tier, and up to 14 new types are added
**switched off** with `origin: "playbook"` for review (the Signal page shows them as "Proposed", grouped by tier). The same
run happens in the background after every `POST /api/playbook/documents`. The strategist must propose at least half
unusual angles (succession, legacy systems in job posts, hiring a person for a software job, reviews, policy changes on the
company's own site, compliance mandates, recalls, launches that change operating load, vendor rollouts...), each findable
on the public web. Custom-type cap is 40. `tier` and `rationale` are editable on custom types via `PATCH`.

### Signal category and lead hunt (2026-11-01, `services/lead_hunt.py`, migration 0006)

`SignalType.category` is `basic` (the obvious triggers every vendor watches; built-ins are always basic) or `unique`
(angles nobody else pitches on; strategist proposals are unique). Settable on create and `PATCH` for custom types.

`POST /api/signal-types/hunt` (admin) `{ keys?, maxSignals=6, maxSearches?, includeBasic=false, findContacts=true, window? }`
→ `{ signals: Signal[], leads, scanned: key[], dropped, note }`. Without `keys` it takes the enabled custom types, unique
first, then by tier (intent, hot, warm, cool), least recently scanned first. One web-search call
(`SIGNAL_SCAN_MODEL`, Haiku by default, `LEAD_HUNT_MAX_SEARCHES`) covers all of them and names the decision maker when a
result does; one more call (`LEAD_HUNT_CONTACT_SEARCHES`) looks up a decision maker for up to 8 companies without one.
Companies go to the signal feed, named people become `AgentLead`s (signal = type name, profile.signalDetail = what
happened, profile.hook = source URL). A match is kept only if its URL was returned by the search, and a person only if
the page naming them was; everything else is counted in `dropped`. `window` overrides the default "last 30 days" rule
(e.g. events this year or in the next two months). Costs are metered as `lead_hunt` / `lead_hunt_contacts`.
Single-signal scans (`/{key}/scan`) also use `SIGNAL_SCAN_MODEL` now, with `SIGNAL_SCAN_MAX_SEARCHES=12` and the same URL check.

### GovCon feed: recompete window from FPDS (2026-10-30, `services/govcon_feeds.py`)

A custom signal type whose `sources` include `"fpds"` is scanned from the public FPDS ATOM feed instead of the AI web
scan: small-business incumbents (`CO_BUS_SIZE_DETERMINATION:"S"`) whose contract's estimated completion date falls
90-180 days out (`ESTIMATED_COMPLETION_DATE:[a,b]`), base-and-all-options value at or above `GOVCON_MIN_AWARD` (default
$250k), one signal per vendor, deduped against the feed by vendor name. Each signal's `detail` carries the agency, award ID
(IDV/PIID), value and end month, so the playbook's recompete email can be written from it, and `url` links the FPDS record.
No AI call and no cost; `fit_score` is a rule: higher for set-asides, mid-size awards and service NAICS. Enabled fpds-sourced
types are rescanned daily with the other feeds (`SIGNAL_FEED_SCAN_INTERVAL_S`). Paging is capped at `GOVCON_MAX_PAGES`
(10 actions per page). FPDS does not expose headcount; verify size on LinkedIn before outreach, as the playbook says.

## Notifications (sidebar bell, 2026-11-17)

`GET /api/notifications` → `{items: [{id, kind, title, body, link, createdAt, unread, count?}], unreadCount, seenAt,
needsYou}` built from live state (unread replies, drafted outbound / social actions, queued messages, failed and
account-less due Channel Posting posts, failed trend pulls, disconnected sender / posting accounts).
`POST /api/notifications/seen` marks everything up to now as read for the current user (per workspace). The bell
(`components/NotificationBell.tsx`) also merges the SEO section's notices (`/api/seo/notifications`).
