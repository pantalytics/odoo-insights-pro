# Blueprint format (version 1)

One JSON file describes a company: its chains, phases, roles, processes,
activities and scenarios. Everything is referenced by `code`, so a file can
be imported again and again (idempotent) and diffed in git. No personal data:
people and ADKAR scores are not part of a blueprint.

```json
{
  "format": "pantalytics-blueprint",
  "version": 1,
  "lang": "en_US",
  "name": "Generic manufacturer",
  "chains":    [{"code": "lead_to_cash", "name": "Lead to Cash", "sequence": 20,
                 "description": "From the first contact to the payment."}],
  "phases":    [{"code": "quotation", "name": "Quotation", "sequence": 30,
                 "apps": ["sale_management"]}],
  "roles":     [{"code": "sales", "name": "Sales", "sequence": 30, "external": false,
                 "description": "Inside sales and account managers."}],
  "processes": [{"code": "quote_approve", "name": "Quote and approve", "sequence": 10,
                 "chain": "lead_to_cash", "owner_role": "sales"}],
  "activities":[{"code": "quote_draft", "name": "Draft the quotation", "sequence": 10,
                 "process": "quote_approve", "role": "sales", "phase": "quotation",
                 "model": "sale.order", "choice_state": "fixed",
                 "open_point": "", "click_path": "<ol><li>Sales, New</li></ol>"}],
  "scenarios": [{"code": "S13", "name": "Approve a quotation", "sequence": 130,
                 "description": "Internal check is not the customer's approval.",
                 "open_point": "",
                 "steps": ["quote_draft",
                           {"activity": "quote_send", "note": "Use test customer A"}]}]
}
```

## Keys per section

| Section | Required for a new record | Optional |
|---|---|---|
| chains | `code`, `name` | `sequence`, `description` |
| phases | `code`, `name` | `sequence`, `apps` (technical module names, shown as chips in the Odoo band) |
| roles | `code`, `name` | `sequence`, `external` (customer, supplier), `description` |
| processes | `code`, `name`, `chain` | `sequence`, `owner_role` |
| activities | `code`, `name`, `process`, `role`, `phase` | `sequence`, `model`, `choice_state` (`proposal`, `provisional`, `fixed`, `revised`), `open_point`, `click_path` (HTML) |
| scenarios | `code`, `name` | `sequence`, `description`, `open_point`, `steps` |

A code has no spaces. `sequence` is a whole number. Names, descriptions,
open points, click paths, notes, codes and apps are text; `external` is
`true` or `false`, without quotes.

## Rules

- `format` and `version` are required; another value is refused.
- `lang` is the language the names are written in. An export always writes
  the English source values with `"lang": "en_US"`, whatever the language of
  the user who exports. An import writes the names in that language (`en_US`
  when the key is left out). A language that is not active in the database
  is refused.
- Every reference (`chain`, `owner_role`, `role`, `phase`, `process`,
  `steps`) must name a code in the same file or already in the database.
  Otherwise the import stops and names every missing code.
- A step is an activity code, or an object `{"activity": code, "note": text}`
  when the step needs a note (for example the test data to use). The export
  writes the object form only for steps with a note.
- Keys left out of an item are not changed on update.
- `model` is a technical model name. Importing a file is strict: an unknown
  model refuses the whole file and names the model (the app may not be
  installed).
- `apps` lists technical module names (`sale_management`, `account`). The
  map shows each module's name in the user's language. An older file with
  app names ("Sales") still works: a value that is no module name is matched
  on the app's name.
- A phase `models` key (older files) is accepted and ignored.
- A file above 5 MB, or with more than 5,000 records in total (all sections
  plus scenario steps), is refused. The same limits apply when
  `import_blueprint` is called directly.
- Every refusal says what is wrong and what to do, and nothing is imported.
- Import creates and updates, never deletes. Importing a file replaces the
  steps of every scenario that lists `steps`.
- Loading the bundled template is lenient and never overwrites the
  company's own work: an unknown model leaves the link empty and the
  notification names the apps to install; missing records are created; on
  existing records only empty values are filled; choice states, the external
  flag, references and existing scenario steps are kept. Only records that
  really change are counted. After installing a missing app, load the
  template again to link it.
- Export writes all records in this format, ordered by sequence.
