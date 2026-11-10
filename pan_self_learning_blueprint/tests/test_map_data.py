from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .common import BlueprintCase

PHASE_KEYS = {"id", "name", "code", "apps"}
ROLE_KEYS = {"id", "name", "is_external", "users", "adkar"}
ACTIVITY_KEYS = {
    "id", "name", "code", "role_id", "phase_id", "choice_state", "rung",
    "open_point", "scenario_ids", "model",
}
SCENARIO_KEYS = {"id", "code", "name", "description", "open_point", "rung", "activity_ids"}


@tagged("post_install", "-at_install")
class TestMapData(BlueprintCase):
    """``get_map_data()``: one call with everything the company map draws, without N+1 queries."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.phase_a.app_labels = "Sales, Invoicing"
        cls.act_a.write(
            {
                "model_id": cls.env["ir.model"]._get("res.partner").id,
                "open_point": "Who approves?",
                "choice_state": "provisional",
            }
        )
        cls.user = new_test_user(cls.env, login="pan_sl_map_user", name="Map test user")
        cls.role_sales.user_ids = cls.user

    def _by_id(self, items):
        return {item["id"]: item for item in items}

    def test_structure_keys(self):
        data = self.Activity.get_map_data()
        self.assertEqual(set(data), {"phases", "roles", "activities", "scenarios"})
        self._make_scenario("t_map_keys", [(10, self.act_a)])
        data = self.Activity.get_map_data()
        for section, keys in (
            ("phases", PHASE_KEYS),
            ("roles", ROLE_KEYS),
            ("activities", ACTIVITY_KEYS),
            ("scenarios", SCENARIO_KEYS),
        ):
            self.assertTrue(data[section], f"{section} must not be empty in this fixture")
            for item in data[section]:
                with self.subTest(section=section, item=item.get("code") or item.get("name")):
                    self.assertEqual(set(item), keys)

    def test_phase_and_role_values(self):
        data = self.Activity.get_map_data()
        phase = self._by_id(data["phases"])[self.phase_a.id]
        self.assertEqual(phase["code"], "t_phase_a")
        self.assertEqual(phase["apps"], ["Sales", "Invoicing"])
        self.assertEqual(self._by_id(data["phases"])[self.phase_b.id]["apps"], [])

        roles = self._by_id(data["roles"])
        self.assertFalse(roles[self.role_sales.id]["is_external"])
        self.assertTrue(roles[self.role_customer.id]["is_external"])
        self.assertEqual(roles[self.role_sales.id]["users"], ["Map test user"])
        self.assertIs(roles[self.role_sales.id]["adkar"], False)

    def test_role_adkar_profile(self):
        self.env["pan.sl.adkar.score"].create(
            {"user_id": self.user.id, "awareness": 1, "desire": 2, "knowledge": 3, "ability": 4, "reinforcement": 5}
        )
        role = self._by_id(self.Activity.get_map_data()["roles"])[self.role_sales.id]
        self.assertEqual(len(role["adkar"]), 5)
        for actual, expected in zip(role["adkar"], (1, 2, 3, 4, 5)):
            self.assertAlmostEqual(actual, expected)

    def test_activity_values(self):
        scenario = self._make_scenario("t_map_values", [(10, self.act_a)])
        self._make_task(self.act_a, rung="2")
        activities = self._by_id(self.Activity.get_map_data()["activities"])
        item = activities[self.act_a.id]
        self.assertEqual(item["code"], "t_act_a")
        self.assertEqual(item["role_id"], self.role_sales.id)
        self.assertEqual(item["phase_id"], self.phase_a.id)
        self.assertEqual(item["choice_state"], "provisional")
        self.assertEqual(item["rung"], 2)
        self.assertEqual(item["open_point"], "Who approves?")
        self.assertEqual(item["scenario_ids"], [scenario.id])
        self.assertEqual(item["model"], "res.partner")

        other = activities[self.act_b.id]
        self.assertIs(other["model"], False)
        self.assertEqual(other["scenario_ids"], [])
        self.assertEqual(other["rung"], 0)

    def test_scenario_activity_order(self):
        scenario = self._make_scenario("t_map_order", [(30, self.act_a), (10, self.act_c), (20, self.act_b)])
        self._make_task(self.act_a | self.act_b | self.act_c, rung="3")
        item = self._by_id(self.Activity.get_map_data()["scenarios"])[scenario.id]
        self.assertEqual(item["code"], "t_map_order")
        self.assertEqual(item["activity_ids"], [self.act_c.id, self.act_b.id, self.act_a.id])
        self.assertEqual(item["rung"], 3)

    def _count_queries(self):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.cr.sql_log_count
        data = self.Activity.get_map_data()
        return self.cr.sql_log_count - before, data

    def _add_activities(self, count, scenario):
        new = self.Activity.browse()
        start = self.Activity.search_count([("code", "=like", f"t_map_bulk_{scenario.code}_%")])
        for index in range(count):
            code = f"t_map_bulk_{scenario.code}_{start + index}"
            new |= self._make_activity(code, self.role_customer, self.phase_b, sequence=100 + index)
        self.Task.create(
            [
                {
                    "name": f"Bulk task {index}",
                    "project_id": self.project.id,
                    "pan_activity_ids": [Command.link(activity.id)],
                    "pan_rung": "1",
                }
                for index, activity in enumerate(new)
            ]
        )
        scenario.write(
            {
                "step_ids": [
                    Command.create({"sequence": 100 + index, "activity_id": activity.id})
                    for index, activity in enumerate(new)
                ]
            }
        )
        return new

    def test_query_count_does_not_grow_with_activities(self):
        """Loose N+1 guard: 30 extra activities may not cost noticeably more queries than 5."""
        scenario = self._make_scenario("t_map_bulk", [(10, self.act_a)])
        self._add_activities(5, scenario)
        self._count_queries()  # warm registry-level caches
        small, data_small = self._count_queries()
        added = self._add_activities(30, scenario)
        large, data_large = self._count_queries()
        self.assertEqual(len(data_large["activities"]), len(data_small["activities"]) + len(added))
        self.assertLess(
            large - small,
            10,
            f"get_map_data used {small} queries before and {large} after adding {len(added)} activities: "
            "it reads per record instead of in batches.",
        )
