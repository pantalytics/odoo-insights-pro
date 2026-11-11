"""19.0.2.0.0: everything is a project task (#22).

Chains, processes, activities and scenarios are removed. Production held only
template data for them (no task links, no ADKAR scores), so their rows go;
Odoo then removes the emptied models and their tables at the end of the
update. Roles now belong to a project: the old shared roles are deleted and
come back per project by loading the template. Phases stay as they are.
"""
import logging

_logger = logging.getLogger(__name__)

REMOVED_TABLES = (
    "pan_sl_activity_project_task_rel",
    "pan_sl_scenario_step",
    "pan_sl_scenario",
    "pan_sl_activity",
    "pan_sl_process",
    "pan_sl_chain",
    # Left behind by 1.2.0 (removed many2many fields), when its post-migration did not run.
    "pan_sl_role_res_users_rel",
    "pan_sl_role_res_groups_rel",
    "ir_model_pan_sl_phase_rel",
)


def migrate(cr, version):
    if not version:
        return
    for table in REMOVED_TABLES:
        cr.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    cr.execute("DELETE FROM ir_model_relation WHERE name IN %s", (REMOVED_TABLES,))
    cr.execute("ALTER TABLE project_task DROP COLUMN IF EXISTS pan_scenario_id")
    cr.execute("ALTER TABLE pan_sl_adkar_score DROP COLUMN IF EXISTS user_id")
    # Roles get a required project; transient import rows a required project too.
    cr.execute("DELETE FROM pan_sl_role")
    _logger.info("[Blueprint] 19.0.2.0.0: %s shared roles removed; load the template per project.", cr.rowcount)
    cr.execute("DELETE FROM pan_sl_blueprint_wizard")
