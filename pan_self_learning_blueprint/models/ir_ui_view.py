from odoo import _, fields, models

# The map is a view type of its own on project.task (2.3), so the standard
# search bar (filters, group by, favourites) works on it. Its arch is empty.
MAP_VIEW_TYPE = "pan_blueprint"


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[(MAP_VIEW_TYPE, "Map")], ondelete={MAP_VIEW_TYPE: "cascade"})

    def _validate_tag_pan_blueprint(self, node, name_manager, node_info):
        if not node_info["validate"]:
            return
        if len(node):
            self._raise_view_error(_("A map view takes no content."), node)
        remaining = set(node.attrib) - {"__validate__", "string", "js_class", "class"}
        if remaining:
            self._raise_view_error(_("Invalid attributes in a map view: %s", ", ".join(sorted(remaining))), node)

    def _get_view_info(self):
        return {MAP_VIEW_TYPE: {"icon": "fa fa-map-o"}} | super()._get_view_info()


class IrActionsActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(selection_add=[(MAP_VIEW_TYPE, "Map")], ondelete={MAP_VIEW_TYPE: "cascade"})
