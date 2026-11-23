# GTM playbook upload

Account → **GTM playbook** → **Playbook documents**. A client uploads their playbook; the app reads it, suggests the
ICP / business profile / personas from it for review, and the Messaging Agent uses it as background when it writes.

Code: `lead-gen-backend/services/playbook.py`, `api/playbook.py`, model `PlaybookDocument` (`playbook_document`);
frontend `components/agent/PlaybookDocuments.tsx` on `app/dashboard/account/page.tsx`.

## Formats

| Upload | How it's read |
| --- | --- |
| PDF | text layer via `pypdf` (scans/image-only PDFs are refused with a clear message; password-protected too) |
| DOCX | the Word XML directly; Heading styles become `#` headings, list paragraphs become `- ` items |
| Notion export (.zip) | every Markdown / HTML / CSV page inside, including Notion's nested `Part-1.zip`; page ids stripped from titles |
| Markdown, text, CSV, HTML | as text (HTML tags stripped, headings kept) |
| .doc, images, other | refused with what to do instead |

Limits: 15 MB per file, 200,000 characters kept per document, 20 documents per workspace.

## Filling the playbook from a document

**Fill playbook from this** → `POST /api/playbook/documents/{id}/suggest`:

- With `ANTHROPIC_API_KEY`: Claude reads the whole document (up to 120k characters) and returns every ICP field,
  the business profile fields (offering, geographies, deal size, case studies) and up to 4 personas, using only what
  the playbook says, plus a note on what it didn't cover.
- Without a key (today): sections are matched by their headings, e.g. "Pain points", "Objections", "Target titles",
  "Case studies", "What we sell". No personas.

The review window lists each suggested field with the current value, pre-ticked when it differs. The user edits and
unticks, then **Apply selected** saves through the normal `PATCH /api/workspace` and `POST /api/personas` (same
validation and admin rule as saving by hand) and marks the document applied. Nothing changes before that.

## Used by the Messaging Agent

Documents with **Messaging Agent reads this when writing** on (default) are given to the AI message writer as cached
background (newest first, up to 24,000 characters), so claims, proof and objection handling match the playbook. The
house tone rules (docs/personalised-messages.md) still win over any style in the document. The rules-based writer
(no key) uses the ICP fields the playbook filled.

## API

```
GET    /api/playbook/documents
POST   /api/playbook/documents              multipart "file"            (admin)
GET    /api/playbook/documents/{id}         + text, last suggestion
PATCH  /api/playbook/documents/{id}         {useInMessages?, applied?}  (admin)
DELETE /api/playbook/documents/{id}                                      (admin)
POST   /api/playbook/documents/{id}/suggest
```
