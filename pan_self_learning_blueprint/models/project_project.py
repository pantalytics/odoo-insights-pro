from odoo import models


class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_open_blueprint_map(self):
        """Open the company map from a project (Projects app, not a separate app)."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("pan_self_learning_blueprint.action_blueprint_map")
        action["params"] = {"project_id": self.id}
        action["display_name"] = self.env._("Map of %s", self.display_name)
        return action
