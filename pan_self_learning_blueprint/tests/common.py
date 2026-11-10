"""Shared fixture for the blueprint tests.

Every record made here uses a code with the ``t_`` prefix, so the tests never
collide with a template that is already loaded in the database.
"""

from odoo.fields import Command
from odoo.tests.common import TransactionCase


class BlueprintCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Chain = cls.env["pan.sl.chain"]
        cls.Phase = cls.env["pan.sl.phase"]
        cls.Role = cls.env["pan.sl.role"]
        cls.Process = cls.env["pan.sl.process"]
        cls.Activity = cls.env["pan.sl.activity"]
        cls.Scenario = cls.env["pan.sl.scenario"]
        cls.Step = cls.env["pan.sl.scenario.step"]
        cls.Task = cls.env["project.task"]

        cls.chain = cls.Chain.create({"name": "Test chain", "code": "t_chain", "sequence": 10})
        cls.phase_a = cls.Phase.create({"name": "Test phase A", "code": "t_phase_a", "sequence": 10})
        cls.phase_b = cls.Phase.create({"name": "Test phase B", "code": "t_phase_b", "sequence": 20})
        cls.role_sales = cls.Role.create({"name": "Test sales", "code": "t_sales", "sequence": 10})
        cls.role_customer = cls.Role.create(
            {"name": "Test customer", "code": "t_customer", "sequence": 20, "is_external": True}
        )
        cls.process = cls.Process.create(
            {
                "name": "Test process",
                "code": "t_process",
                "chain_id": cls.chain.id,
                "owner_role_id": cls.role_sales.id,
            }
        )
        cls.act_a = cls._make_activity("t_act_a", cls.role_sales, cls.phase_a, sequence=10)
        cls.act_b = cls._make_activity("t_act_b", cls.role_sales, cls.phase_b, sequence=20)
        cls.act_c = cls._make_activity("t_act_c", cls.role_customer, cls.phase_b, sequence=30)
        cls.project = cls.env["project.project"].create({"name": "Test implementation project"})

    @classmethod
    def _make_activity(cls, code, role, phase, **extra):
        vals = {
            "name": f"Activity {code}",
            "code": code,
            "process_id": cls.process.id,
            "role_id": role.id,
            "phase_id": phase.id,
        }
        vals.update(extra)
        return cls.Activity.create(vals)

    def _make_task(self, activities, rung="0", scenario=False):
        return self.Task.create(
            {
                "name": "Test task",
                "project_id": self.project.id,
                "pan_activity_ids": [Command.set(activities.ids)],
                "pan_rung": rung,
                "pan_scenario_id": scenario.id if scenario else False,
            }
        )

    def _make_scenario(self, code, steps):
        """Create a scenario; ``steps`` is a list of (sequence, activity)."""
        return self.Scenario.create(
            {
                "name": f"Scenario {code}",
                "code": code,
                "step_ids": [
                    Command.create({"sequence": sequence, "activity_id": activity.id}) for sequence, activity in steps
                ],
            }
        )
