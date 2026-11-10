from odoo import api, fields, models

from .structure import CANCELLED_STATE, RUNG_SELECTION


class ProjectTask(models.Model):
    _inherit = "project.task"

    pan_scenario_id = fields.Many2one(
        comodel_name="pan.sl.scenario",
        string="Blueprint Scenario",
        index=True,
        ondelete="set null",
        help="Blueprint scenario (test route across processes) this task works on.",
    )
    pan_activity_ids = fields.Many2many(
        comodel_name="pan.sl.activity",
        relation="pan_sl_activity_project_task_rel",
        column1="task_id",
        column2="activity_id",
        string="Blueprint Activities",
        help="Blueprint activities this task moves forward. The lowest rung of "
        "the tasks linked to an activity is that activity's progress.",
    )
    pan_rung = fields.Selection(
        selection=RUNG_SELECTION,
        string="Rung",
        default="0",
        required=True,
        tracking=True,
        help="Readiness gate this task has reached for its activities: "
        "Open, Decided (choice made), Built (Odoo configured), Tested, "
        "Trained (people can do it), Live.",
    )


class PanSlActivity(models.Model):
    _inherit = "pan.sl.activity"

    task_ids = fields.Many2many(
        comodel_name="project.task",
        relation="pan_sl_activity_project_task_rel",
        column1="activity_id",
        column2="task_id",
        string="Tasks",
        help="Project tasks that implement this activity.",
    )
    rung = fields.Integer(
        string="Rung",
        compute="_compute_rung",
        store=True,
        compute_sudo=True,
        help="Progress of this activity: the lowest rung (0 Open to 5 Live) "
        "over all its linked tasks, also the ones you cannot open. Cancelled "
        "tasks are left out. 0 when no task is linked.",
    )
    rung_state = fields.Selection(
        selection=RUNG_SELECTION,
        string="Progress",
        compute="_compute_rung_state",
        store=True,
        help="The rung of this activity as a name (Open, Decided, Built, "
        "Tested, Trained, Live), for filtering, grouping and display.",
    )

    planned_hours = fields.Float(
        string="Planned hours",
        compute="_compute_hours",
        store=True,
        compute_sudo=True,
        aggregator="sum",
        help="Sum of the allocated hours of all linked tasks, cancelled tasks "
        "left out. A task linked to several activities counts fully for each of them.",
    )
    spent_hours = fields.Float(
        string="Spent hours",
        compute="_compute_hours",
        store=True,
        compute_sudo=True,
        aggregator="sum",
        help="Sum of the timesheet hours on all linked tasks, cancelled tasks "
        "left out. A task linked to several activities counts fully for each of them.",
    )

    def _counted_tasks(self):
        """All linked tasks that count for progress: every task (sudo, so the
        result is the same for every viewer) except cancelled ones."""
        self.ensure_one()
        return self.sudo().task_ids.filtered(lambda task: task.state != CANCELLED_STATE)

    @api.depends(
        "task_ids.allocated_hours",
        "task_ids.effective_hours",
        "task_ids.state",
        "task_ids.active",
    )
    def _compute_hours(self):
        for activity in self:
            tasks = activity._counted_tasks()
            activity.planned_hours = sum(tasks.mapped("allocated_hours"))
            activity.spent_hours = sum(tasks.mapped("effective_hours"))

    @api.depends("task_ids.pan_rung", "task_ids.state", "task_ids.active")
    def _compute_rung(self):
        for activity in self:
            rungs = [int(rung) for rung in activity._counted_tasks().mapped("pan_rung")]
            activity.rung = min(rungs) if rungs else 0

    @api.depends("rung")
    def _compute_rung_state(self):
        for activity in self:
            activity.rung_state = str(activity.rung)
