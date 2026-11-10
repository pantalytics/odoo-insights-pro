"""Fill a development database with demo progress for the company map.

Run inside `odoo-bin shell -d <db>` after loading the generic template, with
the database name confirmed in an environment variable:
    BLUEPRINT_SEED_OK=<db> odoo-bin shell -d <db>
    >>> exec(open("tools/seed_demo.py").read())
Creates demo users per internal role (internal users: a paid seat on
Enterprise), one task per activity with a rung and hours, and ADKAR scores,
then commits. Development only: the script refuses to run, and creates
nothing, unless BLUEPRINT_SEED_OK equals the name of the connected database.

Each role gets three demo users, because the company map only shows a role's
ADKAR profile once at least three of its users have a score.
"""
import os

from odoo.fields import Command

SEED_GUARD_VARIABLE = "BLUEPRINT_SEED_OK"
DEMO_PROJECT_NAME = "Blueprint demo"
DEMO_USERS_PER_ROLE = 3

roles = env["pan.sl.role"].search([("is_external", "=", False)])
roles_to_seed = roles.filtered(lambda role: not role.user_ids)
activities = env["pan.sl.activity"].search([], order="phase_id, sequence, id")
activities_to_seed = activities.filtered(lambda activity: not activity.task_ids)
Users = env["res.users"].with_context(active_test=False)
planned_logins = [
    f"demo_{role.code}_{number}" for role in roles_to_seed for number in range(1, DEMO_USERS_PER_ROLE + 1)
]
existing_logins = set(Users.search([("login", "in", planned_logins)]).mapped("login"))

print(f"Database: {env.cr.dbname}")
print(
    f"Plan: {len(planned_logins) - len(existing_logins)} new internal demo users, "
    f"{len(existing_logins)} existing demo users linked again, "
    f"up to {len(planned_logins) * 2} ADKAR scores, "
    f"{len(activities_to_seed)} tasks in project '{DEMO_PROJECT_NAME}'."
)
if os.environ.get(SEED_GUARD_VARIABLE) != env.cr.dbname:
    env.cr.rollback()
    raise SystemExit(
        f"Refused: set {SEED_GUARD_VARIABLE}={env.cr.dbname} to confirm this is a development database. "
        "Nothing was created."
    )

project = env["project.project"].search([("name", "=", DEMO_PROJECT_NAME)], limit=1) or env[
    "project.project"
].create({"name": DEMO_PROJECT_NAME})
for index, role in enumerate(roles, start=1):
    if role not in roles_to_seed:
        continue
    for number in range(1, DEMO_USERS_PER_ROLE + 1):
        login = f"demo_{role.code}_{number}"
        user = Users.search([("login", "=", login)], limit=1)
        if not user:
            user = Users.create({"name": f"Demo {role.name} {number}", "login": login})
        elif not user.active:
            user.active = True
        role.user_ids = [Command.link(user.id)]
        for round_, base in ((1, 2), (2, 3)):
            if env["pan.sl.adkar.score"].search_count([("user_id", "=", user.id), ("round", "=", round_)]):
                continue
            env["pan.sl.adkar.score"].create(
                {
                    "user_id": user.id,
                    "round": round_,
                    "awareness": min(5, base + 1),
                    "desire": min(5, base + ((index + number) % 2)),
                    "knowledge": base,
                    "ability": max(1, base - 1 + ((index + number) % 3 == 0)),
                    "reinforcement": base,
                }
            )
for index, activity in enumerate(activities):
    if activity not in activities_to_seed:
        continue
    rung = str(max(0, 5 - (activity.phase_id.sequence // 10) + (index % 2)) % 6)
    env["project.task"].create(
        {
            "name": f"Set up: {activity.name}",
            "project_id": project.id,
            "pan_activity_ids": [Command.link(activity.id)],
            "pan_scenario_id": activity.scenario_ids[:1].id,
            "pan_rung": rung,
            "allocated_hours": 2 + index % 5,
        }
    )
env.cr.commit()
print("seeded", env["project.task"].search_count([("project_id", "=", project.id)]), "tasks")
