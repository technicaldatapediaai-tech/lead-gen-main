# LinkedIn outbound: Claude in Chrome, human presses send

Status: built 2026-10-23. Extends the LinkedIn Posts operator system (`docs/linkedin-posts-agent.md`) to outbound
campaigns. The app never touches linkedin.com itself.

## Why this shape

LinkedIn's official API does not allow connection requests or DMs to non-connections, and hidden browser automation
gets accounts restricted. So the LinkedIn Agent **plans and drafts**, the client **approves in the app**, and an operator
runs a runbook in **Claude in Chrome**, signed in to the client's own account, at human pace, with every outcome
recorded. Same operator tokens, safety caps, working hours and protocol as the Posts agent.

## Flow

1. **Campaign** (channel `linkedin`) with steps of type `visit`, `connect`, `message` and delays, as today.
2. **Enrol leads.** Each enrolment becomes an `outbound_action` for its current step when the step is due:
   `visit` → profile visit; `connect` → connection request with the drafted note (≤ 300 chars);
   `message` → DM (only once connected). Drafts come from `services/personalize.py` (or a template step).
3. **Approve.** Actions start as `drafted`. On the LinkedIn Agent page the client reads each draft, edits if needed,
   and approves (or approves all). Only `approved` actions reach the queue.
4. **Queue.** `GET /api/content/queue` gains `outbound: [...]`: approved actions in due order, within the remaining
   caps (`connect` counts against a new `dailyConnectionLimit`; `message` against `dailyDmLimit`). Visits don't count.
5. **Runbook `linkedin-outbound`** (`.claude/skills/linkedin-outbound/SKILL.md`): for each item opens the profile,
   verifies the name, performs exactly that action, reads the result back, then
   `leadnius_api.py outbound-done <actionId> --outcome ok|failed|uncertain|not_connected|already_connected`.
6. **Outcome** advances the enrolment: ok → next step scheduled after its delay; `not_connected` on a `message`
   step → wait (re-queued daily until the request is accepted, up to 14 days, then `stopped`); `uncertain` → the lead
   is suppressed until a human reviews (never retried automatically); `failed` → recorded, step retried next day once.
7. **Replies** arrive through the existing inbox runbook (`linkedin-inbox-triage` → `/api/content/inbox/ingest`) and
   also through `POST /api/webhooks/inbound`; a reply stops the sequence via `reply_ingest`.

## Data

New table `outbound_action`: `id, org_id, campaign_id, lead_id, enrolment step, kind (visit|connect|message), text,
status (drafted|approved|queued|done|failed|uncertain|skipped), due_at, approved_at, done_at, outcome, notes,
thread_url, operator`. `campaign_lead.next_due_at` is reused for scheduling.

The existing safety settings already carry `dailyConnectionLimit` (default 10/day; LinkedIn's own cap is ~100/week)
and count connections separately from DMs. The ledger (`ContentActionLog`) records `outbound_connect`, `outbound_dm`, `outbound_visit`.

## API (additions, operator token or JWT)

| Method | Path | Body → Response |
| --- | --- | --- |
| GET | `/api/outbound/actions?campaignId=&status=` | `OutboundActionOut[]` |
| POST | `/api/outbound/actions/prepare` | `{ campaignId }` → `{ created }` (draft actions for due enrolments; also runs hourly) |
| PATCH | `/api/outbound/actions/{id}` | `{ text?, status: 'approved' \| 'drafted' \| 'skipped' }` |
| POST | `/api/outbound/actions/approve-all` | `{ campaignId }` → `{ approved }` |
| POST | `/api/outbound/actions/{id}/done` | `{ outcome, notes?, threadUrl?, operator? }` → `OutboundActionOut` |
| GET | `/api/content/queue` | adds `outbound: QueueOutboundItem[]` |

```ts
type OutboundActionOut = { id, campaignId, campaignName, leadId, leadName, leadTitle, company, linkedinUrl, step,
  kind: 'visit'|'connect'|'message', text, status, dueAt, approvedAt, doneAt, outcome, notes, threadUrl };
type QueueOutboundItem = { actionId, kind, leadName, linkedinUrl, text, campaignName, step };
```

## Runbook caps

Per run: at most `min(remaining.connect, 10)` connection requests and `min(remaining.dm, 10)` DMs; visits unlimited
but paced. Spacing `minSpacingSeconds` between any two actions. Stop on any anomaly (protocol §4).
