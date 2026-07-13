# Insights Pro

Product analytics for the **Odoo 19** backend, powered by [PostHog](https://posthog.com).

Insights Pro is a lightweight asset module that injects PostHog into
`web.assets_backend` so you can see where users get stuck — which screens they
open, where they drop off, which flows are slow — without shipping any personal
data off the browser.

## Highlights

- **Key-gated.** Tracking only runs when a PostHog project key is set. Remove
  the key (or flip the switch off) and it goes fully dormant — no script, no
  requests. This build ships with the Pantalytics EU key pre-filled.
- **Pseudonymous identity.** Users are identified as `db#uid` (database name +
  user id). Never a name, never an email.
- **Per-customer workspace.** Every database reports under its own PostHog group,
  so data never mixes between customers.
- **Privacy first.** All input text is masked, autocapture ignores element
  values, and session replay is disabled — all toggleable, all on by default.

## Installation

The module ships **pre-connected** to the Pantalytics PostHog project on
EU Cloud (`https://eu.i.posthog.com`), so a plain install starts sending data
right away.

1. Copy the `pan_insights_pro` folder into your Odoo addons path.
2. Update the apps list and install **Insights Pro**.
3. Reload the backend. That's it.

To point at a **different** PostHog project, go to **Settings → Insights Pro**
(or the Insights Pro app) and change the **project key** (`phc_…`) and **host**
(`https://eu.i.posthog.com` for EU Cloud, `https://us.i.posthog.com` for US).
You can also flip the master switch off there to make the module dormant again.

## Configuration

Everything is stored as system parameters, so it can also be managed via
**Settings → Technical → System Parameters** or set during deployment:

| Parameter | Default | Meaning |
|---|---|---|
| `pan_insights_pro.enabled` | `True` | Master switch. |
| `pan_insights_pro.posthog_project_key` | `phc_gHeP…DzQhS` | PostHog public project key. Empty = dormant. |
| `pan_insights_pro.posthog_host` | `https://eu.i.posthog.com` | PostHog instance URL. |
| `pan_insights_pro.mask_all_text` | `True` | Mask all captured input text. |
| `pan_insights_pro.disable_session_recording` | `True` | Keep session replay off. |

## How it works

On every backend page load, `ir.http.session_info` adds an `pan_insights_pro` block
to the session (key, host, pseudonymous `distinct_id`, workspace, privacy
flags). The backend asset `posthog_loader.js` reads it and — only when a key is
present — bootstraps PostHog, identifies the pseudonymous user, and assigns the
database as a `workspace` group.

## Notes

- The loader fetches `array.js` from your PostHog host. If your backend runs
  under a strict Content-Security-Policy, allow your PostHog host in
  `script-src`/`connect-src`.
- License: LGPL-3.
