# Signal routing: free first, Chrome second, AI credits last

Code: `services/signal_router.py`, `services/free_sources.py`, `api/scout.py`, model `ScoutTask` (migration 0007),
runbook `.claude/skills/linkedin-signal-scout`. Signal page: **Run signals (free first)**; **AI hunt (credits)** is the
last resort.

## The order

| Step | What runs | Cost | Covers |
| --- | --- | --- | --- |
| 1. Free | Python: Google News RSS (signal keywords), Remotive, RemoteOK, Arbeitnow, HN "Who is hiring", built-in news feeds, FPDS | $0 to fetch | sources `news`, `press_releases`, `company_blogs`, `funding_databases`, `job_posts`, `fpds`; built-ins `hiring`, `funding`, `news` |
| 1b. Quality check | Rules plus the free local model (Ollama `qwen2.5:3b`, `services/local_llm.py`). Haiku only if the user approves | $0 | keeps only items that really show the signal and fit the ICP; local-checked company signals score at most 60 |
| 1c. Free people | `services/free_people.py`: authors of community posts (Stack Exchange, Hacker News, Reddit official API when `REDDIT_CLIENT_ID`/`SECRET` are set) who are reachable and pass rules plus the local model; decision makers named, with a LinkedIn link, on the signal company's own website (closes find_people tasks) | $0 | sources `reddit`, `forums`; find_people |
| 2. Chrome | Scout queue worked by Claude in Chrome (`linkedin-signal-scout`), read-only | the user's Claude plan, no API credits | one `search_posts` task per signal and platform: `linkedin` → LinkedIn, `x` → X, `reddit` and `forums` → Reddit, `product_reviews` → review sites; decision makers for signal companies (`find_people`) |
| 3. AI credits | One lead-hunt web-search call for up to 3 signals (`services/lead_hunt.py`) | about $0.10-0.30 per call | only signals free sources missed and Chrome can't cover, or whose scout task sat open `CHROME_STALE_DAYS` |

Quality rules: free items must carry a keyword in the job title or headline and name a real-looking company; the Haiku
check drops the rest and dedupes companies ("JLL" = "JLL Business Services"). Without the check (no key, budget spent,
`FREE_AI_QUALIFY=false`) matches are saved as **unverified** with score at most 45, and never get `find_people` tasks.
AI hunts keep only results whose URL the search returned.

## Claude API needs approval

`AI_REQUIRE_APPROVAL` (default true). `ai_client.generate` refuses (`AiNotApproved`, a kind of `AiNotConfigured`, so
callers fall back to templates and rules) unless the request came from the app in the browser (the user clicked) or
carries `X-AI-Approved: yes`. Background loops, the daily lead job (`ops/daily-leads`), operator tokens and scripts never
reach the API. `FEED_AI_QUALIFY` and `FREE_AI_QUALIFY` are off by default.

Every person from any source is saved through `services/lead_store.save_people`: LinkedIn `/in/` URL, X or Reddit
profile URL, or a published email; score at least `SCOUT_MIN_LEAD_SCORE` (65); never a duplicate.

## Budget

`AI_MONTHLY_BUDGET_USD` (default 2.0) per workspace per calendar month, from `ai_usage`. When spent:
`/api/signal-types/hunt` and custom `/{key}/scan` return 402; the free run skips the Haiku check (results unverified);
the AI fallback in `/run` is skipped. Other settings: `FEED_AI_QUALIFY`, `FREE_AI_QUALIFY` (true), `SIGNAL_STRATEGY_ON_UPLOAD`
(false: the Opus strategy runs from the "From playbook" button only), `SCOUT_FIND_PEOPLE_PER_RUN` (25).

## Schedule

The daily feed loop (`main.py`) runs built-in feeds, FPDS, then `signal_router.run_all_free` for every workspace:
custom signals not scanned in the last `SIGNAL_FEED_SCAN_INTERVAL_S`, then the Chrome queue. It never uses the AI
fallback (only the cheap Haiku check, within budget).

## API

```
GET  /api/signal-types/plan                 [{key, name, enabled, free, chrome, ai, label}]
POST /api/signal-types/run   {allowAi?}     {freeFound, freeBySignal, chromeQueued{search_posts, find_people}, aiUsed, aiNote, aiFound, aiLeads}   (admin)
GET  /api/scout/tasks?status_filter=open&limit=20&platform=reddit       JWT or X-Operator-Token (platform optional)
POST /api/scout/tasks/{id}/result {status: done|skipped, signals[], people[], note}   → {signalsAdded, leadsAdded, status}; 409 if already closed
```

People found on X or Reddit are posted with `platform` and `profileUrl` (kept on the lead's profile; the Leads page
links to them). Reddit people are saved as `u/<username>` and company "Individual" when they name no employer; the
scout never tries to unmask an anonymous account. Reddit's free JSON API refuses scripts (403), so Reddit is a Chrome
platform, not a free source; an official Reddit API app (client id + secret) would make it free.

Operator CLI: `leadnius_api.py scout-tasks [--platform x]`, `leadnius_api.py scout-result <id> --file … | --skip`.
