"""Blueprint file version 2: export, import into one project, the template."""

import base64
import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.blueprint import MAX_RECORDS
from .common import BlueprintCase


def _blueprint(**sections):
    return {"format": "pantalytics-blueprint", "version": 2, "name": "Test", **sections}


FLOW = {
    "name": "S90 Test route",
    "sequence": 90,
    "description": "<p>Route</p>",
    "tasks": [
        {"name": "Draft", "role": "t_sales", "phase": "t_phase_a", "description": "<ol><li>Sales, New</li></ol>"},
        {"name": "Accept", "role": "t_customer", "phase": "t_phase_b"},
    ],
}
ROLES = [{"code": "t_sales", "name": "Sales"}, {"code": "t_customer", "name": "Customer", "external": True}]


@tagged("post_install", "-at_install")
class TestBlueprint(BlueprintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Blueprint = cls.env["pan.sl.blueprint"]
        cls.target = cls.env["project.project"].create({"name": "Target project"})

    def _import(self, data, project=None, **kwargs):
        return self.Blueprint.import_blueprint(project or self.target, data, **kwargs)

    def _flow(self, project, name):
        return self.Task.search([("project_id", "=", project.id), ("name", "=", name), ("parent_id", "=", False)])

    def test_export(self):
        data = self.Blueprint.export_blueprint(self.project)
        self.assertEqual((data["format"], data["version"], data["lang"]), ("pantalytics-blueprint", 2, "en_US"))
        self.assertEqual([role["code"] for role in data["roles"]], ["t_sales", "t_customer"])
        self.assertIn({"code": "t_phase_a", "name": "Test phase A", "sequence": 10}, data["phases"])
        self.assertEqual(
            data["flows"],
            [
                {
                    "name": "S01 Test flow",
                    "sequence": 1,
                    "description": "",
                    "tasks": [
                        {"name": "Task A", "role": "t_sales", "phase": "t_phase_a", "description": ""},
                        {"name": "Task B", "role": "t_customer", "phase": "t_phase_b", "description": ""},
                    ],
                }
            ],
        )
        self.assertNotIn("users", json.dumps(data), "A blueprint holds no people.")

    def test_round_trip_into_another_project_is_idempotent(self):
        data = self.Blueprint.export_blueprint(self.project)
        summary = self._import(data)
        self.assertEqual(
            {key: summary[key] for key in ("roles", "flows", "tasks")},
            {"roles": {"created": 2, "updated": 0}, "flows": {"created": 1, "updated": 0}, "tasks": {"created": 2, "updated": 0}},
        )
        self.assertEqual(summary["phases"]["created"], 0, "Phases are shared and matched on code.")
        self.assertEqual(sum(summary["stages"].values()), 6, "The project gets the six progress stages.")
        exported = self.Blueprint.export_blueprint(self.target)
        self.assertEqual(exported["flows"], data["flows"])
        self.assertEqual(exported["roles"], data["roles"])
        again = self._import(exported)
        for section in ("stages", "phases", "roles", "flows", "tasks"):
            self.assertEqual(again[section], {"created": 0, "updated": 0}, section)
        self.assertEqual(self.Role.search_count([("code", "=", "t_sales")]), 2, "Roles are per project.")

    def test_import_creates_updates_and_never_deletes(self):
        self._import(_blueprint(roles=ROLES, flows=[FLOW]))
        flow = self._flow(self.target, "S90 Test route")
        draft = flow.child_ids.filtered(lambda task: task.name == "Draft")
        self.assertEqual(draft.pan_role_id, self.Role.search([("project_id", "=", self.target.id), ("code", "=", "t_sales")]))
        self.assertEqual(draft.pan_phase_id, self.phase_a)
        self.assertIn("Sales, New", draft.description)
        extra = self.Task.create({"name": "Own task", "project_id": self.target.id, "parent_id": flow.id})
        changed = dict(FLOW, tasks=[dict(FLOW["tasks"][0], phase="t_phase_b")])
        summary = self._import(_blueprint(flows=[changed]))
        self.assertEqual(summary["tasks"], {"created": 0, "updated": 1})
        self.assertEqual(draft.pan_phase_id, self.phase_b)
        self.assertTrue(extra.exists() and (flow.child_ids - extra).filtered(lambda task: task.name == "Accept"))

    def test_roles_must_exist_in_file_or_project(self):
        """Roles are per project: a role code of another project is unknown here."""
        with self.assertRaisesRegex(UserError, "t_sales"):
            self._import(_blueprint(flows=[FLOW]))
        self._import(_blueprint(roles=ROLES))
        self._import(_blueprint(flows=[FLOW]))
        self.assertEqual(len(self._flow(self.target, "S90 Test route").child_ids), 2)

    def test_refusals_in_plain_language(self):
        cases = [
            ({"format": "other"}, "not a blueprint file"),
            ({"format": "pantalytics-blueprint", "version": 1, "chains": []}, "version 1"),
            ({"format": "pantalytics-blueprint", "version": 3}, "version 3"),
            (_blueprint(roles=[{"code": "a b", "name": "X"}]), "space"),
            (_blueprint(roles=[{"code": "x", "name": "X"}, {"code": "x", "name": "Y"}]), "twice"),
            (_blueprint(flows=[{"name": "F", "tasks": [{"description": "no name"}]}]), "no name"),
            (_blueprint(roles=[{"code": "x", "name": "X", "external": "yes"}]), "wrong value"),
            (_blueprint(phases=[{"code": "x", "name": "X", "sequence": True}]), "wrong value"),
            (_blueprint(flows="not a list"), "must be a list"),
            (_blueprint(lang="xx_XX"), "not active"),
            (_blueprint(flows=[{"name": f"F{index}"} for index in range(MAX_RECORDS + 1)]), "at most"),
        ]
        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(UserError, message):
                self._import(data)
        self.assertFalse(self.Role.search([("project_id", "=", self.target.id)]), "A refusal imports nothing.")

    def test_template_loads_and_reload_only_fills(self):
        action = self.target.action_blueprint_load_template()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["next"]["params"], {"project_id": self.target.id})
        self.assertIn("10 flows, 35 tasks", action["params"]["message"])
        data = self.target.get_blueprint_map_data()
        self.assertEqual((len(data["roles"]), len(data["flows"]), len(data["tasks"])), (8, 10, 35))

        # The company's own work survives a reload; only what is empty is filled again.
        task = self.Task.search([("project_id", "=", self.target.id), ("name", "=", "Draft the quotation")])
        sales = task.pan_role_id
        sales.write({"name": "Inside sales", "is_external": True})
        trained = self.target.type_ids.filtered(lambda stage: stage.pan_rung == "4")
        task.write({"description": "<p>Our own way</p>", "pan_phase_id": False, "stage_id": trained.id})
        action = self.target.action_blueprint_load_template()
        self.assertEqual(sales.name, "Inside sales")
        self.assertTrue(sales.is_external)
        self.assertIn("Our own way", task.description)
        self.assertTrue(task.pan_phase_id, "An emptied phase is filled again.")
        self.assertEqual(task.pan_rung, "4")
        self.assertEqual(action["params"]["message"], "Updated 1 tasks.")
        self.assertEqual(self.target.action_blueprint_load_template()["params"]["message"], "Nothing to change.")

    def test_template_gives_the_progress_stages(self):
        """Six stages Open ... Live, shared with other mapped projects; tasks start Open."""
        self.target.action_blueprint_load_template()
        stages = self.target.type_ids.sorted()
        self.assertEqual(stages.mapped("name"), ["Open", "Decided", "Built", "Tested", "Trained", "Live"])
        self.assertEqual(stages.mapped("pan_rung"), ["0", "1", "2", "3", "4", "5"])
        tasks = self.Task.search([("project_id", "=", self.target.id), ("child_ids", "=", False)])
        self.assertEqual(set(tasks.mapped("stage_id.name")), {"Open"})
        other = self.env["project.project"].create({"name": "Second map"})
        summary = self.Blueprint.import_blueprint(other, _blueprint())
        self.assertEqual(summary["stages"], {"created": 0, "updated": 6}, "Existing stages are linked, not copied.")
        self.assertEqual(other.type_ids.sorted(), stages)

    def test_stages_fill_only(self):
        """A project whose stages already carry progress gets none; plain stages stay."""
        self.assertEqual(self._import(_blueprint(), project=self.project)["stages"], {"created": 0, "updated": 0})
        plain = self.env["project.task.type"].create({"name": "New", "project_ids": [(4, self.target.id)]})
        self._import(_blueprint())
        self.assertIn(plain, self.target.type_ids)
        self.assertEqual(len(self.target.type_ids), 7)

    def test_phase_apps_of_2_0_files_are_ignored(self):
        summary = self._import(_blueprint(phases=[{"code": "t_phase_a", "name": "Test phase A", "apps": ["sale"]}]))
        self.assertEqual(summary["phases"], {"created": 0, "updated": 0})

    def test_template_has_no_version_1_keys(self):
        data = self.Blueprint._read_template()
        self.assertEqual(data["version"], 2)
        self.assertFalse({"chains", "processes", "activities", "scenarios"} & set(data))
        names = [task["name"] for flow in data["flows"] for task in flow["tasks"]]
        self.assertEqual(len(names), len(set(names)), "An activity sits in one flow only.")

    def test_import_dialog(self):
        content = json.dumps(_blueprint(roles=[{"code": "t_new", "name": "New role"}])).encode()
        action = self.target.action_blueprint_import()
        self.assertEqual((action["res_model"], action["target"]), ("pan.sl.blueprint.wizard", "new"))
        wizard = self.env["pan.sl.blueprint.wizard"].with_context(action["context"]).create(
            {"file": base64.b64encode(content), "filename": "mine.json"}
        )
        result = wizard.action_import()
        self.assertIn("1 roles.", result["params"]["message"])
        self.assertTrue(self.Role.search([("project_id", "=", self.target.id), ("code", "=", "t_new")]))
        wizard.file = base64.b64encode(b"{broken")
        with self.assertRaisesRegex(UserError, "line 1"):
            wizard.action_import()
