from odoo import fields, models

from .structure import RUNG_SELECTION


class ProjectTaskType(models.Model):
    """Progress is the stage: each task stage carries a progress step, and a
    task's progress follows its stage (``project.task.pan_rung``)."""

    _inherit = "project.task.type"

    pan_rung = fields.Selection(
        selection=RUNG_SELECTION,
        string="Progress",
        default="0",
        required=True,
        help="The progress a task has while it is in this stage: Open, Decided (choice made), "
        "Built (Odoo configured), Tested, Trained (people can do it) or Live. "
        "The map and a flow's Tested % read it from the stage.",
    )
