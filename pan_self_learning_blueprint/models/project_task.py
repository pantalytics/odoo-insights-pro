from odoo import api, fields, models

from .structure import CANCELLED_STATE, RUNG_SELECTION, TESTED_RUNG

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"


class ProjectTask(models.Model):
    """Everything on the map is a task: a task with a role and a phase is a
    chip, a parent task is a flow (its subtasks are the route)."""

    _inherit = "project.task"

    pan_role_id = fields.Many2one(
        "pan.sl.role",
        string="Map role",
        index=True,
        ondelete="set null",
        domain="[('project_id', '=', project_id)]",
        groups=USER_GROUP,
        help="Who does this work: the lane of the task on the project's map.",
    )
    pan_phase_id = fields.Many2one(
        "pan.sl.phase",
        string="Map phase",
        index=True,
        ondelete="set null",
        groups=USER_GROUP,
        help="Where in the document chain this work happens: the column of the task on the map.",
    )
    pan_rung = fields.Selection(
        selection=RUNG_SELECTION,
        string="Map progress",
        default="0",
        required=True,
        tracking=True,
        groups=USER_GROUP,
        help="Readiness of this work: Open, Decided (choice made), Built (Odoo configured), "
        "Tested, Trained (people can do it), Live.",
    )
    pan_flow_progress = fields.Integer(
        string="Flow tested %",
        compute="_compute_pan_flow_progress",
        store=True,
        compute_sudo=True,
        aggregator="avg",
        groups=USER_GROUP,
        help="For a flow (a task with subtasks): the share of its subtasks at Tested or further. "
        "Cancelled subtasks do not count, archived ones do.",
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
            rungs.setdefault(subtask.parent_id.id, []).append(int(subtask.pan_rung))
        for task in self:
            values = rungs.get(task._origin.id)
            task.pan_flow_progress = (
                round(100 * sum(rung >= TESTED_RUNG for rung in values) / len(values)) if values else 0
            )
