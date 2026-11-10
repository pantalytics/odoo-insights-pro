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

    # ------------------------------------------------------------------
    # E5: archived tasks still count; only cancelled ones are left out
    # ------------------------------------------------------------------

    def test_archived_task_still_counts(self):
        scenario = self._make_scenario("t_scen_archive", [(10, self.act_a)])
        task = self._make_task(self.act_a, rung="2", scenario=scenario)
        task.allocated_hours = 4
        self._make_task(self.act_a, rung="5")
        self.assertEqual(self.act_a.rung, 2)
        task.active = False
        self.assertEqual(self.act_a.rung, 2, "An archived task still holds the rung.")
        self.assertEqual(self.act_a.planned_hours, 4)
        self.assertEqual(scenario.rung, 2)
        self.assertEqual(scenario.planned_hours, 4)
        task.pan_rung = "3"
        self.assertEqual(self.act_a.rung, 3, "A change on an archived task still recomputes the activity.")
        self.assertEqual(scenario.rung, 3)

    def test_archived_project_keeps_progress(self):
        """Archiving the implementation project (Odoo archives its tasks too) keeps rung, hours and details."""
        scenario = self._make_scenario("t_scen_project", [(10, self.act_a), (20, self.act_b)])
        task_a = self._make_task(self.act_a, rung="4", scenario=scenario)
        task_b = self._make_task(self.act_b, rung="3", scenario=scenario)
        task_a.allocated_hours = 5
        task_b.allocated_hours = 2
        before = {
            "activity": (self.act_a.rung, self.act_a.rung_state, self.act_a.planned_hours),
            "scenario": (scenario.rung, scenario.progress, scenario.planned_hours),
        }
        self.assertEqual(before["activity"], (4, "4", 5))
        self.assertEqual(before["scenario"], (3, 100, 7))

        self.project.active = False
        self.assertFalse(task_a.active, "Fixture: Odoo archives the tasks of an archived project.")
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(
            (self.act_a.rung, self.act_a.rung_state, self.act_a.planned_hours), before["activity"]
        )
        self.assertEqual(
            (scenario.rung, scenario.progress, scenario.planned_hours), before["scenario"]
        )
        item = next(item for item in self.Activity.get_map_data()["activities"] if item["id"] == self.act_a.id)
        self.assertEqual((item["rung"], item["planned_hours"]), (4, 5))
        details = {item["id"]: item for item in self.Activity.get_map_details()}
        self.assertEqual([task["id"] for task in details[self.act_a.id]["tasks"]], [task_a.id])

    def test_archived_cancelled_task_is_left_out(self):
        task = self._make_task(self.act_a, rung="1")
        self._make_task(self.act_a, rung="4")
        task.write({"active": False, "state": CANCELLED_STATE})
        self.assertEqual(self.act_a.rung, 4)

    # ------------------------------------------------------------------
    # E13: one word per meaning
    # ------------------------------------------------------------------

    def test_progress_words(self):
        """Progress is the Open..Live word; the scenario share is "Tested %"; phases name "Odoo apps"."""
        fields = self.env["ir.model.fields"]
        cases = (
            ("pan.sl.activity", "rung_state", "Progress"),
            ("pan.sl.activity", "rung", "Progress level"),
            ("pan.sl.scenario", "progress", "Tested %"),
            ("pan.sl.phase", "app_labels", "Odoo apps"),
            ("project.task", "pan_rung", "Blueprint progress"),
        )
        for model, name, label in cases:
            with self.subTest(model=model, field=name):
                self.assertEqual(self.env[model]._fields[name].string, label)
                self.assertTrue(fields._get(model, name).help, f"{model}.{name} needs a help text.")
