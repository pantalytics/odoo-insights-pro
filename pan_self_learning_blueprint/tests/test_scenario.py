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
