"""Fill a development database with demo progress for the company map.

Run inside `odoo-bin shell -d <db>`, with the database name confirmed in an
environment variable:
    BLUEPRINT_SEED_OK=<db> odoo-bin shell -d <db>
    >>> exec(open("tools/seed_demo.py").read())
Loads the generic template into the project "Blueprint demo", then gives its
map tasks a progress step and hours, and creates demo people (contacts, no
logins) per internal role with ADKAR scores, then commits. Development
only: the script refuses to run, and creates nothing, unless
BLUEPRINT_SEED_OK equals the name of the connected database.

Every internal role gets three scored demo people, also a role that already
has people (they may have no score), because a role's ADKAR band only shows
once at least three of its people have a score. The latest scores differ per role
(low, medium, high), so the role panel shows each band. Rerunning creates
nothing new: demo people are found again by their reference.
"""
import os
from datetime import timedelta

from odoo import fields
from odoo.fields import Command

SEED_GUARD_VARIABLE = "BLUEPRINT_SEED_OK"
DEMO_PROJECT_NAME = "Blueprint demo"
DEMO_PEOPLE_PER_ROLE = 3
# Latest-round score per role, in turn: low, medium, high band.
DEMO_BAND_BASES = (2, 3, 4)

project = env["project.project"].search([("name", "=", DEMO_PROJECT_NAME)], limit=1)
roles = env["pan.sl.role"].search([("project_id", "=", project.id), ("is_external", "=", False)]) if project else []
Partners = env["res.partner"].with_context(active_test=False)
planned_refs = [f"demo_{role.code}_{number}" for role in roles for number in range(1, DEMO_PEOPLE_PER_ROLE + 1)]
existing_refs = set(Partners.search([("ref", "in", planned_refs)]).mapped("ref"))

print(f"Database: {env.cr.dbname}")
print(
    f"Plan: {len(planned_refs) - len(existing_refs)} new demo contacts, "
    f"{len(existing_refs)} existing demo contacts kept, on {len(roles)} internal roles, "
    f"up to {len(planned_refs) * 2} ADKAR scores, "
    f"the template and demo progress in project '{DEMO_PROJECT_NAME}'."
)
if os.environ.get(SEED_GUARD_VARIABLE) != env.cr.dbname:
    env.cr.rollback()
    raise SystemExit(
        f"Refused: set {SEED_GUARD_VARIABLE}={env.cr.dbname} to confirm this is a development database. "
        "Nothing was created."
    )

project = project or env["project.project"].create({"name": DEMO_PROJECT_NAME})
project.action_blueprint_load_template()
roles = env["pan.sl.role"].search([("project_id", "=", project.id), ("is_external", "=", False)])
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
tasks = env["project.task"].search(
    [("project_id", "=", project.id), ("child_ids", "=", False), ("pan_rung", "=", "0"), ("allocated_hours", "=", 0)],
    order="id",
)
# Progress follows the stage (2.1): pick the project's stage with the wanted step.
stage_by_rung = {stage.pan_rung: stage for stage in project.type_ids}
for index, task in enumerate(tasks):
    rung = str(max(0, 5 - (task.pan_phase_id.sequence // 10) + (index % 2)) % 6)
    vals = {"allocated_hours": 2 + index % 5}
    if rung in stage_by_rung:
        vals["stage_id"] = stage_by_rung[rung].id
    task.write(vals)
# Flows get a deadline (every third one already passed) and tasks an owner,
# so "Late" and owner names show on the demo map.
today = fields.Date.context_today(env.user)
flows = env["project.task"].search(
    [("project_id", "=", project.id), ("child_ids", "!=", False), ("date_deadline", "=", False)], order="sequence, id"
)
for index, flow in enumerate(flows):
    flow.date_deadline = today + timedelta(days=-5 if index % 3 == 0 else 14 + index)
env["project.task"].search([("project_id", "=", project.id), ("user_ids", "=", False)]).user_ids = env.ref("base.user_admin")
env.cr.commit()
print("seeded", env["project.task"].search_count([("project_id", "=", project.id)]), "tasks")
