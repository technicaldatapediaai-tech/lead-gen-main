# LinkedIn Posts Agent — design and API contract

The LinkedIn Posts agent runs the weekly content waterfall for one client per organisation (workspace):
Stage 0 find the idea → Stage 1 create → Stage 2 repurpose → Stage 3 ship → Stage 4 convert the engagers.
It lives under the **Content** group in the sidebar (`/dashboard/agents/linkedin-posts`) and is built on the
skills from `timscheuerai/linkedin-funnel` (MIT; vendored under `lead-gen-backend/skills/linkedin-funnel/`).

Conventions are the same as `docs/agent-api-contract.md`: every path is prefixed `/api/content`, registered
without trailing slashes (add `/api/content` to the frontend no-slash list), JWT auth via `get_current_org`,
camelCase JSON via `CamelModel`, UUID ids, UTC timestamps with `Z`. One client = one organisation; the
org switcher selects the client.

## Principles that shape every endpoint

1. **Drafting is not publishing.** Nothing is scheduled, posted or sent by the server. Claude drafts; a human
   approves in the app; a human (or Claude in Chrome under human supervision) executes on LinkedIn.
2. **Account safety.** All LinkedIn actions go through the operator runbooks (`.claude/skills/linkedin-*`) which
   read the app's queues and enforce the client's safety limits: per-day caps, minimum spacing (default 185 s),
   working hours, 1st-degree-only DMs, intent saved before every send, never auto-resend after an uncertain
   outcome. The app keeps the ledger (`content_action_log`) and refuses to hand out work past the caps.
3. **Voice rules are enforced, not suggested.** Every generated text passes `services/voice_rules.check()`
   (deterministic: no em dashes, no banned openers/clichés, specificity heuristics) and the client's voice file is
   in every system prompt. Findings are returned with the draft and shown in the UI.
4. **Numbers only from the proof file.** Prompts forbid inventing metrics; the client's `proof` list is the only
   source of numbers.
5. **Duplicable.** Onboarding is a form + "clone setup from another client". Everything per client lives in
   `content_profile` and the content tables; the skills and global voice rules are shared.

## Data model (all tables org-scoped: `org_id UUID FK organization.id`, indexed)

