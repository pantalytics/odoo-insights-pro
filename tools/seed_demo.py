"""Fill a development database with demo progress for the company map.

Run inside `odoo-bin shell -d <db>` after loading the generic template:
    exec(open("tools/seed_demo.py").read())
Creates demo users per internal role, one task per activity with a rung and
hours, and ADKAR scores. Development only: never run on a customer database.
"""
from odoo.fields import Command

project = env["project.project"].search([("name", "=", "Blueprint demo")], limit=1) or env[
    "project.project"
].create({"name": "Blueprint demo"})
roles = env["pan.sl.role"].search([("is_external", "=", False)])
for index, role in enumerate(roles, start=1):
    if not role.user_ids:
        user = env["res.users"].create({"name": f"Demo {role.name}", "login": f"demo_{role.code}"})
        role.user_ids = [Command.link(user.id)]
        for round_, base in ((1, 2), (2, 3)):
            env["pan.sl.adkar.score"].create(
                {
                    "user_id": user.id,
                    "round": round_,
                    "awareness": min(5, base + 1),
                    "desire": min(5, base + (index % 2)),
                    "knowledge": base,
                    "ability": max(1, base - 1 + (index % 3 == 0)),
                    "reinforcement": base,
                }
            )
for index, activity in enumerate(env["pan.sl.activity"].search([], order="phase_id, sequence, id")):
    if activity.task_ids:
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
