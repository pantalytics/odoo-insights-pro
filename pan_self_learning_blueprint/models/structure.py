from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Readiness gates of an activity, kept on its tasks (project.task.pan_rung)
# and shown on activities and scenarios as rung_state (the word, never the number).
RUNG_SELECTION = [
    ("0", "Open"),
    ("1", "Decided"),
    ("2", "Built"),
    ("3", "Tested"),
    ("4", "Trained"),
    ("5", "Live"),
]

# From this rung on ("Tested") an activity counts as ready in a scenario's
# progress and in the progress band of the map.
TESTED_RUNG = 3

# Task state of a cancelled task (project). Cancelled tasks do not count for
# the rung or the hours of an activity or scenario.
CANCELLED_STATE = "1_canceled"


class PanSlStructureMixin(models.AbstractModel):
    """Shared behaviour for every blueprint record matched on ``code``.

    Used by chain, phase, role, process, activity and scenario. The blueprint
    import/export matches all of them on their ``code`` (it is also the key in
    the exported JSON), so the code must be present, trimmed and unique.
    Also offers the count and "open activities" helpers for smart buttons.
    """

    _name = "pan.sl.structure.mixin"
    _description = "Blueprint structure (code handling)"

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            code = record.code or ""
            if not code.strip():
                raise ValidationError(
                    _("%(model)s '%(name)s' needs a code.", model=record._description, name=record.name)
                )
            if code != code.strip() or any(char.isspace() for char in code):
                raise ValidationError(
                    _(
                        "The code '%(code)s' of %(model)s '%(name)s' may not contain spaces.",
                        code=code,
                        model=record._description,
                        name=record.name,
                    )
                )

    def _action_open_activities(self, field_name):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Activities of %(name)s", name=self.display_name),
            "res_model": "pan.sl.activity",
            "view_mode": "list,form",
            "domain": [(field_name, "=", self.id)],
            "context": {f"default_{field_name}": self.id},
        }

    def _compute_count_by(self, comodel, field_name, target_field):
        counts = dict(
            self.env[comodel]._read_group([(field_name, "in", self.ids)], [field_name], ["__count"])
        )
        for record in self:
            record[target_field] = counts.get(record, 0)


class PanSlProgressMixin(models.AbstractModel):
    """Rung and hours of an activity or a scenario, computed in one place.

    A model using it implements ``_progress_tasks()`` (the tasks that count
    for its hours) and ``_progress_rungs()`` (the rungs its rung is the lowest
    of), and overrides ``_compute_rung`` and ``_compute_hours`` only to declare
    its own ``@api.depends``. Stored and computed as sudo, so progress is the
    same for every viewer.
    """

    _name = "pan.sl.progress.mixin"
    _description = "Blueprint progress (rung and hours)"

    rung = fields.Integer(
        string="Rung",
        compute="_compute_rung",
        store=True,
        compute_sudo=True,
        help="Technical: the rung as a number (0 Open to 5 Live). Shown as Progress.",
    )
    rung_state = fields.Selection(
        selection=RUNG_SELECTION,
        string="Progress",
        compute="_compute_rung_state",
        store=True,
        help="Open, Decided, Built, Tested, Trained or Live.",
    )
    planned_hours = fields.Float(
        string="Planned hours",
        compute="_compute_hours",
        store=True,
        compute_sudo=True,
        aggregator="sum",
        help="Sum of the allocated hours of the counted tasks, cancelled tasks left out.",
    )
    spent_hours = fields.Float(
        string="Spent hours",
        compute="_compute_hours",
        store=True,
        compute_sudo=True,
        aggregator="sum",
        help="Sum of the timesheet hours on the counted tasks, cancelled tasks left out.",
    )

    def _progress_tasks(self):
        """The project tasks that count for the hours of this record."""
        raise NotImplementedError()

    def _progress_rungs(self):
        """The rungs (ints) this record's rung is the lowest of."""
        raise NotImplementedError()

    @staticmethod
    def _counted(tasks):
        """The tasks that count: all but the cancelled ones. Pass them as sudo,
        so the result is the same for every viewer."""
        return tasks.filtered(lambda task: task.state != CANCELLED_STATE)

    def _compute_rung(self):
        for record in self:
            rungs = record._progress_rungs()
            record.rung = min(rungs) if rungs else 0

    @api.depends("rung")
    def _compute_rung_state(self):
        for record in self:
            record.rung_state = str(record.rung)

    def _compute_hours(self):
        for record in self:
            tasks = record._progress_tasks()
            record.planned_hours = sum(tasks.mapped("allocated_hours"))
            record.spent_hours = sum(tasks.mapped("effective_hours"))


