from odoo.fields import Command
from odoo.tests import tagged

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestRung(BlueprintCase):
    """Activity rung = lowest task rung (0 without tasks); scenario rung = lowest activity rung."""

    def test_task_rung_default(self):
        task = self.Task.create({"name": "Default rung", "project_id": self.project.id})
        self.assertEqual(task.pan_rung, "0")

    def test_rung_selection(self):
        values = [value for value, _label in self.Task._fields["pan_rung"].selection]
        self.assertEqual(values, ["0", "1", "2", "3", "4", "5"])

    def test_activity_without_tasks_is_zero(self):
        self.assertEqual(self.act_a.rung, 0)

    def test_activity_rung_is_min_of_tasks(self):
        self._make_task(self.act_a, rung="3")
        self._make_task(self.act_a, rung="5")
        self.assertEqual(self.act_a.rung, 3)
        self._make_task(self.act_a, rung="1")
        self.assertEqual(self.act_a.rung, 1)

    def test_activity_rung_follows_task_changes(self):
        task = self._make_task(self.act_a, rung="2")
        self.assertEqual(self.act_a.rung, 2)
        task.pan_rung = "4"
        self.assertEqual(self.act_a.rung, 4)
        task.pan_activity_ids = [Command.unlink(self.act_a.id)]
        self.assertEqual(self.act_a.rung, 0)

    def test_task_links_both_ways(self):
        task = self._make_task(self.act_a | self.act_b, rung="2")
        self.assertIn(task, self.act_a.task_ids)
        self.assertIn(task, self.act_b.task_ids)
        self.assertEqual(self.act_a.rung, 2)
        self.assertEqual(self.act_b.rung, 2)
        self.assertEqual(self.act_c.rung, 0)

    def test_scenario_rung_is_min_of_activities(self):
        scenario = self._make_scenario("t_scen_rung", [(10, self.act_a), (20, self.act_b)])
        self._make_task(self.act_a, rung="4")
        self._make_task(self.act_b, rung="2")
        self.assertEqual(scenario.rung, 2)

    def test_scenario_rung_zero_when_an_activity_has_no_task(self):
        scenario = self._make_scenario("t_scen_open", [(10, self.act_a), (20, self.act_c)])
        self._make_task(self.act_a, rung="5")
        self.assertEqual(scenario.rung, 0)

    def test_scenario_without_steps_is_zero(self):
        scenario = self._make_scenario("t_scen_empty", [])
        self.assertEqual(scenario.rung, 0)

    def test_scenario_rung_follows_task_changes(self):
        scenario = self._make_scenario("t_scen_live", [(10, self.act_a)])
        task = self._make_task(self.act_a, rung="3")
        self.assertEqual(scenario.rung, 3)
        task.pan_rung = "5"
        self.assertEqual(scenario.rung, 5)

    def test_scenario_tasks(self):
        scenario = self._make_scenario("t_scen_tasks", [(10, self.act_a)])
        task = self._make_task(self.act_a, rung="1", scenario=scenario)
        self.assertEqual(scenario.task_ids, task)
        self.assertEqual(scenario.task_count, 1)
