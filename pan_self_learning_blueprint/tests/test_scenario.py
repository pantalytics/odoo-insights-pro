from odoo.fields import Command
from odoo.tests import tagged

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestScenario(BlueprintCase):
    """Scenario routes: activities ordered by step sequence, searchable from the activity."""

    def test_activity_ids_ordered_by_step_sequence(self):
        scenario = self._make_scenario(
            "t_scen_order", [(30, self.act_a), (10, self.act_b), (20, self.act_c)]
        )
        self.assertEqual(scenario.activity_ids.ids, [self.act_b.id, self.act_c.id, self.act_a.id])

    def test_activity_ids_follow_resequence(self):
        scenario = self._make_scenario("t_scen_reseq", [(10, self.act_a), (20, self.act_b)])
        self.assertEqual(scenario.activity_ids.ids, [self.act_a.id, self.act_b.id])
        scenario.step_ids.filtered(lambda step: step.activity_id == self.act_b).sequence = 1
        self.assertEqual(scenario.activity_ids.ids, [self.act_b.id, self.act_a.id])

    def test_steps_cascade_with_scenario(self):
        scenario = self._make_scenario("t_scen_cascade", [(10, self.act_a)])
        steps = scenario.step_ids
        self.assertTrue(steps)
        scenario.unlink()
        self.assertFalse(steps.exists())

    def test_activity_scenario_ids(self):
        first = self._make_scenario("t_scen_one", [(10, self.act_a), (20, self.act_b)])
        second = self._make_scenario("t_scen_two", [(10, self.act_b)])
        self.assertEqual(self.act_a.scenario_ids, first)
        self.assertEqual(self.act_b.scenario_ids, first | second)
        self.assertFalse(self.act_c.scenario_ids)

    def test_search_activity_by_scenario(self):
        first = self._make_scenario("t_scen_search1", [(10, self.act_a), (20, self.act_b)])
        second = self._make_scenario("t_scen_search2", [(10, self.act_c)])
        ours = [("code", "like", "t_act_%")]
        self.assertEqual(
            self.Activity.search(ours + [("scenario_ids", "in", first.ids)]), self.act_a | self.act_b
        )
        self.assertEqual(self.Activity.search(ours + [("scenario_ids", "=", second.id)]), self.act_c)
        self.assertEqual(
            self.Activity.search(ours + [("scenario_ids", "in", (first | second).ids)]),
            self.act_a | self.act_b | self.act_c,
        )

    def test_search_activity_by_scenario_name(self):
        scenario = self._make_scenario("t_scen_named", [(10, self.act_c)])
        scenario.name = "Unusual route name for the search test"
        found = self.Activity.search([("scenario_ids.name", "ilike", "Unusual route name")])
        self.assertEqual(found, self.act_c)

    def test_search_activity_not_in_scenario(self):
        scenario = self._make_scenario("t_scen_negative", [(10, self.act_a)])
        ours = [("code", "like", "t_act_%")]
        found = self.Activity.search(ours + [("scenario_ids", "not in", scenario.ids)])
        self.assertEqual(found, self.act_b | self.act_c)

    def test_search_activity_scenario_not_set(self):
        """("scenario_ids", "=", False): the activities in no scenario route at all."""
        self._make_scenario("t_scen_unset", [(10, self.act_a), (20, self.act_b)])
        ours = [("code", "like", "t_act_%")]
        self.assertEqual(self.Activity.search(ours + [("scenario_ids", "=", False)]), self.act_c)
        self.assertEqual(self.Activity.search(ours + [("scenario_ids", "!=", False)]), self.act_a | self.act_b)

    def test_search_activity_scenario_set_counts_match(self):
        """"Is set" and "is not set" split the activities without overlap or gap."""
        self._make_scenario("t_scen_split", [(10, self.act_b)])
        total = self.Activity.search_count([])
        unset = self.Activity.search_count([("scenario_ids", "=", False)])
        is_set = self.Activity.search_count([("scenario_ids", "!=", False)])
        self.assertEqual(unset + is_set, total)
        self.assertEqual(is_set, len(self.Step.search([]).activity_id))

    def test_search_activity_scenario_ids_or_unset(self):
        scenario = self._make_scenario("t_scen_mixed", [(10, self.act_a)])
        self._make_scenario("t_scen_other", [(10, self.act_b)])
        ours = [("code", "like", "t_act_%")]
        found = self.Activity.search(ours + [("scenario_ids", "in", [scenario.id, False])])
        self.assertEqual(found, self.act_a | self.act_c)

    # ------------------------------------------------------------------
    # D9: progress = share of the scenario's activities that are Tested or further
    # ------------------------------------------------------------------

    def test_progress_zero_without_activities(self):
        scenario = self._make_scenario("t_scen_prog_empty", [])
        self.assertEqual(scenario.progress, 0.0)

    def test_progress_is_share_of_tested_activities(self):
        scenario = self._make_scenario(
            "t_scen_prog", [(10, self.act_a), (20, self.act_b), (30, self.act_c), (40, self.act_a)]
        )
        self.assertEqual(scenario.progress, 0.0)
        self._make_task(self.act_a, rung="2")
        self.assertEqual(scenario.progress, 0.0, "Built is not yet tested.")
        task_b = self._make_task(self.act_b, rung="3")
        self.assertAlmostEqual(scenario.progress, 100 / 3, msg="A revisited activity counts once.")
        self._make_task(self.act_c, rung="5")
        self.assertAlmostEqual(scenario.progress, 200 / 3)
        task_b.pan_rung = "1"
        self.assertAlmostEqual(scenario.progress, 100 / 3, msg="Progress follows the task rungs.")

    def test_progress_is_stored_and_searchable(self):
        """The "Not tested" filter searches on the stored progress."""
        done = self._make_scenario("t_scen_prog_done", [(10, self.act_a)])
        open_ = self._make_scenario("t_scen_prog_open", [(10, self.act_b)])
        self._make_task(self.act_a, rung="3")
        self.assertTrue(self.Scenario._fields["progress"].store)
        ours = [("code", "like", "t_scen_prog_%")]
        self.assertEqual(self.Scenario.search(ours + [("progress", "<", 100)]), open_)
        self.assertEqual(self.Scenario.search(ours + [("progress", "=", 100)]), done)

    def test_progress_drops_with_a_new_untested_step(self):
        scenario = self._make_scenario("t_scen_prog_add", [(10, self.act_a)])
        self._make_task(self.act_a, rung="4")
        self.assertEqual(scenario.progress, 100.0)
        scenario.write({"step_ids": [Command.create({"sequence": 20, "activity_id": self.act_b.id})]})
        self.assertEqual(scenario.progress, 50.0)
