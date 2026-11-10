# Blueprint module: architecture and contract

Module `pan_self_learning_blueprint` (Odoo 19), part of Odoo Self Learning.
Design background: issue #18. This file is the contract every part of the
module is built against. Change it first, then the code.

## Idea

- **Three pillars, one atom.** Business (what we do), system (what Odoo must
  do), people (can they do it). The **activity** is the shared key: one role
  does one thing to one Odoo document.
- **Hierarchy:** chain (L1) → process (L2) → activity (L3) → click path (L4).
  A **scenario** is a test route across processes (not a level).
- **Map orientation is fixed:** left → right = phases (Odoo's document chain);
  top → bottom = from why to with-what: progress band, then role lanes with
  activities (external roles at the edges: first and last), then an Odoo band.
- **Gates per activity, as a rung on tasks:** 0 Open, 1 Decided, 2 Built,
  3 Tested, 4 Trained, 5 Live. Choices iterate: proposal → provisional →
  fixed → revised.

## Two use cases, one module

1. **A company on its own Odoo**: maps itself, configures Odoo and keeps
   improving after go-live (new tasks keep pointing at activities).
2. **An implementation partner working on a client's Odoo**: same module,
   installed in the client's database; the partner's people are users there.

Design rules that follow: no partner or customer concept in the model, one
blueprint per company (`company_id` where multi-company matters later), tasks
from any project can link to activities, and nothing ends at go-live (rung
"Live" is a state, not the end of the record).

## Models (technical names are binding)

### `pan.sl.structure.mixin` — `models/structure.py`
AbstractModel inherited by chain, phase, role, process, activity and
scenario: every record the blueprint matches on `code`. Constraint
`_check_code`: the code is present and has no spaces. Helpers
`_compute_count_by()` (counts for smart buttons, one `_read_group`) and
`_action_open_activities()`. Also holds the shared constants
`RUNG_SELECTION` (`"0"`..`"5"`: Open, Decided, Built, Tested, Trained, Live)
and `CANCELLED_STATE` (`"1_canceled"`, the project task state that never
counts for progress or hours).

### `pan.sl.chain` (L1) — `models/structure.py`
`name` (Char, required, translate), `code` (Char, required, unique),
`sequence` (Integer, default 10), `description` (Text),
`process_ids` (One2many `pan.sl.process`, `chain_id`). `_order = "sequence, id"`.

### `pan.sl.phase` (map column) — `models/structure.py`
`name` (Char, required, translate), `code` (Char, required, unique),
`sequence` (Integer), `model_ids` (Many2many `ir.model`),
`app_labels` (Char, comma separated, shown as chips in the Odoo band),
`activity_ids` (One2many `pan.sl.activity`, `phase_id`). `_order = "sequence, id"`.

### `pan.sl.role` (map lane) — `models/structure.py`
`name` (Char, required, translate), `code` (Char, required, unique),
`sequence` (Integer), `is_external` (Boolean: customer, supplier),
`group_ids` (Many2many `res.groups`, the Odoo access this role needs),
`user_ids` (Many2many `res.users`, relation `pan_sl_role_res_users_rel`),
`description` (Text), `activity_ids` (One2many `pan.sl.activity`, `role_id`).
`_order = "sequence, id"`.
Method `_get_adkar_profile()` is added by `models/adkar.py` (see below).

### `pan.sl.process` (L2) — `models/process_activity.py`
`name` (Char, required, translate), `code` (Char, required, unique),
`chain_id` (Many2one `pan.sl.chain`, required, ondelete restrict),
`owner_role_id` (Many2one `pan.sl.role`), `sequence`,
`activity_ids` (One2many `pan.sl.activity`, `process_id`), `activity_count`,
`action_view_activities()` (smart button on the form).

### `pan.sl.activity` (L3, the atom) — `models/process_activity.py`
Inherits `mail.thread` and `pan.sl.structure.mixin` (the chatter keeps the history of choice iterations).
`name` (Char, required, translate), `code` (Char, required, unique),
`process_id` (Many2one, required, ondelete restrict),
`chain_id` (related `process_id.chain_id`, stored),
`role_id` (Many2one `pan.sl.role`, required),
`phase_id` (Many2one `pan.sl.phase`, required),
`model_id` (Many2one `ir.model`, ondelete set null),
`click_path` (Html: the L4 steps, becomes manual and exercise),
`choice_state` (Selection `proposal|provisional|fixed|revised`, default
`proposal`, tracking=True), `open_point` (Text: "to check"), `sequence`.
Added by other files: `scenario_ids` (`models/scenario.py`), `task_ids`,
`rung`, `rung_state`, `planned_hours`, `spent_hours`
(`models/project_task.py`).

### `pan.sl.scenario` + `pan.sl.scenario.step` — `models/scenario.py`
Scenario (inherits `pan.sl.structure.mixin`): `name`, `code` (unique),
`description` (Text, goal), `open_point` (Text), `sequence`, `step_ids`
(One2many step), `activity_ids` (Many2many computed from steps, ordered by
step sequence), `rung` (Integer, stored, computed = min stored `rung` of its
activities, 0 if none), `rung_state` (stored Selection from `rung`, see
below), `planned_hours` / `spent_hours` (see below), `task_ids` (One2many
`project.task`, `pan_scenario_id`), `task_count`. The scenario list sorts
least ready first (`rung, sequence, id`).
Step: `scenario_id` (required, cascade), `sequence`, `activity_id`
(required), `note` (Char). Adds `scenario_ids` (Many2many computed, with
`_search`) on `pan.sl.activity`. `('scenario_ids', '=', False)` finds the
activities that are in no step; `!= False` the ones that are in a step.

### `project.task` (inherit) — `models/project_task.py`
`pan_scenario_id` (Many2one `pan.sl.scenario`, index),
`pan_activity_ids` (Many2many `pan.sl.activity`, relation
`pan_sl_activity_project_task_rel`),
`pan_rung` (Selection `0..5` as strings: Open, Decided, Built, Tested,
Trained, Live; default `"0"`, tracking=True).
On `pan.sl.activity`: `task_ids` (Many2many inverse of `pan_activity_ids`),
`rung` (Integer, computed = min `int(pan_rung)` over the counted tasks, 0 if
none), `rung_state` (Selection `RUNG_SELECTION`, string "Progress", computed
from `rung`, for display, filters and grouping),
`planned_hours` / `spent_hours` (Float, computed = sum of `allocated_hours` /
`effective_hours` of the counted tasks; a task linked to several activities
counts fully for each). Same two fields on `pan.sl.scenario`, summed over its
own `task_ids`, so each task counts once there. Depends on `hr_timesheet`
(which also installs Employees and analytic accounting).

**Progress is the same for everyone.** `rung`, `rung_state`, `planned_hours`
and `spent_hours` on activity and scenario are stored and computed with sudo
(`compute_sudo=True`) over all linked tasks, also the ones the viewer cannot
open. **Counted tasks** are all linked tasks except cancelled ones (state
`1_canceled`); when every linked task is cancelled the rung is 0. Stored, so
lists can filter ("Not Live"), group by "Rung" and sum the hours.

Hours: estimates and timesheets stay on the tasks of whoever does the work
(in the partner use case: the partner's own Odoo, linked by the same codes).

### `pan.sl.adkar.score` — `models/adkar.py`
`user_id` (Many2one `res.users`, required), `date` (Date, default today),
`round` (Integer, default 1: survey round), `awareness`, `desire`,
`knowledge`, `ability`, `reinforcement` (Integer 1-5, SQL/py constraint),
`note` (Text, manager-only: `groups=group_blueprint_manager`), `role_ids`
(related/computed from roles holding the user).
On `pan.sl.role`: `_get_adkar_profile()` → list of five floats (average over
the role's users of each user's latest round) or `False` when fewer than
`ADKAR_MIN_USERS_FOR_PROFILE` (3) of the role's users have a score, so a
profile never shows one person. `_get_adkar_profiles()` is the batch version
used by the map; both read scores with sudo and return only the aggregate.

**Scores are personal.** Record rules in `security/adkar_rules.xml`: a
Blueprint user reads only their own scores (`rule_adkar_score_own`), a
Blueprint administrator reads and writes all of them
(`rule_adkar_score_manager_all`). The company map never shows an
individual score.

### Blueprint (open format) — `models/blueprint.py`
AbstractModel `pan.sl.blueprint` with `@api.model export_blueprint()` → dict
and `@api.model import_blueprint(data, strict=True, fill_empty_only=False)` →
summary dict. Idempotent: records match on `code`, existing ones are updated,
nothing is deleted. Unknown codes in references raise `UserError` naming
every unknown code (references are resolved with one query per section).
Export writes English source names and `"lang": "en_US"`; import writes names
in the file's `lang`. Format: see `docs/blueprint-format.md`.

**Loading a template never overwrites company edits.** "Load template" calls
`import_blueprint(data, strict=False, fill_empty_only=True)`: unknown models
leave the link empty and are reported per app (`MODEL_APPS`); missing
records are created; on existing records only empty fields are filled and
phase models are linked (added, never removed); choice states, booleans,
references and existing scenario steps are never written.

TransientModel `pan.sl.blueprint.wizard`: `mode` (`import|export|template`),
`file` (Binary), `filename`, `template` (Selection of files in
`data/blueprints/`, radio, preselected when only one ships), `result` (Text,
shown as a success box), `warning` (Text: the apps to install, shown as a
warning box with an "Open Apps" button for system administrators). Buttons
`action_import`, `action_export`, `action_load_template`.

### Map data — `models/map_data.py`
On `pan.sl.activity`: `@api.model get_map_data()` → dict
`{phases:[{id,name,code,apps:[str]}], roles:[{id,name,is_external,users:[str],adkar:[5 floats]|false}],
activities:[{id,name,code,role_id,phase_id,choice_state,rung,open_point,scenario_ids:[int],model:str|false,
training:[{id,name,trained:bool}]}],
scenarios:[{id,code,name,description,open_point,rung,activity_ids:[ordered ints]}]}`.
One call, no N+1 (read in batches). `adkar` is the role profile (false below
three scored users). `training` lists the users of the activity's role with
`trained = rung >= TRAINED_RUNG` (4, "Trained"): the map answers "who still
needs training" from progress, never from individual ADKAR scores.
`@api.model get_map_details()` → `[{id, tasks:[{id,name,rung:int}], click_path:str|false}]`
(one entry per activity; `click_path` is the first line of the click path as
plain text), loaded in parallel by the map for the Detail stop (one search
for all tasks).

**Clash** (counter on the map): an activity whose choice is `revised`, or
`fixed` while it still has an open point. Both mean "decided, but not settled".

## XML ids (binding)

| Id | Owner file |
|---|---|
| `group_blueprint_user`, `group_blueprint_manager` (implies user) | `security/security.xml` |
| `rule_adkar_score_own`, `rule_adkar_score_manager_all` | `security/adkar_rules.xml` |
| `chain_basis`, `chain_lead_to_cash`, `chain_source_to_pay`, `chain_plan_to_produce`, `chain_record_to_report`, `chain_hire_to_retire` | `data/default_structure.xml` |
| `phase_master_data`, `phase_request`, `phase_quotation`, `phase_order`, `phase_plan_produce`, `phase_purchase_receive`, `phase_deliver`, `phase_invoice_pay` | `data/default_structure.xml` |
| `action_chain`, `action_phase`, `action_role` + views | `views/structure_views.xml` |
| `action_process`, `action_activity` + views | `views/activity_views.xml` |
| `action_scenario` + views | `views/scenario_views.xml` |
| `action_adkar_score` + views | `views/adkar_views.xml` |
| task form page "Blueprint" (inherit `project.view_task_form2`) | `views/project_task_views.xml` |
| `action_blueprint_wizard` + view | `views/blueprint_views.xml` |
| `action_blueprint_map` (ir.actions.client, tag `pan_sl_blueprint_map`) | `views/map_action.xml` |
| `menu_blueprint_root` (app "Blueprint"), submenus | `views/menus.xml` |

Chains and phases in `data/default_structure.xml` carry `forcecreate="0"`:
a fresh install creates them, an upgrade never brings back one the company
deleted.

Menu: Blueprint → Company map (default) · Model (Chains, Processes,
Activities, Scenarios, Phases, Roles) · People (ADKAR scores) · Import /
export (`menu_blueprint_blueprint`; item "Load a template, import or export",
`menu_blueprint_import_export`). Managers see Model and import; users see
map, read model and their own ADKAR scores.

## Client action — `static/src/map/`
OWL component registered in `registry.category("actions")` as
`pan_sl_blueprint_map`. Loads `get_map_data` once. SVG company map with the
fixed orientation. Controls in one row: scenario select (all / one),
colour by (Choices / Progress / People ADKAR), zoom as a slider (range input, fit
at the left end, up to 4x; mouse wheel and pinch move the same slider; label
"Zoom"). No +/− buttons. A one-line intro per stop sits above the map.

**Keyboard and screen readers.** The SVG is focusable: arrow keys pan (Shift
further), PageUp/PageDown pan a screen, `+`/`-` zoom, Home fits. Tab and
Shift+Tab walk every block or chip of the current stop in map order, culled
ones included, and the camera follows focus (`reveal()`). Slider arrow keys
jump between stops (Shift fine-tunes), the stop labels are buttons with
`aria-pressed`, and an `aria-live` region announces the stop. Each chip's
`aria-label` holds name, status, rung, clash, open point and users. Every
colour tone also has a shape (check, half disc, cross, dashed), so status is
never colour only.

**State.** Zoom, view box, scenario, colour-by, clash highlight, the
selected activity and the phase panel are saved with `useSetupAction`
(`getLocalState`) and restored from the breadcrumb.

**Rendering choice (10-11): plain OWL + SVG, no diagram library.** The fixed
grid is our map projection: it must be deterministic so everyone finds the
same thing in the same place. Node-network libraries (Cytoscape, vis-network)
use auto layouts that move things around; Mermaid and Excalidraw are static
or hand-drawn. Interaction like a map: drag to pan, wheel/pinch/double-click
to zoom on the cursor, continuous zoom with the four stops as thresholds,
render only what is in view. Fallback if this ever feels too heavy:
Leaflet with `CRS.Simple` (non-geographic map, zoom-dependent layers).
Mermaid and Excalidraw stay possible as exports from the same data, for
documents and workshops.

**Semantic zoom (like a map: more detail appears as you zoom in, never just
bigger text).** The slider has four marked stops; content switches at each:

| Stop | Name | Question | What is drawn |
|---|---|---|---|
| 1 (fit) | Company | Are we on track, where is it stuck? | Progress band per phase with %, lane names, each role × phase cell as one coloured block with a count (no activity names), open-choice and clash counters in the header |
| 2 | Processes | What happens where? | Activity chips with names and colour dot; selected scenario route with numbered steps |
| 3 | Activities | Who, how far, what is open? | Chips add rung bar (0-5), user initials of the role, an "open point" marker, the Odoo model name |
| 4 | Detail | What exactly? | Under each chip its linked tasks (name, rung) and the first line of the click path |

Selecting a scenario jumps to stop 2 and fits the route. Clicking a chip
always opens the side panel (the "street view"), at any stop. Selecting
a scenario dims other activities and draws the numbered route. Clicking an
activity opens a side panel (role, users, scenarios, open point, choice
state) with a button that opens the activity form, and lists the role's
users as "Trained" or "Needs training" (from `training`); the role's ADKAR
average sits in a closed details toggle. Opening the panel keeps the chip in
view next to it. Clicking a phase name opens a phase panel: who still needs
training in that phase, "x of y activities trained" per person with buttons
to the activities still to train, and roles without users. The clash
counters are buttons: they dim everything else and zoom to the clashes.
Uses Odoo's own CSS variables so it matches the backend in light and dark.
Empty state when there are no activities: explain and offer "Load a
template", which opens the wizard in template mode and reloads the map when
it closes.

## Conventions
- Odoo 19: `list` views (not `tree`), `invisible=`/`readonly=` expressions,
  no `attrs`. English source strings, Dutch in `i18n/nl.po`.
- Field help on every field. No hardcoded fallbacks; raise clear errors.
- Tests: `tests/`, `TransactionCase`, tagged `post_install`, `-at_install`.
