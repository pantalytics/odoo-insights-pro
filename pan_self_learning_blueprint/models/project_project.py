from lxml import html as lxml_html

from odoo import api, fields, models
from odoo.tools import html2plaintext

from .project_task import USER_GROUP
from .structure import CANCELLED_STATE, TRAINED_RUNG

# Block elements whose text counts as one line of a description.
_LINE_TAGS = ("li", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre")


class ProjectProject(models.Model):
    """A project is a company map: its roles are the lanes, the shared phases
    the columns, its parent tasks the flows and its other tasks the chips."""

    _inherit = "project.project"

    pan_role_ids = fields.One2many(
        "pan.sl.role",
        "project_id",
        string="Map roles",
        groups=USER_GROUP,
        help="The roles (map rows) of this project. A project with roles has a map.",
    )

    @api.model
    def get_blueprint_map_projects(self):
        """The projects with a map (at least one role) the user can read, by name."""
        projects = self.search([("pan_role_ids", "!=", False)], order="name, id")
        return [{"id": project.id, "name": project.name} for project in projects]

    def action_open_blueprint_map(self):
        """Open the map of this project (Projects app, not a separate app)."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("pan_self_learning_blueprint.action_blueprint_map")
        action["params"] = {"project_id": self.id}
        return action

    # ------------------------------------------------------------------
    # Map data (contract: docs/data-model.md)
    # ------------------------------------------------------------------

    def get_blueprint_map_data(self):
        """Everything the map (and an agent) needs for this project, in one call.

        Records are read as recordsets, so related values are fetched in
        batches and the query count does not grow with the number of tasks.
        """
        self.ensure_one()
        phases = self.env["pan.sl.phase"].search([])
        roles = self.pan_role_ids.sorted()
        tasks = self.env["project.task"].search(
            [("project_id", "=", self.id), ("state", "!=", CANCELLED_STATE)], order="sequence, id"
        )
        flows = tasks.filtered("child_ids")
        work = tasks - flows
        flow_tasks, training = {}, {}
        for task in work:
            if task.parent_id in flows:
                flow_tasks.setdefault(task.parent_id.id, []).append(task.id)
            if task.pan_role_id and int(task.pan_rung or 0) < TRAINED_RUNG:
                training.setdefault(task.pan_role_id.id, []).append(task.id)

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        now = fields.Datetime.now()
        flow_rows = []
        for flow in flows:
            late = bool(flow.date_deadline and flow.date_deadline < now and flow.pan_flow_progress < 100)
            flow_rows.append(
                {
                    "id": flow.id,
                    "name": flow.name,
                    "progress": flow.pan_flow_progress,
                    "deadline": flow.date_deadline
                    and fields.Datetime.context_timestamp(self, flow.date_deadline).date().isoformat(),
                    "late": late,
                    "task_ids": flow_tasks.get(flow.id, []),
                }
            )
        # Worst first: lowest Tested %, then late before on time; ``tasks`` is
        # already in sequence order and the sort is stable.
        flow_rows.sort(key=lambda row: (row["progress"], not row["late"]))

        return {
            "project": {"id": self.id, "name": self.name},
            "phases": [{"id": phase.id, "code": phase.code, "name": phase.name} for phase in phases],
            "roles": [
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "is_external": role.is_external,
                    "people": role.partner_ids.mapped("name"),
                    "adkar": adkar_bands[role.id],
                    "open_training_task_ids": training.get(role.id, []),
                }
                for role in roles
            ],
            "flows": flow_rows,
            "tasks": [
                {
                    "id": task.id,
                    "name": task.name,
                    "role_id": task.pan_role_id.id,
                    "phase_id": task.pan_phase_id.id,
                    "flow_id": task.parent_id.id if task.parent_id in flows else False,
                    "stage": task.stage_id.name or False,
                    "rung": int(task.pan_rung or 0),
                    "user_names": task.user_ids.mapped("name"),
                    "planned_hours": task.allocated_hours,
                    "spent_hours": task.effective_hours,
                    "description": self._blueprint_first_line(task.description),
                }
                for task in work
            ],
        }

    def action_blueprint_training(self):
        """Who still needs training: the project's tasks with a role below
        Trained, grouped by role, with the role's people."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Training"),
            "res_model": "project.task",
            "view_mode": "list,form",
            "views": [(self.env.ref("pan_self_learning_blueprint.view_task_list_training").id, "list"), (False, "form")],
            "domain": [
                ("project_id", "=", self.id),
                ("child_ids", "=", False),
                ("state", "!=", CANCELLED_STATE),
                ("pan_role_id", "!=", False),
                "|",
                ("pan_rung", "=", False),
                ("pan_rung", "in", [str(rung) for rung in range(TRAINED_RUNG)]),
            ],
            "context": {"group_by": ["pan_role_id"], "default_project_id": self.id},
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
