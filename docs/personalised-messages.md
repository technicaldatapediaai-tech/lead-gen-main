# Personalised messages

Every outreach message on every channel (email, LinkedIn connection notes and DMs, WhatsApp) is written for one person
from what we know about them, in one house tone. Code: `lead-gen-backend/services/message_writer.py` (writer, tone
check) and `services/personalize.py` (rules templates).

## What a message is built from

`message_writer.gather()` collects, for one lead:

| Source | Fields |
| --- | --- |
| Buying signals | `lead.profile.signalDetail`, the latest 3 Signal Agent rows for the lead's company (type, detail, date), else the lead's signal type |
| Individual profile | headline, tenure, location, recent activity, company note (`lead.profile`) |
| ICP | Workspace settings → ICP: titles, company size, industries, pains, value props, objections, CTA |
| Persona | the persona matched by job title: pains, what they care about, value, proof, CTA |
| Our company | name, offering, case studies |

Nothing else is given to the writer, and it is told never to invent numbers, names, customers or events.

## House tone

Simple, conversational, no appreciation:

- Short sentences and everyday words, how a peer would text a peer.
- **No appreciation**: no congratulations, praise, "loved/enjoyed your post", "impressive", thanks for their content.
  The signal is stated as a plain fact ("Saw Finlytics is hiring 5 SDRs.").
- No filler openers ("hope you're well", "I came across", "reaching out"), no buzzwords (leverage, synergy, unlock).
- No exclamation marks, no emoji, no sign-off lines.
- One idea and one easy question.

`tone_issues(text)` enforces this in code: banned phrases, `!`, emoji, more than one question, length limits per channel
(LinkedIn connection note 300 characters, LinkedIn DM 600, email 700, WhatsApp 450) and unfilled `{{variables}}`.

## How a message gets written

1. **Template step** (`mode: "template"` with a `body`): the step's own text with variables filled
   (`{{firstName}}`/`{{first_name}}`, `{{name}}`, `{{company}}`, `{{title}}`, `{{signal}}` = the signal as a plain fact,
   `{{case_study_link}}`, `{{calendar_link}}`). If any variable can't be filled, the writer writes that lead's message
   instead, so a prospect never receives `{{similar_company}}`.
2. **Otherwise, AI** when `ANTHROPIC_API_KEY` is set: Claude (`CONTENT_AI_MODEL`, effort `MESSAGE_AI_EFFORT`) writes the
   message from the facts above with the tone rules, channel format and sequence step (first touch, follow-up with one
   new point, short last note). The draft is tone-checked; if it fails, Claude gets the list of problems and rewrites
   once. If it fails again, or the API errors, step 3 is used.
3. **Rules template** (no key, or fallback): the signal as a fact, one persona/ICP pain, what we do, the CTA.

Sends never stop because of the AI: any error falls back to the rules template.

## API

```
GET  /api/messages/tone              the rules, length limits, and whether AI writing is configured
POST /api/messages/check-tone        {text, subject?, channel, kind}            -> {ok, issues[]}
POST /api/messages/write             {leadId, channel, step?, kind?, useAi?}    -> {subject, body, angle, factsUsed, source, toneIssues}
POST /api/messages/campaign-preview  {campaignId, limit?}  what each lead's next step would send (nothing is sent)
GET  /api/channels                   per channel: connected accounts, how it sends, what is still needed
```

`source` is `ai`, `rules` or `template`. Email and WhatsApp sends and LinkedIn drafts all go through
`message_writer.for_step()`, so the preview shows exactly what would go out.
