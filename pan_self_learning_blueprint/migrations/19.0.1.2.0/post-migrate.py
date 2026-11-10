"""19.0.1.2.0: remove what the move to contacts left behind.

The pre-migration copied role members and ADKAR scores to contacts. The ORM
does not drop a many2many table of a removed field, so the tables of the three
removed many2many fields go here, with their relation records:
- ``pan_sl_role_res_users_rel``: role.user_ids, now role.partner_ids;
- ``pan_sl_role_res_groups_rel``: role.group_ids;
- ``ir_model_pan_sl_phase_rel``: phase.model_ids.
The ``user_id`` column is dropped too: its NOT NULL would otherwise block new
scores until the upgrade ends.
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

REMOVED_RELATION_TABLES = (
    "pan_sl_role_res_users_rel",
    "pan_sl_role_res_groups_rel",
    "ir_model_pan_sl_phase_rel",
)


def migrate(cr, version):
    if not version:
        return
    for table in REMOVED_RELATION_TABLES:
        cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(table)))
    cr.execute("DELETE FROM ir_model_relation WHERE name IN %s", (REMOVED_RELATION_TABLES,))
    cr.execute("ALTER TABLE pan_sl_adkar_score DROP COLUMN IF EXISTS user_id")
    # Progress now also counts archived tasks; Odoo does not recompute stored
    # fields whose compute changed, so do it once here.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model in ("pan.sl.activity", "pan.sl.scenario"):
        records = env[model].with_context(active_test=False).search([])
        for fname in ("rung", "planned_hours", "spent_hours"):
            env.add_to_compute(records._fields[fname], records)
    env.flush_all()
    _logger.info("[Blueprint] 19.0.1.2.0: removed the old user links of roles and ADKAR scores and the tables of removed fields.")
