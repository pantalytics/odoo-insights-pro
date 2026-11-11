"""19.0.2.1.0: renamed labels ("Map role" is now "Role", ...) keep their old
translation on an update, so this module's terms are loaded again, overwriting."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.module.module"].search([("name", "=", "pan_self_learning_blueprint")])._update_translations(overwrite=True)
