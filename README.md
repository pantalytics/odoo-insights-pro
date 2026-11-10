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
its continuous improvement. The company sits on one map you zoom like Google
Maps, with its people, training and progress, on top of the Projects app.

### What it does

- **One atom.** The business (what we do), the system (what Odoo must do)
  and the people (can they do it) meet in the **activity**: one role does one
  thing to one Odoo document.
- **Hierarchy.** Chain → process → activity → click path. A **scenario** is a
  test route across processes; its Tested % is the share of its activities
  that are tested.
- **Progress.** Project tasks get a scenario, the activities they move
  forward and a progress: Open, Decided, Built, Tested, Trained, Live. An
  activity is as far as its least advanced task, the same for everyone.
  Archived tasks count; cancelled tasks do not. Choices per activity go
  proposal → provisional → fixed → revised, with the history in the chatter.
- **Hours.** Planned and spent hours per activity and scenario, summed from
  the linked tasks.
- **People.** Roles list their people as contacts, so people without a login
  count too. ADKAR scores are personal: users see only their own,
  administrators see all. A role shows one band (high, medium or low) once
  three of its people have a score, never a number.
- **Open format.** The whole model imports and exports as one JSON blueprint
  (`docs/blueprint-format.md`). Records match on `code`, so importing again
  updates and never deletes. A blueprint holds no personal data.

### Install

1. Put the `pan_self_learning_blueprint` folder on your Odoo 19 addons path.
2. Install **Odoo Self Learning: Blueprint**. It depends on `project`,
   `hr_timesheet`, `mail` and `web`.
3. Under **Settings, Users**: *Blueprint / User* opens the map and reads the
   model and their own ADKAR scores; *Blueprint / Administrator* edits
   everything and imports or exports. System administrators get
   Administrator.

### Load, import and export

Under **Blueprint, Import / export** (administrators):

- **Load template** loads the bundled template and opens the map with a
  summary. Loading it again only fills what is missing and keeps your own
  work. After installing a missing app, load it again to link it.
- **Import file** imports your own blueprint. It is strict: an unknown model
  refuses the file. Files above 5 MB or with more than 5,000 records are
  refused.
- **Export** downloads the current model as `blueprint.json`.

### The company map

**Blueprint, Company map**: phases from left to right; from top to bottom
the Tested band, the role lanes (customer and supplier at the edges) and the
Odoo apps per phase. A phase names its apps by technical module name
(`sale_management`); the map shows the app's name, greyed out when it is not
installed.

- **Zoom stops**: Company, Activities, Status, Detail. More appears per stop,
  up to the linked tasks.
- **Scenario**: all activities, or one scenario with its numbered route,
  zoomed so the whole route is in view.
- **Colour by**: Choices (settled or not), Progress, or Training (trained, or
  still to train). The legend shows only the active mode.
- **Side panel**: an activity shows chain and process, role, training (who
  still has to be trained), scenarios, choice, progress, hours and open
  point. A role name opens the role: its people, ADKAR band and number of
  activities.
- **Keyboard**: arrow keys pan, `+`/`-` zoom, Home fits, Tab walks the
  activities. Zoom, position, scenario and colour mode survive a page refresh
  and the breadcrumb.

With no activities yet, administrators get one button, *Load template*.

### For agents

Over MCP, XML-RPC or JSON-RPC, as a Blueprint user unless noted:

- **Read the picture**: `pan.sl.activity.get_map_data()` returns chains,
  processes, phases (with apps), roles (people, ADKAR band) and every
  activity with process, chain, role, phase, choice, progress and hours, in
  one call. `get_map_details()` adds the tasks and the first click path line.
- **Read the model**: `pan.sl.blueprint.export_blueprint()` returns the
  blueprint dict (`docs/blueprint-format.md`).
- **Change the model** (administrators):
  `pan.sl.blueprint.import_blueprint(data)` creates and updates by `code` and
  returns a summary. Strict by default.
- **Move progress**: write `pan_rung` (`"0"`..`"5"`) and `pan_activity_ids` on
  `project.task`; activities and scenarios recompute.

### UI check

`tools/ui_check.mjs` is a Playwright script for a running local Odoo with the
module installed and the template loaded. It opens the map as admin/admin on
desktop and mobile and checks the zoom stops, scenarios, colour modes, side
panels, keyboard, refresh and breadcrumb restore. It exits non-zero on any
page or console error.

```bash
DB=mydb OUT=/tmp/blueprint-ui node tools/ui_check.mjs
```
