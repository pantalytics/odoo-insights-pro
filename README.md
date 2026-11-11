# Odoo Self Learning

Product analytics for the **Odoo 19** backend, powered by [PostHog](https://posthog.com).

Odoo Self Learning is a lightweight asset module that injects PostHog into
`web.assets_backend` so you can see where users get stuck: which screens they
open, where they drop off, which flows are slow. On the server it reports
errors by type and stack, never their text. No personal data leaves Odoo.

## Highlights

- **Dormant until connected.** Nothing is sent until an administrator presses
  *Connect to Pantalytics* in Settings. The PostHog project key and host arrive
  in a signed entitlement from Pantalytics; no key is typed, shipped or stored
  in a data file. Disconnect (in Odoo or in the Pantalytics panel) and the
  module goes quiet at its next daily check-in.
- **Pseudonymous identity.** Users are identified as `db#uid` (database name +
  user id). Never a name, never an email.
- **Per-customer workspace.** Every database reports under its own PostHog
  group, keyed by the database uuid Pantalytics knows it by, so data never
  mixes between customers.
- **Privacy first.** All input text is masked, autocapture ignores element
  values, and session replay can be switched off per instance.
- **Server errors.** Tracebacks, failed scheduled actions and other `ERROR`
  log lines go to PostHog error tracking as the exception type, the stack
  (module, function, file, line) and the log message's format string. Never
  the error text, the message's values or local variables. Same project and
  `workspace` group as the browser events.

## Installation

1. Copy the `pan_self_learning` folder into your Odoo addons path.
2. Update the apps list and install **Odoo Self Learning**.
3. Go to **Settings, Odoo Self Learning** and press **Connect to Pantalytics**.
   A tab opens on the Pantalytics panel with the code filled in. Sign in,
   check that the page names this Odoo, press Approve, then come back.

That is the whole setup. The module needs the `cryptography` and `requests`
Python packages, both of which ship with Odoo.

## Configuration

Privacy switches on the same settings page, stored as system parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `pan_self_learning.enabled` | `True` | Master switch. Off keeps the module dormant even when connected. |
| `pan_self_learning.mask_all_text` | `False` | Also mask all visible text in recordings. |
| `pan_self_learning.disable_session_recording` | `False` | Turn session replay off for this instance. |
| `pan_self_learning.server_errors` | `True` | Report server errors (type and stack only). |

For a staging server, two environment variables override where the module
talks to and which signature it trusts: `PAN_SELF_LEARNING_SERVER_URL` and
`PAN_SELF_LEARNING_PUBLIC_KEY`. Never a settings field.

## How it works

Connecting is the device flow Mail Pro uses: Odoo asks the Pantalytics server
for a pairing code, the administrator approves it in their browser, and Odoo
collects an installation key. Once a day the module sends a heartbeat (the
database uuid and two version strings, nothing else) and gets back a signed
entitlement: the PostHog project key and host, whether sessions may be
recorded, and whether server errors may be reported. The entitlement is only stored when its Ed25519 signature checks
out against the public key shipped in `models/pan_self_learning_link.py` and
its `db_uuid` matches this database.

On every backend page load, `ir.http.session_info` adds a `pan_self_learning`
block to the session (key, host, pseudonymous `distinct_id`, workspace,
privacy flags) read from that entitlement. The backend asset
`posthog_loader.js` reads it and, only when a key is present, bootstraps
PostHog, identifies the pseudonymous user, and assigns the database as a
`workspace` group.

The server side lives in `pantalytics/odoo-mcp-pro-admin`
(`mcp_server_odoo_admin/apps/self_learning.py`).

Server errors: a logging handler on the root logger puts every `ERROR`
record logged inside a database on a bounded queue. One background thread per
process reads that database's entitlement through its own cursor, sends at
most one event per error kind per minute to `<host>/i/v0/e/`, and drops
anything it cannot send. Errors logged outside a database (server start, the
database manager) are not reported. The code is `server_errors.py`.

## Notes

- The loader fetches `array.js` from the PostHog host named in the
  entitlement. If your backend runs under a strict Content-Security-Policy,
  allow that host in `script-src`/`connect-src`.
- Upgrading from 19.0.1.x removes the pre-filled project key; press Connect to
  Pantalytics once to resume.
- License: LGPL-3.

## Blueprint module

`pan_self_learning_blueprint` is a second, independent module in this
repository: a simple app that gives insight into an Odoo implementation and
its continuous improvement, inside the Projects app. Everything is a project
task; the company map is another view on the tasks of one project
(`docs/data-model.md`).

### What it does

- **A project is a map.** Its roles are the rows, the shared phases the
  columns. A task with a role and a phase is one chip.
- **Flows.** A parent task is a flow (a test scenario); its subtasks are the
  route. Its Tested % is the share of subtasks at Tested or further; archived
  subtasks count, cancelled ones do not.
- **Progress is the stage.** Every stage carries a progress step: Open,
  Decided, Built, Tested, Trained, Live; a task's progress is its stage's,
  so the kanban and the map agree. Choices are discussed in the task chatter,
  click paths live in the description, hours are the task's allocated hours
  and timesheets.
- **People.** Roles list their people as contacts, so people without a login
  count too. ADKAR scores are personal: users see only their own,
  administrators see all. A role shows one band (high, medium or low) once
  three of its people have a score, never a number.
- **Open format.** A project imports and exports as one JSON blueprint
  (`docs/blueprint-format.md`). Importing again updates and never deletes.
  A blueprint holds no personal data.

### Install

1. Put the `pan_self_learning_blueprint` folder on your Odoo 19 addons path.
2. Install **Odoo Self Learning: Blueprint**. It depends on `project`,
   `hr_timesheet`, `mail` and `web`.
3. Under **Settings, Users**: *Blueprint / User* opens maps, sets role, phase
   and stage on tasks and reads their own ADKAR scores; *Blueprint /
   Administrator* edits phases and roles, sees all scores and loads, imports
   or exports. System administrators get Administrator.

### Use

- **Projects, Map** opens the map (with several mapped projects, pick one
  first). A project's form and kanban card have a **Map** button too. Tasks
  without a role or a phase are not on the grid; their flow lists them.
- On the project form (administrators): **Load template** fills the project
  from the bundled template and gives it the six progress stages (again: only
  what is empty), **Import** reads a blueprint file, **Export** downloads
  `blueprint.json`.
- **Projects, Configuration** holds the shared phases, the roles of all
  projects and the ADKAR scores.

Upgrading to 2.1 resets every task's progress to Open (it now follows the
stage); load the template again to give a project the six progress stages.

Upgrading from 1.x removes chains, processes, activities and scenarios and
the shared roles; load the template in a project to get them back as tasks.

### For agents

Over MCP, XML-RPC or JSON-RPC, as a Project user unless noted:

- **Read the picture**: `project.project.get_blueprint_map_data()` on one
  project returns phases, roles (with people and open training), flows (worst
  first, with deadline) and every task (contract in `docs/data-model.md`).
  `project.project.get_blueprint_map_projects()` lists the mapped projects.
- **Move progress**: write `stage_id` (a stage whose `pan_rung` is the step),
  `pan_role_id` and `pan_phase_id` on `project.task`.
- **Blueprint** (administrators): `pan.sl.blueprint.export_blueprint(project_id)`
  and `pan.sl.blueprint.import_blueprint(project_id, data)`.

### UI check

`tools/ui_check.mjs` is a Playwright script for a running local Odoo with the
module installed and the template loaded. It opens the map as admin/admin on
desktop and mobile and checks the zoom stops, scenarios, colour modes, side
panels, keyboard, refresh and breadcrumb restore. It exits non-zero on any
page or console error.

```bash
DB=mydb OUT=/tmp/blueprint-ui node tools/ui_check.mjs
```
