from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

ADKAR_FIELDS = ("awareness", "desire", "knowledge", "ability", "reinforcement")
ADKAR_MIN = 1
ADKAR_MAX = 5
# A role profile is only shown when at least this many of its users have a
# score, so the "average" on the company map never exposes one person.
ADKAR_MIN_USERS_FOR_PROFILE = 3


class PanSlAdkarScore(models.Model):
    """One ADKAR self-assessment of one user in one survey round.

    ADKAR (Awareness, Desire, Knowledge, Ability, Reinforcement) measures
    whether people are ready for the change. Each element is scored 1 to 5.
    The company map shows the average profile per role, based on the latest
    round of each user holding that role.

    Scores are personal: record rules let a Blueprint user read only their
    own scores, managers read all of them, and the note is manager-only.
    """

    _name = "pan.sl.adkar.score"
    _description = "ADKAR score"
    _order = "date desc, round desc, id desc"
    _rec_name = "user_id"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        index=True,
        ondelete="cascade",
        help="The person this ADKAR score is about.",
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
        help="Survey round. The company map uses the latest round of each user.",
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
        "pan.sl.role",
        string="Roles",
        compute="_compute_role_ids",
        search="_search_role_ids",
        help="Blueprint roles held by this user (from the users on each role).",
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
                            "%(element)s for %(user)s must be between %(min)s and %(max)s, not %(value)s.",
                            element=labels[name],
                            user=score.user_id.display_name,
                            min=ADKAR_MIN,
                            max=ADKAR_MAX,
                            value=value,
                        )
                    )

    @api.constrains("round")
    def _check_round(self):
        for score in self:
            if score.round < 1:
                raise ValidationError(
                    _("The survey round of %(user)s must be 1 or higher.", user=score.user_id.display_name)
                )

    @api.depends(*ADKAR_FIELDS)
    def _compute_average(self):
        for score in self:
            score.average = sum(score[name] for name in ADKAR_FIELDS) / len(ADKAR_FIELDS)

    @api.depends("user_id")
    def _compute_role_ids(self):
        roles = self.env["pan.sl.role"].search([("user_ids", "in", self.user_id.ids)])
        for score in self:
            score.role_ids = roles.filtered(lambda role: score.user_id in role.user_ids)

    def _search_role_ids(self, operator, value):
        Role = self.env["pan.sl.role"]
        if operator == "in":
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            if not all(isinstance(item, int) for item in values):
                return NotImplemented
            roles = Role.browse(values).exists()
        elif operator == "ilike" and isinstance(value, str):
            roles = Role.search([("name", "ilike", value)])
        elif operator == "any":
            roles = Role.search(value)
        else:
            return NotImplemented
        return Domain("user_id", "in", roles.user_ids.ids)


class PanSlRole(models.Model):
    _inherit = "pan.sl.role"

    def _get_adkar_profile(self):
        """Average ADKAR profile of the users holding this role.

        For each user of the role only the latest score counts (highest round,
        then latest date). Returns a list of five floats in ADKAR order, or
        ``False`` when fewer than ``ADKAR_MIN_USERS_FOR_PROFILE`` of the
        role's users have a score (no individual profile is ever returned).
        """
        self.ensure_one()
        return self._get_adkar_profiles()[self.id]

    def _get_adkar_profiles(self):
        """Batch version of :meth:`_get_adkar_profile`: ``{role_id: profile}``.

        Scores are read with sudo, because a Blueprint user may only read their
        own scores; only the aggregate per role leaves this method.
        """
        users = self.user_ids
        latest = {}
        if users:
            scores = (
                self.env["pan.sl.adkar.score"]
                .sudo()
                .search(
                    [("user_id", "in", users.ids)],
                    order="round desc, date desc, id desc",
                )
            )
            for score in scores:
                latest.setdefault(score.user_id.id, score)
        profiles = {}
        for role in self:
            role_scores = [latest[user.id] for user in role.user_ids if user.id in latest]
            if len(role_scores) < ADKAR_MIN_USERS_FOR_PROFILE:
                profiles[role.id] = False
                continue
            profiles[role.id] = [
                sum(score[name] for score in role_scores) / len(role_scores) for name in ADKAR_FIELDS
            ]
        return profiles
