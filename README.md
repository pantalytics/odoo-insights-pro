# Insights Pro

Product analytics for the **Odoo 19** backend, powered by [PostHog](https://posthog.com).

Insights Pro is a lightweight asset module that injects PostHog into
`web.assets_backend` so you can see where users get stuck — which screens they
open, where they drop off, which flows are slow.

## Highlights

- **Active on install.** This build ships with the Pantalytics EU key pre-filled
  and the master switch on, so a plain install starts sending data immediately.
  It is key-gated, not off-by-default: remove the key (or flip the switch off)
  and it goes fully dormant — no script, no requests.
- **Pseudonymous identity.** Users are identified as `db#uid` (database name +
  user id). Never a name, never an email.
- **Per-customer workspace.** Every database reports under its own PostHog group,
  so data never mixes between customers.
- **Session replay is on by default.** Typed input is always masked (`maskAllInputs`
  is hard-coded on), so what users type never leaves the browser. Autocapture also
  ignores element values.

> **Read this before installing for a customer.** With the shipped defaults,
> session replay records the rendered backend — and `mask_all_text` is `False`,
> so *visible* text is not masked. Recordings will contain whatever is on screen,
> including personal data in list and form views. If that is not what you want,
> set `pan_insights_pro.disable_session_recording` to `True` (no replay) or
> `pan_insights_pro.mask_all_text` to `True` (replay with all text hidden) before
> or at install time.

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
| `pan_insights_pro.posthog_project_key` | `phc_sfCT…SQrtu` | PostHog public project key. Empty = dormant. |
| `pan_insights_pro.posthog_host` | `https://eu.i.posthog.com` | PostHog instance URL. |
| `pan_insights_pro.mask_all_text` | `False` | `True` also masks all *visible* text in recordings. Typed input is masked either way. |
| `pan_insights_pro.disable_session_recording` | `False` | `True` turns session replay off. |

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
