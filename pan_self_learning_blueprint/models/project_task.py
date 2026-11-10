from odoo import api, fields, models

from .structure import RUNG_SELECTION


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
        help="Blueprint activities this task moves forward; the lowest progress of "
        "their tasks is the progress of an activity.",
    )
    pan_rung = fields.Selection(
        selection=RUNG_SELECTION,
        string="Blueprint progress",
        default="0",
        required=True,
        tracking=True,
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
        help="Technical: the lowest rung (0 Open to 5 Live) over all linked tasks, "
        "also the ones you cannot open, cancelled tasks left out. 0 when no task is linked.",
    )
    planned_hours = fields.Float(
        help="Sum of the allocated hours of all linked tasks, cancelled tasks "
        "left out. A task linked to several activities counts fully for each of them.",
    )
    spent_hours = fields.Float(
        help="Sum of the timesheet hours on all linked tasks, cancelled tasks "
        "left out. A task linked to several activities counts fully for each of them.",
    )

    def _progress_tasks(self):
        self.ensure_one()
        return self._counted(self.sudo().task_ids)

    def _progress_rungs(self):
        return [int(rung) for rung in self._progress_tasks().mapped("pan_rung")]

    @api.depends("task_ids.pan_rung", "task_ids.state", "task_ids.active")
    def _compute_rung(self):
        return super()._compute_rung()

    @api.depends(
        "task_ids.allocated_hours",
        "task_ids.effective_hours",
        "task_ids.state",
        "task_ids.active",
    )
    def _compute_hours(self):
        return super()._compute_hours()
