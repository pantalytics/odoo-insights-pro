# -*- coding: utf-8 -*-
{
    "name": "Insights Pro",
    "summary": "Product analytics for the Odoo backend, powered by PostHog",
    "description": """
Insights Pro
============

A lightweight asset module that injects PostHog into the Odoo backend so you
can see where users get stuck.

Key characteristics
--------------------
* **Active on install** — ships enabled, with the Pantalytics EU project key
  pre-filled, so a plain install starts sending data immediately. Clear the key
  (or flip the switch off) under *Settings > Insights Pro* to make it dormant.
* **Pseudonymous identity** — users are identified as ``db#uid`` (database name
  plus user id), never by name or email.
* **Per-customer workspace** — each database reports under its own group so data
  never mixes between customers.
* **Session replay is on by default.** Typed input is always masked, so what
  users type never leaves the browser. Visible text is *not* masked unless you
  enable *Mask all text* — meaning recordings capture whatever is on screen,
  including customer data rendered in list and form views.
    """,
    "author": "Pantalytics",
    "website": "https://pantalytics.com",
    "category": "Productivity/Analytics",
    "version": "19.0.1.2.0",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [
        "data/ir_config_parameter.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pan_insights_pro/static/src/js/posthog_loader.js",
        ],
    },
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
