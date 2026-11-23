# Notion content template (per client)

One Notion page per client, duplicated from a master template. It is the client's view of the LinkedIn Posts
agent: everything the app produces lands here for approval, and the app's `GET /api/content/export/notion`
emits rows in exactly this shape so the sync (via the Notion connector) is a 1:1 mapping.

Design notes: this extends the `linkedin-funnel` schema (Content Board / Pillars & Topics / Hooks / Creator
Inspo DB) with the states and links the client asked for: Ready and Scheduled statuses, a Source piece relation,
outlier posts in the inspiration database, and a weekly planner. Pillar options are set per client during
onboarding and must match the app's `content_profile.pillars[].name` exactly.

## Page layout

```
<Client> · Content HQ
├── 📌 This week            (linked view: Weekly planner filtered to current week)
├── 💡 Inspiration
│   ├── Creators            (database)
│   └── Outlier posts       (database, relation → Creators)
├── 🧠 Idea slate           (database)
├── 🎬 Pieces               (database: the weekly long-form piece)
├── 🗂 Content board        (database, relation → Pieces, → Idea slate)
├── 📅 Weekly planner       (views of Content board + Weeks database)
└── ⚙️ Setup                (page: pillars, voice rules, proof list, keyword resources; read-only mirror of the app)
```

## Databases

### 1. Creators (Inspiration)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | |
| Platform | Select | LinkedIn, X, YouTube |
| Handle | Text | |
| URL | URL | |
| Niche | Text | |
| What to learn | Text | technique only, never their stories or numbers |
| What not to copy | Text | |
| Active | Checkbox | monitored weekly |
| Outlier posts | Relation ← Outlier posts | |
| Added | Date | |

Views: **Active creators** (table, filter Active), **By platform** (board grouped by Platform).

### 2. Outlier posts (Inspiration)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | first line of the post or a label |
| Creator | Relation → Creators | |
| Platform | Select | LinkedIn, X |
| URL | URL | |
| Posted | Date | |
| Hook | Text | the opening line, kept for shape only |
| Format | Select | Text, Carousel, Video, Graphic, Thread, Article |
| Likes / Comments / Reposts / Views | Number ×4 | |
| Outlier ratio | Number | post engagement ÷ creator median |
| Why it worked | Text | |
| Tags | Multi-select | free |
| Used in idea | Relation → Idea slate | |
| Saved | Date | |

Page body: the full post text in a code block.
Views: **Newest** (table, sort Saved desc), **Top outliers** (gallery, sort Outlier ratio desc), **By creator** (board).

### 3. Idea slate (Stage 0)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | the idea in one line |
| Week | Select or Text | ISO week, e.g. `2026-W43` |
| Status | Select | Proposed, Picked, Backlog, Rejected |
| Pillar | Select | per-client pillar names |
| Funnel job | Select | Reach, Belief, Signup |
| Problem | Text | one problem |
| Claim | Text | one claim |
| Example | Text | one example |
| Proof of demand | Text | signals / outliers that justify it |
| Outliers | Relation ← Outlier posts | |
| Rank | Number | |
| AI generated | Checkbox | |
| Piece | Relation ← Pieces | |

Views: **This week's slate** (gallery, filter Week = current), **Backlog** (table, Status = Backlog).

### 4. Pieces (Stage 1, one per week)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | chosen title |
| Week | Text | |
| Idea | Relation → Idea slate | |
| Status | Select | Packaging, Scripted, Recorded, Edited, Transcribed, Done |
| Title A / Title B | Text ×2 | packaging first |
| Hook | Text | |
| Thumbnail notes | Text | |
| Release date | Date | |
| File | URL or Files | the edited video |
| Posts | Relation ← Content board | the waterfall |

Page body: Outline (table: Chapter · On screen · Claim), Script, Transcript, Argument (newsletter-ready) as toggles.

### 5. Content board (Stages 2–3)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | hook / first line |
| Status | Select | **Idea, Drafting, Ready, Scheduled, Published** |
| Pillar | Select | per-client pillar names (exactly one) |
| Platform | Select | LinkedIn, X, Newsletter, YouTube |
| Type | Select | Newsletter, Video, Lesson, Opinion, Proof, Chapter, Graphic, X article, Micro, Resource, Idea |
| Source piece | Relation → Pieces | which long-form piece it came from |
| Source ref | Text | chapter / transcript pointer |
| Publish date | Date | |
| Week | Formula | `formatDate(prop("Publish date"), "YYYY-[W]WW")` |
| Approved | Checkbox | |
| Approved by | Person | |
| Graphic | Files | |
| Published URL | URL | |
| Likes / Comments / Views | Number ×3 | filled after publishing |
| Voice check | Select | Pass, Warnings, Blocked (from the app) |
| App id | Text | hidden; the app's post UUID for sync |

Page body: the paste-ready post text in a code block; for graphics, the graphic brief underneath.
Views: **Board** (board grouped by Status, the client's approval view), **Calendar** (by Publish date),
**All posts** (table), **Needs approval** (table, Status = Ready and Approved unchecked).

### 6. Weeks (planner rows)

| Property | Type | Options / notes |
|---|---|---|
| Name | Title | `2026-W43` |
| Status | Select | Ideas, Create, Repurpose, Ship, Convert, Closed |
| Picked idea | Relation → Idea slate | |
| Piece | Relation → Pieces | |
| Posts | Relation → Content board | |
| Winners | Text | close notes |
| Questions collected | Text | |
| Next idea | Text | |

## Weekly planner (views, no extra database)

- **Planner** = Content board as a **board grouped by Publish date → week** (Notion: group by the Week formula),
  with Pillar and Platform shown as tags on each card. Sub-group by Platform.
- **This week** = the same view filtered to the current week, embedded at the top of the client page.
- The app exports one row per post with `pillar`, `platform`, `sourcePiece`, `publishDate`, which is the
  minimum every post must carry.

## Sync contract (`GET /api/content/export/notion?week=`)

```json
{
  "client": {"name": "...", "pillars": ["..."]},
  "creators": [{"appId", "name", "platform", "handle", "url", "niche", "whatToLearn", "whatNotToCopy", "active", "added"}],
  "outliers": [{"appId", "name", "creatorAppId", "platform", "url", "posted", "hook", "format", "likes", "comments", "reposts", "views", "outlierRatio", "whyItWorked", "tags", "text", "saved"}],
  "ideas": [{"appId", "name", "week", "status", "pillar", "funnelJob", "problem", "claim", "example", "proofOfDemand", "rank", "aiGenerated"}],
  "pieces": [{"appId", "name", "week", "ideaAppId", "status", "titleA", "titleB", "hook", "thumbnailNotes", "releaseDate", "fileUrl", "outline", "script", "transcript", "argument"}],
  "posts": [{"appId", "name", "status", "pillar", "platform", "type", "sourcePieceAppId", "sourceRef", "publishDate", "approved", "graphicUrl", "publishedUrl", "voiceCheck", "body", "graphicBrief"}],
  "weeks": [{"name", "status", "pickedIdeaAppId", "pieceAppId", "winners", "questions", "nextIdea"}]
}
```

Status values map 1:1 (`drafting` → Drafting, etc.). `appId` is stored in the Notion "App id" property so later
syncs update instead of duplicating (the repo's rule: query before create, never make a second posts database).

## Open items to confirm against the client's example

- Whether the client wants Ideas as a separate database (above) or as `Status = Idea` cards on the Content board.
- Whether to keep the repo's "Pillars & Topics" and "Hooks" databases (useful, but the app doesn't need them).
- Any extra properties their current board carries (owner, review notes, asset links).
