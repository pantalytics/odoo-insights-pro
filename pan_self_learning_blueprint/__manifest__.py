{
    "name": "Odoo Self Learning: Blueprint",
    "summary": "Map the business (chains, processes, activities, roles) and track implementation readiness on one company map",
    "description": """
Odoo Self Learning: Blueprint
=============================

Describe a company as one model (value chain, process, activity, click path),
put Odoo over it (apps, models, access groups) and track readiness per
activity: choices made, Odoo ready, people ready (ADKAR), live.

Project tasks get three fields (scenario, activities, rung). An activity is
as far as its least advanced task, the same for every user; cancelled tasks
do not count. Planned and spent hours per activity and scenario are summed
from the linked tasks (allocated hours and timesheets stay on the tasks; that
is why the module depends on Timesheets).

One company map shows it all, filtered by scenario and coloured by choices,
progress or ADKAR, and shows per activity and phase who still needs
training. ADKAR scores are personal: users see their own, administrators see
all; a role average needs at least three scored users.

Import and export the whole model as an open JSON blueprint. Loading the
bundled template again only fills what is missing and never overwrites the
company's own choices.
    """,
    "author": "Pantalytics",
    "website": "https://pantalytics.com",
    "category": "Services/Project",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "depends": ["project", "hr_timesheet", "mail", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/adkar_rules.xml",
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
