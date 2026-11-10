from odoo.fields import Command
from odoo.tests import tagged

from ..models.structure import CANCELLED_STATE
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

    # ------------------------------------------------------------------
    # cancelled tasks, stored values, rung_state
    # ------------------------------------------------------------------

    def test_cancelled_task_does_not_hold_back_the_rung(self):
        cancelled = self._make_task(self.act_a, rung="0")
        self._make_task(self.act_a, rung="4")
        self.assertEqual(self.act_a.rung, 0)
        cancelled.state = CANCELLED_STATE
        self.assertEqual(self.act_a.rung, 4, "A cancelled task must not count for the rung.")
        cancelled.state = "01_in_progress"
        self.assertEqual(self.act_a.rung, 0, "A task that is no longer cancelled counts again.")

    def test_only_cancelled_tasks_gives_zero(self):
        task = self._make_task(self.act_a, rung="5")
        self.assertEqual(self.act_a.rung, 5)
        task.state = CANCELLED_STATE
        self.assertEqual(self.act_a.rung, 0)
        self.assertEqual(self.act_a.rung_state, "0")

    def test_cancelled_task_leaves_scenario_rung(self):
        scenario = self._make_scenario("t_scen_cancel", [(10, self.act_a), (20, self.act_b)])
        self._make_task(self.act_a, rung="3")
        blocker = self._make_task(self.act_b, rung="1")
        self._make_task(self.act_b, rung="4")
        self.assertEqual(scenario.rung, 1)
        blocker.state = CANCELLED_STATE
        self.assertEqual(scenario.rung, 3)

    def test_rung_is_stored_and_searchable(self):
        for model, field_name in (
            ("pan.sl.activity", "rung"),
            ("pan.sl.activity", "rung_state"),
            ("pan.sl.activity", "planned_hours"),
            ("pan.sl.activity", "spent_hours"),
            ("pan.sl.scenario", "rung"),
            ("pan.sl.scenario", "rung_state"),
            ("pan.sl.scenario", "planned_hours"),
            ("pan.sl.scenario", "spent_hours"),
        ):
            with self.subTest(model=model, field=field_name):
                self.assertTrue(self.env[model]._fields[field_name].store, f"{model}.{field_name} must be stored")
        self._make_task(self.act_a, rung="2")
        self._make_task(self.act_b, rung="4")
        ours = [("code", "like", "t_act_%")]
        self.assertEqual(self.Activity.search(ours + [("rung", "<", 3)]), self.act_a | self.act_c)
        self.assertEqual(self.Activity.search(ours + [("rung_state", "=", "4")]), self.act_b)
        groups = dict(
            self.Activity._read_group(ours, ["rung_state"], ["__count"])
        )
        self.assertEqual(groups, {"0": 1, "2": 1, "4": 1})

    def test_rung_state_labels(self):
        expected = [
            ("0", "Open"),
            ("1", "Decided"),
            ("2", "Built"),
            ("3", "Tested"),
            ("4", "Trained"),
            ("5", "Live"),
        ]
        for model in ("pan.sl.activity", "pan.sl.scenario"):
            with self.subTest(model=model):
                self.assertEqual(self.env[model]._fields["rung_state"].selection, expected)
        self.assertEqual(self.Task._fields["pan_rung"].selection, expected)

    def test_rung_state_follows_rung(self):
        scenario = self._make_scenario("t_scen_state", [(10, self.act_a)])
        self.assertEqual(self.act_a.rung_state, "0")
        self.assertEqual(scenario.rung_state, "0")
        task = self._make_task(self.act_a, rung="3")
        self.assertEqual(self.act_a.rung_state, "3")
        self.assertEqual(scenario.rung_state, "3")
        task.pan_rung = "5"
        self.assertEqual(self.act_a.rung_state, "5")
        self.assertEqual(scenario.rung_state, "5")
        labels = dict(self.Activity._fields["rung_state"]._description_selection(self.env))
        self.assertEqual(labels[self.act_a.rung_state], "Live")
