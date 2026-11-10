"""Access per group, checked as real (non-super) users with ``with_user()``.

Contract: users see the map and read the model; managers edit the model,
pick Odoo models (ir.model) and import. ADKAR scores are personal: a user
reads only the scores on their own contact, a manager reads all, the note is
manager-only, and the map shows a role band only over at least three people.
Progress (rung, hours) is the same for every viewer, whatever tasks they may
open. Project users without Blueprint access see no Blueprint fields on tasks.
"""

import base64
import json

from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import BlueprintCase

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"
MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager"
MODEL_SECTIONS = (
    "pan.sl.chain",
    "pan.sl.phase",
    "pan.sl.role",
    "pan.sl.process",
    "pan.sl.activity",
    "pan.sl.scenario",
    "pan.sl.scenario.step",
)


@tagged("post_install", "-at_install")
class TestSecurity(BlueprintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bp_user = new_test_user(cls.env, login="pan_sl_sec_user", name="Blueprint user", groups=USER_GROUP)
        cls.bp_manager = new_test_user(
            cls.env, login="pan_sl_sec_manager", name="Blueprint manager", groups=MANAGER_GROUP
        )
        cls.bp_colleague = new_test_user(
            cls.env, login="pan_sl_sec_colleague", name="Blueprint colleague", groups=USER_GROUP
        )
        cls.bp_third = new_test_user(cls.env, login="pan_sl_sec_third", name="Blueprint third", groups=USER_GROUP)
        cls.project_user = new_test_user(
            cls.env,
            login="pan_sl_sec_project",
            name="Blueprint project user",
            groups=f"{USER_GROUP},project.group_project_user",
        )
        cls.outsider = new_test_user(cls.env, login="pan_sl_sec_outsider", name="No blueprint access")
        cls.scenario = cls.Scenario.create(
            {
                "name": "Security route",
                "code": "t_sec_route",
                "step_ids": [Command.create({"sequence": 10, "activity_id": cls.act_a.id})],
            }
        )
        cls.Score = cls.env["pan.sl.adkar.score"]

    def _score(self, user, value=3, note=False):
        vals = dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), value)
        return self.Score.create(dict(vals, partner_id=user.partner_id.id, note=note))

    # ------------------------------------------------------------------
    # Blueprint user: read the model, open the map, change nothing
    # ------------------------------------------------------------------

    def test_user_reads_the_model(self):
        for model in MODEL_SECTIONS:
            with self.subTest(model=model):
                records = self.env[model].with_user(self.bp_user).search([])
                self.assertTrue(records, f"A Blueprint user must see {model} records.")
                records.read(["display_name"])
        activity = self.act_a.with_user(self.bp_user)
        self.assertEqual(activity.rung, 0)
        self.assertEqual(activity.rung_state, "0")
        self.assertEqual(activity.scenario_ids, self.scenario)

    def test_user_opens_the_map(self):
        Activity = self.Activity.with_user(self.bp_user)
        data = Activity.get_map_data()
        self.assertIn(self.act_a.id, [item["id"] for item in data["activities"]])
        details = Activity.get_map_details()
        self.assertIn(self.act_a.id, [item["id"] for item in details])

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_sees_model_name_without_ir_model_access(self):
        """D6: the map and the activity show ``model_name``; only managers read ir.model."""
        self.act_a.model_id = self.env["ir.model"]._get("res.partner")
        activity = self.act_a.with_user(self.bp_user)
        activity.invalidate_recordset()
        self.assertEqual(activity.model_name, "res.partner")
        data = self.Activity.with_user(self.bp_user).get_map_data()
        item = next(item for item in data["activities"] if item["id"] == self.act_a.id)
        self.assertEqual(item["model"], "res.partner")
        found = self.Activity.with_user(self.bp_user).search([("model_name", "=", "res.partner")])
        self.assertIn(self.act_a, found)

        with self.assertRaises(AccessError):
            self.env["ir.model"].with_user(self.bp_user).search([("model", "=", "res.partner")])
        self.assertTrue(self.env["ir.model"].with_user(self.bp_manager).search([("model", "=", "res.partner")]))

    def test_activity_form_hides_model_picker_from_users(self):
        """D6: a plain user's activity form has no ``model_id`` (it would read ir.model)."""
        for user, has_picker in ((self.bp_user, False), (self.bp_manager, True)):
            with self.subTest(user=user.login):
                views = self.Activity.with_user(user).get_views([(False, "form")])
                arch = etree.fromstring(views["views"]["form"]["arch"])
                self.assertEqual(bool(arch.xpath("//field[@name='model_id']")), has_picker)
                self.assertNotEqual(bool(arch.xpath("//field[@name='model_name']")), has_picker)
        self.act_a.model_id = self.env["ir.model"]._get("res.partner")
        views = self.Activity.with_user(self.bp_user).get_views([(False, "form")])
        arch = etree.fromstring(views["views"]["form"]["arch"])
        fields = {node.get("name") for node in arch.iter("field")} & set(self.Activity._fields)
        record = self.act_a.with_user(self.bp_user).web_read({name: {} for name in fields})
        self.assertEqual(record[0]["model_name"], "res.partner")

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_cannot_change_the_model(self):
        for record in (self.chain, self.phase_a, self.role_sales, self.process, self.act_a, self.scenario):
            with self.subTest(model=record._name):
                with self.assertRaises(AccessError):
                    record.with_user(self.bp_user).write({"name": "Changed by a user"})
                with self.assertRaises(AccessError):
                    record.with_user(self.bp_user).unlink()
        with self.assertRaises(AccessError):
            self.Chain.with_user(self.bp_user).create({"name": "User chain", "code": "t_sec_chain"})
        with self.assertRaises(AccessError):
            self.Activity.with_user(self.bp_user).create(
                {
                    "name": "User activity",
                    "code": "t_sec_act",
                    "process_id": self.process.id,
                    "role_id": self.role_sales.id,
                    "phase_id": self.phase_a.id,
                }
            )
        with self.assertRaises(AccessError):
            self.scenario.step_ids.with_user(self.bp_user).write({"sequence": 99})

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_cannot_import(self):
        with self.assertRaises(AccessError):
            self.env["pan.sl.blueprint.wizard"].with_user(self.bp_user).create({})
        for xmlid in ("action_blueprint_load_template", "action_blueprint_export"):
            with self.subTest(action=xmlid), self.assertRaises(AccessError):
                self.env.ref(f"pan_self_learning_blueprint.{xmlid}").with_user(self.bp_user).run()
        data = {
            "format": "pantalytics-blueprint",
            "version": 1,
            "chains": [{"code": "t_sec_bp_chain", "name": "Chain"}],
        }
        with self.assertRaises(AccessError):
            self.env["pan.sl.blueprint"].with_user(self.bp_user).import_blueprint(data)
        self.assertFalse(self.Chain.search_count([("code", "=", "t_sec_bp_chain")]))

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_internal_user_without_group_sees_nothing(self):
        with self.assertRaises(AccessError):
            self.Activity.with_user(self.outsider).search([])
        with self.assertRaises(AccessError):
            self.Activity.with_user(self.outsider).get_map_data()
        with self.assertRaises(AccessError):
            self.Score.with_user(self.outsider).search([])

    # ------------------------------------------------------------------
    # Blueprint manager: edit the model and import
    # ------------------------------------------------------------------

    def test_manager_edits_the_model(self):
        activity = self.act_a.with_user(self.bp_manager)
        activity.write({"choice_state": "fixed", "open_point": "Set by the manager"})
        self.assertEqual(self.act_a.choice_state, "fixed")
        chain = self.Chain.with_user(self.bp_manager).create({"name": "Manager chain", "code": "t_sec_mchain"})
        self.Scenario.with_user(self.bp_manager).create(
            {
                "name": "Manager route",
                "code": "t_sec_mroute",
                "step_ids": [Command.create({"sequence": 10, "activity_id": self.act_b.id})],
            }
        )
        chain.unlink()
        self.assertFalse(chain.exists())

    def test_manager_imports_and_exports(self):
        data = {
            "format": "pantalytics-blueprint",
            "version": 1,
            "chains": [{"code": "t_sec_bp_chain", "name": "Chain"}],
        }
        wizard = self.env["pan.sl.blueprint.wizard"].with_user(self.bp_manager).create(
            {"file": base64.b64encode(json.dumps(data).encode()), "filename": "manager.json"}
        )
        action = wizard.action_import()
        self.assertIn("Created", action["params"]["message"])
        self.assertEqual(self.Chain.search_count([("code", "=", "t_sec_bp_chain")]), 1)
        action = self.env.ref("pan_self_learning_blueprint.action_blueprint_export").with_user(self.bp_manager).run()
        self.assertEqual(action["type"], "ir.actions.act_url")

    def test_manager_loads_template(self):
        action = self.env.ref("pan_self_learning_blueprint.action_blueprint_load_template")
        result = action.with_user(self.bp_manager).run()
        self.assertEqual(result["tag"], "display_notification")
        self.assertTrue(result["params"]["message"])

    # ------------------------------------------------------------------
    # ADKAR: own scores only, notes for managers, profile as aggregate
    # ------------------------------------------------------------------

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.models")
    def test_user_reads_only_own_scores(self):
        own = self._score(self.bp_user, note="Own note")
        other = self._score(self.bp_colleague, note="Colleague's blocker")
        Score = self.Score.with_user(self.bp_user)
        partners = (self.bp_user | self.bp_colleague).partner_id
        self.assertEqual(Score.search([("partner_id", "in", partners.ids)]), own)
        own.with_user(self.bp_user).read(["awareness", "average"])
        with self.assertRaises(AccessError):
            other.with_user(self.bp_user).read(["awareness"])

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_note_is_manager_only(self):
        own = self._score(self.bp_user, note="Own note")
        with self.assertRaises(AccessError):
            own.with_user(self.bp_user).read(["note"])
        self.assertNotIn("note", self.Score.with_user(self.bp_user).fields_get())
        self.assertEqual(own.with_user(self.bp_manager).read(["note"])[0]["note"], "Own note")

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_cannot_write_scores(self):
        own = self._score(self.bp_user)
        with self.assertRaises(AccessError):
            own.with_user(self.bp_user).write({"awareness": 5})
        with self.assertRaises(AccessError):
            self._score_as(self.bp_user, self.bp_user)

    def _score_as(self, author, user):
        return self._score_partner_as(author, user.partner_id)

    def _score_partner_as(self, author, partner):
        vals = dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 4)
        return self.Score.with_user(author).create(dict(vals, partner_id=partner.id))

    def test_manager_reads_and_records_all_scores(self):
        own = self._score(self.bp_user)
        other = self._score(self.bp_colleague)
        partners = (self.bp_user | self.bp_colleague).partner_id
        found = self.Score.with_user(self.bp_manager).search([("partner_id", "in", partners.ids)])
        self.assertEqual(found, own | other)
        created = self._score_as(self.bp_manager, self.bp_third)
        self.assertEqual(created.partner_id, self.bp_third.partner_id)

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.models")
    def test_manager_scores_person_without_login(self):
        """D4: someone without a login is scored by a manager; users never see that score."""
        person = self.env["res.partner"].create({"name": "Warehouse worker without login"})
        score = self._score_partner_as(self.bp_manager, person)
        self.assertEqual(score.partner_id, person)
        self.assertEqual(self.Score.with_user(self.bp_manager).search([("partner_id", "=", person.id)]), score)
        self.assertFalse(self.Score.with_user(self.bp_user).search([("partner_id", "=", person.id)]))

    def test_band_visible_to_user_only_as_aggregate(self):
        """A user without access to colleagues' scores still sees the role band on the map."""
        self.role_sales.partner_ids = (self.bp_user | self.bp_colleague | self.bp_third).partner_id
        self._score(self.bp_user, 1)
        self._score(self.bp_colleague, 3)
        roles = {role["id"]: role for role in self.Activity.with_user(self.bp_user).get_map_data()["roles"]}
        self.assertIs(roles[self.role_sales.id]["adkar"], False, "Two scores: no band, also not for a user.")
        self._score(self.bp_third, 5)
        roles = {role["id"]: role for role in self.Activity.with_user(self.bp_user).get_map_data()["roles"]}
        self.assertEqual(roles[self.role_sales.id]["adkar"], "medium")
        role = self.role_sales.with_user(self.bp_user)
        self.assertEqual(role._get_adkar_bands(), {self.role_sales.id: "medium"})

    # ------------------------------------------------------------------
    # Progress is the same for every viewer
    # ------------------------------------------------------------------

    def _private_setup(self):
        private_project = self.env["project.project"].create(
            {"name": "Followers-only project", "privacy_visibility": "followers"}
        )
        open_project = self.env["project.project"].create(
            {"name": "Open project", "privacy_visibility": "employees"}
        )
        hidden = self.Task.create(
            {
                "name": "Hidden task",
                "project_id": private_project.id,
                "pan_activity_ids": [Command.set(self.act_a.ids)],
                "pan_rung": "1",
                "allocated_hours": 2,
            }
        )
        visible = self.Task.create(
            {
                "name": "Visible task",
                "project_id": open_project.id,
                "pan_activity_ids": [Command.set(self.act_a.ids)],
                "pan_rung": "4",
                "allocated_hours": 3,
            }
        )
        return hidden, visible

    def test_rung_same_for_every_viewer(self):
        hidden, visible = self._private_setup()
        self.assertFalse(
            self.Task.with_user(self.project_user).search([("id", "=", hidden.id)]),
            "Fixture: the project user must not be able to see the hidden task.",
        )
        for viewer in (self.env.user, self.bp_manager, self.bp_user, self.project_user):
            with self.subTest(viewer=viewer.login):
                activity = self.act_a.with_user(viewer)
                activity.invalidate_recordset()
                self.assertEqual(activity.rung, 1)
                self.assertEqual(activity.rung_state, "1")
                self.assertEqual(activity.planned_hours, 5)
                self.assertEqual(self.scenario.with_user(viewer).rung, 1)
                item = next(
                    item
                    for item in self.Activity.with_user(viewer).get_map_data()["activities"]
                    if item["id"] == self.act_a.id
                )
                self.assertEqual(item["rung"], 1)
                ours = [("code", "like", "t_act_%")]
                self.assertEqual(
                    self.Activity.with_user(viewer).search(ours + [("rung", "=", 1)]), self.act_a
                )

    def test_rung_recomputed_with_hidden_tasks_when_user_edits(self):
        """A project user moving their own task forward does not skip a task they cannot see."""
        hidden, visible = self._private_setup()
        visible.pan_rung = "2"
        visible.with_user(self.project_user).pan_rung = "5"
        self.assertEqual(visible.pan_rung, "5")
        self.assertEqual(self.act_a.rung, 1)
        hidden.pan_rung = "3"
        self.assertEqual(self.act_a.with_user(self.project_user).rung, 3)

    def test_map_details_do_not_leak_hidden_task_names(self):
        hidden, visible = self._private_setup()
        details = {item["id"]: item for item in self.Activity.with_user(self.project_user).get_map_details()}
        names = [task["name"] for task in details[self.act_a.id]["tasks"]]
        self.assertIn("Visible task", names)
        self.assertNotIn("Hidden task", names)
        manager_details = {item["id"]: item for item in self.Activity.get_map_details()}
        self.assertIn("Hidden task", [task["name"] for task in manager_details[self.act_a.id]["tasks"]])

    # ------------------------------------------------------------------
    # D13: tasks for project users without Blueprint access
    # ------------------------------------------------------------------

    def test_task_views_hide_blueprint_without_group(self):
        """A project user outside Blueprint opens task views and a linked task without errors."""
        project_only = new_test_user(
            self.env, login="pan_sl_sec_project_only", name="Project only", groups="project.group_project_user"
        )
        task = self.Task.create(
            {
                "name": "Linked task",
                "project_id": self.project.id,
                "pan_activity_ids": [Command.set(self.act_a.ids)],
                "pan_scenario_id": self.scenario.id,
                "pan_rung": "2",
            }
        )
        Task = self.Task.with_user(project_only)
        views = Task.get_views([(False, "form"), (False, "list"), (False, "search")])
        for view_type, view in views["views"].items():
            with self.subTest(view=view_type):
                arch = etree.fromstring(view["arch"])
                self.assertFalse(
                    arch.xpath("//*[starts-with(@name, 'pan_')]"), f"The {view_type} view shows Blueprint fields."
                )
        # What the web client reads: the fields in the form arch it was given.
        arch = etree.fromstring(views["views"]["form"]["arch"])
        fields = {node.get("name") for node in arch.iter("field")} & set(self.Task._fields)
        record = task.with_user(project_only).web_read({name: {} for name in fields})
        self.assertEqual(record[0]["id"], task.id)

        views = self.Task.with_user(self.project_user).get_views([(False, "form")])
        self.assertIn("pan_blueprint_page", views["views"]["form"]["arch"], "Blueprint users keep the page.")

    # ------------------------------------------------------------------
    # E15: Blueprint task fields carry the Blueprint user group
    # ------------------------------------------------------------------

    def test_task_blueprint_fields_have_the_user_group(self):
        """The pan_* task fields are restricted on the model, not only hidden in the views."""
        for name in ("pan_scenario_id", "pan_activity_ids", "pan_rung"):
            with self.subTest(field=name):
                self.assertEqual(self.Task._fields[name].groups, USER_GROUP)
        project_only = new_test_user(
            self.env, login="pan_sl_sec_fields", name="Fields project only", groups="project.group_project_user"
        )
        task = self._make_task(self.act_a, rung="2")
        Task = self.Task.with_user(project_only)
        self.assertFalse({"pan_scenario_id", "pan_activity_ids", "pan_rung"} & set(Task.fields_get()))
        with self.assertRaises(AccessError), mute_logger("odoo.models"):
            task.with_user(project_only).read(["pan_rung"])
        self.assertEqual(task.with_user(self.project_user).read(["pan_rung"])[0]["pan_rung"], "2")

    def test_users_have_no_access_to_the_import_wizard(self):
        """E15: only managers have an access line on the import wizard; users have none at all."""
        Access = self.env["ir.model.access"]
        lines = Access.search([("model_id.model", "=", "pan.sl.blueprint.wizard")])
        self.assertEqual(lines.group_id, self.env.ref(MANAGER_GROUP))
        self.assertFalse(Access.with_user(self.bp_user).check("pan.sl.blueprint.wizard", "read", False))
