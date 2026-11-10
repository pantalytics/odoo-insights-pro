"""Fill a development database with demo progress for the company map.

Run inside `odoo-bin shell -d <db>` after loading the generic template, with
the database name confirmed in an environment variable:
    BLUEPRINT_SEED_OK=<db> odoo-bin shell -d <db>
    >>> exec(open("tools/seed_demo.py").read())
Creates demo people (contacts, no logins) per internal role, one task per
activity with a progress step and hours, and ADKAR scores, then commits. Development
only: the script refuses to run, and creates nothing, unless
BLUEPRINT_SEED_OK equals the name of the connected database.

Every internal role gets three scored demo people, also a role that already
has people (they may have no score), because a role's ADKAR band only shows
once at least three of its people have a score. The latest scores differ per role
(low, medium, high), so the role panel shows each band. Rerunning creates
nothing new: demo people are found again by their reference.
"""
import os

from odoo.fields import Command

SEED_GUARD_VARIABLE = "BLUEPRINT_SEED_OK"
DEMO_PROJECT_NAME = "Blueprint demo"
DEMO_PEOPLE_PER_ROLE = 3
# Latest-round score per role, in turn: low, medium, high band.
DEMO_BAND_BASES = (2, 3, 4)

roles = env["pan.sl.role"].search([("is_external", "=", False)])
activities = env["pan.sl.activity"].search([], order="phase_id, sequence, id")
activities_to_seed = activities.filtered(lambda activity: not activity.task_ids)
Partners = env["res.partner"].with_context(active_test=False)
planned_refs = [f"demo_{role.code}_{number}" for role in roles for number in range(1, DEMO_PEOPLE_PER_ROLE + 1)]
existing_refs = set(Partners.search([("ref", "in", planned_refs)]).mapped("ref"))

print(f"Database: {env.cr.dbname}")
print(
    f"Plan: {len(planned_refs) - len(existing_refs)} new demo contacts, "
    f"{len(existing_refs)} existing demo contacts kept, on {len(roles)} internal roles, "
    f"up to {len(planned_refs) * 2} ADKAR scores, "
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
for index, role in enumerate(roles):
    latest_base = DEMO_BAND_BASES[index % len(DEMO_BAND_BASES)]
    for number in range(1, DEMO_PEOPLE_PER_ROLE + 1):
        ref = f"demo_{role.code}_{number}"
        partner = Partners.search([("ref", "=", ref)], limit=1)
        if not partner:
            partner = Partners.create({"name": f"Demo {role.name} {number}", "ref": ref, "is_company": False})
        elif not partner.active:
            partner.active = True
        role.partner_ids = [Command.link(partner.id)]
        for round_, base in ((1, max(1, latest_base - 1)), (2, latest_base)):
            if env["pan.sl.adkar.score"].search_count([("partner_id", "=", partner.id), ("round", "=", round_)]):
                continue
            env["pan.sl.adkar.score"].create(
                {
                    "partner_id": partner.id,
                    "round": round_,
                    "awareness": min(5, base + 1),
                    "desire": min(5, base + number % 2),
                    "knowledge": base,
                    "ability": base,
                    "reinforcement": min(5, base + 1),
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
