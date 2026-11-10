# Blueprint module: architecture and contract

Module `pan_self_learning_blueprint` (Odoo 19), part of Odoo Self Learning.
Design background: issue #18. This file is the contract every part of the
module is built against. Change it first, then the code.

## Goal (Rutger, 10-11-2026)

A simple app that gives insight into an Odoo implementation and its
continuous improvement, built on the Projects app and the Google Maps idea:
one map, zoom out to the whole company, zoom in to one activity. It goes
beyond the technical implementation: the company on a map, the people,
training and progress. Ready for AI-assisted implementation and improvement.
Every change is judged against this goal; simpler wins.

## Idea

- **Three pillars, one atom.** Business (what we do), system (what Odoo must
  do), people (can they do it). The **activity** is the shared key: one role
  does one thing to one Odoo document.
- **Hierarchy:** chain (L1) → process (L2) → activity (L3) → click path (L4).
  A **scenario** is a test route across processes (not a level).
- **Map orientation is fixed:** left → right = phases (Odoo's document chain);
  top → bottom = progress band, role lanes with activities (external roles
  first and last), Odoo band.
- **Progress per activity, as a rung on tasks:** 0 Open, 1 Decided, 2 Built,
  3 Tested, 4 Trained, 5 Live. Choices iterate: proposal → provisional →
  fixed → revised.

## Two use cases, one module

1. **A company on its own Odoo**: maps itself, configures Odoo and keeps
   improving after go-live.
2. **An implementation partner on a client's Odoo**: same module, installed
   in the client's database.

So: no partner or customer concept in the model, one blueprint per company,
tasks from any project can link to activities, and "Live" is a state, not
the end of the record.

## Models (technical names are binding)

### `pan.sl.structure.mixin` — `models/structure.py`
AbstractModel for chain, phase, role, process, activity and scenario: every
record matches on `code` (`_check_code`: present, no spaces). Helpers
`_compute_count_by()` and `_action_open_activities()`. Constants
`RUNG_SELECTION` (`"0"`..`"5"`), `TESTED_RUNG` (3) and `CANCELLED_STATE`
(`"1_canceled"`).

### `pan.sl.progress.mixin` — `models/structure.py`
AbstractModel for activity and scenario: `rung` (Integer, technical, never
shown), `rung_state` (Selection from `rung`, the field views show),
`planned_hours`, `spent_hours`, and the shared computes. Each model supplies
`_progress_tasks()` and `_progress_rungs()`; `_counted(tasks)` leaves out
cancelled tasks. All four fields are stored and computed with sudo over all
linked tasks, so progress is the same for everyone. When every linked task is
cancelled the rung is 0.

### `pan.sl.chain` (L1) — `models/structure.py`
`name` (translate), `code` (unique), `sequence`, `description`,
`process_ids`.

### `pan.sl.phase` (map column) — `models/structure.py`
`name` (translate), `code` (unique), `sequence`, `app_labels` (Char, comma
separated: the app chips in the Odoo band), `activity_ids`.

### `pan.sl.role` (map lane) — `models/structure.py`, `models/adkar.py`
`name` (translate), `code` (unique), `sequence`, `is_external` (customer,
supplier), `description`, `activity_ids`. `partner_ids` (Many2many
`res.partner`, relation `pan_sl_role_res_partner_rel`, string "People"): the
people who hold the role. Contacts, so people without a login can be listed
and scored. The other side is `res.partner.pan_role_ids`.
`_get_adkar_bands()` → `{role_id: "low" | "medium" | "high" | False}` (see
ADKAR).

### `pan.sl.process` (L2) — `models/process_activity.py`
`name`, `code` (unique), `chain_id` (required, ondelete restrict),
`owner_role_id`, `sequence`, `activity_ids`, `activity_count`.

### `pan.sl.activity` (L3, the atom) — `models/process_activity.py`
Inherits `mail.thread`, the structure mixin and (in `models/project_task.py`)
the progress mixin. `name`, `code` (unique), `process_id` (required),
`chain_id` (related, stored), `role_id` (required), `phase_id` (required),
`model_id` (Many2one `ir.model`, managers only in views), `model_name`
(related `model_id.model`, stored: what the map, export and users read),
`click_path` (Html, L4), `choice_state` (`proposal|provisional|fixed|revised`,
tracking), `open_point`, `sequence`. Added elsewhere: `scenario_ids`,
`task_ids` and the progress fields.

### `pan.sl.scenario` + `pan.sl.scenario.step` — `models/scenario.py`
Scenario (structure and progress mixins): `name`, `code`, `description`,
`open_point`, `sequence`, `step_ids`, `activity_ids` (computed from steps, in
step order), `progress` (Float 0-100, stored: share of its activities with
rung >= Tested, 0 without activities), `task_ids`, `task_count`. Its
`rung_state` is labelled "Lowest progress". Ordered by `sequence`.
Step: `scenario_id` (cascade), `sequence`, `activity_id` (required), `note`.
Adds `scenario_ids` (computed, searchable) on the activity.

### `project.task` (inherit) — `models/project_task.py`
`pan_scenario_id`, `pan_activity_ids` (relation
`pan_sl_activity_project_task_rel`), `pan_rung` ("Blueprint progress",
Selection `"0"`..`"5"`, tracking). Shown only to Blueprint users. Hours are
the task's `allocated_hours` and `effective_hours`; a task on several
activities counts for each, and once per scenario. Depends on `hr_timesheet`.

### `pan.sl.adkar.score` — `models/adkar.py`
`partner_id` (Many2one `res.partner`, "Person", required, ondelete
restrict), `date`, `round`, `awareness`, `desire`, `knowledge`, `ability`,
`reinforcement` (1-5, SQL constraint), `average`, `note` (managers only),
`role_ids` (related `partner_id.pan_role_ids`).

**ADKAR band.** `_get_adkar_bands()` takes each person's latest score, averages
each element over the role, and turns the weakest element into a band: low
(<= 2), medium (< 4), high (>= 4). `False` when fewer than
`ADKAR_MIN_PEOPLE_FOR_BAND` (3) people of the role have a score. Read with
sudo; only the word leaves the server.

**Scores are personal.** `rule_adkar_score_own`
(`[('partner_id', '=', user.partner_id.id)]`) for Blueprint users;
`rule_adkar_score_manager_all` for administrators. Scores of people without a
login are visible to administrators only.

### Blueprint (open format) — `models/blueprint.py`
AbstractModel `pan.sl.blueprint`: `export_blueprint()` → dict and
`import_blueprint(data, strict=True, fill_empty_only=False)` → summary.
Records match on `code`; nothing is deleted. Unknown codes raise one
`UserError` naming all of them. More than `MAX_RECORDS` (5000) records is
refused. Format: `docs/blueprint-format.md`.

Direct actions, no wizard modes:
- `action_load_template()`: loads the bundled template
  (`data/blueprints/generic_manufacturing.json`) with `strict=False,
  fill_empty_only=True` and reopens the map with a one-line summary. Only
  records it really changes are written and counted; a second load says
  "Nothing to change." Missing apps make the notification a sticky warning.
- `action_export()`: downloads `blueprint.json`.
- TransientModel `pan.sl.blueprint.wizard`: `file`, `filename`,
  `action_import()`. Strict; refuses files above `MAX_FILE_BYTES` (5 MB).

Loading a template never overwrites company edits: only empty fields are
filled; choice states, booleans, references and existing steps are kept.

### Map data — `models/map_data.py`
`pan.sl.activity.get_map_data()` → one dict, read in batches:

```
phases:     [{id, name, code, apps: [{name, installed}]}]
roles:      [{id, name, is_external, users: [str], adkar: "low"|"medium"|"high"|false}]
activities: [{id, name, code, role_id, phase_id, choice_state, rung,
              open_point, scenario_ids: [int], model: str|false}]
scenarios:  [{id, code, name, description, open_point, rung, progress: int,
              activity_ids: [ordered ints]}]
```

`installed` is true when an installed application (`ir.module.module`
shortdesc, sudo) has that name. `users` are names only.
`get_map_details()` → `[{id, tasks: [{id, name, rung}], click_path}]`
(cancelled tasks left out; `click_path` is the first line as plain text),
loaded in parallel for the Detail stop.

## Security

`group_blueprint_user` opens the map and reads the model and their own
scores; `group_blueprint_manager` (implies user) edits everything. Read on
`ir.model` is granted to managers only (they pick the model); users see
`model_name`.

## Upgrade to 19.0.1.2.0

`migrations/19.0.1.2.0/pre-migrate.py` moves role members and scores from
users to their partners (`pan_sl_role_res_partner_rel`, `partner_id`) and
drops the XML ids of the old default chains and phases, so those records stay
as ordinary data. `post-migrate.py` drops `pan_sl_role_res_users_rel` and the
old `user_id` column.

## XML ids (binding)

| Id | Owner file |
|---|---|
| `group_blueprint_user`, `group_blueprint_manager` | `security/security.xml` |
| `rule_adkar_score_own`, `rule_adkar_score_manager_all` | `security/adkar_rules.xml` |
| `action_chain`, `action_phase`, `action_role` + views | `views/structure_views.xml` |
| `action_process`, `action_activity` + views | `views/activity_views.xml` |
| `action_scenario` + views | `views/scenario_views.xml` |
| `action_adkar_score` + views | `views/adkar_views.xml` |
| task form page "Blueprint" (inherit `project.view_task_form2`) | `views/project_task_views.xml` |
| `action_blueprint_load_template`, `action_blueprint_export` (server actions), `action_blueprint_import` + `view_blueprint_import_form` | `views/blueprint_views.xml` |
| `action_blueprint_map` (client action `pan_sl_blueprint_map`) | `views/map_action.xml` |
| `menu_blueprint_root` and submenus | `views/menus.xml` |

Menu: Blueprint → Company map · Model (Chains, Processes, Activities,
Scenarios, Phases, Roles) · People (ADKAR scores) · Import / export (managers:
Load template, Import file, Export).

## Client action — `static/src/map/`
OWL component `pan_sl_blueprint_map`, plain OWL + SVG, no diagram library:
the fixed grid must be deterministic so everyone finds the same thing in the
same place. Loads `get_map_data` once. One row of controls: scenario select
(each option ends in its progress %), colour by (Choices, Progress, People),
zoom slider (fit to 4x; wheel and pinch move it).

**Colour by.** The legend shows only the active mode, at most 3 items. Green
and amber also carry a glyph (check, half disc), so status is never colour
only. Red is never used: red means broken.

| Mode | Green | Amber | Grey |
|---|---|---|---|
| Choices | Settled (fixed) | Not settled (proposal, provisional, revised) | |
| Progress | Tested or further | Decided or built | Open |
| People | ADKAR high | ADKAR medium or low | No ADKAR data |

**Semantic zoom.** Four stops; content switches at each:

| Stop | Name | What is drawn |
|---|---|---|
| 1 (fit) | Company | Progress % per phase, one block per role × phase with a count, "N not settled" per phase |
| 2 | Processes | Activity chips with names; the selected scenario route with numbered steps |
| 3 | Activities | Chips add a 5-segment bar with the rung word and an open-point marker |
| 4 | Detail | Under each chip its tasks (name, rung word) and the first line of the click path |

The rung is always the word ("Tested"), never a number. Apps that are not
installed are greyed out in the Odoo band. Clicking a chip opens the side
panel: role (members by name, ADKAR band), scenarios, choice, progress, open
point, model, and a button to the activity form.

**Keyboard.** The SVG is focusable: arrows pan, `+`/`-` zoom, Home fits, Tab
walks the blocks or chips of the current stop and the camera follows.
Zoom, view box, scenario, colour-by and selection are saved with
`useSetupAction` and restored from the breadcrumb.

**Empty state** (no activities): one muted line in a dashed box. Managers get
"No company model yet." and one button, "Load template"
(`action_blueprint_load_template`, which reopens the map). Users get "No
company model yet. Ask a Blueprint administrator."

## Conventions
- Odoo 19: `list` views, `invisible=`/`readonly=` expressions, no `attrs`.
  English source strings, Dutch in `i18n/nl.po`.
- Every field has `string=` and `help=`. No silent fallbacks; raise clear errors.
- Views show `rung_state`, never the integer `rung`. Sequence only as a list
  handle. Copy follows `docs/brand.md`.
- Tests: `tests/`, `TransactionCase`, tagged `post_install`, `-at_install`.
