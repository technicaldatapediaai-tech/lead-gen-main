# My Strategy

Sidebar → **My Strategy** (above Sales Leads), `/dashboard/strategy`. One place per workspace to plan the month and the
week, see progress, review each period and keep a log of what needs to change. Everything here is free: no AI calls,
no paid data.

It borrows from common GTM and productivity methods:

| Idea | Where it shows up |
| --- | --- |
| OKRs: objective + measurable key results | **Focus** + **Goals** with targets and live progress |
| EOS "Rocks" / Big 3 | **Top 3 priorities** under the focus |
| 12 Week Year pace tracking | Each goal compares its value with where it should be by today: *On track / At risk / Behind / Done / Missed* |
| GTM experiment loop | **Experiments**: hypothesis → result, prompted for the result when ticked done |
| Retro: Start / Stop / Continue | **Weekly / Monthly review** with a 1–10 score and the next focus |
| Decision / learning log | **Learnings**: what we learned, the evidence, what to change; open until *Applied* |
| GTM plays | Templates: Outbound pipeline, Content-led growth, Launch / new offer, Pipeline clean-up |

## Tabs

- **This week / This month**: a period switcher (‹ ›). With no plan yet you start one by splitting the month plan
  into the week (goal targets ÷ weeks in the month), from a GTM play, by copying the last period, or blank. Optionally
  bring over the unfinished tasks of the last period.
  The plan page shows: focus + top 3, overall progress ring, "Worth a look" hints, goals, tasks & experiments,
  (month) the weeks of the month, the review, and the learnings logged in this period.
- **Learnings**: filter by To change / Applied / Dropped and by area (ICP, messaging, channel, offer, content, process).
- **History**: past weeks or months with score, goals hit, tasks done and next focus; a row opens that period.

## Live goal metrics

Counted for the plan's period from the app's own tables (`services/strategy.py`, `METRICS`):

| Metric | Counts |
| --- | --- |
| `leads_added` | `agent_lead.created_at` |
| `signals_found` | `signal.detected_at` |
| `emails_sent` | `email_message` direction out |
| `linkedin_sent` | `outbound_action` done, kind connect / message |
| `whatsapp_sent` | `whatsapp_message` out, not failed |
| `social_actions` | `social_action` done (X / Reddit / LinkedIn comments + DMs) |
| `messages_sent` | the four above together |
| `replies`, `positive_replies` | `reply.received_at` (positive = sentiment) |
| `posts_published` | `channel_post` posted |
| `manual` | typed in on the goal (meetings, deals, revenue, followers…) |

Periods are UTC: a month starts on the 1st, a week on Monday.

## Closing a period

**Close week / month** in the review saves it and marks the plan closed. Two options (on by default):

- every line under *Start doing* / *Stop doing* becomes a learning;
- unfinished tasks are copied to the next period. If that period has no plan yet, one is created with the review's
  next focus and the same goals.

Closing happens once; saving the review again does not add learnings or tasks twice. **Reopen** sets it active again.

## Code

- Backend: `models/strategy.py` (4 tables), `alembic/versions/0016_my_strategy.py`, `services/strategy.py`,
  `api/strategy.py` (`/api/strategy/*`), tests `tests/test_strategy.py`.
- Frontend: `app/dashboard/strategy/page.tsx`, `components/strategy/*`, `lib/agent/strategy.ts`.
