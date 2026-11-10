from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ADKAR_FIELDS = ("awareness", "desire", "knowledge", "ability", "reinforcement")
ADKAR_MIN = 1
ADKAR_MAX = 5
# A role band is only shown when at least this many of its people have a
# score, so the company map never says something about one person.
ADKAR_MIN_PEOPLE_FOR_BAND = 3
# Band of the weakest ADKAR element of a role: "low" up to 2, "medium" below 4,
# "high" from 4.
ADKAR_BAND_LOW_MAX = 2
ADKAR_BAND_HIGH_MIN = 4


class PanSlAdkarScore(models.Model):
    """One ADKAR assessment of one person in one survey round.

    ADKAR (Awareness, Desire, Knowledge, Ability, Reinforcement) measures
    whether people are ready for the change. Each element is scored 1 to 5.
    People are contacts, so someone without a login can be scored too. The
    company map shows per role only a band (low, medium, high) for the weakest
    element, based on the latest round of each person holding that role.

    Scores are personal: record rules let a Blueprint user read only the
    scores on their own contact, managers read all of them, and the note is
    manager-only.
    """

    _name = "pan.sl.adkar.score"
    _description = "ADKAR score"
    _order = "date desc, round desc, id desc"
    _rec_name = "partner_id"

    partner_id = fields.Many2one(
        "res.partner",
        string="Person",
        required=True,
        index=True,
        ondelete="restrict",
        help="The person this ADKAR score is about. A contact, so a person without a login can be scored too.",
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
        help="Date on which the score was taken.",
    )
    round = fields.Integer(
        string="Round",
        required=True,
        default=1,
        aggregator="max",
        help="Survey round. The company map uses the latest round of each person.",
    )
    awareness = fields.Integer(
        string="Awareness",
        required=True,
        aggregator="avg",
        help="1-5: does this person understand why the change is needed?",
    )
    desire = fields.Integer(
        string="Desire",
        required=True,
        aggregator="avg",
        help="1-5: does this person want to take part in the change?",
    )
    knowledge = fields.Integer(
        string="Knowledge",
        required=True,
        aggregator="avg",
        help="1-5: does this person know how to work in the new way?",
    )
    ability = fields.Integer(
        string="Ability",
        required=True,
        aggregator="avg",
        help="1-5: can this person actually do the work in Odoo, day to day?",
    )
    reinforcement = fields.Integer(
        string="Reinforcement",
        required=True,
        aggregator="avg",
        help="1-5: is the new way of working anchored, so people do not fall back?",
    )
    average = fields.Float(
        string="Average",
        compute="_compute_average",
        store=True,
        digits=(3, 2),
        aggregator="avg",
        help="Average of the five ADKAR elements of this score.",
    )
    note = fields.Text(
        string="Note",
        groups="pan_self_learning_blueprint.group_blueprint_manager",
        help="Context for the score, for example the main blocker the person mentioned.",
    )
    role_ids = fields.Many2many(
        related="partner_id.pan_role_ids",
        string="Roles",
        help="Blueprint roles held by this person.",
    )

    _round_positive = models.Constraint(
        "CHECK (round >= 1)",
        "The survey round must be 1 or higher.",
    )

    @api.constrains(*ADKAR_FIELDS)
    def _check_adkar_range(self):
        labels = {name: self._fields[name].string for name in ADKAR_FIELDS}
        for score in self:
            for name in ADKAR_FIELDS:
                value = score[name]
                if not ADKAR_MIN <= value <= ADKAR_MAX:
                    raise ValidationError(
                        _(
                            "%(element)s for %(person)s must be between %(min)s and %(max)s, not %(value)s.",
                            element=labels[name],
                            person=score.partner_id.display_name,
                            min=ADKAR_MIN,
                            max=ADKAR_MAX,
                            value=value,
                        )
                    )

    @api.depends(*ADKAR_FIELDS)
    def _compute_average(self):
        for score in self:
            score.average = sum(score[name] for name in ADKAR_FIELDS) / len(ADKAR_FIELDS)


class ResPartner(models.Model):
    _inherit = "res.partner"

    pan_role_ids = fields.Many2many(
        "pan.sl.role",
        "pan_sl_role_res_partner_rel",
        "partner_id",
        "role_id",
        string="Blueprint roles",
        groups="pan_self_learning_blueprint.group_blueprint_user",
        help="Blueprint roles this person holds (the other side of the people on each role).",
    )


class PanSlRole(models.Model):
    _inherit = "pan.sl.role"

    partner_ids = fields.Many2many(
        "res.partner",
        "pan_sl_role_res_partner_rel",
        "role_id",
        "partner_id",
        string="People",
        domain=[("is_company", "=", False)],
        help="The people who hold this role. Contacts, so people without a login can be listed and scored too.",
    )

    def _get_adkar_bands(self):
        """ADKAR band per role: ``{role_id: "low" | "medium" | "high" | False}``.

        For each person of the role only the latest score counts (highest
        round, then latest date). The band describes the weakest of the five
        element averages. ``False`` when fewer than
        ``ADKAR_MIN_PEOPLE_FOR_BAND`` of the role's people have a score.
        Scores are read with sudo, because a Blueprint user may only read their
        own; only the band word leaves this method, never a number.
        """
        partners = self.partner_ids
        latest = {}
        if partners:
            scores = (
                self.env["pan.sl.adkar.score"]
                .sudo()
                .search(
                    [("partner_id", "in", partners.ids)],
                    order="round desc, date desc, id desc",
                )
            )
            for score in scores:
                latest.setdefault(score.partner_id.id, score)
        bands = {}
        for role in self:
            role_scores = [latest[partner.id] for partner in role.partner_ids if partner.id in latest]
            if len(role_scores) < ADKAR_MIN_PEOPLE_FOR_BAND:
                bands[role.id] = False
                continue
            weakest = min(
                sum(score[name] for score in role_scores) / len(role_scores) for name in ADKAR_FIELDS
            )
            if weakest <= ADKAR_BAND_LOW_MAX:
                bands[role.id] = "low"
            elif weakest < ADKAR_BAND_HIGH_MIN:
                bands[role.id] = "medium"
            else:
                bands[role.id] = "high"
        return bands
