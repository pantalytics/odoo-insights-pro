{
    "name": "Odoo Self Learning: Blueprint",
    "summary": "A company map per project: every activity is a task with a role, a phase and a progress",
    "description": """
Odoo Self Learning: Blueprint
=============================

Everything is a project task. A project with the Map switch on (project
Settings) is a company map: "Map" is a view of the project's tasks next to
Kanban and List, with Odoo's search bar, and Projects > Map lists those
projects. Its roles are the rows, the shared phases the
columns; a band on top answers on schedule, still to do, flows, training
and choices. A task with a role
and a phase is one chip on the map. Progress is the stage: each stage
carries a step (Open, Decided, Built, Tested, Trained, Live), so the kanban
and the map always agree. A parent task is a flow (a test scenario); its
subtasks are the route, shown as a swimlane with arrows; its Tested % is the share of subtasks at Tested
or further. Hours are the task's allocated hours and timesheets.

People are contacts, so someone without a login can hold a role and be
scored. ADKAR scores are personal: users see their own, administrators see
all; the map shows per role only a band for the weakest element, and only
when at least three people of the role have a score.

Administrators fill a project from the bundled template, or import and
export it as an open JSON blueprint, which also gives the project the six
progress stages. Loading the template only fills what is empty; import
creates and updates, never deletes.
    """,
    "author": "Pantalytics",
    "website": "https://pantalytics.com",
    "category": "Services/Project",
    "version": "19.0.2.6.0",
    "license": "LGPL-3",
    "depends": ["project", "hr_timesheet", "mail", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/adkar_rules.xml",
        "security/role_rules.xml",
        "views/structure_views.xml",
        "views/adkar_views.xml",
        "views/project_task_type_views.xml",
        "views/project_task_views.xml",
        "views/blueprint_views.xml",
        "views/map_action.xml",
        "views/project_project_views.xml",
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
