from odoo.fields import Command
from odoo.tests import tagged

from .common import BlueprintCase

PHASE_KEYS = {"id", "name", "code", "apps"}
APP_KEYS = {"name", "installed"}
ROLE_KEYS = {"id", "name", "is_external", "users", "adkar"}
ACTIVITY_KEYS = {
    "id", "name", "code", "role_id", "phase_id", "choice_state", "rung",
    "open_point", "scenario_ids", "model",
}
DETAIL_KEYS = {"id", "tasks", "click_path"}
DETAIL_TASK_KEYS = {"id", "name", "rung"}
SCENARIO_KEYS = {"id", "code", "name", "description", "open_point", "rung", "progress", "activity_ids"}


@tagged("post_install", "-at_install")
class TestMapData(BlueprintCase):
    """``get_map_data()``: one call with everything the company map draws, without N+1 queries."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.phase_a.app_labels = "Project, T not an app"
        cls.act_a.write(
            {
                "model_id": cls.env["ir.model"]._get("res.partner").id,
                "open_point": "Who approves?",
                "choice_state": "provisional",
            }
        )
        Partner = cls.env["res.partner"]
        cls.people = Partner.create(
            [{"name": "Map test person"}, {"name": "Map test person 2"}, {"name": "Map test person 3"}]
        )
        cls.role_sales.partner_ids = cls.people[0]

    def _by_id(self, items):
        return {item["id"]: item for item in items}

    def _role(self, role):
        return self._by_id(self.Activity.get_map_data()["roles"])[role.id]

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

    def test_phase_apps_with_installed_flag(self):
        """D12: each app is ``{name, installed}``; installed only for an installed application."""
        phases = self._by_id(self.Activity.get_map_data()["phases"])
        phase = phases[self.phase_a.id]
        self.assertEqual(phase["code"], "t_phase_a")
        self.assertEqual(
            phase["apps"],
            [{"name": "Project", "installed": True}, {"name": "T not an app", "installed": False}],
        )
        for app in phase["apps"]:
            self.assertEqual(set(app), APP_KEYS)
        self.assertEqual(phases[self.phase_b.id]["apps"], [])

    def test_role_values(self):
        roles = self._by_id(self.Activity.get_map_data()["roles"])
        self.assertFalse(roles[self.role_sales.id]["is_external"])
        self.assertTrue(roles[self.role_customer.id]["is_external"])
        self.assertEqual(roles[self.role_sales.id]["users"], ["Map test person"])
        self.assertEqual(roles[self.role_customer.id]["users"], [])
        self.assertIs(roles[self.role_sales.id]["adkar"], False)

    def test_role_adkar_band(self):
        """D5: the band appears once three people of the role have a score, and is only a word."""
        Score = self.env["pan.sl.adkar.score"]
        self.role_sales.partner_ids = self.people
        values = {"awareness": 5, "desire": 4, "knowledge": 4, "ability": 4, "reinforcement": 3}
        Score.create([dict(values, partner_id=person.id) for person in self.people[:2]])
        self.assertIs(self._role(self.role_sales)["adkar"], False, "Two scored people must not give a band.")
        Score.create(dict(values, partner_id=self.people[2].id))
        self.assertEqual(self._role(self.role_sales)["adkar"], "medium")

    def test_no_adkar_number_reaches_the_map(self):
        """D5: no float, no list of scores and no person id leave the server in the map data."""
        Score = self.env["pan.sl.adkar.score"]
        self.role_sales.partner_ids = self.people
        Score.create(
            [
                {"partner_id": person.id, "awareness": 1, "desire": 2, "knowledge": 3, "ability": 4,
                 "reinforcement": 5}
                for person in self.people
            ]
        )
        role = self._role(self.role_sales)
        self.assertEqual(role["adkar"], "low")
        self.assertTrue(all(isinstance(name, str) for name in role["users"]))

        def walk(value, path):
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, f"{path}.{key}")
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")
            else:
                self.assertNotIsInstance(value, float, f"{path} is a float; the map gets no scores.")

        walk(self.Activity.get_map_data(), "data")

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
        self.assertNotIn("training", item, "D3: no per-person training on the map.")

        other = activities[self.act_b.id]
        self.assertIs(other["model"], False)
        self.assertEqual(other["scenario_ids"], [])
        self.assertEqual(other["rung"], 0)

    def test_scenario_activity_order_and_progress(self):
        scenario = self._make_scenario("t_map_order", [(30, self.act_a), (10, self.act_c), (20, self.act_b)])
        self._make_task(self.act_a | self.act_b, rung="3")
        self._make_task(self.act_c, rung="1")
        item = self._by_id(self.Activity.get_map_data()["scenarios"])[scenario.id]
        self.assertEqual(item["code"], "t_map_order")
        self.assertEqual(item["activity_ids"], [self.act_c.id, self.act_b.id, self.act_a.id])
        self.assertEqual(item["rung"], 1)
        self.assertEqual(item["progress"], 67, "Two of three activities tested, as a rounded percentage.")
        self.assertIsInstance(item["progress"], int)

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

    # ------------------------------------------------------------------
    # get_map_details (zoom stop "Detail")
    # ------------------------------------------------------------------

    def test_map_details_shape(self):
        """One item per activity: ``{id, tasks: [{id, name, rung}], click_path}`` (what map_action.js reads)."""
        self.act_a.click_path = "<ol><li>Contacts, New</li><li>Save</li></ol>"
        shared = self._make_task(self.act_a | self.act_b, rung="3")
        shared.name = "Shared task"
        only_a = self._make_task(self.act_a, rung="1")
        details = self.Activity.get_map_details()
        self.assertIsInstance(details, list)
        by_id = self._by_id(details)
        self.assertEqual(set(by_id), set(self.Activity.search([]).ids))
        for item in details:
            self.assertEqual(set(item), DETAIL_KEYS)
            for task in item["tasks"]:
                self.assertEqual(set(task), DETAIL_TASK_KEYS)
                self.assertIsInstance(task["rung"], int)

        tasks_a = {task["id"]: task for task in by_id[self.act_a.id]["tasks"]}
        self.assertEqual(set(tasks_a), {shared.id, only_a.id})
        self.assertEqual(tasks_a[shared.id], {"id": shared.id, "name": "Shared task", "rung": 3})
        self.assertEqual(tasks_a[only_a.id]["rung"], 1)
        self.assertEqual(
            [task["id"] for task in by_id[self.act_b.id]["tasks"]],
            [shared.id],
            "A task linked to two activities appears under both.",
        )
        self.assertEqual(by_id[self.act_c.id]["tasks"], [])
        self.assertEqual(by_id[self.act_a.id]["click_path"], "Contacts, New")
        self.assertIs(by_id[self.act_b.id]["click_path"], False)

    def test_map_details_leave_out_cancelled_tasks(self):
        """Cancelled tasks do not count for the rung, so the Detail stop does not list them either."""
        kept = self._make_task(self.act_a, rung="2")
        cancelled = self._make_task(self.act_a, rung="0")
        cancelled.state = "1_canceled"
        tasks = self._by_id(self.Activity.get_map_details())[self.act_a.id]["tasks"]
        self.assertEqual([task["id"] for task in tasks], [kept.id])

    def test_map_first_line(self):
        cases = [
            ("<ol><li>A</li><li>B</li></ol>", "A"),
            ("<div><ul><li>X</li></ul></div>", "X"),
            ("<p>  Open   <b>Sales</b> </p><p>Then save</p>", "Open Sales"),
            ("line1<br>line2", "line1"),
            ("plain text", "plain text"),
            ("<p><br></p>", False),
            ("", False),
            (False, False),
        ]
        for click_path, expected in cases:
            with self.subTest(click_path=click_path):
                self.assertEqual(self.Activity._map_first_line(click_path), expected)

    def _count_detail_queries(self):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.cr.sql_log_count
        details = self.Activity.get_map_details()
        return self.cr.sql_log_count - before, details

    def test_map_details_query_count_does_not_grow(self):
        """Loose N+1 guard for get_map_details, like the one for get_map_data."""
        scenario = self._make_scenario("t_map_dbulk", [(10, self.act_a)])
        self._add_activities(5, scenario)
        self._count_detail_queries()
        small, details_small = self._count_detail_queries()
        added = self._add_activities(30, scenario)
        large, details_large = self._count_detail_queries()
        self.assertEqual(len(details_large), len(details_small) + len(added))
        self.assertLess(
            large - small,
            10,
            f"get_map_details used {small} queries before and {large} after adding {len(added)} activities: "
            "it reads per record instead of in batches.",
        )
