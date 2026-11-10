from odoo import api, fields, models
from odoo.fields import Domain


class PanSlScenario(models.Model):
    """A test route across processes: an ordered list of activities."""

    _name = "pan.sl.scenario"
    _description = "Blueprint Scenario"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the scenario, for example 'Make to order, delivered and invoiced'.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique, stable code of the scenario. Used to match records on blueprint import.",
    )
    description = fields.Text(
        string="Goal",
        help="What this scenario proves when it runs end to end.",
    )
    open_point = fields.Text(
        string="Open Point",
        help="What still has to be checked or decided for this scenario.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of the scenario in lists and in the scenario selector of the map.",
    )
    step_ids = fields.One2many(
        "pan.sl.scenario.step",
        "scenario_id",
        string="Steps",
        copy=True,
        help="Ordered steps of the route; each step is one activity.",
    )
    activity_ids = fields.Many2many(
        "pan.sl.activity",
        string="Activities",
        compute="_compute_activity_ids",
        help="Activities of this scenario, in the order of its steps.",
    )
    rung = fields.Integer(
        string="Rung",
        compute="_compute_rung",
        help="Lowest rung (0 Open to 5 Live) of the activities in this scenario; "
        "0 when the scenario has no activities.",
    )
    task_ids = fields.One2many(
        "project.task",
        "pan_scenario_id",
        string="Tasks",
        help="Project tasks that work on this scenario.",
    )
    task_count = fields.Integer(
        string="Task Count",
        compute="_compute_task_count",
        help="Number of project tasks linked to this scenario.",
    )

    _code_uniq = models.Constraint(
        "unique (code)",
        "A scenario with this code already exists. Scenario codes must be unique.",
    )

    @api.depends("step_ids.sequence", "step_ids.activity_id")
    def _compute_activity_ids(self):
        for scenario in self:
            steps = scenario.step_ids.sorted(lambda s: (s.sequence, s.id or 0))
            # Keep the order of first appearance; a route may revisit an activity.
            ordered_ids = list(dict.fromkeys(steps.activity_id.ids))
            scenario.activity_ids = self.env["pan.sl.activity"].browse(ordered_ids)

    @api.depends("step_ids.activity_id.rung")
    def _compute_rung(self):
        for scenario in self:
            rungs = scenario.step_ids.activity_id.mapped("rung")
            scenario.rung = min(rungs) if rungs else 0

    @api.depends("task_ids")
    def _compute_task_count(self):
        counts = dict(
            self.env["project.task"]._read_group(
                [("pan_scenario_id", "in", self.ids)],
                groupby=["pan_scenario_id"],
                aggregates=["__count"],
            )
        )
        for scenario in self:
            scenario.task_count = counts.get(scenario, 0)

    def action_view_tasks(self):
        """Open the project tasks of this scenario."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Tasks of %s", self.display_name),
            "res_model": "project.task",
            "view_mode": "list,kanban,form",
            "domain": [("pan_scenario_id", "=", self.id)],
            "context": {"default_pan_scenario_id": self.id},
        }


class PanSlScenarioStep(models.Model):
    """One step of a scenario route: one activity at a position."""

    _name = "pan.sl.scenario.step"
    _description = "Blueprint Scenario Step"
    _order = "scenario_id, sequence, id"

    scenario_id = fields.Many2one(
        "pan.sl.scenario",
        string="Scenario",
        required=True,
        ondelete="cascade",
        index=True,
        help="Scenario this step belongs to.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Position of the step in the scenario route.",
    )
    activity_id = fields.Many2one(
        "pan.sl.activity",
        string="Activity",
        required=True,
        ondelete="restrict",
        index=True,
        help="Activity performed in this step.",
    )
    note = fields.Char(
        string="Note",
        help="What to check or enter in this step, for example the test data to use.",
    )
    role_id = fields.Many2one(
        related="activity_id.role_id",
        string="Role",
        help="Role that performs the activity of this step.",
    )
    phase_id = fields.Many2one(
        related="activity_id.phase_id",
        string="Phase",
        help="Phase of the activity of this step.",
    )


class PanSlActivity(models.Model):
    _inherit = "pan.sl.activity"

    scenario_ids = fields.Many2many(
        "pan.sl.scenario",
        string="Scenarios",
        compute="_compute_scenario_ids",
        search="_search_scenario_ids",
        help="Scenarios whose route passes through this activity.",
    )

    def _compute_scenario_ids(self):
        steps = self.env["pan.sl.scenario.step"].search([("activity_id", "in", self.ids)])
        by_activity = {}
        for step in steps:
            by_activity.setdefault(step.activity_id.id, set()).add(step.scenario_id.id)
        Scenario = self.env["pan.sl.scenario"]
        for activity in self:
            activity.scenario_ids = Scenario.browse(sorted(by_activity.get(activity.id, ())))

    def _search_scenario_ids(self, operator, value):
        if operator in Domain.NEGATIVE_OPERATORS:
            # The ORM retries with the positive operator and negates the result.
            return NotImplemented
        steps = self.env["pan.sl.scenario.step"]._search(Domain("scenario_id", operator, value))
        return Domain("id", "in", steps.subselect("activity_id"))
