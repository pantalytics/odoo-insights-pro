from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from ..models.adkar import ADKAR_MIN_USERS_FOR_PROFILE
from .common import BlueprintCase

ELEMENTS = ("awareness", "desire", "knowledge", "ability", "reinforcement")


@tagged("post_install", "-at_install")
class TestAdkar(BlueprintCase):
    """ADKAR scores: 1..5 per element; role profile = average of each user's latest round,
    only when at least ``ADKAR_MIN_USERS_FOR_PROFILE`` users of the role have a score."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Score = cls.env["pan.sl.adkar.score"]
        cls.user_one = new_test_user(cls.env, login="pan_sl_test_user_one", name="Test user one")
        cls.user_two = new_test_user(cls.env, login="pan_sl_test_user_two", name="Test user two")
        cls.user_three = new_test_user(cls.env, login="pan_sl_test_user_three", name="Test user three")
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
        self.role_sales.user_ids = self.user_one | self.user_two | self.user_three
        self._score(self.user_one, (1, 1, 1, 1, 1), round_=1)
        self._score(self.user_one, (5, 4, 3, 2, 1), round_=2)
        self._score(self.user_two, (1, 1, 1, 1, 1), round_=1)
        self._score(self.user_three, (3, 4, 5, 3, 1), round_=1)
        # A user outside the role does not count.
        self._score(self.user_other, (5, 5, 5, 5, 5), round_=3)
        profile = self.role_sales._get_adkar_profile()
        self.assertEqual(len(profile), 5)
        for actual, expected in zip(profile, (3.0, 3.0, 3.0, 2.0, 1.0)):
            self.assertAlmostEqual(actual, expected)

    def test_minimum_users_for_profile(self):
        self.assertEqual(ADKAR_MIN_USERS_FOR_PROFILE, 3)

    def test_profile_hidden_below_three_users(self):
        """One or two scored users never give a profile: it would expose individual scores."""
        self.role_customer.user_ids = self.user_one | self.user_two | self.user_three
        self._score(self.user_one, (2, 3, 4, 5, 1))
        self.assertIs(self.role_customer._get_adkar_profile(), False, "One scored user gives no profile.")
        self._score(self.user_two, (4, 3, 2, 1, 5))
        self.assertIs(self.role_customer._get_adkar_profile(), False, "Two scored users give no profile.")
        self._score(self.user_three, (3, 3, 3, 3, 3))
        profile = self.role_customer._get_adkar_profile()
        for actual in profile:
            self.assertAlmostEqual(actual, 3.0)

    def test_profile_ignores_users_without_scores(self):
        """Users of the role without a score neither count towards the minimum nor the average."""
        self.role_sales.user_ids = self.user_one | self.user_two | self.user_three | self.user_other
        self._score(self.user_one, (4, 4, 4, 4, 4))
        self._score(self.user_two, (4, 4, 4, 4, 4))
        self.assertIs(self.role_sales._get_adkar_profile(), False)
        self._score(self.user_three, (1, 1, 1, 1, 1))
        profile = self.role_sales._get_adkar_profile()
        for actual in profile:
            self.assertAlmostEqual(actual, 3.0)

    def test_profiles_batch_matches_single(self):
        self.role_sales.user_ids = self.user_one | self.user_two | self.user_three
        for user in self.role_sales.user_ids:
            self._score(user, (2, 2, 2, 2, 2))
        profiles = (self.role_sales | self.role_customer)._get_adkar_profiles()
        self.assertEqual(profiles[self.role_sales.id], self.role_sales._get_adkar_profile())
        self.assertIs(profiles[self.role_customer.id], False)
