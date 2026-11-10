"""19.0.1.2.0: people are contacts (res.partner), no longer users.

Runs before the models are updated, while the old user columns still exist:
- ADKAR scores get ``partner_id``, filled from the partner of ``user_id``, so
  the ORM can make the new column NOT NULL without losing a score.
- Role members move from ``pan_sl_role_res_users_rel`` to
  ``pan_sl_role_res_partner_rel`` (same layout as the ORM creates; the ORM
  then adds the foreign keys).
- Chains and phases from the removed ``data/default_structure.xml`` lose their
  XML ids and stay as ordinary records, matched on code like everything the
  template loads.
"""
import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

MODULE = "pan_self_learning_blueprint"


def migrate(cr, version):
    if not version:
        return
    if sql.column_exists(cr, "pan_sl_adkar_score", "user_id"):
        if not sql.column_exists(cr, "pan_sl_adkar_score", "partner_id"):
            cr.execute("ALTER TABLE pan_sl_adkar_score ADD COLUMN partner_id INTEGER")
        cr.execute(
            """
            UPDATE pan_sl_adkar_score score
               SET partner_id = users.partner_id
              FROM res_users users
             WHERE users.id = score.user_id
               AND score.partner_id IS NULL
            """
        )
        _logger.info("[Blueprint] 19.0.1.2.0: %s ADKAR scores moved to the person's contact.", cr.rowcount)

    if sql.table_exists(cr, "pan_sl_role_res_users_rel"):
        cr.execute(
            """
            CREATE TABLE IF NOT EXISTS pan_sl_role_res_partner_rel (
                role_id INTEGER NOT NULL,
                partner_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, partner_id)
            );
            CREATE INDEX IF NOT EXISTS pan_sl_role_res_partner_rel_partner_id_role_id_idx
                ON pan_sl_role_res_partner_rel (partner_id, role_id);
            INSERT INTO pan_sl_role_res_partner_rel (role_id, partner_id)
                 SELECT rel.role_id, users.partner_id
                   FROM pan_sl_role_res_users_rel rel
                   JOIN res_users users ON users.id = rel.user_id
            ON CONFLICT DO NOTHING;
            """
        )
        _logger.info("[Blueprint] 19.0.1.2.0: %s role members moved to contacts.", cr.rowcount)

    cr.execute(
        "DELETE FROM ir_model_data WHERE module = %s AND model IN ('pan.sl.chain', 'pan.sl.phase')",
        (MODULE,),
    )
    _logger.info("[Blueprint] 19.0.1.2.0: %s default chains and phases kept as ordinary records.", cr.rowcount)
