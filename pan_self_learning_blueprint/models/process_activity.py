from odoo import fields, models


class PanSlProcess(models.Model):
    """L2: a business process inside a value chain."""

    _name = "pan.sl.process"
    _description = "Blueprint Process"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the business process, for example 'Handle a quotation'.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique, stable code of the process. Used to match records on blueprint import.",
    )
    chain_id = fields.Many2one(
        "pan.sl.chain",
        string="Chain",
        required=True,
        ondelete="restrict",
        index=True,
        help="Value chain (level 1) this process belongs to.",
    )
    owner_role_id = fields.Many2one(
        "pan.sl.role",
        string="Owner Role",
        ondelete="set null",
        help="Role that owns this process and decides on its choices.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of the process within its chain.",
    )
    activity_ids = fields.One2many(
        "pan.sl.activity",
        "process_id",
        string="Activities",
        help="Activities (level 3) that make up this process.",
    )
    activity_count = fields.Integer(
        string="Activity Count",
        compute="_compute_activity_count",
        help="Number of activities in this process.",
    )

    _code_uniq = models.Constraint(
        "unique (code)",
        "A process with this code already exists. Process codes must be unique.",
    )

    def _compute_activity_count(self):
        counts = dict(
            self.env["pan.sl.activity"]._read_group(
                [("process_id", "in", self.ids)],
                groupby=["process_id"],
                aggregates=["__count"],
            )
        )
        for process in self:
            process.activity_count = counts.get(process, 0)


class PanSlActivity(models.Model):
    """L3, the atom: one role does one thing to one Odoo document."""

    _name = "pan.sl.activity"
    _description = "Blueprint Activity"
    _inherit = ["mail.thread"]
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        tracking=True,
        help="What the role does, for example 'Confirm the sales order'.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique, stable code of the activity. Used to match records on blueprint import.",
    )
    process_id = fields.Many2one(
        "pan.sl.process",
        string="Process",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
        help="Process (level 2) this activity belongs to.",
    )
    chain_id = fields.Many2one(
        "pan.sl.chain",
        string="Chain",
        related="process_id.chain_id",
        store=True,
        index=True,
        help="Value chain (level 1) of the process, stored for filtering and grouping.",
    )
    role_id = fields.Many2one(
        "pan.sl.role",
        string="Role",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
        help="Role (map lane) that performs this activity.",
    )
    phase_id = fields.Many2one(
        "pan.sl.phase",
        string="Phase",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
        group_expand="_read_group_expand_full",
        help="Phase (map column) in the Odoo document chain where this activity happens.",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Odoo Document",
        ondelete="set null",
        help="Odoo model (document) this activity acts on, for example sale.order.",
    )
    click_path = fields.Html(
        string="Click Path",
        help="Level 4: the steps in Odoo. Basis for the manual and the exercise.",
    )
    choice_state = fields.Selection(
        [
            ("proposal", "Proposal"),
            ("provisional", "Provisional"),
            ("fixed", "Fixed"),
            ("revised", "Revised"),
        ],
        string="Choice State",
        required=True,
        default="proposal",
        tracking=True,
        help="Where the choices for this activity stand: proposal, provisional, "
        "fixed or revised after being fixed. The chatter keeps the history.",
    )
    open_point = fields.Text(
        string="Open Point",
        help="What still has to be checked or decided for this activity.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Order of the activity within its phase and role lane.",
    )

    _code_uniq = models.Constraint(
        "unique (code)",
        "An activity with this code already exists. Activity codes must be unique.",
    )
