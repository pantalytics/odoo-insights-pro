from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Progress steps of a task stage (project.task.type.pan_rung), shown as words.
# Loading a blueprint gives a project one stage per step, named after it.
RUNG_SELECTION = [
    ("0", "Open"),
    ("1", "Decided"),
    ("2", "Built"),
    ("3", "Tested"),
    ("4", "Trained"),
    ("5", "Live"),
]

# From this rung on ("Tested") a subtask counts as done in its flow's progress.
TESTED_RUNG = 3

# Below this rung ("Trained") the people of a task's role still need training.
TRAINED_RUNG = 4

# Task state of a cancelled task (project). Cancelled tasks do not count.
CANCELLED_STATE = "1_canceled"


class PanSlStructureMixin(models.AbstractModel):
    """A phase or role is matched on ``code`` by the blueprint import, so the
    code must be present and have no spaces."""

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
            if any(char.isspace() for char in code):
                raise ValidationError(
                    _(
                        "The code '%(code)s' of %(model)s '%(name)s' may not contain spaces.",
                        code=code,
                        model=record._description,
                        name=record.name,
                    )
                )


class PanSlPhase(models.Model):
    _name = "pan.sl.phase"
    _inherit = ["pan.sl.structure.mixin"]
    _description = "Phase"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the phase, shown as a column on the map (left to right follows Odoo's document chain).",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Unique technical code, used to match phases when importing a blueprint.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Position of the column on the map, from left to right.",
    )
    _code_unique = models.Constraint(
        "unique (code)",
        "A phase with this code already exists. Phase codes must be unique.",
    )


class PanSlRole(models.Model):
    _name = "pan.sl.role"
    _inherit = ["pan.sl.structure.mixin"]
    _description = "Role"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
        help="Name of the role, shown as a lane on the map, for example Sales or Warehouse.",
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Technical code, unique within the project, used to match roles when importing a blueprint.",
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        index=True,
        ondelete="cascade",
        help="The project (company map) this role is a lane of.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        help="Position of the lane on the map, from top to bottom (external roles go to the edges).",
    )
    is_external = fields.Boolean(
        string="External",
        help="Tick for roles outside the company, such as the customer or the supplier. They are drawn at the edges of the map.",
    )
    description = fields.Text(
        string="Description",
        help="What this role is responsible for.",
    )

    _code_unique = models.Constraint(
        "unique (project_id, code)",
        "A role with this code already exists in this project. Role codes must be unique per project.",
    )
