"""Fill a development database with demo progress for the company map.

Run inside `odoo-bin shell -d <db>`, with the database name confirmed in an
environment variable:
    BLUEPRINT_SEED_OK=<db> odoo-bin shell -d <db>
    >>> exec(open("tools/seed_demo.py").read())
Loads the generic template into the project "Blueprint demo", then gives its
map tasks a progress step and hours, and creates demo people (contacts, no
logins) per internal role with ADKAR scores, and two milestones, then
commits. Development
only: the script refuses to run, and creates nothing, unless
BLUEPRINT_SEED_OK equals the name of the connected database.

Every internal role gets three scored demo people, also a role that already
has people (they may have no score), because a role's ADKAR band only shows
once at least three of its people have a score. The latest scores differ per role
(low, medium, high), so the role panel shows each band. Rerunning creates
nothing new: demo people are found again by their reference.

With BLUEPRINT_SEED_SIZE=large it also adds a ninth phase, eight more flows
and four steps with long Dutch titles to every flow (18 flows, about 110
tasks, like a real project), to check that a big map still fits the screen.
"""
import os
from datetime import timedelta

from odoo import fields
from odoo.fields import Command

SEED_GUARD_VARIABLE = "BLUEPRINT_SEED_OK"
SEED_SIZE_VARIABLE = "BLUEPRINT_SEED_SIZE"
LARGE_STEPS_PER_FLOW = 4
LARGE_EXTRA_FLOWS = (
    "S11 Artikelmigratie uit BEMET",
    "S12 Leveranciers per artikel",
    "S13 Calculatie en offerte op maat",
    "S14 Plaatbewerking plannen",
    "S15 Lassen en samenstellen",
    "S16 Kwaliteit en certificaten",
    "S17 Service en reserveonderdelen",
    "S18 Rapportage voor de directie",
)
LARGE_TITLES = (
    "René levert resterende Bemet-artikelen aan voor de artikelmaster",
    "Leveranciersprijzen per artikel controleren en vastleggen in Odoo",
    "Werkvoorbereiding stemt bewerkingen en routings af met de werkplaats",
    "Inkoop bevestigt levertijden van plaatmateriaal en halffabricaten",
    "Kwaliteitscontrole op gelaste samenstellingen vóór verzending",
    "Facturatie van termijnen volgens het betalingsschema van de klant",
    "Nacalculatie van uren en materiaal per productieorder",
)
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
# BLUEPRINT_SEED_SIZE=large: a ninth phase, eight more flows and four steps per flow with
# long titles, spread over the cells (about 115 tasks, like a real project).
if os.environ.get(SEED_SIZE_VARIABLE) == "large":
    extra_phase = env["pan.sl.phase"].search([("code", "=", "demo_go_live")], limit=1) or env["pan.sl.phase"].create(
        {"name": "Go-live and aftercare", "code": "demo_go_live", "sequence": 90}
    )
    all_roles = env["pan.sl.role"].search([("project_id", "=", project.id)])
    all_phases = env["pan.sl.phase"].search([])
    for index, flow_name in enumerate(LARGE_EXTRA_FLOWS):
        if not env["project.task"].search_count([("project_id", "=", project.id), ("name", "=", flow_name)]):
            env["project.task"].create({"name": flow_name, "project_id": project.id, "sequence": 110 + index})
    flow_tasks = env["project.task"].search(
        [("project_id", "=", project.id), ("parent_id", "=", False), ("name", "in", LARGE_EXTRA_FLOWS)]
    ) | env["project.task"].search([("project_id", "=", project.id), ("child_ids", "!=", False)])
    flow_tasks = flow_tasks.sorted(lambda task: (task.sequence, task.id))
    for flow_index, flow in enumerate(flow_tasks):
        code = flow.name.split(" ")[0]
        for step in range(1, LARGE_STEPS_PER_FLOW + 1):
            name = f"{code}.{step} [BLOCKER] {LARGE_TITLES[(flow_index + step) % len(LARGE_TITLES)]}"
            if env["project.task"].search_count([("parent_id", "=", flow.id), ("name", "=", name)]):
                continue
            env["project.task"].create(
                {
                    "name": name,
                    "project_id": project.id,
                    "parent_id": flow.id,
                    "sequence": 100 + step,
                    "pan_role_id": all_roles[(flow_index * 3 + step) % len(all_roles)].id,
                    "pan_phase_id": all_phases[(flow_index + step * 2) % len(all_phases)].id,
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
# Two milestones, so the map's "On schedule?" answer has a next one (2.3).
project.allow_milestones = True
for name, days, reached in (("Design signed off", -20, True), ("Data migrated", 12, False), ("Go-live", 60, False)):
    if not env["project.milestone"].search_count([("project_id", "=", project.id), ("name", "=", name)]):
        env["project.milestone"].create(
            {"project_id": project.id, "name": name, "deadline": today + timedelta(days=days), "is_reached": reached}
        )
# Level of detail on the map: a one-line summary and keywords per flow, keywords for the company.
for flow in env["project.task"].search([("project_id", "=", project.id), ("child_ids", "!=", False)]):
    steps = flow.child_ids.sorted(lambda task: (task.sequence, task.id))
    phases = steps.pan_phase_id.sorted("sequence")
    if not flow.pan_summary and phases:
        flow.pan_summary = f"{len(steps)} steps, from {phases[0].name} to {phases[-1].name}"
    if not flow.pan_keywords:
        flow.pan_keywords = ", ".join(dict.fromkeys(steps.pan_role_id.mapped("name")))
if not project.pan_keywords:
    project.pan_keywords = "custom machines, sheet metal, project sales, BEMET migration"
# Level 0 of the map: the company in one page, from and to, start and target.
if not project.pan_brief:
    project.write(
        {
            "pan_brief": (
                "<p><b>Demo Machinebouw</b> designs and builds custom machines and sheet-metal assemblies "
                "for food and packaging plants: 45 people, engineering, a workshop and assembly.</p>"
                "<p>Sells per project, on quotation with drawings; about 120 customers in the Benelux, "
                "most of them repeat. Buys plate, profiles and parts from some 60 suppliers.</p>"
                "<p>Today orders, articles and purchasing run in BEMET and Excel; the go-live moves "
                "sales, purchasing, production and invoicing to Odoo.</p>"
            ),
            "pan_from_systems": "BEMET/PDC-Win, Excel",
            "pan_to_systems": "Odoo 19, UNS",
        }
    )
if not project.date_start:
    project.write({"date_start": today - timedelta(days=75), "date": today + timedelta(days=105)})
env.cr.commit()
print("seeded", env["project.task"].search_count([("project_id", "=", project.id)]), "tasks")
