# Social agents: X Agent, Reddit Agent, LinkedIn post comments

Outbound → **X Agent** (`/dashboard/agents/x`) and **Reddit Agent** (`/dashboard/agents/reddit`): comments on relevant
posts and direct messages to captured leads. LinkedIn Agent → **Comment on posts** tab: comments only (LinkedIn DMs and
connection requests stay in LinkedIn campaigns, docs/linkedin-outbound.md).

## Flow

1. Lead capture stores relevant posts (`social_post`) and leads with a profile on each platform (docs/lead-capture.md).
2. The person picks posts → **Draft comments**, or leads → **Draft DMs**. Default draft is a free starter text
   (`source: starter`) that must be edited before it can be approved. **Write with AI** (only shown when a Claude key is
   set) uses the Claude API for that click only, per the user's rule that every API use is approved.
3. Every message is approved one by one (or "Approve all ready", which skips starters and drafts with issues).
   Approval checks: house tone and voice rules (no em dashes, no praise, one question…), length per platform
   (X reply 280, Reddit comment 2000…), no links, no placeholders, and do-not-contact for DMs.
4. Sending: the operator runs `.claude/skills/social-outbound` (Claude in Chrome, the client's signed-in account), or a
   person sends by hand with **Open → Copy text → Mark as sent**. `POST /api/social/actions/{id}/done` records the
   outcome once (ok / failed / uncertain); ok comments mark the post `commented`; touches are kept on the lead
   (`profile.socialTouches`).

## Safety (per platform, `organization.settings.socialAgents`)

| | comments / day | DMs / day | minutes apart |
|---|---|---|---|
| X | 15 | 10 | 10 |
| Reddit | 8 | 5 | 15 |
| LinkedIn | 15 | n/a | 5 |

Caps max 50 comments / 40 DMs. Pause switch. `GET /api/social/{platform}/queue` hands the operator approved items
within today's remaining allowance; `nextAllowedAt` enforces spacing. Platform rules shown in the app: X forbids
automated replies and DMs from keyword searches (so every message is human-approved and sent one at a time); Reddit
subreddits often ban self-promotion and DMs, so comments must help on their own.

## API

- `GET/PUT /api/social/{platform}/settings` → `{settings, safety, aiAvailable}`
- `GET /api/social/{platform}/actions?status=&kind=`, `GET /api/social/{platform}/leads` (x, reddit)
- `POST /api/social/{platform}/comments/draft {postIds, useAi}`, `POST /api/social/{platform}/dms/draft {leadIds, useAi}`
- `PATCH /api/social/actions/{id} {text?, status?: approved|drafted|skipped}`, `POST /api/social/{platform}/actions/approve-all {kind?}`
- `GET /api/social/{platform}/queue`, `POST /api/social/actions/{id}/done {outcome, resultUrl, notes, operator}` (JWT or operator token)
- Operator CLI: `leadnius_api.py social-queue | social-safety | social-done`

Table `social_action` (migration 0008). Tests: `tests/test_lead_capture.py`.
