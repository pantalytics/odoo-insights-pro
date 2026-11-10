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
`activity_ids` (One2many `pan.sl.activity`, `process_id`).

### `pan.sl.activity` (L3, the atom) — `models/process_activity.py`
Inherits `mail.thread` (the chatter keeps the history of choice iterations).
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
`rung` (`models/project_task.py`).

### `pan.sl.scenario` + `pan.sl.scenario.step` — `models/scenario.py`
Scenario: `name`, `code` (unique), `description` (Text, goal),
`open_point` (Text), `sequence`, `step_ids` (One2many step),
`activity_ids` (Many2many computed from steps, ordered by step sequence),
`rung` (Integer, computed = min `rung` of its activities, 0 if none),
`task_ids` (One2many `project.task`, `pan_scenario_id`), `task_count`.
Step: `scenario_id` (required, cascade), `sequence`, `activity_id`
(required), `note` (Char). Adds `scenario_ids` (Many2many computed, with
`_search`) on `pan.sl.activity`.

### `project.task` (inherit) — `models/project_task.py`
`pan_scenario_id` (Many2one `pan.sl.scenario`, index),
`pan_activity_ids` (Many2many `pan.sl.activity`, relation
`pan_sl_activity_project_task_rel`),
`pan_rung` (Selection `0..5` as strings: Open, Decided, Built, Tested,
Trained, Live; default `"0"`, tracking=True).
On `pan.sl.activity`: `task_ids` (Many2many inverse of `pan_activity_ids`),
`rung` (Integer, computed = min `int(pan_rung)` over `task_ids`, 0 if none),
`planned_hours` / `spent_hours` (Float, computed = sum of `allocated_hours` /
`effective_hours` of `task_ids`; a task linked to several activities counts
fully for each). Same two fields on `pan.sl.scenario`, summed over its own
`task_ids`, so each task counts once there. Depends on `hr_timesheet`.

Hours: estimates and timesheets stay on the tasks of whoever does the work
(in the partner use case: the partner's own Odoo, linked by the same codes).

### `pan.sl.adkar.score` — `models/adkar.py`
`user_id` (Many2one `res.users`, required), `date` (Date, default today),
`round` (Integer, default 1: survey round), `awareness`, `desire`,
`knowledge`, `ability`, `reinforcement` (Integer 1-5, SQL/py constraint),
`note` (Text), `role_ids` (related/computed from roles holding the user).
On `pan.sl.role`: `_get_adkar_profile()` → list of five floats (average over
the role's users of each user's latest round) or `False` when no scores.

### Blueprint (open format) — `models/blueprint.py`
AbstractModel `pan.sl.blueprint` with `@api.model export_blueprint()` → dict
and `@api.model import_blueprint(data)` → summary dict. Idempotent: records
match on `code`, existing ones are updated, nothing is deleted. Unknown codes
in references raise `UserError` naming the code. Format: see
`docs/blueprint-format.md`.
TransientModel `pan.sl.blueprint.wizard`: `mode` (`import|export|template`),
`file` (Binary), `filename`, `template` (Selection of files in
`data/blueprints/`), `result` (Text). Buttons `action_import`,
`action_export`, `action_load_template`.

### Map data — `models/map_data.py`
On `pan.sl.activity`: `@api.model get_map_data()` → dict
`{phases:[{id,name,code,apps:[str]}], roles:[{id,name,is_external,users:[str],adkar:[5 floats]|false}],
activities:[{id,name,code,role_id,phase_id,choice_state,rung,open_point,scenario_ids:[int],model:str|false}],
scenarios:[{id,code,name,description,open_point,rung,activity_ids:[ordered ints]}]}`.
One call, no N+1 (read in batches).
`@api.model get_map_details()` → `{activity_id: {tasks:[{id,name,rung}], click_path_first_line:str}}`,
loaded in parallel by the map for the Detail stop (one search for all tasks).

**Clash** (counter on the map): an activity whose choice is `revised`, or
`fixed` while it still has an open point. Both mean "decided, but not settled".

## XML ids (binding)

| Id | Owner file |
|---|---|
| `group_blueprint_user`, `group_blueprint_manager` (implies user) | `security/security.xml` |
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

Menu: Blueprint → Company map (default) · Model (Chains, Processes,
Activities, Scenarios, Phases, Roles) · People (ADKAR scores) · Blueprint
(Import / export). Managers see Model and import; users see map, read model.

## Client action — `static/src/map/`
OWL component registered in `registry.category("actions")` as
`pan_sl_blueprint_map`. Loads `get_map_data` once. SVG company map with the
fixed orientation. Controls in one row: scenario select (all / one),
colour by (Choices / Progress / People ADKAR), zoom as a slider (range input, fit
at the left end, up to 4x; mouse wheel and pinch move the same slider; label
"Zoom"). No +/− buttons.

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
state) with a button that opens the activity form. Uses Odoo's own CSS
variables so it matches the backend in light and dark. Empty state when
there are no activities: explain and offer "Load a template".

## Conventions
- Odoo 19: `list` views (not `tree`), `invisible=`/`readonly=` expressions,
  no `attrs`. English source strings, Dutch in `i18n/nl.po`.
- Field help on every field. No hardcoded fallbacks; raise clear errors.
- Tests: `tests/`, `TransactionCase`, tagged `post_install`, `-at_install`.
