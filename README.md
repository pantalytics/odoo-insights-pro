# Insights Pro

Product analytics for the **Odoo 19** backend, powered by [PostHog](https://posthog.com).

Insights Pro is a lightweight asset module that injects PostHog into
`web.assets_backend` so you can see where users get stuck — which screens they
open, where they drop off, which flows are slow — without shipping any personal
data off the browser.

## Highlights

- **Dormant by default.** The module does nothing until you set a PostHog
  project key. No key → no script, no requests, no-op.
- **Pseudonymous identity.** Users are identified as `db#uid` (database name +
  user id). Never a name, never an email.
- **Per-customer workspace.** Every database reports under its own PostHog group,
  so data never mixes between customers.
- **Privacy first.** All input text is masked, autocapture ignores element
  values, and session replay is disabled — all toggleable, all on by default.

## Installation

1. Copy the `insights_pro` folder into your Odoo addons path.
2. Update the apps list and install **Insights Pro**.
3. Go to **Settings → Insights Pro** (or the Insights Pro app), paste your
   PostHog **project key** (`phc_…`) and confirm the **host**
   (`https://eu.i.posthog.com` for EU Cloud, `https://us.i.posthog.com` for US).
4. Reload the backend. That's it.

## Configuration

Everything is stored as system parameters, so it can also be managed via
**Settings → Technical → System Parameters** or set during deployment:

| Parameter | Default | Meaning |
|---|---|---|
| `insights_pro.enabled` | `True` | Master switch. |
| `insights_pro.posthog_project_key` | *(empty)* | PostHog public project key. Empty = dormant. |
| `insights_pro.posthog_host` | `https://eu.i.posthog.com` | PostHog instance URL. |
| `insights_pro.mask_all_text` | `True` | Mask all captured input text. |
| `insights_pro.disable_session_recording` | `True` | Keep session replay off. |

## How it works

On every backend page load, `ir.http.session_info` adds an `insights_pro` block
to the session (key, host, pseudonymous `distinct_id`, workspace, privacy
flags). The backend asset `posthog_loader.js` reads it and — only when a key is
present — bootstraps PostHog, identifies the pseudonymous user, and assigns the
database as a `workspace` group.

## Notes

- The loader fetches `array.js` from your PostHog host. If your backend runs
  under a strict Content-Security-Policy, allow your PostHog host in
  `script-src`/`connect-src`.
- License: LGPL-3.
