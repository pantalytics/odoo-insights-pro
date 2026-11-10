# Blueprint format (version 1)

One JSON file describes a company: its chains, phases, roles, processes,
activities and scenarios. Everything is referenced by `code`, so a file can
be imported again and again (idempotent) and diffed in git. No personal data:
people and ADKAR scores are not part of a blueprint.

```json
{
  "format": "pantalytics-blueprint",
  "version": 1,
  "name": "Generic manufacturer",
  "chains":    [{"code": "lead_to_cash", "name": "Lead to Cash", "sequence": 20}],
  "phases":    [{"code": "quotation", "name": "Quotation", "sequence": 30,
                 "models": ["sale.order"], "apps": ["Sales"]}],
  "roles":     [{"code": "sales", "name": "Sales", "sequence": 30, "external": false}],
  "processes": [{"code": "quote_approve", "name": "Quote and approve",
                 "chain": "lead_to_cash", "owner_role": "sales"}],
  "activities":[{"code": "quote_draft", "name": "Draft the quotation",
                 "process": "quote_approve", "role": "sales", "phase": "quotation",
                 "model": "sale.order", "choice_state": "fixed",
                 "open_point": "", "click_path": "<ol><li>Sales, New</li></ol>"}],
  "scenarios": [{"code": "S13", "name": "Approve a quotation",
                 "description": "Internal check is not the customer's approval.",
                 "open_point": "", "steps": ["quote_draft"]}]
}
```

Rules:
- `format` and `version` are required; another value is refused.
- Every reference (`chain`, `role`, `phase`, `process`, `steps`) must name a
  code in the same file or already in the database. Otherwise the import
  stops and names the missing code.
- `model` is a technical model name; an unknown model is refused with its
  name (the app may not be installed).
- Import creates and updates, never deletes.
- Export writes all records in this format, ordered by sequence.
