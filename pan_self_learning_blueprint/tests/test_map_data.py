"""The map contract of docs/data-model.md: ``project.get_blueprint_map_data()``,
the project list of the Map menu, progress as the stage and the training list."""

from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.tests import new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestMapData(BlueprintCase):
    def _data(self, project=None):
        return (project or self.project).get_blueprint_map_data()

    def _task(self, data, task):
        return next(row for row in data["tasks"] if row["id"] == task.id)

    def test_contract_keys(self):
        data = self._data()
        self.assertEqual(
            set(data),
            {"project", "milestones", "phases", "stages", "roles", "flows", "tasks", "progress_history", "ideal", "verdict", "weeks_behind"},
        )
        # No target date: no burn-up (tests/test_burnup.py).
        self.assertEqual((data["progress_history"], data["ideal"], data["verdict"], data["weeks_behind"]), ([], False, False, 0))
        self.assertEqual(data["milestones"], [])
        self.assertEqual(
            data["stages"],
            [{"id": stage.id, "name": stage.name, "rung": int(rung)} for rung, stage in sorted(self.stages.items())],
        )
        self.assertEqual(
            data["project"],
            {
                "id": self.project.id,
                "name": self.project.name,
                "brief": False,
                "keywords": [],
                "from_systems": False,
                "to_systems": False,
                "date_start": False,
                "date_end": False,
            },
        )
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
                    "summary": False,
                    "keywords": [],
                    "progress": 50,
                    "deadline": False,
                    "late": False,
                    "days_late": 0,
                    "open_count": 1,
                    "mean_rung": 2.0,
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
                "stage_id": self.stages["3"].id,
                "stage": "Test 3",
                "rung": 3,
                "user_names": [],
                "planned_hours": 0.0,
                "spent_hours": 0.0,
                "description": False,
                "summary": False,
                "keywords": [],
            },
        )

    def test_company_summary_and_keywords(self):
        """Round 5: the company page, systems and dates on the project; a summary
        (else the description's first line) and at most three keywords per flow and task."""
        self.project.write(
            {
                "pan_brief": "<p>We build machines.</p>",
                "pan_keywords": "a, b,, c , d",
                "pan_from_systems": "BEMET",
                "pan_to_systems": "Odoo",
                "date_start": "2026-09-01",
                "date": "2027-03-01",
            }
        )
        self.flow.description = "<p>Flow line one</p><p>two</p>"
        self.task_a.write({"pan_summary": "Task A in short", "pan_keywords": "x, y"})
        data = self._data()
        project = data["project"]
        self.assertEqual(project["keywords"], ["a", "b", "c"])
        self.assertIn("We build machines.", project["brief"])
        self.assertEqual(
            (project["from_systems"], project["to_systems"], project["date_start"], project["date_end"]),
            ("BEMET", "Odoo", "2026-09-01", "2027-03-01"),
        )
        self.assertEqual(data["flows"][0]["summary"], "Flow line one")
        self.flow.pan_summary = "S01 in one line"
        self.assertEqual(self._data()["flows"][0]["summary"], "S01 in one line")
        task = self._task(data, self.task_a)
        self.assertEqual((task["summary"], task["keywords"]), ("Task A in short", ["x", "y"]))

    def test_milestones_by_deadline(self):
        """2.3: the project's milestones for "On schedule?", by deadline, undated last."""
        Milestone = self.env["project.milestone"]
        later, undated, sooner = Milestone.create(
            [
                {"name": "Later", "project_id": self.project.id, "deadline": "2026-12-20"},
                {"name": "Undated", "project_id": self.project.id},
                {"name": "Sooner", "project_id": self.project.id, "deadline": "2026-11-20", "is_reached": True},
            ]
        )
        other = self.env["project.project"].create({"name": "Other milestones"})
        Milestone.create({"name": "Elsewhere", "project_id": other.id})
        self.assertEqual(
            self._data()["milestones"],
            [
                {"id": sooner.id, "name": "Sooner", "deadline": "2026-11-20", "reached": True},
                {"id": later.id, "name": "Later", "deadline": "2026-12-20", "reached": False},
                {"id": undated.id, "name": "Undated", "deadline": False, "reached": False},
            ],
        )

    def test_domain_restricts_tasks_not_flow_progress(self):
        """2.3: the Map view's search restricts the tasks; a flow keeps its
        progress and open count over all its tasks, lists only the matching
        ones, and drops out without any; training follows the matching tasks."""
        other_flow = self.Task.create({"name": "S02 Other flow", "project_id": self.project.id, "sequence": 2})
        task_c = self._make_task("Task C", self.role_sales, self.phase_b, parent_id=other_flow.id)
        data = self.project.get_blueprint_map_data(domain=[("name", "in", ["Task B", "Task C"])])
        self.assertEqual([row["id"] for row in data["tasks"]], [self.task_b.id, task_c.id])
        flows = {row["id"]: row for row in data["flows"]}
        self.assertEqual(set(flows), {self.flow.id, other_flow.id})
        self.assertEqual(flows[self.flow.id]["task_ids"], [self.task_b.id])
        self.assertEqual((flows[self.flow.id]["progress"], flows[self.flow.id]["open_count"]), (50, 1))
        self.assertEqual(data["roles"][0]["open_training_task_ids"], [task_c.id])

        data = self.project.get_blueprint_map_data(domain=[("id", "=", self.task_a.id)])
        self.assertEqual([row["id"] for row in data["flows"]], [self.flow.id])
        self.assertEqual(self.project.get_blueprint_map_data(domain=[("id", "=", 0)])["flows"], [])
        # A domain on the flow itself does not hide its tasks: flows are known from all tasks.
        data = self.project.get_blueprint_map_data(domain=[("parent_id", "=", self.flow.id)])
        self.assertEqual(data["flows"][0]["task_ids"], [self.task_a.id, self.task_b.id])

    def test_order_orders_tasks_not_flow_route(self):
        """2.3: chips follow the view's order; a flow's route keeps the task sequence."""
        data = self.project.get_blueprint_map_data(order="name desc")
        self.assertEqual([row["id"] for row in data["tasks"]], [self.task_b.id, self.task_a.id])
        self.assertEqual(data["flows"][0]["task_ids"], [self.task_a.id, self.task_b.id])

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
        # Lowest mean step first: S03 (1.5), S01 and S04 (2.0, by sequence), S05 (3), S02 (5).
        self.assertEqual(
            [flow["name"] for flow in flows], ["S03 Late", "S01 Test flow", "S04 On time", "S05 Finished", "S02 Done"]
        )
        self.assertEqual([flow["mean_rung"] for flow in flows], [1.5, 2.0, 2.0, 3.0, 5.0])
        by_name = {flow["name"]: flow for flow in flows}
        self.assertTrue(by_name["S03 Late"]["late"])
        self.assertEqual((by_name["S03 Late"]["days_late"], by_name["S03 Late"]["open_count"]), (2, 1))
        self.assertEqual((by_name["S04 On time"]["days_late"], by_name["S02 Done"]["open_count"]), (0, 0))
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

    def test_flow_ties_break_on_late_then_open_tasks(self):
        """Same mean step: late first, then more open tasks, then sequence."""
        now = fields.Datetime.now()
        self.task_a.stage_id = self.stages["0"]  # S01: 0 %, 2 open, not late
        flows = {}
        for sequence, (name, days, rungs) in enumerate(
            [("Late 1 day", 1, "0"), ("Late 5 days", 5, "0"), ("Three open", 0, "000"), ("One open", 0, "0")], start=2
        ):
            deadline = now - timedelta(days=days) if days else False
            flows[name] = self.Task.create(
                {"name": name, "project_id": self.project.id, "sequence": sequence, "date_deadline": deadline}
            )
            for index, rung in enumerate(rungs):
                self._make_task(f"{name} {index}", rung=rung, parent_id=flows[name].id)
        rows = self._data()["flows"]
        self.assertEqual(
            [row["name"] for row in rows], ["Late 1 day", "Late 5 days", "Three open", "One open", "S01 Test flow"]
        )
        self.assertEqual([row["days_late"] for row in rows], [1, 5, 0, 0, 0])
        self.assertEqual([row["open_count"] for row in rows], [1, 1, 3, 1, 2])

    def test_flow_stage_follows_its_subtasks(self):
        """Fix 1: the flow's stage is the project stage of its lowest subtask step."""
        self.assertEqual(self.flow.stage_id, self.stages["1"], "Task A Tested, Task B Decided: the flow is Decided.")
        self.task_b.stage_id = self.stages["4"]
        self.assertEqual(self.flow.stage_id, self.stages["3"])
        self.task_a.stage_id = self.stages["5"]
        self.assertEqual(self.flow.stage_id, self.stages["4"])
        new = self._make_task("New work", self.role_sales, self.phase_b, rung="0")
        self.assertEqual(self.flow.stage_id, self.stages["0"], "A new open subtask pulls the flow back.")
        new.state = "1_canceled"
        self.assertEqual(self.flow.stage_id, self.stages["4"], "A cancelled subtask does not count.")
        new.state = "01_in_progress"
        self.assertEqual(self.flow.stage_id, self.stages["0"])
        new.unlink()
        self.assertEqual(self.flow.stage_id, self.stages["4"])
        self.task_b.parent_id = False
        self.assertEqual(self.flow.stage_id, self.stages["5"], "A subtask moved out no longer counts.")
        self.assertEqual(self.flow.pan_rung, "5")

    def test_flow_stage_nested_and_unmapped(self):
        """A flow inside a flow moves both; a project without a map, or without
        a stage for the step, leaves the flow where it is."""
        inner = self._make_task("Inner flow", rung="3")
        sub = self.Task.create({"name": "Inner work", "project_id": self.project.id, "parent_id": inner.id, "stage_id": self.stages["0"].id})
        self.assertEqual(inner.stage_id, self.stages["0"])
        self.assertEqual(self.flow.stage_id, self.stages["0"])
        sub.stage_id = self.stages["5"]
        self.assertEqual(inner.stage_id, self.stages["5"])
        self.assertEqual(self.flow.stage_id, self.stages["1"], "Task B (Decided) is now the lowest.")

        plain = self.env["project.project"].create({"name": "No map"})
        stage_open, stage_done = self.env["project.task.type"].create(
            [{"name": "Plain open", "pan_rung": "0", "project_ids": [(4, plain.id)]},
             {"name": "Plain done", "pan_rung": "5", "project_ids": [(4, plain.id)]}]
        )
        flow = self.Task.create({"name": "Plain flow", "project_id": plain.id, "stage_id": stage_done.id})
        self.Task.create({"name": "Plain work", "project_id": plain.id, "parent_id": flow.id, "stage_id": stage_open.id})
        self.assertEqual(flow.stage_id, stage_done, "No map, no roll-up.")
        self.assertFalse(flow.pan_is_map_flow)
        self.assertTrue(self.flow.pan_is_map_flow)
        self.assertFalse(self.task_a.pan_is_map_flow)

        self.stages["0"].project_ids = [(3, self.project.id)]  # the project has no Open stage any more
        self.task_b.stage_id = self.stages["0"]
        self.assertEqual(self.flow.stage_id, self.stages["1"], "No stage for the step: the flow stays.")

    def test_flow_stage_left_alone_in_a_shared_workflow(self):
        """Production bug 11-11: a project whose stages share a step (Icebox,
        Backlog and Estimated all Open) is no ladder; its flows never move."""
        self.task_b.stage_id = self.stages["3"]
        self.task_a.stage_id = self.stages["3"]
        self.assertEqual(self.flow.stage_id, self.stages["3"])
        icebox, backlog = self.env["project.task.type"].create(
            [{"name": "Icebox", "sequence": -2, "pan_rung": "0", "project_ids": [(4, self.project.id)]},
             {"name": "Backlog", "sequence": -1, "pan_rung": "0", "project_ids": [(4, self.project.id)]}]
        )
        self.flow.stage_id = backlog
        self.task_a.stage_id = self.stages["0"]
        self.assertEqual(self.flow.stage_id, backlog, "Shared workflow: the flow stays in Backlog, not Icebox.")
        self._make_task("More work", self.role_sales, self.phase_b, rung="0")
        self.assertEqual(self.flow.stage_id, backlog)

    def test_flow_rollup_needs_no_write_access_on_the_flow(self):
        user = new_test_user(self.env, login="pan_sl_rollup_user", groups="project.group_project_user")
        self.project.privacy_visibility = "followers"
        self.project.message_subscribe(partner_ids=user.partner_id.ids)
        self.task_b.with_user(user).stage_id = self.stages["5"]
        self.assertEqual(self.flow.stage_id, self.stages["3"])

    def test_kanban_shows_tested_on_flows(self):
        arch = self.env["project.task"].with_user(self.env.ref("base.user_admin")).get_views([(False, "kanban")])
        self.assertIn("o_pan_sl_kanban_tested", arch["views"]["kanban"]["arch"])

    def test_training_list(self):
        """Still to train: internal roles below Trained, as a visible default filter, grouped and expanded."""
        self.role_sales.partner_ids = self.env["res.partner"].create([{"name": "Anna"}, {"name": "Bram"}])
        self._make_task("Trained", self.role_sales, self.phase_b, rung="4")
        self._make_task("No role", phase=self.phase_a)
        self._make_task("Cancelled", self.role_sales, self.phase_a, state="1_canceled")
        action = self.project.action_blueprint_training()
        self.assertEqual((action["res_model"], action["name"]), ("project.task", "Still to train"))
        self.assertEqual(action["context"]["search_default_pan_still_to_train"], 1)
        self.assertEqual(action["context"]["search_default_pan_groupby_role"], 1)
        search = self.env["project.task"].get_views([(False, "search")])["views"]["search"]["arch"]
        node = etree.fromstring(search).xpath("//filter[@name='pan_still_to_train']")[0]
        self.assertEqual(node.get("string"), "Still to train")
        found = self.Task.search(action["domain"] + safe_eval(node.get("domain")))
        self.assertEqual(found, self.task_a, "Task B belongs to an external role; flows, cancelled and trained tasks are left out.")
        self.assertEqual(self.task_a.pan_role_people, "Anna, Bram")
        list_view = self.env["ir.ui.view"].browse(action["views"][0][0])
        self.assertEqual(list_view, self.env.ref("pan_self_learning_blueprint.view_task_list_training"))
        list_arch = etree.fromstring(list_view.arch)
        self.assertEqual(list_arch.get("expand"), "1", "Role groups open.")
        self.assertIn("o_pan_sl_wrap", list_arch.xpath("//field[@name='pan_role_people']")[0].get("class"))

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
