# Sales Leads (replies)

Every reply from a lead lands in **Sales Leads**, sorted into positive, neutral and negative.

## Where replies come from

| Channel | How it arrives |
|---|---|
| Email | The inbox check reads new mail and matches it to leads and sent emails |
| LinkedIn | Every 5 minutes Leadnius reads the linked account's recent chats through Unipile (no webhook needed) |
| WhatsApp | Meta or Unipile webhooks |

A reply stops that lead's sequences. An opt-out adds them to do-not-contact.

## Answering (built 2026-11-20)

The reply view shows the real conversation: what was actually sent to the lead, their reply, and your answers.

- **Send** posts your text on the channel the reply came in on (`POST /api/replies/{id}/respond`,
  `services/reply_send.py`):
  - email: from the inbox that received it, in the same thread, as "Re: …";
  - LinkedIn: through the Unipile-linked account (needs the Unipile sending method);
  - WhatsApp: free text inside WhatsApp's 24-hour window.
- **AI draft** writes an answer from the playbook for you to edit (`POST /api/replies/{id}/draft`). It uses AI credits
  and runs only on a click. It never sends.
- Text with a `{{placeholder}}` left in it is refused.
- Answers are kept on the reply (`reply.responses`, migration 0014). In a channel's test mode they are logged and
  marked "Test · not sent".

Nothing is sent automatically: there is no autopilot. The old "AI Reply Agent" switch, "Book meeting" and
"Next action" controls did nothing and were removed.

Tests: `tests/test_reply_send.py`.
