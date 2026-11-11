# Blueprint format (version 2)

One JSON file describes one project as a company map: the phases (shared by
all projects), the project's roles and its flows with their tasks. No
personal data: people, ADKAR scores, progress and hours are not part of a
blueprint. Importing gives the project the six progress stages (Open ...
Live) when it has none yet (`docs/data-model.md`).

```json
{
  "format": "pantalytics-blueprint",
  "version": 2,
  "lang": "en_US",
  "name": "Generic manufacturer",
  "phases": [{"code": "quotation", "name": "Quotation", "sequence": 30}],
  "roles":  [{"code": "sales", "name": "Sales", "sequence": 30, "external": false,
              "description": "Inside sales and account managers."}],
  "flows":  [{"name": "S13 Approve a quotation", "sequence": 130,
              "description": "<p>Internal check is not the customer's approval.</p>",
              "tasks": [{"name": "Draft the quotation", "role": "sales", "phase": "quotation",
                         "description": "<ol><li>Sales, New</li></ol>"}]}]
}
```

| Section | Matched on | Required | Optional |
|---|---|---|---|
| phases | `code` (shared) | `code`, `name` | `sequence` (`apps` of 2.0 files is ignored) |
| roles | `code` within the project | `code`, `name` | `sequence`, `external`, `description` |
| flows | `name` within the project | `name` | `sequence`, `description` (HTML), `tasks` |
| tasks | `name` within their flow | `name` | `role`, `phase` (codes), `description` (HTML, e.g. the click path) |

## Rules

- `format` and `version` are required. Version 1 files (chains, processes,
  activities, scenarios) are refused with a message; load the template or
  export again.
- A file is imported into one project. Import creates and updates, never
  deletes. Keys left out are not changed. Task order in the file is the
  route order.
- A task's `role` and `phase` must be a code in the file or already in the
  project (roles) or the database (phases).
- Codes have no spaces. `sequence` is a whole number, `external` is `true`
  or `false`, the rest is text.
- `lang` is the language of the names; export always writes English
  (`en_US`). A language that is not active is refused.
- Loading the bundled template only fills what is empty and never changes
  the company's own names, descriptions, flags, stages or progress.
- Export writes the project's flows (parent tasks with subtasks) and their
  non-cancelled subtasks. Tasks outside a flow are project work and are not
  exported.
- Files above 5 MB or with more than 5,000 records are refused. Every
  refusal says what is wrong and what to do, and nothing is imported.
