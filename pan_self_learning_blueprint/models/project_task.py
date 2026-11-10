from odoo import api, fields, models

from .structure import RUNG_SELECTION


class ProjectTask(models.Model):
    _inherit = "project.task"

    pan_scenario_id = fields.Many2one(
        comodel_name="pan.sl.scenario",
        string="Blueprint Scenario",
        index=True,
        ondelete="set null",
        groups="pan_self_learning_blueprint.group_blueprint_user",
        help="Blueprint scenario (test route across processes) this task works on.",
    )
    pan_activity_ids = fields.Many2many(
        comodel_name="pan.sl.activity",
        relation="pan_sl_activity_project_task_rel",
        column1="task_id",
        column2="activity_id",
        string="Blueprint Activities",
        groups="pan_self_learning_blueprint.group_blueprint_user",
        help="Blueprint activities this task moves forward; the lowest progress of "
        "their tasks is the progress of an activity.",
    )
    pan_rung = fields.Selection(
        selection=RUNG_SELECTION,
        string="Blueprint progress",
        default="0",
        required=True,
        tracking=True,
        groups="pan_self_learning_blueprint.group_blueprint_user",
        help="Readiness gate this task has reached for its activities: "
        "Open, Decided (choice made), Built (Odoo configured), Tested, "
        "Trained (people can do it), Live.",
    )


class PanSlActivity(models.Model):
    _name = "pan.sl.activity"
    _inherit = ["pan.sl.activity", "pan.sl.progress.mixin"]

    task_ids = fields.Many2many(
        comodel_name="project.task",
        relation="pan_sl_activity_project_task_rel",
        column1="activity_id",
        column2="task_id",
        string="Tasks",
        help="Project tasks that implement this activity.",
    )
    rung = fields.Integer(
        help="Technical: the lowest progress (0 Open to 5 Live) over all linked tasks, "
        "also archived ones and the ones you cannot open, cancelled tasks left out. "
        "0 when no task is linked.",
    )
    planned_hours = fields.Float(
        help="Sum of the allocated hours of all linked tasks, archived ones included, "
        "cancelled tasks left out. A task linked to several activities counts fully for each of them.",
    )
    spent_hours = fields.Float(
        help="Sum of the timesheet hours on all linked tasks, archived ones included, "
        "cancelled tasks left out. A task linked to several activities counts fully for each of them.",
    )

    def _counted_tasks(self):
        """The tasks that count for this activity, archived ones included."""
        self.ensure_one()
        return self._counted(self.sudo().with_context(active_test=False).task_ids)

    @api.depends("task_ids.pan_rung", "task_ids.state")
    def _compute_rung(self):
        for activity in self:
            rungs = [int(rung) for rung in activity._counted_tasks().mapped("pan_rung")]
            activity.rung = min(rungs) if rungs else 0

    @api.depends("task_ids.allocated_hours", "task_ids.effective_hours", "task_ids.state")
    def _compute_hours(self):
        for activity in self:
            tasks = activity._counted_tasks()
            activity.planned_hours = sum(tasks.mapped("allocated_hours"))
            activity.spent_hours = sum(tasks.mapped("effective_hours"))
