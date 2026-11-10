from odoo.tests import tagged

from ..models.structure import CANCELLED_STATE
from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestHours(BlueprintCase):
    """Planned and spent hours roll up from tasks to activities and scenarios."""

    def _log(self, task, hours):
        employee = self.env["hr.employee"].create({"name": "Consultant", "user_id": self.env.uid})
        self.env["account.analytic.line"].create(
            {
                "name": "Work",
                "task_id": task.id,
                "project_id": task.project_id.id,
                "unit_amount": hours,
                "employee_id": employee.id,
            }
        )

    def test_activity_without_tasks_has_no_hours(self):
        self.assertEqual(self.act_a.planned_hours, 0)
        self.assertEqual(self.act_a.spent_hours, 0)

    def test_activity_sums_planned_and_spent(self):
        task_one = self._make_task(self.act_a)
        task_two = self._make_task(self.act_a)
        task_one.allocated_hours = 4
        task_two.allocated_hours = 6
        self._log(task_one, 3)
        self.assertEqual(self.act_a.planned_hours, 10)
        self.assertEqual(self.act_a.spent_hours, 3)

    def test_scenario_counts_each_task_once(self):
        scenario = self._make_scenario("t_hours", [(10, self.act_a), (20, self.act_b)])
        task = self._make_task(self.act_a | self.act_b, scenario=scenario)
        task.allocated_hours = 5
        self._log(task, 2)
        self.assertEqual(scenario.planned_hours, 5)
        self.assertEqual(scenario.spent_hours, 2)
        # The same task counts fully for each activity it moves forward.
        self.assertEqual(self.act_a.planned_hours, 5)
        self.assertEqual(self.act_b.planned_hours, 5)

    def test_cancelled_tasks_left_out_of_hours(self):
        scenario = self._make_scenario("t_hours_cancel", [(10, self.act_a)])
        kept = self._make_task(self.act_a, scenario=scenario)
        cancelled = self._make_task(self.act_a, scenario=scenario)
        kept.allocated_hours = 4
        cancelled.allocated_hours = 6
        self._log(cancelled, 2)
        self.assertEqual(self.act_a.planned_hours, 10)
        self.assertEqual(scenario.planned_hours, 10)
        cancelled.state = CANCELLED_STATE
        self.assertEqual(self.act_a.planned_hours, 4)
        self.assertEqual(self.act_a.spent_hours, 0)
        self.assertEqual(scenario.planned_hours, 4)
        self.assertEqual(scenario.spent_hours, 0)

    def test_hours_can_be_summed_in_a_group_by(self):
        self._make_task(self.act_a).allocated_hours = 3
        self._make_task(self.act_b).allocated_hours = 5
        [(total,)] = self.Activity._read_group([("code", "like", "t_act_%")], [], ["planned_hours:sum"])
        self.assertEqual(total, 8)
