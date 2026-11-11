"""The map contract of docs/data-model.md: ``project.get_blueprint_map_data()``."""

from odoo.tests import tagged

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestMapData(BlueprintCase):
    def _data(self, project=None):
        return (project or self.project).get_blueprint_map_data()

    def test_contract_keys(self):
        data = self._data()
        self.assertEqual(set(data), {"project", "phases", "roles", "flows", "tasks", "unplaced_count"})
        self.assertEqual(data["project"], {"id": self.project.id, "name": self.project.name})
        phase = next(phase for phase in data["phases"] if phase["id"] == self.phase_a.id)
        self.assertEqual(set(phase), {"id", "code", "name", "apps"})
        self.assertEqual(
            data["roles"][0],
            {"id": self.role_sales.id, "code": "t_sales", "name": "Test sales", "is_external": False, "users": [], "adkar": False},
        )
        self.assertEqual(
            data["flows"], [{"id": self.flow.id, "name": "S01 Test flow", "progress": 50, "task_ids": [self.task_a.id, self.task_b.id]}]
        )
        task = data["tasks"][0]
        self.assertEqual(
            set(task),
            {"id", "name", "role_id", "phase_id", "flow_id", "rung", "user_names", "planned_hours", "spent_hours", "description"},
        )
        self.assertEqual(
            (task["id"], task["role_id"], task["phase_id"], task["flow_id"], task["rung"]),
            (self.task_a.id, self.role_sales.id, self.phase_a.id, self.flow.id, 3),
        )
        self.assertEqual(data["unplaced_count"], 0)

    def test_only_this_projects_roles_and_tasks(self):
        other = self.env["project.project"].create({"name": "Other map"})
        self.Role.create({"name": "Other role", "code": "t_sales", "project_id": other.id})
        self.Task.create({"name": "Other task", "project_id": other.id, "pan_phase_id": self.phase_a.id})
        data = self._data()
        self.assertEqual([role["id"] for role in data["roles"]], [self.role_sales.id, self.role_customer.id])
        self.assertEqual(self._data(other)["unplaced_count"], 1)
        self.assertEqual(len(self._data(other)["phases"]), len(data["phases"]), "Phases are shared.")

    def test_unplaced_and_cancelled_tasks(self):
        """Tasks without role or phase are counted, not drawn; cancelled tasks are left out of both."""
        no_role = self._make_task("No role", phase=self.phase_a, parent=False)
        self._make_task("No phase", role=self.role_sales)
        self._make_task("Cancelled", self.role_sales, self.phase_a, state="1_canceled")
        self._make_task("Cancelled unplaced", parent=False, state="1_canceled")
        data = self._data()
        self.assertEqual({task["id"] for task in data["tasks"]}, {self.task_a.id, self.task_b.id})
        self.assertEqual(data["unplaced_count"], 2)
        action = self.project.action_blueprint_unplaced_tasks()
        found = self.Task.search(action["domain"])
        self.assertEqual(len(found), 2)
        self.assertIn(no_role, found)
        self.assertNotIn(self.flow, found, "A flow is never 'not on the map'.")

    def test_flow_progress_counts_archived_not_cancelled(self):
        """Tested % = subtasks at Tested or further, archived included, cancelled left out."""
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self._make_task("Cancelled", self.role_sales, self.phase_a, rung="0", state="1_canceled")
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self.task_b.pan_rung = "5"
        self.assertEqual(self.flow.pan_flow_progress, 100)
        self._make_task("Open one", self.role_sales, self.phase_b, rung="0").active = False
        self.assertEqual(self.flow.pan_flow_progress, 67, "An archived subtask still counts.")
        self.task_a.parent_id = False
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self.assertEqual(self.task_a.pan_flow_progress, 0, "A task without subtasks has no progress.")

    def test_subtask_of_a_flow_with_its_own_subtasks_is_a_flow(self):
        sub = self.Task.create({"name": "Sub of A", "project_id": self.project.id, "parent_id": self.task_a.id})
        data = self._data()
        self.assertIn(self.task_a.id, [flow["id"] for flow in data["flows"]])
        self.assertNotIn(self.task_a.id, [task["id"] for task in data["tasks"]])
        self.assertEqual(data["unplaced_count"], 1, "The new subtask has no role or phase yet.")
        self.assertIn(sub, self.Task.search(self.project.action_blueprint_unplaced_tasks()["domain"]))

    def test_task_values(self):
        self.task_a.write(
            {
                "allocated_hours": 4.0,
                "user_ids": [(6, 0, self.env.user.ids)],
                "description": "<div><ol><li>Sales, New</li><li>Save</li></ol></div>",
            }
        )
        task = next(task for task in self._data()["tasks"] if task["id"] == self.task_a.id)
        self.assertEqual(task["planned_hours"], 4.0)
        self.assertEqual(task["spent_hours"], 0.0)
        self.assertEqual(task["user_names"], [self.env.user.name])
        self.assertEqual(task["description"], "Sales, New")
        self.task_a.description = False
        task = next(task for task in self._data()["tasks"] if task["id"] == self.task_a.id)
        self.assertIs(task["description"], False)

    def test_phase_apps(self):
        self.phase_a.app_labels = "project, no_such_module"
        phase = next(phase for phase in self._data()["phases"] if phase["id"] == self.phase_a.id)
        self.assertEqual(phase["apps"][0], {"name": "Project", "module": "project", "installed": True})
        self.assertEqual(phase["apps"][1], {"name": "no_such_module", "module": False, "installed": False})

    def test_role_people_and_band(self):
        people = self.env["res.partner"].create([{"name": f"Person {index}"} for index in range(3)])
        self.role_sales.partner_ids = people
        for person in people:
            self.env["pan.sl.adkar.score"].create(
                dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 2) | {"partner_id": person.id}
            )
        role = self._data()["roles"][0]
        self.assertEqual(sorted(role["users"]), ["Person 0", "Person 1", "Person 2"])
        self.assertEqual(role["adkar"], "low")

    def _count_queries(self):
        self.env.invalidate_all()
        before = self.env.cr.sql_log_count
        self._data()
        return self.env.cr.sql_log_count - before

    def test_query_count_does_not_grow_with_tasks(self):
        self._data()
        few = self._count_queries()
        for index in range(20):
            self._make_task(f"Extra {index}", self.role_sales, self.phase_b, description="<p>Step</p>")
        self._data()
        self.assertLessEqual(self._count_queries(), few)
