# Lead capture: LinkedIn, X, Reddit, Slack

Lead Agent → **Capture channels**. People who post about the workspace's topics, or comment on, reply to, like or
repost those posts, are checked against the ICP. Fits become `AgentLead` rows tagged with the channel they came from.

## Where it runs

| Channel | How it is read | When |
|---|---|---|
| Slack | Slack Web API with the workspace's own token (bot `xoxb-` or user `xoxp-`), channels it picks | "Capture now", and every 6 h in the background loop |
| Reddit | Official Reddit API (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, app-only OAuth, free) | same as Slack |
| Reddit without keys, X, LinkedIn | A `scout_task` of kind `capture_posts`, worked by the Claude in Chrome runbook `.claude/skills/social-lead-capture` | only when the operator asks |
| LinkedIn engagers on the workspace's own posts | `POST /api/content/engagers/ingest` (LinkedIn Posts agent) also runs lead capture | whenever engagers are uploaded |

The app never logs in to X, LinkedIn or Reddit. Slack scopes: `channels:history`, `channels:read`, `groups:history`,
`groups:read`, `users:read`, `users:read.email`. The token is stored Fernet-encrypted in `organization.settings.slackCapture`.

## Config (`organization.settings.leadCapture`)

```json
{"channels": {"linkedin": {"enabled": true, "keywords": [], "postUrls": []},
              "x": {"enabled": true, "keywords": [], "accounts": []},
              "reddit": {"enabled": true, "keywords": [], "subreddits": []},
              "slack": {"enabled": false, "keywords": [], "channels": [{"id": "C…", "name": "general"}]}},
 "capture": {"posts": true, "comments": true, "likes": true}}
```

**Fill from GTM playbook** (rules, no AI): keywords from enabled signal types (intent and hot tiers first), persona pains
and the ICP pains; `r/…` and `@…` mentions in the playbook and signal sources; the workspace's published LinkedIn post URLs.
Last runs per channel: `organization.settings.leadCaptureRuns`.

## Who becomes a lead (`services/lead_capture.py`)

Fit score = 30 + title (30 for a persona / ICP title match, 10 for a senior title only) + 8 per keyword hit in what they
wrote or engaged with (max 3) + 8 for an ICP industry + action (post 12, comment / reply 10, repost 6, like / reaction 4).
Saved when the title matches or the score reaches `SCOUT_MIN_LEAD_SCORE` (65). Rejected: vendors ("we help", "book a
call"…), the workspace's own company, and duplicates (lead_store). People with no job title but their own words
(most Reddit and X accounts) go to the local Ollama model (`local_llm.judge`); without it they are not saved.

Lead fields: `profile.channel`, `captureAction`, `postUrl`, `postExcerpt`, `community`, `commentText`, `foundBy`;
`signal` reads like "Commented on a post (LinkedIn)". `GET /api/leads` returns `channel` (also `signal` / `manual` for
older leads) and `/api/leads/stats` returns `byChannel`.

Posts are stored in `social_post` (unique per workspace by URL) with `relevance` (25 per matched keyword) so the X,
Reddit and LinkedIn agents can comment on them (docs/social-agents.md).

## API

- `GET/PUT /api/capture/config`, `POST /api/capture/config/from-playbook` (admin)
- `POST /api/capture/run {platforms?}` (admin): API channels now, Chrome tasks for the rest (one open task per platform)
- `POST /api/capture/ingest {platform, taskId?, posts[], people[], note}` (JWT or operator token); closes the task once
- `POST /api/capture/slack/connect {token}`, `DELETE /api/capture/slack`, `GET /api/capture/slack/channels`
- `GET /api/capture/posts?platform=&status=&minRelevance=`, `PATCH /api/capture/posts/{id} {status: new|ignored}`
- Operator CLI: `leadnius_api.py capture-tasks | capture-ingest`. `GET /api/scout/tasks` hides `capture_posts` unless `kind=capture_posts`.

Tests: `tests/test_lead_capture.py`.
