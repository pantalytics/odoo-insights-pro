"""19.0.1.2.0: remove what the move to contacts left behind.

The pre-migration copied role members and ADKAR scores to contacts. The ORM
does not drop a many2many table of a removed field, so the old role-user
table goes here, with its relation record. The ``user_id`` column is dropped
too: its NOT NULL would otherwise block new scores until the upgrade ends.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS pan_sl_role_res_users_rel")
    cr.execute("DELETE FROM ir_model_relation WHERE name = 'pan_sl_role_res_users_rel'")
    cr.execute("ALTER TABLE pan_sl_adkar_score DROP COLUMN IF EXISTS user_id")
    _logger.info("[Blueprint] 19.0.1.2.0: removed the old user links of roles and ADKAR scores.")
