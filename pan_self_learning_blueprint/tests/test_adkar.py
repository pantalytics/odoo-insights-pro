from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from ..models.adkar import ADKAR_MIN_PEOPLE_FOR_BAND
from .common import BlueprintCase

ELEMENTS = ("awareness", "desire", "knowledge", "ability", "reinforcement")


@tagged("post_install", "-at_install")
class TestAdkar(BlueprintCase):
    """ADKAR scores: 1..5 per element, on a contact. The role band is the weakest element
    average of each person's latest score, only with at least ``ADKAR_MIN_PEOPLE_FOR_BAND``
    scored people."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Score = cls.env["pan.sl.adkar.score"]
        Partner = cls.env["res.partner"]
        cls.person_one = Partner.create({"name": "Test person one"})
        cls.person_two = Partner.create({"name": "Test person two"})
        cls.person_three = Partner.create({"name": "Test person three"})
        cls.person_other = Partner.create({"name": "Test person other"})

    def _score(self, partner, values, round_=1, **extra):
        vals = dict(zip(ELEMENTS, values), partner_id=partner.id, round=round_)
        vals.update(extra)
        return self.Score.create(vals)

    def _band(self, role):
        return role._get_adkar_bands()[role.id]

    def test_role_members_are_contacts(self):
        """D4: roles hold contacts; the old user link is gone."""
        self.assertEqual(self.Role._fields["partner_ids"].comodel_name, "res.partner")
        self.assertEqual(self.Score._fields["partner_id"].comodel_name, "res.partner")
        self.assertNotIn("user_ids", self.Role._fields, "pan.sl.role.user_ids must be replaced by partner_ids.")
        self.assertNotIn("user_id", self.Score._fields)

    def test_person_without_login_can_be_scored(self):
        self.assertFalse(self.person_one.user_ids)
        self.role_sales.partner_ids = self.person_one
        score = self._score(self.person_one, (3, 3, 3, 3, 3))
        self.assertEqual(score.partner_id, self.person_one)
        self.assertEqual(self.person_one.pan_role_ids, self.role_sales)

    def test_range_accepted(self):
        low = self._score(self.person_one, (1, 1, 1, 1, 1))
        high = self._score(self.person_one, (5, 5, 5, 5, 5), round_=2)
        self.env.flush_all()
        self.assertEqual(low.awareness, 1)
        self.assertEqual(high.reinforcement, 5)

    @mute_logger("odoo.sql_db")
    def test_range_refused(self):
        for element in ELEMENTS:
            for value in (0, 6):
                with self.subTest(element=element, value=value):
                    values = dict.fromkeys(ELEMENTS, 3)
                    values[element] = value
                    with self.assertRaises(ValidationError):
                        self._score(self.person_one, tuple(values[name] for name in ELEMENTS))
                        self.env.flush_all()

    def test_range_refused_on_write(self):
        score = self._score(self.person_one, (3, 3, 3, 3, 3))
        with self.assertRaises(ValidationError), mute_logger("odoo.sql_db"):
            score.knowledge = 9
            self.env.flush_all()

    def test_defaults(self):
        score = self._score(self.person_one, (3, 3, 3, 3, 3), round_=1)
        self.assertEqual(score.round, 1)
        self.assertTrue(score.date)
        default_round = self.Score.default_get(["round"]).get("round")
        self.assertEqual(default_round, 1)

    def test_role_ids_from_role_people(self):
        self.role_sales.partner_ids = self.person_one
        score = self._score(self.person_one, (3, 3, 3, 3, 3))
        self.assertIn(self.role_sales, score.role_ids)
        other = self._score(self.person_other, (3, 3, 3, 3, 3))
        self.assertNotIn(self.role_sales, other.role_ids)

    def test_scores_searchable_by_role(self):
        self.role_sales.partner_ids = self.person_one | self.person_two
        mine = self._score(self.person_one, (3, 3, 3, 3, 3)) | self._score(self.person_two, (2, 2, 2, 2, 2))
        other = self._score(self.person_other, (4, 4, 4, 4, 4))
        for domain in ([("role_ids", "in", self.role_sales.ids)], [("role_ids", "=", self.role_sales.id)]):
            with self.subTest(domain=domain):
                found = self.Score.search(domain)
                self.assertEqual(found & (mine | other), mine)

    def test_minimum_people_for_band(self):
        self.assertEqual(ADKAR_MIN_PEOPLE_FOR_BAND, 3)

    def test_band_false_without_scores(self):
        self.assertIs(self._band(self.role_sales), False, "A role without people has no band.")
        self.role_sales.partner_ids = self.person_one | self.person_two | self.person_three
        self.assertIs(self._band(self.role_sales), False, "People without scores give no band.")

    def test_band_hidden_below_three_people(self):
        """One or two scored people never give a band: it would say something about one person."""
        self.role_customer.partner_ids = self.person_one | self.person_two | self.person_three
        self._score(self.person_one, (5, 5, 5, 5, 5))
        self.assertIs(self._band(self.role_customer), False, "One scored person gives no band.")
        self._score(self.person_two, (5, 5, 5, 5, 5))
        self.assertIs(self._band(self.role_customer), False, "Two scored people give no band.")
        self._score(self.person_three, (5, 5, 5, 5, 5))
        self.assertEqual(self._band(self.role_customer), "high")

    def test_band_ignores_people_without_scores(self):
        """People of the role without a score count neither towards the minimum nor the average."""
        self.role_sales.partner_ids = self.person_one | self.person_two | self.person_three | self.person_other
        self._score(self.person_one, (4, 4, 4, 4, 4))
        self._score(self.person_two, (4, 4, 4, 4, 4))
        self.assertIs(self._band(self.role_sales), False)
        self._score(self.person_three, (4, 4, 4, 4, 4))
        self.assertEqual(self._band(self.role_sales), "high")

    def test_band_uses_latest_round_per_person(self):
        self.role_sales.partner_ids = self.person_one | self.person_two | self.person_three
        self._score(self.person_one, (1, 1, 1, 1, 1), round_=1)
        self._score(self.person_one, (5, 5, 5, 5, 4), round_=2)
        self._score(self.person_two, (5, 5, 5, 5, 4))
        self._score(self.person_three, (5, 5, 5, 5, 4))
        # Someone outside the role does not count.
        self._score(self.person_other, (1, 1, 1, 1, 1), round_=3)
        self.assertEqual(self._band(self.role_sales), "high", "Old rounds and outsiders must not pull the band down.")

    def test_band_thresholds_on_weakest_element(self):
        """The weakest element average decides: <= 2 low, < 4 medium, >= 4 high."""
        people = self.person_one | self.person_two | self.person_three
        self.role_sales.partner_ids = people
        cases = [
            # reinforcement of the three people (the other elements are 5), expected band
            ((2, 2, 2), "low"),
            ((1, 2, 3), "low"),  # average exactly 2
            ((2, 3, 2), "medium"),  # average 2.33
            ((3, 4, 4), "medium"),  # average 3.67
            ((4, 4, 4), "high"),
            ((5, 4, 3), "high"),  # average exactly 4
        ]
        for round_, (values, expected) in enumerate(cases, start=1):
            with self.subTest(values=values):
                for person, value in zip(people, values):
                    self._score(person, (5, 5, 5, 5, value), round_=round_)
                self.assertEqual(self._band(self.role_sales), expected)

    def test_band_is_a_word_never_a_number(self):
        """D5: only a band word or False leaves the method, no float and no list of scores."""
        self.role_sales.partner_ids = self.person_one | self.person_two | self.person_three
        for person in self.role_sales.partner_ids:
            self._score(person, (2, 3, 4, 3, 2))
        bands = (self.role_sales | self.role_customer)._get_adkar_bands()
        self.assertEqual(set(bands), {self.role_sales.id, self.role_customer.id})
        self.assertEqual(bands[self.role_sales.id], "low")
        self.assertIs(bands[self.role_customer.id], False)
        for value in bands.values():
            self.assertIn(value, ("low", "medium", "high", False))
