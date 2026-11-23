# Daily leads

Goal: **30 new, verified, ICP-matched leads per workspace per day**, using free sources first and Claude in Chrome second,
with no AI-credit lead hunts.

- **Schedule:** a launchd job runs `daily_leads.py` every day at 07:00 (`~/Library/LaunchAgents/in.leadnius.daily-leads.plist`).
  - If the Mac was asleep at 07:00, the job runs when it wakes.
  - The job stops at 23:30. A lock file stops two runs from overlapping.
- **Steps:**
  1. Free pass for every workspace (`/api/signal-types/run`, `allowAi: false`). This also re-queues the post searches on
     LinkedIn, X, Reddit and review sites (`SCOUT_POSTS_REPEAT_DAYS = 1`).
  2. The Chrome scout works the workspaces in turn, one run of up to 15 tasks per workspace per round and at most 4 runs
     each. It stops for a workspace once it reaches 30 leads today or its queue is empty.
  3. If the Claude usage limit is hit, the job waits 30 minutes and tries again.
  4. At the end it writes a summary and refreshes `client-playbooks/lead-lists/*.csv`.
- **Verified:** the server (`POST /api/scout/tasks/{id}/result`) rejects a person who:
  - has no LinkedIn `/in/` URL and no X or Reddit profile URL
  - has a fit score below 65 (`SCOUT_MIN_LEAD_SCORE`)
  - is already a lead, matched by name and company or by profile URL
- **Pivot Money** (North America only): every day the scout works Reddit tasks first, then X and LinkedIn.
- **Workspaces:** `accounts.json` lists them in priority order. It holds the demo logins, so keep it at mode 600.
- **Logs:** `logs/<date>.log` (progress and summary), `logs/<date>-scout.log` (each scout report), `logs/<date>-summary.json`.

Run by hand:
- `python3 daily_leads.py`
- `python3 daily_leads.py --orgs "Pivot Money" --not-before 19:25`

Requirements:
- The Mac must be awake, with Chrome open and Claude in Chrome connected (Browser 1).
- LinkedIn and X must be signed in.
- The backend is started automatically if it's down.
