"""Shared fixture: one project with two roles, two phases and a flow.

Every phase made here uses a code with the ``t_`` prefix, so the tests never
collide with phases a loaded template put in the database.
"""

from odoo.tests.common import TransactionCase


class BlueprintCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Phase = cls.env["pan.sl.phase"]
        cls.Role = cls.env["pan.sl.role"]
        cls.Task = cls.env["project.task"]
        cls.project = cls.env["project.project"].create({"name": "Test implementation project"})
        cls.phase_a = cls.Phase.create({"name": "Test phase A", "code": "t_phase_a", "sequence": 10})
        cls.phase_b = cls.Phase.create({"name": "Test phase B", "code": "t_phase_b", "sequence": 20})
        cls.role_sales = cls.Role.create(
            {"name": "Test sales", "code": "t_sales", "sequence": 10, "project_id": cls.project.id}
        )
        cls.role_customer = cls.Role.create(
            {
                "name": "Test customer",
                "code": "t_customer",
                "sequence": 20,
                "is_external": True,
                "project_id": cls.project.id,
            }
        )
        cls.flow = cls.Task.create({"name": "S01 Test flow", "project_id": cls.project.id, "sequence": 1})
        cls.task_a = cls._make_task("Task A", cls.role_sales, cls.phase_a, rung="3")
        cls.task_b = cls._make_task("Task B", cls.role_customer, cls.phase_b, rung="1")

    @classmethod
    def _make_task(cls, name, role=None, phase=None, rung="0", parent=True, **extra):
        vals = {
            "name": name,
            "project_id": cls.project.id,
            "parent_id": cls.flow.id if parent else False,
            "pan_role_id": role.id if role else False,
            "pan_phase_id": phase.id if phase else False,
            "pan_rung": rung,
        }
        vals.update(extra)
        return cls.Task.create(vals)
