"""The map contract of docs/data-model.md: ``project.get_blueprint_map_data()``,
the project list of the Map menu, progress as the stage and the training list."""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestMapData(BlueprintCase):
    def _data(self, project=None):
        return (project or self.project).get_blueprint_map_data()

    def _task(self, data, task):
        return next(row for row in data["tasks"] if row["id"] == task.id)

    def test_contract_keys(self):
        data = self._data()
        self.assertEqual(set(data), {"project", "phases", "roles", "flows", "tasks"})
        self.assertEqual(data["project"], {"id": self.project.id, "name": self.project.name})
        phase = next(phase for phase in data["phases"] if phase["id"] == self.phase_a.id)
        self.assertEqual(phase, {"id": self.phase_a.id, "code": "t_phase_a", "name": "Test phase A"})
        self.assertEqual(
            data["roles"][0],
            {
                "id": self.role_sales.id,
                "code": "t_sales",
                "name": "Test sales",
                "is_external": False,
                "people": [],
                "adkar": False,
                "open_training_task_ids": [self.task_a.id],
            },
        )
        self.assertEqual(
            data["flows"],
            [
                {
                    "id": self.flow.id,
                    "name": "S01 Test flow",
                    "progress": 50,
                    "deadline": False,
                    "late": False,
                    "task_ids": [self.task_a.id, self.task_b.id],
                }
            ],
        )
        self.assertEqual(
            self._task(data, self.task_a),
            {
                "id": self.task_a.id,
                "name": "Task A",
                "role_id": self.role_sales.id,
                "phase_id": self.phase_a.id,
                "flow_id": self.flow.id,
                "stage": "Test 3",
                "rung": 3,
                "user_names": [],
                "planned_hours": 0.0,
                "spent_hours": 0.0,
                "description": False,
            },
        )

    def test_every_task_without_flows_or_cancelled(self):
        """All work of the project, placed or not; a flow lists all its subtasks."""
        no_role = self._make_task("No role", phase=self.phase_a, parent=False)
        no_phase = self._make_task("No phase", role=self.role_sales)
        self._make_task("Cancelled", self.role_sales, self.phase_a, state="1_canceled")
        data = self._data()
        self.assertEqual(
            [row["id"] for row in data["tasks"]], [self.task_a.id, self.task_b.id, no_role.id, no_phase.id]
        )
        self.assertNotIn(self.flow.id, [row["id"] for row in data["tasks"]])
        self.assertEqual(self._task(data, no_role)["role_id"], False)
        self.assertEqual(self._task(data, no_role)["flow_id"], False)
        self.assertEqual(data["flows"][0]["task_ids"], [self.task_a.id, self.task_b.id, no_phase.id])

    def test_only_this_projects_roles_and_tasks(self):
        other = self.env["project.project"].create({"name": "Other map"})
        self.Role.create({"name": "Other role", "code": "t_sales", "project_id": other.id})
        self.Task.create({"name": "Other task", "project_id": other.id, "pan_phase_id": self.phase_a.id})
        data = self._data()
        self.assertEqual([role["id"] for role in data["roles"]], [self.role_sales.id, self.role_customer.id])
        self.assertEqual(len(self._data(other)["tasks"]), 1)
        self.assertEqual(len(self._data(other)["phases"]), len(data["phases"]), "Phases are shared.")

    def test_flows_worst_first_with_deadline_and_late(self):
        now = fields.Datetime.now()
        done = self.Task.create({"name": "S02 Done", "project_id": self.project.id, "sequence": 2})
        late = self.Task.create(
            {"name": "S03 Late", "project_id": self.project.id, "sequence": 3, "date_deadline": now - timedelta(days=2)}
        )
        on_time = self.Task.create(
            {"name": "S04 On time", "project_id": self.project.id, "sequence": 4, "date_deadline": now + timedelta(days=2)}
        )
        finished_late = self.Task.create(
            {"name": "S05 Finished", "project_id": self.project.id, "sequence": 5, "date_deadline": now - timedelta(days=2)}
        )
        self._make_task("Done 1", rung="5", parent_id=done.id)
        self._make_task("Late 1", rung="3", parent_id=late.id)
        self._make_task("Late 2", rung="0", parent_id=late.id)
        self._make_task("On time 1", rung="0", parent_id=on_time.id)
        self._make_task("On time 2", rung="4", parent_id=on_time.id)
        self._make_task("Finished 1", rung="3", parent_id=finished_late.id)
        flows = self._data()["flows"]
        # S01, S03 and S04 are at 50 %: the late one first, then by sequence.
        self.assertEqual(
            [flow["name"] for flow in flows], ["S03 Late", "S01 Test flow", "S04 On time", "S02 Done", "S05 Finished"]
        )
        by_name = {flow["name"]: flow for flow in flows}
        self.assertTrue(by_name["S03 Late"]["late"])
        self.assertFalse(by_name["S04 On time"]["late"])
        self.assertFalse(by_name["S05 Finished"]["late"], "A flow at 100 % is never late.")
        deadline = fields.Datetime.context_timestamp(on_time, on_time.date_deadline).date()
        self.assertEqual(by_name["S04 On time"]["deadline"], deadline.isoformat())
        self.assertEqual(by_name["S01 Test flow"]["deadline"], False)

    def test_progress_is_the_stage(self):
        """A task's progress follows its stage; changing a stage's progress moves its tasks."""
        self.assertEqual(self.task_a.pan_rung, "3")
        self.task_b.stage_id = self.stages["4"]
        self.assertEqual(self.task_b.pan_rung, "4")
        self.assertEqual(self.flow.pan_flow_progress, 100)
        self.stages["4"].pan_rung = "2"
        self.assertEqual(self.task_b.pan_rung, "2")
        self.assertEqual(self.flow.pan_flow_progress, 50)
        no_stage = self._make_task("No stage", stage_id=False)
        self.assertFalse(no_stage.pan_rung)
        self.assertEqual(self._task(self._data(), no_stage)["rung"], 0, "No stage counts as Open.")

    def test_flow_progress_counts_archived_not_cancelled(self):
        """Tested % = subtasks at Tested or further, archived included, cancelled left out."""
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self._make_task("Cancelled", self.role_sales, self.phase_a, rung="0", state="1_canceled")
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self.task_b.stage_id = self.stages["5"]
        self.assertEqual(self.flow.pan_flow_progress, 100)
        self._make_task("Open one", self.role_sales, self.phase_b, rung="0").active = False
        self.assertEqual(self.flow.pan_flow_progress, 67, "An archived subtask still counts.")
        self.task_a.parent_id = False
        self.assertEqual(self.flow.pan_flow_progress, 50)
        self.assertEqual(self.task_a.pan_flow_progress, 0, "A task without subtasks has no progress.")

    def test_subtask_with_its_own_subtasks_is_a_flow(self):
        self.Task.create({"name": "Sub of A", "project_id": self.project.id, "parent_id": self.task_a.id})
        data = self._data()
        self.assertIn(self.task_a.id, [flow["id"] for flow in data["flows"]])
        self.assertNotIn(self.task_a.id, [task["id"] for task in data["tasks"]])

    def test_task_values(self):
        self.task_a.write(
            {
                "allocated_hours": 4.0,
                "user_ids": [(6, 0, self.env.user.ids)],
                "description": "<div><ol><li>Sales, New</li><li>Save</li></ol></div>",
            }
        )
        task = self._task(self._data(), self.task_a)
        self.assertEqual(task["planned_hours"], 4.0)
        self.assertEqual(task["user_names"], [self.env.user.name])
        self.assertEqual(task["description"], "Sales, New")
        self.task_a.description = False
        self.assertIs(self._task(self._data(), self.task_a)["description"], False)

    def test_role_people_band_and_training(self):
        people = self.env["res.partner"].create([{"name": f"Person {index}"} for index in range(3)])
        self.role_sales.partner_ids = people
        for person in people:
            self.env["pan.sl.adkar.score"].create(
                dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 2) | {"partner_id": person.id}
            )
        trained = self._make_task("Trained", self.role_sales, self.phase_b, rung="4")
        no_phase = self._make_task("No phase", self.role_sales, rung="0")
        role = self._data()["roles"][0]
        self.assertEqual(sorted(role["people"]), ["Person 0", "Person 1", "Person 2"])
        self.assertEqual(role["adkar"], "low")
        self.assertEqual(role["open_training_task_ids"], [self.task_a.id, no_phase.id])
        self.assertNotIn(trained.id, role["open_training_task_ids"])

    def test_training_list(self):
        self.role_sales.partner_ids = self.env["res.partner"].create([{"name": "Anna"}, {"name": "Bram"}])
        self._make_task("Trained", self.role_sales, self.phase_b, rung="4")
        self._make_task("No role", phase=self.phase_a)
        action = self.project.action_blueprint_training()
        self.assertEqual((action["res_model"], action["context"]["group_by"]), ("project.task", ["pan_role_id"]))
        found = self.Task.search(action["domain"])
        self.assertEqual(found, self.task_a | self.task_b)
        self.assertEqual(self.task_a.pan_role_people, "Anna, Bram")
        list_view = self.env["ir.ui.view"].browse(action["views"][0][0])
        self.assertEqual(list_view, self.env.ref("pan_self_learning_blueprint.view_task_list_training"))

    def test_map_projects(self):
        """Projects > Map: the projects with at least one role, by name."""
        self.env["project.project"].create({"name": "No map here"})
        other = self.env["project.project"].create({"name": "A first map"})
        self.Role.create({"name": "R", "code": "t_r", "project_id": other.id})
        found = self.env["project.project"].get_blueprint_map_projects()
        names = [row["name"] for row in found]
        self.assertIn({"id": self.project.id, "name": self.project.name}, found)
        self.assertNotIn("No map here", names)
        self.assertLess(names.index("A first map"), names.index(self.project.name))

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
