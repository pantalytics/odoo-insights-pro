from odoo import api, fields, models

RUNG_SELECTION = [
    ("0", "Open"),
    ("1", "Decided"),
    ("2", "Built"),
    ("3", "Tested"),
    ("4", "Trained"),
    ("5", "Live"),
]


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
        help="Progress of this activity: the lowest rung (0 Open to 5 Live) "
        "over its linked tasks, 0 when no task is linked.",
    )

    planned_hours = fields.Float(
        string="Planned hours",
        compute="_compute_hours",
        help="Sum of the allocated hours of the linked tasks. A task linked to "
        "several activities counts fully for each of them.",
    )
    spent_hours = fields.Float(
        string="Spent hours",
        compute="_compute_hours",
        help="Sum of the timesheet hours on the linked tasks. A task linked to "
        "several activities counts fully for each of them.",
    )

    @api.depends("task_ids.allocated_hours", "task_ids.effective_hours")
    def _compute_hours(self):
        for activity in self:
            activity.planned_hours = sum(activity.task_ids.mapped("allocated_hours"))
            activity.spent_hours = sum(activity.task_ids.mapped("effective_hours"))

    @api.depends("task_ids.pan_rung")
    def _compute_rung(self):
        for activity in self:
            rungs = [int(rung) for rung in activity.task_ids.mapped("pan_rung")]
            activity.rung = min(rungs) if rungs else 0
