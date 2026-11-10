{
    "name": "Odoo Self Learning: Blueprint",
    "summary": "Map the business (chains, processes, activities, roles) and track implementation readiness on one company map",
    "description": """
Odoo Self Learning: Blueprint
=============================

Describe a company as one model (value chain, process, activity, click path),
put Odoo over it (apps, models, access groups) and track readiness per
activity: choices made, Odoo ready, people ready (ADKAR), live.

Project tasks get three fields (scenario, activities, rung). One company map
shows it all, filtered by scenario and coloured by choices, progress or ADKAR.
Import and export the whole model as an open JSON blueprint.
    """,
    "author": "Pantalytics",
    "website": "https://pantalytics.com",
    "category": "Services/Project",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["project", "mail", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/default_structure.xml",
        "views/structure_views.xml",
        "views/activity_views.xml",
        "views/scenario_views.xml",
        "views/adkar_views.xml",
        "views/project_task_views.xml",
        "views/blueprint_views.xml",
        "views/map_action.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pan_self_learning_blueprint/static/src/map/**/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
