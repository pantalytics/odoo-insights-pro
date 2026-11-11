from lxml import html as lxml_html

from odoo import models
from odoo.tools import html2plaintext

from .structure import CANCELLED_STATE

# Block elements whose text counts as one line of a description.
_LINE_TAGS = ("li", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre")


class ProjectProject(models.Model):
    """A project is a company map: its roles are the lanes, the shared phases
    the columns, its parent tasks the flows and its other tasks the chips."""

    _inherit = "project.project"

    def action_open_blueprint_map(self):
        """Open the map of this project (Projects app, not a separate app)."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("pan_self_learning_blueprint.action_blueprint_map")
        action["params"] = {"project_id": self.id}
        action["display_name"] = self.env._("Map of %s", self.display_name)
        return action

    # ------------------------------------------------------------------
    # Map data (contract: docs/data-model.md)
    # ------------------------------------------------------------------

    def _blueprint_unplaced_domain(self):
        """Tasks of this project that are no flow and miss a role or a phase."""
        self.ensure_one()
        return [
            ("project_id", "=", self.id),
            ("child_ids", "=", False),
            ("state", "!=", CANCELLED_STATE),
            "|",
            ("pan_role_id", "=", False),
            ("pan_phase_id", "=", False),
        ]

    def get_blueprint_map_data(self):
        """Everything the map (and an agent) needs for this project, in one call.

        Records are read as recordsets, so related values are fetched in
        batches and the query count does not grow with the number of tasks.
        """
        self.ensure_one()
        phases = self.env["pan.sl.phase"].search([])
        roles = self.env["pan.sl.role"].search([("project_id", "=", self.id)])
        tasks = self.env["project.task"].search(
            [("project_id", "=", self.id), ("state", "!=", CANCELLED_STATE)], order="sequence, id"
        )
        flows = tasks.filtered("child_ids")
        placed = (tasks - flows).filtered(lambda task: task.pan_role_id and task.pan_phase_id)

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        modules = self._blueprint_modules({value for phase in phases for value in phase._app_values()})
        flow_tasks = {}
        for task in placed:
            if task.parent_id in flows:
                flow_tasks.setdefault(task.parent_id.id, []).append(task.id)

        return {
            "project": {"id": self.id, "name": self.name},
            "phases": [
                {
                    "id": phase.id,
                    "code": phase.code,
                    "name": phase.name,
                    "apps": [self._blueprint_app(value, modules) for value in phase._app_values()],
                }
                for phase in phases
            ],
            "roles": [
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "is_external": role.is_external,
                    "users": role.partner_ids.mapped("name"),
                    "adkar": adkar_bands[role.id],
                }
                for role in roles
            ],
            "flows": [
                {
                    "id": flow.id,
                    "name": flow.name,
                    "progress": flow.pan_flow_progress,
                    "task_ids": flow_tasks.get(flow.id, []),
                }
                for flow in flows
            ],
            "tasks": [
                {
                    "id": task.id,
                    "name": task.name,
                    "role_id": task.pan_role_id.id,
                    "phase_id": task.pan_phase_id.id,
                    "flow_id": task.parent_id.id if task.parent_id in flows else False,
                    "rung": int(task.pan_rung),
                    "user_names": task.user_ids.mapped("name"),
                    "planned_hours": task.allocated_hours,
                    "spent_hours": task.effective_hours,
                    "description": self._blueprint_first_line(task.description),
                }
                for task in placed
            ],
            "unplaced_count": self.env["project.task"].search_count(self._blueprint_unplaced_domain()),
        }

    def action_blueprint_unplaced_tasks(self):
        """The tasks of this project that are not on the map yet (no role or no phase)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Not on the map"),
            "res_model": "project.task",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": self._blueprint_unplaced_domain(),
            "context": {"default_project_id": self.id},
        }

    def _blueprint_modules(self, values):
        """The modules a phase's ``app_labels`` refer to, keyed by each value.

        A value is a technical module name (``sale_management``). A value that
        is no module name is matched on the module's name (shortdesc) in
        en_US or in the user's language, so labels such as "Sales" keep
        working. Values that match nothing are left out.
        """
        if not values:
            return {}
        # ir.module.module is technical metadata; reading it exposes no business data.
        Module = self.env["ir.module.module"].sudo()
        found = {module.name: module for module in Module.search([("name", "in", list(values))])}
        for lang in dict.fromkeys(["en_US", self.env.lang or "en_US"]):
            rest = [value for value in values if value not in found]
            if not rest:
                break
            for module in Module.with_context(lang=lang).search([("shortdesc", "in", rest)]):
                # Prefer the installed one when several modules share a name.
                current = found.get(module.shortdesc)
                if not current or (current.state != "installed" and module.state == "installed"):
                    found[module.shortdesc] = module
        return found

    def _blueprint_app(self, value, modules):
        """One Odoo app chip: the module's name in the user's language."""
        module = modules.get(value)
        if not module:
            return {"name": value, "module": False, "installed": False}
        return {
            "name": module.with_context(lang=self.env.lang).shortdesc,
            "module": module.name,
            "installed": module.state == "installed",
        }

    def _blueprint_first_line(self, html):
        """First line of an HTML description as plain text, ``False`` when empty."""
        if not html or not html2plaintext(html).strip():
            return False
        root = lxml_html.fragment_fromstring(str(html), create_parent="div")
        for element in root.iter(*_LINE_TAGS):
            if element is root:
                continue
            # Skip wrappers whose text lives in nested blocks (e.g. a div around a list).
            if any(child.tag in _LINE_TAGS + ("ol", "ul") for child in element):
                continue
            text = " ".join(element.text_content().split())
            if text:
                return text
        for line in html2plaintext(html).splitlines():
            if line.strip():
                return line.strip()
        return False

    # ------------------------------------------------------------------
    # Blueprint buttons (managers, project form header)
    # ------------------------------------------------------------------

    def action_blueprint_load_template(self):
        """Fill this project from the bundled template, then open its map."""
        self.ensure_one()
        Blueprint = self.env["pan.sl.blueprint"]
        summary = Blueprint.import_blueprint(self, Blueprint._read_template(), fill_empty_only=True)
        return Blueprint._notify_and_open_map(self.env._("Template loaded"), summary, self)

    def action_blueprint_import(self):
        """Open the small dialog to import a blueprint file into this project."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import blueprint"),
            "res_model": "pan.sl.blueprint.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_blueprint_export(self):
        """Download this project as blueprint.json."""
        self.ensure_one()
        return self.env["pan.sl.blueprint"]._download(self)