class PanSlChain(models.Model):
    _name = "pan.sl.chain"
    _inherit = ["pan.sl.structure.mixin"]
    _description = "Value chain"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the value chain (level 1), for example Lead to cash.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique technical code, used to match records when importing a blueprint.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of the chain in lists and on the company map.",
    )
    description = fields.Text(
        string="Description",
        help="What this chain covers, from the first trigger to the end result.",
    )
    process_ids = fields.One2many(
        "pan.sl.process",
        "chain_id",
        string="Processes",
        help="The processes (level 2) that make up this chain.",
    )
    process_count = fields.Integer(
        string="Process count",
        compute="_compute_process_count",
        help="Number of processes in this chain.",
    )
    activity_count = fields.Integer(
        string="Activity count",
        compute="_compute_activity_count",
        help="Number of activities in the processes of this chain.",
    )

    _code_unique = models.Constraint(
        "unique (code)",
        "A chain with this code already exists. Chain codes must be unique.",
    )

    @api.depends("process_ids")
    def _compute_process_count(self):
        self._compute_count_by("pan.sl.process", "chain_id", "process_count")

    def _compute_activity_count(self):
        self._compute_count_by("pan.sl.activity", "chain_id", "activity_count")

    def action_view_activities(self):
        return self._action_open_activities("chain_id")


class PanSlPhase(models.Model):
    _name = "pan.sl.phase"
    _inherit = ["pan.sl.structure.mixin"]
    _description = "Phase"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the phase, shown as a column on the company map (left to right follows Odoo's document chain).",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique technical code, used to match records when importing a blueprint.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Position of the column on the company map, from left to right.",
    )
    app_labels = fields.Char(
        string="Apps",
        help="Comma separated Odoo app names as in the Apps menu, for example: Sales, Inventory.",
    )
    activity_ids = fields.One2many(
        "pan.sl.activity",
        "phase_id",
        string="Activities",
        help="Activities that take place in this phase.",
    )
    activity_count = fields.Integer(
        string="Activity count",
        compute="_compute_activity_count",
        help="Number of activities in this phase.",
    )

    _code_unique = models.Constraint(
        "unique (code)",
        "A phase with this code already exists. Phase codes must be unique.",
    )

    @api.depends("activity_ids")
    def _compute_activity_count(self):
        self._compute_count_by("pan.sl.activity", "phase_id", "activity_count")

    def action_view_activities(self):
        return self._action_open_activities("phase_id")


class PanSlRole(models.Model):
    _name = "pan.sl.role"
    _inherit = ["pan.sl.structure.mixin"]
    _description = "Role"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the role, shown as a lane on the company map, for example Sales or Warehouse.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique technical code, used to match records when importing a blueprint.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Position of the lane on the company map, from top to bottom (external roles go to the edges).",
    )
    is_external = fields.Boolean(
        string="External",
        help="Tick for roles outside the company, such as the customer or the supplier. They are drawn at the edges of the map.",
    )
    description = fields.Text(
        string="Description",
        help="What this role is responsible for.",
    )
    activity_ids = fields.One2many(
        "pan.sl.activity",
        "role_id",
        string="Activities",
        help="Activities performed by this role.",
    )
    activity_count = fields.Integer(
        string="Activity count",
        compute="_compute_activity_count",
        help="Number of activities performed by this role.",
    )

    _code_unique = models.Constraint(
        "unique (code)",
        "A role with this code already exists. Role codes must be unique.",
    )

    @api.depends("activity_ids")
    def _compute_activity_count(self):
        self._compute_count_by("pan.sl.activity", "role_id", "activity_count")

    def action_view_activities(self):
        return self._action_open_activities("role_id")