| Table | Purpose | Key columns |
|---|---|---|
| `content_profile` (1 per org) | Client onboarding | `pillars` JSONB `[{key,name,promise,boundary}]`; `voice_file` TEXT (markdown, the client's voice file); `voice_rules` JSONB `string[]` (client-specific extra rules); `proof` JSONB `[{claim,value,period,source,cleared:bool}]`; `positioning`, `ideal_follower`, `offer` TEXT; `icp` JSONB (see Qualification); `platforms` JSONB `string[]`; `posting_days` JSONB; `posts_per_week` int=5; `timezone`; `keyword_resources` JSONB `[{keyword,resourceName,resourceUrl,dmTemplate,publicReply}]`; `safety` JSONB (see Safety); `notion` JSONB `{pageUrl, databases:{...}}`; `onboarding_complete` bool; `cloned_from_org_id` nullable; timestamps |
| `content_creator` | Inspiration DB: creators monitored | name, platform (`linkedin|x|youtube`), handle, url, niche, what_to_learn, what_not_to_copy, active bool, added_at |
| `content_outlier_post` | Inspiration DB: outlier posts saved | creator_id nullable FK (SET NULL), platform, url, author, posted_at nullable, text, hook, format, metrics JSONB `{likes,comments,reposts,views}`, outlier_ratio float nullable, why_it_worked, tags JSONB, saved_at |
| `content_signal` | Stage 0 inputs | source (`comment|dm|sales_call|post_performance|manual`), text, person, url, week (ISO), tags JSONB, used_in_idea_id nullable, captured_at |
| `content_idea` | Stage 0 slate | week, title, problem, claim, example, proof_of_demand JSONB `[{kind:signal|outlier|post|note, refId?, note}]`, pillar_key, funnel_job (`reach|belief|signup`), status (`proposed|picked|rejected|backlog`), rank int, ai_generated bool, created_at, picked_at nullable |
| `content_piece` | Stage 1 long-form piece | idea_id FK, week, title_a, title_b, chosen_title, hook, thumbnail_notes, outline JSONB `[{chapter,onScreen,claim}]`, script TEXT, transcript TEXT, argument TEXT (newsletter-ready), chapters JSONB `[{title,startSeconds,summary}]`, file_url, status (`packaging|scripted|recorded|edited|transcribed|done`), release_date nullable, timestamps |
| `content_post` | Stage 2/3 posts | piece_id nullable FK (SET NULL), idea_id nullable, type (`newsletter|video|lesson|opinion|proof|chapter|graphic|x_article|micro|resource|idea`), pillar_key, platform (`linkedin|x|newsletter|youtube`), title, hook, body TEXT, graphic_brief TEXT, graphic_url, source_ref (chapter/transcript pointer), status (`idea|drafting|ready|scheduled|published`), publish_date nullable, published_url, approved_by nullable UUID, approved_at nullable, notion_page_id, sort_order int, ai_generated bool, voice_findings JSONB, metrics JSONB, timestamps |
| `content_week` (PK org_id+week) | Weekly run state | status (`ideas|create|repurpose|ship|convert|closed`), picked_idea_id, piece_id, close_notes JSONB `{winners[],questions[],nextIdea}`, notion_synced_at |
| `content_engager` | Stage 4 people | post_id nullable, post_url, name, headline, company, linkedin_url (UNIQUE per org), action (`like|comment|profile_view|repost`), comment_text, keyword_matched, connection_degree (`1|2|3|unknown`), fit_status (`unscored|qualified|review|not_fit`), qualification JSONB (schema below), dm_status (`none|drafted|approved|sent|replied|declined|suppressed`), resource_status (`none|requested|queued|delivered`), notes, captured_at, updated_at |
| `content_message` | DM drafts + ledger | engager_id FK (CASCADE), kind (`warm_dm|resource_delivery|inbox_reply|public_reply|connection_note`), intent, inbound_text (the thread/message being replied to), draft TEXT, final TEXT, status (`drafted|approved|sent|failed|rejected`), approved_by, approved_at, sent_at, sent_by, thread_url, created_at |
| `content_action_log` | Safety ledger | action (`dm_sent|resource_delivered|public_reply|connection_sent|collect_engagers|inbox_read`), ref_id nullable, operator, outcome (`ok|failed|uncertain`), notes, at |
| `content_operator_token` | Runbook auth | name, token_hash, created_by, created_at, last_used_at, revoked bool |

### Safety settings (`content_profile.safety`, defaults)

```json
{ "dailyDmLimit": 20, "dailyConnectionLimit": 10, "dailyPublicReplyLimit": 20, "peoplePerHour": 10,
  "minSpacingSeconds": 185, "workingHours": {"from": "09:00", "to": "18:00"}, "onlyFirstDegreeDms": true,
  "requireApprovalForDms": true, "autoApproveResourceDelivery": false, "pauseAll": false }
```

### Qualification JSON (stored on `content_engager.qualification`, from the repo's schema)

`{ companyScore 0-100, personaScore 0-100, companyDisqualified, personaDisqualified, fitStatus: qualified|review|not_fit,
companyReason, personaReason, missing: string[], evidenceUsed: string[] }`. `content_profile.icp` holds
`{ companyRubric: string, personRubric: string, companyThreshold: 70, personThreshold: 70, exclusions: string[] }`.

## Endpoints

### Profile / onboarding (`api/content_profile.py`)
| Method & path | Notes |
|---|---|
| `GET /api/content/profile` | Creates a default profile on first call. Returns `ContentProfile` |
| `PATCH /api/content/profile` | admin; shallow-merge of top-level fields; JSON sections replaced wholesale |
| `POST /api/content/profile/clone` `{fromOrgId}` | admin; user must be a member of the source org; copies pillars, voice_file, voice_rules, proof (cleared only), positioning, ideal_follower, offer, icp, platforms, posting_days, posts_per_week, keyword_resources, safety, creators; sets `cloned_from_org_id` |
| `POST /api/content/profile/voice/calibrate` `{samples:[{kind: authored|transcript|ghostwritten|rejected, text}]}` | AI: voice-calibration → returns `{voiceFile, rules[]}`; does not save (UI saves via PATCH) |
| `POST /api/content/voice/check` `{text}` | deterministic `voice_rules.check` → `{findings:[{rule, message, excerpt?}], ok}` |
| `GET/POST /api/content/operator-tokens`, `DELETE /{id}` | admin; POST returns the plaintext token once |

### Inspiration (`api/content_inspiration.py`)
`GET/POST /api/content/creators`, `PATCH/DELETE /api/content/creators/{id}`;
`GET /api/content/outliers?platform=&creatorId=`, `POST /api/content/outliers` (single or `{posts:[...]}` bulk),
`PATCH/DELETE /api/content/outliers/{id}`.

### Stage 0 — signals and ideas (`api/content_ideas.py`)
| Method & path | Notes |
|---|---|
| `GET /api/content/signals?week=` / `POST` (single or `{signals:[...]}`) / `DELETE /{id}` | |
| `GET /api/content/ideas?week=&status=` | |
| `POST /api/content/ideas/generate` `{week?}` | AI: idea slate from this week's signals + recent outliers + creators + last week's post metrics → creates 3–5 `proposed` ideas (replaces existing `proposed` ideas for the week). Returns `ContentIdea[]` |
| `POST /api/content/ideas` / `PATCH /{id}` / `DELETE /{id}` | manual ideas / edits |
| `POST /api/content/ideas/{id}/pick` | sets `picked`, others for the week → `backlog`; creates/updates `content_week` (`status: create`, `picked_idea_id`); creates an empty `content_piece` (`status: packaging`). Returns `{idea, piece, week}` |

### Stage 1 — creation (`api/content_pieces.py`)
| Method & path | Notes |
|---|---|
| `GET /api/content/pieces?week=` / `GET /{id}` / `PATCH /{id}` | |
| `POST /api/content/pieces/{id}/package` | AI: titles A/B, hook, thumbnail notes, outline (one chapter = one objection). Saves + returns piece |
| `POST /api/content/pieces/{id}/script` | AI: recordable script from outline + proof; saves `script`, status `scripted` |
| `POST /api/content/pieces/{id}/transcript` `{transcript}` | stores raw transcript; AI: cleans it, extracts `chapters` and `argument`; status `transcribed` |

### Stage 2 — repurpose (`api/content_posts.py`)
| Method & path | Notes |
|---|---|
| `POST /api/content/pieces/{id}/repurpose` `{types?: string[]}` | AI: harvests the transcript/argument into posts (newsletter, lesson, opinion, proof, chapter, graphic brief, x_article, micro, resource) each with pillar, platform, source_ref, suggested publish_date within the week; creates `content_post` rows with status `drafting` and `voice_findings`. Returns `ContentPost[]` |
| `GET /api/content/posts?week=&status=&platform=&pillar=&pieceId=` | ordered by publish_date, sort_order |
| `POST /api/content/posts` / `PATCH /{id}` / `DELETE /{id}` | PATCH re-runs `voice_rules.check` on body changes and stores findings |
| `POST /api/content/posts/{id}/rewrite` `{instructions?}` | AI: linkedin-copywriter + hook-writer rewrite in voice; returns updated post |
| `POST /api/content/posts/{id}/status` `{status}` | board moves; `ready` requires zero blocking voice findings; `scheduled` requires `publishDate`; `published` accepts `{publishedUrl}` |
| `POST /api/content/posts/{id}/approve` | sets approved_by/at, status `ready` |

### Stage 3 — ship (`api/content_posts.py`)
| Method & path | Notes |
|---|---|
| `GET /api/content/board?week=` | `{columns: {idea:[], drafting:[], ready:[], scheduled:[], published:[]}}` |
| `GET /api/content/planner?week=` | posts grouped by day with pillar/platform tags + the week row |
| `GET /api/content/weeks` / `GET /api/content/weeks/{week}` / `PATCH /api/content/weeks/{week}` | week state, close notes |
| `GET /api/content/export/notion?week=` | JSON matching `docs/notion-content-template.md` (databases → rows) for the Notion sync |
| `GET /api/content/export/csv?database=posts|creators|outliers|ideas|pieces&week=` | CSV attachments |

### Stage 4 — convert (`api/content_convert.py`)
| Method & path | Notes |
|---|---|
| `GET /api/content/engagers?fit=&dm=&postId=&action=` | |
| `POST /api/content/engagers/ingest` `{postUrl, postId?, engagers:[{name, headline?, company?, linkedinUrl, action, commentText?, connectionDegree?}]}` | JWT **or** operator token. Upserts by `linkedin_url`; matches `keyword_resources` against comment text → sets `keyword_matched`, `resource_status: requested`; logs `collect_engagers`. Returns `{added, updated, keywordMatches}` |
| `PATCH /api/content/engagers/{id}` | notes, connection_degree, dm_status overrides |
| `POST /api/content/engagers/qualify` `{ids?: string[]}` (default: all `unscored`) | AI qualification per engager against `profile.icp` → stores qualification + fit_status. Returns counts |
| `POST /api/content/engagers/{id}/draft` `{kind: warm_dm|resource_delivery|inbox_reply|public_reply, inboundText?}` | AI (resource_delivery uses the keyword template, no AI) → creates `content_message` `drafted`. Returns message |
| `POST /api/content/engagers/draft-all` `{kind: warm_dm}` | drafts for every `qualified` engager with `dm_status: none` (capped at 25 per call) |
| `GET /api/content/messages?status=&kind=` | |
| `PATCH /api/content/messages/{id}` `{final?, status: approved|rejected}` | approval; `approved` requires `final` non-empty and voice check passes |
| `POST /api/content/messages/{id}/sent` `{outcome: ok|failed|uncertain, threadUrl?, operator?}` | JWT or operator token; writes ledger, sets engager dm/resource status; `uncertain` → status stays `approved` but engager `dm_status: suppressed` until reviewed |
| `POST /api/content/inbox/ingest` `{threads:[{linkedinUrl, name, lastInboundText, threadUrl}]}` | operator token; upserts engagers (action `profile_view` if new), creates `inbox_reply` drafts via AI |
| `GET /api/content/safety/status` | `{limits, usedToday:{dm,connection,publicReply}, remaining, nextAllowedAt, paused, workingHoursOk}` from the ledger |
| `GET /api/content/queue` | operator token or JWT: `{collect:[{postId, postUrl, keyword?}], send:[approved messages with engager + exact text], safety}`; `send` is empty when paused/out of hours/caps reached |

### Operator token auth
Header `X-Operator-Token: <token>`; `api/content_deps.py:get_org_for_operator` resolves the org (sha256 hash
lookup, updates `last_used_at`). Endpoints marked "operator token" accept either auth.

## AI service (`services/content_ai.py`, built on `services/ai_client.py`)

- Anthropic Python SDK (`AsyncAnthropic`), model `claude-opus-5-5`, `client.messages.parse(..., output_format=PydanticModel)`,
  `max_tokens` 16000, `output_config={"effort": "high"}` for drafting jobs and `"medium"` for qualification/rewrites.
  System prompt = `[global rules] + [skill texts] + [client context]` as a single system text block with
  `cache_control: {"type": "ephemeral"}` (stable per client; user turn carries the volatile task data).
  Check `stop_reason == "refusal"` and raise `AiRefused`. Missing `ANTHROPIC_API_KEY` → `503 {"detail": "AI drafting is not configured (ANTHROPIC_API_KEY)"}`.
- `services/skill_prompts.py`: loads vendored `skills/linkedin-funnel/skills/<name>/SKILL.md` (+ references) by name,
  strips frontmatter, caches in memory. Jobs → skills:
  - idea slate: `content-waterfall` (stage 0), `content-strategy`, `youtube-title-outlier-packaging`
  - package: `youtube-title-outlier-packaging`, `linkedin-hook-writer`, `content-waterfall/references/brief-template.md`
  - script: `youtube-script`
  - transcript → chapters/argument: `longform-edit`, `repurpose-content`
  - repurpose: `repurpose-content`, `newsletter-writer`, `linkedin-copywriter`, `linkedin-hook-writer`, `x-article-writer`, `x-copywriter`, `graphics-designer`, `week-posts`
  - rewrite: `linkedin-copywriter`, `linkedin-hook-writer`, `brand-review`
  - qualify: `templates/qualification-prompt.md`, `templates/icp-rubric.md`
  - DMs / inbox: `guides/dm-conversion.md`, `linkedin-unibox-reply` (+ `references/anti-patterns.md`)
  - voice calibration: `voice-calibration`
- Global rules block (always first in the system prompt): no em dashes; no generic openers or cliché AI phrasing
  (list in `voice_rules.BANNED_PHRASES`); specifics and story-based proof only; numbers only from the proof list;
  cut anything 1,000 other brands could post; one point per piece; borrow the shape of outliers, never the words;
  LinkedIn links go in the first comment; drafts are not approvals.
- Client context block: pillars, voice_file, voice_rules, proof (cleared only), positioning, ideal_follower, offer,
  platforms, posting days, timezone.

## Operator runbooks (`Lead Gen/.claude/skills/`)

Project skills that an operator runs in Claude Code with Claude in Chrome connected (the `chrome-browser` skill).
Each starts by calling `GET /api/content/queue` and `GET /api/content/safety/status` with the operator token
(from `LEADNIUS_OPERATOR_TOKEN` env or asked once), never acts outside the queue, and stops on any anomaly.

| Skill | What it does |
|---|---|
| `linkedin-collect-engagers` | For each queued post: open the post, read reactions and comments (name, headline, profile URL, comment text), optionally the "Who viewed your profile" page; `POST /engagers/ingest`. Read-only, human pace, no clicking "connect". |
| `linkedin-send-approved` | For each item in `queue.send`: re-check safety status, open the person's profile/thread, verify 1st-degree (else skip and report), send the exact `final` text, read it back, `POST /messages/{id}/sent`, wait `minSpacingSeconds`. Never edits text, never sends twice, reports `uncertain` when unsure. |
| `linkedin-keyword-delivery` | For a post with a keyword: collect comments → ingest (keyword matches become resource requests) → the app drafts deliveries from the template → if `autoApproveResourceDelivery` they appear in `queue.send`, else wait for approval → send-approved flow. 2nd-degree: public reply "connect first" (from template) instead of a DM. |
| `linkedin-inbox-triage` | Read unanswered threads (never opts into anything), `POST /inbox/ingest`; the app drafts replies for approval. |

## Frontend

Route `/dashboard/agents/linkedin-posts` (client component shell with tabs; `?tab=` honoured):
`Overview` (this week's stage progress, counts, next actions, safety status card) · `Ideas` (Stage 0: signals list + add, inspiration DB sub-tabs creators/outliers, "Generate slate", slate cards with proof of demand, Pick) ·
`Create` (Stage 1: packaging titles/hook/outline, script editor, transcript upload → chapters + argument) ·
`Repurpose` (Stage 2: "Generate posts" with type checklist, post cards grouped by root (argument / file / transcript), inline edit, voice findings, Rewrite, Approve) ·
`Ship` (Stage 3: kanban Idea → Drafting → Ready → Scheduled → Published with drag/move + publish date; Weekly planner grid days × posts with pillar/platform tags; Notion export + CSV; Close the week) ·
`Convert` (Stage 4: engagers table with fit/dm/resource badges, Qualify, Draft DMs, approval inbox with final-text editor + voice check, keyword→resource settings, safety dashboard with today's usage, queue preview for operators) ·
`Setup` (onboarding: pillars, voice file + calibrate from samples, proof list, positioning/ideal follower/offer, ICP rubric, platforms/days/timezone, keyword resources, safety limits, Notion link, operator tokens, Clone from client).

Sidebar: "Content" becomes a collapsible group like Outbound with `LinkedIn Posts` (PenLine/Linkedin glyph); Blog & SEO and Video Script stay "Soon". Agents index: the Content section's "LinkedIn Post Agent" card becomes active and links here.
