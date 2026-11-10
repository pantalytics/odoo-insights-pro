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
- **Progress per activity, set on tasks:** 0 Open, 1 Decided, 2 Built,
  3 Tested, 4 Trained, 5 Live (technical name `rung`; the word on screen is
  "Progress"). Choices iterate: proposal → provisional → fixed → revised.

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
AbstractModel for activity and scenario with the shared fields only: `rung`
(Integer "Progress level", technical, never shown), `rung_state` ("Progress",
Selection from `rung`, the field views show), `planned_hours`, `spent_hours`,
and the helper `_counted(tasks)` that leaves out cancelled tasks. Activity and
scenario each define their own `_compute_rung` and `_compute_hours` with
their own `@api.depends`. All four fields are stored and computed with sudo
over all linked tasks, archived ones included (`active_test=False`), so
progress is the same for everyone and survives archiving a project. When
every linked task is cancelled the rung is 0.

### `pan.sl.chain` (L1) — `models/structure.py`
`name` (translate), `code` (unique), `sequence`, `description`,
`process_ids`.

### `pan.sl.phase` (map column) — `models/structure.py`
`name` (translate), `code` (unique), `sequence`, `app_labels` ("Odoo apps",
Char: comma separated technical module names such as `sale_management`, the
chips in the Odoo band), `activity_ids`.

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
step order), `progress` ("Tested %", Float 0-100, stored: share of its
activities with rung >= Tested, 0 without activities), `task_ids`,
`task_count`. Its `rung_state` is labelled "Lowest progress". Its rung is the
lowest of its activities; its hours count each of its tasks once. Ordered by
`sequence`.
Step: `scenario_id` (cascade), `sequence`, `activity_id` (required), `note`.
Adds `scenario_ids` (computed, searchable) on the activity.

### `project.task` (inherit) — `models/project_task.py`
`pan_scenario_id`, `pan_activity_ids` (relation
`pan_sl_activity_project_task_rel`), `pan_rung` ("Blueprint progress",
Selection `"0"`..`"5"`, tracking). All three have
`groups="pan_self_learning_blueprint.group_blueprint_user"`. Hours are
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
`UserError` naming all of them. Above `MAX_FILE_BYTES` (5 MB, measured as
JSON) or `MAX_RECORDS` (5000) records is refused, also on a direct RPC call.
Every error says in plain words what is wrong and what to do. Format:
`docs/blueprint-format.md`.

Direct actions, no wizard modes:
- `action_load_template()`: loads the bundled template
  (`data/blueprints/generic_manufacturing.json`) with `strict=False,
  fill_empty_only=True` and reopens the map (`target: "main"`, one
  breadcrumb) with a one-line summary. Only records it really changes are
  written and counted; a second load says "Nothing to change." Missing apps
  make the notification a sticky warning.
- `action_export()`: downloads `blueprint.json` directly, no dialog.
- TransientModel `pan.sl.blueprint.wizard`: `file`, `filename`,
  `action_import()`. Strict. Managers only.

Loading a template never overwrites company edits: only empty fields are
filled; choice states, booleans, references and existing steps are kept.

### Map data — `models/map_data.py`
`pan.sl.activity.get_map_data()` → one dict, read in batches:

```
chains:     [{id, code, name}]
processes:  [{id, code, name, chain_id, owner_role_id}]
phases:     [{id, name, code, apps: [{name, module, installed}]}]
roles:      [{id, code, name, is_external, users: [str], adkar: "low"|"medium"|"high"|false}]
activities: [{id, name, code, process_id, chain_id, role_id, phase_id,
              choice_state, rung, planned_hours, spent_hours, open_point,
              scenario_ids: [int], model: str|false}]
scenarios:  [{id, code, name, description, open_point, rung, progress: int,
              activity_ids: [ordered ints]}]
```

An app value is matched on `ir.module.module.name` (sudo); a value that is no
module name is matched on shortdesc in en_US, then the user's language.
`name` is the module's shortdesc in the user's language, `installed` is
`state == "installed"`. A value that matches nothing is still shown, as not
installed. `users` are names only.
`get_map_details()` → `[{id, tasks: [{id, name, rung}], click_path}]`
(archived tasks kept, cancelled left out; `click_path` is the first line as
plain text), loaded in parallel for the Detail stop.

## Security

