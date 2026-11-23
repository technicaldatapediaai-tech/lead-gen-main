# Reddit through your own Reddit app (posts, comments, DMs)

Built 2026-11-19. Each workspace can connect its own Reddit "script" app. Leadnius then sends the Reddit Agent's
approved comments and DMs, and publishes scheduled Content Studio posts, on Reddit's official API. No browser,
Chrome extension or operator is needed. (The Chrome extension is blocked on reddit.com.)

Based on [Satvik-jain/reddit-automation](https://github.com/Satvik-jain/reddit-automation), which uses PRAW with a script
app. That repo has no license, so no code was copied. The same Reddit endpoints are called with httpx, async like the
other senders. Two parts of that repo were deliberately left out:
- its daily unattended AI post on a random topic;
- its instant AI replies.

Both post without review, which breaks Leadnius' approve-first rule and gets Reddit accounts banned.

## Connecting (Account → Connected IDs → Reddit → Connect → Your Reddit app)

1. Signed in as the Reddit account to use, open reddit.com/prefs/apps, then **create another app**.
2. Choose type **script** and set the redirect URI to `http://localhost:8080`.
3. Enter in Leadnius:
   - the client ID (the code under the app name);
   - the secret;
   - the Reddit username and password.

Leadnius checks the login with Reddit's password grant and reads `/api/v1/me` before saving.

**How it's stored:** as a `PublishAccount` (`platform` "reddit", `meta.via` "reddit_app").
- `token_enc`: the current access token.
- `refresh_enc`: the encrypted `{secret, password}`, used to log in again when the token expires.

**Limits:**
- Accounts with two-factor login can't use a script app; Reddit refuses the password grant.
- Connecting sets the workspace's Reddit sending method to `api`.
- Disconnecting the last Reddit app sets it back to `chrome`.

## What it does

| What | When it goes out | Endpoint |
|---|---|---|
| Comment on a post / reply to a comment | Reddit Agent item **approved** by a person; one per pass, within the agent's daily caps and spacing | `POST oauth.reddit.com/api/comment` (`thing_id` t3_ post / t1_ comment, taken from the URL) |
| Direct message | Reddit Agent DM **approved**; same caps | `POST /api/compose` (`to`, `subject`, `text`) |
| Post (self / link) | Content Studio card **scheduled** in Channel Posting | `POST /api/submit` (existing publisher, using this app's token) |

The sender is `reddit_api.run_loop`. It runs every `REDDIT_SENDER_INTERVAL_S` (120 s), and only for workspaces whose
Reddit method is `api`.

**When Reddit says no:**
- **Rate limit** (`RATELIMIT`, 429) or a server error: the item goes back to the queue.
- **Timeout:** recorded as "uncertain", because it may have posted. It's never retried automatically.
- **403, locked or deleted threads:** recorded as "failed", with Reddit's reason.

## Test mode

With `REDDIT_DRY_RUN` on, comments and DMs are logged instead of sent. The default is `DEV_MODE`, so it's on locally.
- Test sends are marked "(dry run)" in the item's notes.
- Account → Connected IDs lists Reddit among the channels in test mode.
- Content Studio posts follow `CONTENT_POST_DRY_RUN`, as before.

## Code and tests

- **Code:**
  - `services/reddit_api.py`: login, token, comment / message calls and the sender.
  - `api/connections.py`: `POST /api/connections/reddit-app` and the Reddit row.
  - `services/publishers.py`: `_token` uses the app.
  - `services/delivery.py`: Reddit methods `api` and `chrome`.
- **Frontend:**
  - `components/settings/ConnectedAccounts.tsx` (`RedditAppModal`);
  - `components/agent/SendingMethod.tsx`;
  - `components/agent/SocialAgent.tsx`: automatic-send wording when the app is used.
- **Tests:** `tests/test_reddit_app.py`, with Reddit faked. It covers connect / list / disconnect, logging in again, that
  only approved items are sent, test mode, and the rate-limit retry.
