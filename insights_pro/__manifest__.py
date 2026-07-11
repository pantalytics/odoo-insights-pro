# -*- coding: utf-8 -*-
{
    "name": "Insights Pro",
    "summary": "Product analytics for the Odoo backend, powered by PostHog",
    "description": """
Insights Pro
============

A lightweight, privacy-conscious asset module that injects PostHog into the
Odoo backend so you can see where users get stuck.

Key characteristics
--------------------
* **Dormant by default** — does nothing until a real PostHog project key is set
  under *Settings > Insights Pro*.
* **Pseudonymous identity** — users are identified as ``db#uid`` (database name
  plus user id), never by name or email.
* **Per-customer workspace** — each database reports under its own group so data
  never mixes between customers.
* **Privacy first** — all input text is masked, autocapture keeps element text
  out of events, and session replay is disabled.
    """,
    "author": "Pantalytics",
    "website": "https://pantalytics.com",
    "category": "Productivity/Analytics",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [
        "data/ir_config_parameter.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "insights_pro/static/src/js/posthog_loader.js",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
