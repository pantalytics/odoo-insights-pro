from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PanSlStructureMixin(models.AbstractModel):
    """Shared behaviour for the structural blueprint records (chain, phase, role).

    Every structural record is matched on its ``code`` by the blueprint
    import/export, so the code must be present, trimmed and unique.
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
    model_ids = fields.Many2many(
        "ir.model",
        string="Odoo models",
        help="The Odoo documents (models) handled in this phase, for example quotations or deliveries.",
    )
    app_labels = fields.Char(
        string="Apps",
        help="Comma separated Odoo app names shown as chips in the Odoo band of the map, for example: Sales, Inventory.",
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
    group_ids = fields.Many2many(
        "res.groups",
        string="Access groups",
        help="The Odoo access groups people in this role need to do their activities.",
    )
    user_ids = fields.Many2many(
        "res.users",
        "pan_sl_role_res_users_rel",
        "role_id",
        "user_id",
        string="Users",
        help="The people who hold this role.",
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
