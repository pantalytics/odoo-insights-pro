from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import BlueprintCase

ELEMENTS = ("awareness", "desire", "knowledge", "ability", "reinforcement")


@tagged("post_install", "-at_install")
class TestAdkar(BlueprintCase):
    """ADKAR scores: 1..5 per element; role profile = average of each user's latest round."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Score = cls.env["pan.sl.adkar.score"]
        cls.user_one = new_test_user(cls.env, login="pan_sl_test_user_one", name="Test user one")
        cls.user_two = new_test_user(cls.env, login="pan_sl_test_user_two", name="Test user two")
        cls.user_other = new_test_user(cls.env, login="pan_sl_test_user_other", name="Test user other")

    def _score(self, user, values, round_=1, **extra):
        vals = dict(zip(ELEMENTS, values), user_id=user.id, round=round_)
        vals.update(extra)
        return self.Score.create(vals)

    def test_range_accepted(self):
        low = self._score(self.user_one, (1, 1, 1, 1, 1))
        high = self._score(self.user_one, (5, 5, 5, 5, 5), round_=2)
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
                        self._score(self.user_one, tuple(values[name] for name in ELEMENTS))
                        self.env.flush_all()

    def test_range_refused_on_write(self):
        score = self._score(self.user_one, (3, 3, 3, 3, 3))
        with self.assertRaises(ValidationError), mute_logger("odoo.sql_db"):
            score.knowledge = 9
            self.env.flush_all()

    def test_defaults(self):
        score = self._score(self.user_one, (3, 3, 3, 3, 3), round_=1)
        self.assertEqual(score.round, 1)
        self.assertTrue(score.date)
        default_round = self.Score.default_get(["round"]).get("round")
        self.assertEqual(default_round, 1)

    def test_role_ids_from_role_users(self):
        self.role_sales.user_ids = self.user_one
        score = self._score(self.user_one, (3, 3, 3, 3, 3))
        self.assertIn(self.role_sales, score.role_ids)
        other = self._score(self.user_other, (3, 3, 3, 3, 3))
        self.assertNotIn(self.role_sales, other.role_ids)

    def test_profile_false_without_scores(self):
        self.assertIs(self.role_sales._get_adkar_profile(), False, "A role without users has no profile.")
        self.role_sales.user_ids = self.user_one | self.user_two
        self.assertIs(self.role_sales._get_adkar_profile(), False, "Users without scores give no profile.")

    def test_profile_uses_latest_round_per_user(self):
        self.role_sales.user_ids = self.user_one | self.user_two
        self._score(self.user_one, (1, 1, 1, 1, 1), round_=1)
        self._score(self.user_one, (5, 4, 3, 2, 1), round_=2)
        self._score(self.user_two, (1, 1, 1, 1, 1), round_=1)
        # A user outside the role does not count.
        self._score(self.user_other, (5, 5, 5, 5, 5), round_=3)
        profile = self.role_sales._get_adkar_profile()
        self.assertEqual(len(profile), 5)
        for actual, expected in zip(profile, (3.0, 2.5, 2.0, 1.5, 1.0)):
            self.assertAlmostEqual(actual, expected)

    def test_profile_single_user(self):
        self.role_customer.user_ids = self.user_two
        self._score(self.user_two, (2, 3, 4, 5, 1))
        profile = self.role_customer._get_adkar_profile()
        for actual, expected in zip(profile, (2, 3, 4, 5, 1)):
            self.assertAlmostEqual(actual, expected)

    def test_profile_ignores_users_without_scores(self):
        self.role_sales.user_ids = self.user_one | self.user_two
        self._score(self.user_one, (4, 4, 4, 4, 4))
        profile = self.role_sales._get_adkar_profile()
        for actual in profile:
            self.assertAlmostEqual(actual, 4.0)
