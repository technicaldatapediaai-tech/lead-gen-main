"""One Claude in Chrome scout run (linkedin-signal-scout runbook) for one workspace.

Usage: run_scout.py <org> [max_tasks] [goal] [platform]
With a platform (linkedin, x, reddit), the run works only that platform's post searches (several scouts can then run in
parallel, one per platform); only the linkedin scout also works find_people tasks.
The operator token is created for this run, passed only through the child's environment, and revoked afterwards.
Prints the scout's report; exit code 3 when the Claude usage limit is hit.
"""
import os
import subprocess
import sys

from leadnius import HERE, ROOT, call, org_token

org = sys.argv[1]
max_tasks = int(sys.argv[2]) if len(sys.argv) > 2 else 15
goal = int(sys.argv[3]) if len(sys.argv) > 3 else 30
platform = sys.argv[4] if len(sys.argv) > 4 else ""
ONLY = ({"linkedin": "This scout works LinkedIn only: list tasks with `scout-tasks --platform linkedin --limit 40`. Work the find_people "
                     "tasks FIRST (highest score first; they give a verified lead in 1-2 page loads), then the linkedin search_posts "
                     "tasks; leave x, reddit and reviews tasks for the other scouts.",
         "x": "This scout works X only: list tasks with `scout-tasks --platform x --limit 15` and work only search_posts tasks whose "
              "payload.platform is x; never work find_people or other platforms' tasks (other scouts run them in parallel).",
         "web": "This scout works directory tasks only: list tasks with `scout-tasks --platform web --limit 15` and work only "
                "search_posts tasks whose payload.platform is web, as the runbook's directory section says; never work LinkedIn, "
                "X, Reddit or find_people tasks (another scout runs those in parallel).",
         "reddit": "This scout works Reddit only: list tasks with `scout-tasks --platform reddit --limit 15` and work only search_posts "
                   "tasks whose payload.platform is reddit; never work find_people or other platforms' tasks (other scouts run them in parallel)."}
        .get(platform, ""))
FILES = os.path.join(HERE, "scout-files")

NOTES = {
    "Pivot Money": "This workspace is B2C, North America only: the lead is an individual NRI living in the US or Canada who is moving "
                   "back to India, or who moved back from the US or Canada in the last 24 months. Skip anyone in other countries. "
                   "Any profession qualifies; put their situation in title (e.g. 'Engineer in Seattle, moving to Pune in March 2027'). "
                   "Company 'Individual' is fine when they name no employer. Skip advisers, CAs, banks and other vendors posting about "
                   "the topic (except for the two partner signals). Every day, work Reddit first: run `scout-tasks --platform reddit` "
                   "and finish those tasks before the others.",
}

prompt = f"""You are running the linkedin-signal-scout runbook for the Leadnius workspace "{org}".

First connect to the Chrome browser named "Browser 1" (macOS, id c83523e1-aff1-4343-9afc-487a0a0e8b7a) with the browser-selection
tool; never use "Browser 2". Then read .claude/skills/linkedin-signal-scout/SKILL.md and
.claude/skills/linkedin-ops/references/safety-protocol.md and follow them exactly. LEADNIUS_OPERATOR_TOKEN and LEADNIUS_API_URL are already
set in your environment (never print the token). Use the CLI: python3 .claude/skills/linkedin-ops/scripts/leadnius_api.py ...

The operator has already approved this run and confirmed the LinkedIn account signed in to Chrome is the right one, so skip asking
them; but if LinkedIn is not signed in, shows a CAPTCHA, security check or any anomaly, stop immediately and report it.
You may open one new tab (create a tab group if needed) and must close it at the end.

Each search_posts task has payload.platform (linkedin, x, reddit or reviews): search only that platform, as the runbook's
section for it says. If X or Reddit is not signed in or shows a login wall, skip those tasks with a note and carry on.
{NOTES.get(org, "")}
{ONLY}
Other scouts may be using the same Chrome at the same time in their own tabs: only ever use the tab you opened.

BULK MODE (speed matters): for each search_posts task, read the full first page of results (and one scroll) and submit EVERY
person on it who qualifies, up to 10 per task, not just the first one or two. For find_people, submit up to 2 per company.

Today's goal for this workspace: about {goal} more VERIFIED leads. Verified means: a real person you saw on the page, who holds the
role now and fits the ICP (score 65 or more), with a LinkedIn profile URL (https://www.linkedin.com/in/<slug>/) or, for X and Reddit,
their profile URL. Never pad the count: the server rejects people without a profile URL, below 65, or already in the workspace,
and lists them in `rejected`. Prefer people we don't have yet; search only recent posts (past week where the platform allows).

Caps for this run: at most {max_tasks} tasks and {max_tasks * 4} page loads. Work search_posts tasks first, then find_people. Read-only:
never click Connect, Follow, Like, Comment, Message or any action menu. Skip a task (scout-result <id> --skip --notes "...") when
nothing qualifies. Write scratch JSON files only under {FILES}/.

Finish with a short report: tasks done / skipped, leads added and rejected, signals added (from the CLI responses), and any anomalies."""

os.makedirs(FILES, exist_ok=True)
jwt = org_token(org)
tok = call("POST", "/content/operator-tokens", jwt, body={"name": f"daily-scout {org}"})
env = {**os.environ, "LEADNIUS_API_URL": "http://localhost:8000", "LEADNIUS_OPERATOR_TOKEN": tok["token"],
       "LEADNIUS_OPERATOR_NAME": "claude-in-chrome-scout"}
allowed = ["mcp__claude-in-chrome__*", "Bash(python3 .claude/skills/linkedin-ops/scripts/leadnius_api.py:*)", "Bash(sleep:*)",
           "Read", f"Edit(/{FILES}/**)", f"Bash(rm {FILES}/:*)"]
code = 0
try:
    r = subprocess.run(["claude", "-p", prompt, "--chrome", "--add-dir", FILES, "--allowedTools", *allowed],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=5400)
    out = r.stdout[-6000:]
    print(out)
    if r.returncode:
        print("STDERR:", r.stderr[-1500:])
    if any(s in (out + r.stderr).lower() for s in ("session limit", "usage limit", "rate limit")):
        code = 3
except subprocess.TimeoutExpired:
    print("scout run timed out")
finally:
    call("DELETE", f"/content/operator-tokens/{tok['id']}", jwt)  # revoke the run's token
    print("operator token revoked")
sys.exit(code)
