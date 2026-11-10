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
repository. It describes a company as one model and tracks how far the Odoo
implementation is, per activity, on one company map.

### What it does

- **Three pillars, one atom.** The business (what we do), the system (what
  Odoo must do) and the people (can they do it) meet in the **activity**: one
  role does one thing to one Odoo document.
- **Hierarchy.** Chain (L1) → process (L2) → activity (L3) → click path (L4).
  A **scenario** is a test route across processes.
- **Readiness.** Project tasks get a scenario, the activities they move
  forward and a rung: 0 Open, 1 Decided, 2 Built, 3 Tested, 4 Trained,
  5 Live. An activity is as far as its least advanced task, counted over all
  its tasks (also the ones you cannot open) so everyone sees the same
  progress; cancelled tasks are left out. Choices per activity go proposal →
  provisional → fixed → revised, with the history in the chatter.
- **Hours.** Planned (allocated) and spent (timesheet) hours per activity and
  scenario, summed from the linked tasks, cancelled tasks left out. A task on
  several activities counts for each of them, and once per scenario.
  Estimates and timesheets stay on the tasks.
- **People.** The map shows, per activity and per phase, which users of a
  role still need training (an activity counts as trained from rung 4).
  ADKAR scores (awareness, desire, knowledge, ability, reinforcement) are
  personal: users see only their own, administrators see all of them and the
  notes. The map shows a role's average only once at least three of its
  users have a score.
- **Open format.** The whole model imports and exports as one JSON blueprint
  (`docs/blueprint-format.md`). Records match on `code`, so importing again
  updates and never deletes. A blueprint holds no personal data.

It works the same for a company on its own Odoo and for an implementation
partner working in a client's database: there is no partner or customer
concept in the model, and nothing ends at go-live.

### Install

1. Put the `pan_self_learning_blueprint` folder on your Odoo 19 addons path.
2. Update the apps list and install **Odoo Self Learning: Blueprint**. It
   depends on `project`, `hr_timesheet` (for planned and spent hours), `mail`
   and `web`. `hr_timesheet` also installs the Timesheets and Employees apps
   (with analytic accounting), so on a database that does not use them yet
   the install adds them.
3. Give people access under **Settings, Users**: *Blueprint / User* opens the
   map and reads the model and their own ADKAR scores, *Blueprint /
   Administrator* edits the model, records everyone's ADKAR scores and notes,
   and imports or exports blueprints. System administrators get
   Administrator.

### Load the template

Open **Blueprint, Import / export, Load a template, import or export**,
choose *Load a template* (the bundled template in `data/blueprints/` is
preselected) and press **Load template**. Models of apps that are not
installed are skipped; the result names the apps to install, with a button
to the Apps list. Loading the template again is safe: it only creates what is
missing and fills empty fields and links, and keeps your own choices, click
paths, open points and scenario steps. So install the missing apps, then load
the template again to link them.
To use your own blueprint, choose *Import a file*; that import is strict and
refuses a model that is not installed. *Export* downloads the current model
as `blueprint.json`, ready to keep in git.

### The company map

**Blueprint, Company map** shows everything in one picture with a fixed
orientation: phases (Odoo's document chain) from left to right; from top to
bottom a progress band, the role lanes with their activities (external roles
such as customer and supplier at the edges) and an Odoo band with the apps per
phase.

- **Scenario**: show all activities or one scenario; the route is drawn with
  numbered steps and the other activities are dimmed.
- **Colour by**: choices, progress (rung) or people (ADKAR). Every colour
  also has a shape, so status never depends on colour alone.
- **Zoom**: more detail appears as you zoom in, from one block per role and
  phase up to the linked tasks under each activity.
- **Clashes**: a choice that is decided but not settled (revised, or fixed
  with an open point) is outlined in red. Click the clash counter to show
  only the clashes.
- **Side panel**: click an activity to see its role, scenarios, choice
  state, rung, open point and which users still need training, with a button
  to open the activity form. Click a phase name to see who still needs
  training in that phase.
- **Keyboard**: arrow keys pan, `+`/`-` zoom, Home fits the map, Tab walks
  the activities. Zoom, position and selection come back when you return
  through the breadcrumb.

With no activities yet, the map explains itself and offers *Load a template*.

### UI check

`tools/ui_check.mjs` is a Playwright script for a running local Odoo with the
module installed and a template loaded. It logs in as admin/admin, opens the
map, takes desktop and mobile screenshots, selects a scenario, opens the side
panel of the first activity, checks keyboard navigation and the state
restore after the breadcrumb, and exits non-zero on any page or console
error or missing element.

```bash
DB=mydb OUT=/tmp/blueprint-ui node tools/ui_check.mjs
```
