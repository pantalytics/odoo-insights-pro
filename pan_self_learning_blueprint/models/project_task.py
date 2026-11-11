from odoo import api, fields, models

from .structure import CANCELLED_STATE, TESTED_RUNG

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"

# A change to one of these fields of a subtask can move its flow's stage.
_ROLLUP_FIELDS = frozenset({"stage_id", "state", "parent_id", "active", "project_id"})
# Flows inside flows move up at most this many levels per change.
_MAX_FLOW_LEVELS = 10


class ProjectTask(models.Model):
    """Everything on the map is a task: a task with a role and a phase is a
    chip, a parent task is a flow (its subtasks are the route). A task's
    progress is its stage's progress."""

    _inherit = "project.task"

    pan_role_id = fields.Many2one(
        "pan.sl.role",
        string="Role",
        index=True,
        ondelete="set null",
        domain="[('project_id', '=', project_id)]",
        groups=USER_GROUP,
        help="Who does this work: the row of the task on the project's map.",
    )
    pan_phase_id = fields.Many2one(
        "pan.sl.phase",
        string="Phase",
        index=True,
        ondelete="set null",
        groups=USER_GROUP,
        help="Where in the document chain this work happens: the column of the task on the map.",
    )
    pan_rung = fields.Selection(
        related="stage_id.pan_rung",
        string="Progress step",
        store=True,
        readonly=True,
        groups=USER_GROUP,
        help="Readiness of this work, set by its stage: Open, Decided (choice made), "
        "Built (Odoo configured), Tested, Trained (people can do it), Live.",
    )
    pan_flow_progress = fields.Integer(
        string="Tested %",
        compute="_compute_pan_flow_progress",
        store=True,
        compute_sudo=True,
        aggregator="avg",
        groups=USER_GROUP,
        help="For a flow (a task with subtasks): the share of its subtasks at Tested or further. "
        "Cancelled subtasks do not count, archived ones do.",
    )
    pan_is_map_flow = fields.Boolean(
        string="Flow on a map",
        compute="_compute_pan_is_map_flow",
        compute_sudo=True,
        groups=USER_GROUP,
        help="This task has subtasks in a project with a map, so it is a flow: its stage follows its subtasks.",
    )
    pan_role_people = fields.Char(
        string="People",
        compute="_compute_pan_role_people",
        compute_sudo=True,
        groups=USER_GROUP,
        help="The people who hold the role of this task, so who must be trained on it.",
    )

    @api.depends("child_ids.pan_rung", "child_ids.state", "child_ids.active")
    def _compute_pan_flow_progress(self):
        # Archived subtasks count (archiving must not wipe progress), so read
        # them without the active filter, in one search for all flows.
        subtasks = (
            self.env["project.task"]
            .with_context(active_test=False)
            .search([("parent_id", "in", self.ids), ("state", "!=", CANCELLED_STATE)])
            if self.ids
            else self.browse()
        )
        rungs = {}
        for subtask in subtasks:
            rungs.setdefault(subtask.parent_id.id, []).append(int(subtask.pan_rung or 0))
        for task in self:
            values = rungs.get(task._origin.id)
            task.pan_flow_progress = (
                round(100 * sum(rung >= TESTED_RUNG for rung in values) / len(values)) if values else 0
            )

    @api.depends("child_ids", "project_id.pan_role_ids")
    def _compute_pan_is_map_flow(self):
        for task in self:
            task.pan_is_map_flow = bool(task.child_ids and task.project_id.pan_role_ids)

    @api.depends("pan_role_id.partner_ids.name")
    def _compute_pan_role_people(self):
        for task in self:
            task.pan_role_people = ", ".join(task.pan_role_id.partner_ids.mapped("name"))

    # ------------------------------------------------------------------
    # A flow's stage follows its subtasks (fix 1 of the 2.2 round)
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks.parent_id._pan_rollup_flow_stage()
        return tasks

    def write(self, vals):
        rollup = not self.env.context.get("pan_flow_rollup") and not _ROLLUP_FIELDS.isdisjoint(vals)
        before = self.parent_id if rollup else None
        result = super().write(vals)
        if rollup:
            (before | self.parent_id)._pan_rollup_flow_stage()
        return result

    def unlink(self):
        parents = self.parent_id
        result = super().unlink()
        parents.exists()._pan_rollup_flow_stage()
        return result

    def _pan_rollup_flow_stage(self):
        """Put each flow in ``self`` in the stage of its lowest step: the
        project stage whose progress equals the lowest progress among its
        non-cancelled subtasks (archived ones count, as for Tested %).

        Only flows of projects with a map whose stages each carry a different
        step (the six stages of the template), never a project that shares
        several stages per step, such as Icebox, Backlog and Estimated all at
        Open. A flow already in a stage with the right step stays where it is. Nested flows move up level by level, in a
        bounded loop over the parents of the flows that moved (no recursion);
        the writes carry a context key so they do not start a roll-up of their
        own.
        """
        Task = self.env["project.task"].sudo().with_context(active_test=False, pan_flow_rollup=True)
        flows = Task.browse(self.ids)
        for _level in range(_MAX_FLOW_LEVELS):
            flows = flows.filtered(lambda flow: flow.project_id.pan_role_ids)
            if not flows:
                break
            ladder_projects = flows.project_id.filtered(lambda project: project._pan_has_stage_ladder())
            flows = flows.filtered(lambda flow: flow.project_id in ladder_projects)
            if not flows:
                break
            subtasks = Task.search([("parent_id", "in", flows.ids), ("state", "!=", CANCELLED_STATE)])
            lowest = {}
            for subtask in subtasks:
                rung = int(subtask.pan_rung or 0)
                lowest[subtask.parent_id.id] = min(rung, lowest.get(subtask.parent_id.id, rung))
            stages = self.env["project.task.type"].sudo().search(
                [("project_ids", "in", flows.project_id.ids)], order="sequence, id"
            )
            moved = Task.browse()
            for flow in flows:
                if flow.id not in lowest:
                    continue
                rung = str(lowest[flow.id])
                if flow.stage_id.pan_rung == rung:
                    continue
                stage = next(
                    (s for s in stages if s.pan_rung == rung and flow.project_id in s.project_ids), None
                )
                if stage and flow.stage_id != stage:
                    flow.stage_id = stage
                    moved |= flow
            flows = moved.parent_id