`group_blueprint_user` opens the map and reads the model and their own
scores; `group_blueprint_manager` (implies user) edits everything and owns
the wizard. Read on `ir.model` is granted to managers only (they pick the
model); users see `model_name`. Managers also get read on the abstract
`pan.sl.blueprint`: Odoo hides a menu whose server action's model the user
cannot read, and both server actions are bound to it.

## Upgrade to 19.0.1.2.0

`migrations/19.0.1.2.0/pre-migrate.py` moves role members and scores from
users to their partners (`pan_sl_role_res_partner_rel`, `partner_id`) and
drops the XML ids of the old default chains and phases, so those records stay
as ordinary data. `post-migrate.py` drops the tables of the three removed
many2many fields, `pan_sl_role_res_users_rel`, `pan_sl_role_res_groups_rel`
and `ir_model_pan_sl_phase_rel`, with their `ir_model_relation` rows, and the
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
Scenarios, Phases, Roles) · People (ADKAR scores) · Blueprint (managers: Load
template, Import file, Export).

## Client action — `static/src/map/`
OWL component `pan_sl_blueprint_map`, plain OWL + SVG, no diagram library:
the fixed grid must be deterministic so everyone finds the same thing in the
same place. Loads `get_map_data` once. One row of controls: scenario select
(each option ends in "Tested N%"), colour by (Choices, Progress, Training),
zoom slider (fit to 4x; wheel and pinch move it).

**Colour by.** The legend shows only the active mode, at most 3 items. Green
and amber also carry a glyph (check, half disc), so status is never colour
only. Red is never used: red means broken.

| Mode | Green | Amber | Grey |
|---|---|---|---|
| Choices | Settled (fixed) | Not settled (proposal, provisional, revised) | |
| Progress | Tested or further | Decided or built | Open |
| Training | Trained (rung >= 4) | Still to train | Nobody in the role |

**Semantic zoom.** Four stops; content switches at each:

| Stop | Name | What is drawn |
|---|---|---|
| 1 (fit) | Company | Tested % per phase, one block per role × phase with a count, "N not settled" per phase |
| 2 | Activities | Activity chips with names; the selected scenario route with numbered steps |
| 3 | Status | Chips add a 5-segment progress meter (0 grey, 1-2 amber, 3-5 green, as the list badges) with the word and an open-point marker |
| 4 | Detail | Under each chip its tasks (name, progress word) and the first line of the click path |

Progress is always the word ("Tested"), never a number. Activities starts at
the scale where its whole layout fits. Choosing a scenario zooms within
Activities until the whole route is in view, and announces "Showing scenario
X, N steps" (aria-live). After a stop change with nothing in view, the
nearest block or chip is centred; on a phone always. A chip's accessible
name is activity, phase, role and the state of the current colour mode.

**Side panels.** An activity: chain › process · phase, role (opens the role
panel), training ("Trained", or "Still to train" with the role's people),
scenarios, choice, progress, hours (planned · spent), open point, model, and
a button to the activity form. A role (from the panel or a lane label): its
people, ADKAR band (or "Needs three scored people") and number of
activities. Phase headers stay plain text.

**Keyboard.** The SVG is focusable: arrows pan, `+`/`-` zoom, Home fits, Tab
walks the blocks or chips of the current stop and the camera follows. Lane
labels are buttons (Enter, Space). Zoom, view box, scenario, colour-by and
selection are saved with `useSetupAction` (breadcrumb). Zoom, centre,
scenario and colour-by are also kept in `sessionStorage` under
`pan_sl_blueprint_map:<action id>`, so they survive a page refresh.

**Empty state** (no activities): one muted line in a dashed box. Managers get
"No company model yet." and one button, "Load template": it calls
`action_load_template`, shows the summary and reloads the map in place.
Users get "No company model yet. Ask a Blueprint administrator."

## Conventions
- Odoo 19: `list` views, `invisible=`/`readonly=` expressions, no `attrs`.
  English source strings, Dutch in `i18n/nl.po`.
- Every field has `string=` and `help=`. No silent fallbacks; raise clear errors.
- Views show `rung_state`, never the integer `rung`. Sequence only as a list
  handle. Copy follows `docs/brand.md`.
- Tests: `tests/`, `TransactionCase`, tagged `post_install`, `-at_install`.
