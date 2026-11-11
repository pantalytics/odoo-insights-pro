from odoo import api, fields, models
from odoo.fields import Domain

from .ir_ui_view import MAP_VIEW_TYPE
from .project_task import USER_GROUP
from .structure import CANCELLED_STATE, TESTED_RUNG, TRAINED_RUNG


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

    def _pan_has_stage_ladder(self):
        """True when no two stages of the project share a progress step, as
        with the six template stages. Only then may a flow's stage follow its
        tasks; a shared workflow (Icebox, Backlog, Estimated all at Open) is
        left alone."""
        self.ensure_one()
        rungs = self.env["project.task.type"].sudo().search([("project_ids", "in", self.id)]).mapped("pan_rung")
        return len(rungs) == len(set(rungs))

    @api.model
    def get_blueprint_map_projects(self):
        """The projects with a map (at least one role) the user can read, by name."""
        projects = self.search([("pan_role_ids", "!=", False)], order="name, id")
        return [{"id": project.id, "name": project.name} for project in projects]

    def action_open_blueprint_map(self):
        """Open the project's tasks in the Map view (the map is a view type
        on project.task since 2.3, so the standard search bar works on it).
        All tasks, not only the open ones: the map shows progress up to Live."""
        self.ensure_one()
        action = self.action_view_tasks()
        views = action["views"]
        map_views = [view for view in views if view[1] == MAP_VIEW_TYPE] or [(False, MAP_VIEW_TYPE)]
        action["views"] = map_views + [view for view in views if view[1] != MAP_VIEW_TYPE]
        action["context"] = {key: value for key, value in action["context"].items() if key != "search_default_open_tasks"}
        action["mobile_view_mode"] = MAP_VIEW_TYPE  # phones open the map too, not the kanban
        return action

    def action_view_tasks(self):
        """The Map view sits in the view switcher of a project with a map, for
        Blueprint users; other projects and users do not see it."""
        action = super().action_view_tasks()
        if not (self.env.user.has_group(USER_GROUP) and self.sudo().pan_role_ids):
            action["views"] = [view for view in action["views"] if view[1] != MAP_VIEW_TYPE]
        return action

    # ------------------------------------------------------------------
    # Map data (contract: docs/data-model.md)
    # ------------------------------------------------------------------

    def get_blueprint_map_data(self, domain=None, order=None):
        """Everything the map (and an agent) needs for this project, in one call.

        ``domain`` (optional, a task domain such as the map view's search)
        restricts the listed tasks; a flow keeps its progress and open count
        over all its tasks but lists only matching ones, and a flow without a
        matching task is left out. ``order`` (optional) orders ``tasks`` (the
        chips within a cell); a flow's ``task_ids`` always follow sequence.

        Records are read as recordsets, so related values are fetched in
        batches and the query count does not grow with the number of tasks.
        """
        self.ensure_one()
        phases = self.env["pan.sl.phase"].search([])
        roles = self.pan_role_ids.sorted()
        base = [("project_id", "=", self.id), ("state", "!=", CANCELLED_STATE)]
        tasks = self.env["project.task"].search(base, order="sequence, id")
        flows = tasks.filtered("child_ids")
        if domain:
            matching = self.env["project.task"].search(Domain.AND([base, domain]), order=order or "sequence, id")
        elif order:
            matching = self.env["project.task"].search(base, order=order)
        else:
            matching = tasks
        work = matching - flows
        flow_tasks, open_counts, training = {}, {}, {}
        for task in tasks - flows:
            if task.parent_id in flows:
                open_counts[task.parent_id.id] = open_counts.get(task.parent_id.id, 0) + (int(task.pan_rung or 0) < TESTED_RUNG)
        for task in work.sorted(lambda task: (task.sequence, task.id)):
            rung = int(task.pan_rung or 0)
            if task.parent_id in flows:
                flow_tasks.setdefault(task.parent_id.id, []).append(task.id)
            if task.pan_role_id and rung < TRAINED_RUNG:
                training.setdefault(task.pan_role_id.id, []).append(task.id)
        if domain:
            flows = flows.filtered(lambda flow: flow.id in flow_tasks)

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        today = fields.Date.context_today(self)
        flow_rows = []
        for flow in flows:
            deadline = flow.date_deadline and fields.Datetime.context_timestamp(self, flow.date_deadline).date()
            late = bool(deadline and deadline < today and flow.pan_flow_progress < 100)
            flow_rows.append(
                {
                    "id": flow.id,
                    "name": flow.name,
                    "progress": flow.pan_flow_progress,
                    "deadline": deadline and deadline.isoformat(),
                    "late": late,
                    "days_late": (today - deadline).days if late else 0,
                    "open_count": open_counts.get(flow.id, 0),
                    "task_ids": flow_tasks.get(flow.id, []),
                }
            )
        # Worst first: lowest Tested %, late before on time, longer late first,
        # more open tasks first; ``tasks`` is already in sequence order and the
        # sort is stable, so sequence breaks the last tie.
        flow_rows.sort(key=lambda row: (row["progress"], not row["late"], -row["days_late"], -row["open_count"]))

        milestones = self.env["project.milestone"].search(
            [("project_id", "=", self.id)], order="deadline asc nulls last, id"
        )
        return {
            "project": {"id": self.id, "name": self.name},
            "milestones": [
                {
                    "id": milestone.id,
                    "name": milestone.name,
                    "deadline": milestone.deadline and milestone.deadline.isoformat(),
                    "reached": milestone.is_reached,
                }
                for milestone in milestones
            ],
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
                }
                for task in work
            ],
        }

    def action_blueprint_training(self):
        """Still to train: the project's tasks of internal roles below Trained,
        grouped by role (groups open), with the role's people. The condition is
        the search filter "Still to train", so it shows in the search bar."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Still to train"),
            "res_model": "project.task",
            "view_mode": "list,form",
            "views": [(self.env.ref("pan_self_learning_blueprint.view_task_list_training").id, "list"), (False, "form")],
            "domain": [("project_id", "=", self.id)],
            "context": {
                "search_default_pan_still_to_train": 1,
                "search_default_pan_groupby_role": 1,
                "default_project_id": self.id,
            },
        }

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
