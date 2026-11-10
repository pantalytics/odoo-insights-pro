"""Access per group, checked as real (non-super) users with ``with_user()``.

Contract: users see the map and read the model; managers edit the model and
import. ADKAR scores are personal: a user reads only their own scores, a
manager reads all, the note is manager-only, and a role profile is only an
aggregate over at least three users. Progress (rung, hours) is the same for
every viewer, whatever tasks they may open.
"""

import base64
import json

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
        return self.Score.create(dict(vals, user_id=user.id, note=note))

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

    def test_user_opens_the_map_with_odoo_models(self):
        """The map names the Odoo model of an activity; a plain user may not read ir.model."""
        partner_model = self.env["ir.model"]._get("res.partner")
        self.act_a.model_id = partner_model
        self.phase_a.model_ids = [Command.set(partner_model.ids)]
        data = self.Activity.with_user(self.bp_user).get_map_data()
        item = next(item for item in data["activities"] if item["id"] == self.act_a.id)
        self.assertEqual(item["model"], "res.partner")

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
            self.env["pan.sl.blueprint.wizard"].with_user(self.bp_user).create({"mode": "import"})
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
            {
                "mode": "import",
                "file": base64.b64encode(json.dumps(data).encode()),
                "filename": "manager.json",
            }
        )
        wizard.action_import()
        self.assertTrue(wizard.result)
        self.assertEqual(self.Chain.search_count([("code", "=", "t_sec_bp_chain")]), 1)
        wizard = self.env["pan.sl.blueprint.wizard"].with_user(self.bp_manager).create({"mode": "export"})
        wizard.action_export()
        self.assertTrue(wizard.file)

    def test_manager_exports_phase_models(self):
        partner_model = self.env["ir.model"]._get("res.partner")
        self.phase_a.model_ids = [Command.set(partner_model.ids)]
        self.act_a.model_id = partner_model
        exported = self.env["pan.sl.blueprint"].with_user(self.bp_manager).export_blueprint()
        phase = next(item for item in exported["phases"] if item["code"] == "t_phase_a")
        self.assertEqual(phase["models"], ["res.partner"])

    def test_manager_loads_template(self):
        Wizard = self.env["pan.sl.blueprint.wizard"].with_user(self.bp_manager)
        templates = Wizard._fields["template"].get_values(self.env)
        wizard = Wizard.create({"mode": "template", "template": templates[0]})
        wizard.action_load_template()
        self.assertTrue(wizard.result)

    # ------------------------------------------------------------------
    # ADKAR: own scores only, notes for managers, profile as aggregate
    # ------------------------------------------------------------------

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.models")
    def test_user_reads_only_own_scores(self):
        own = self._score(self.bp_user, note="Own note")
        other = self._score(self.bp_colleague, note="Colleague's blocker")
        Score = self.Score.with_user(self.bp_user)
        self.assertEqual(Score.search([("user_id", "in", (self.bp_user | self.bp_colleague).ids)]), own)
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
        vals = dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 4)
        return self.Score.with_user(author).create(dict(vals, user_id=user.id))

    def test_manager_reads_and_records_all_scores(self):
        own = self._score(self.bp_user)
        other = self._score(self.bp_colleague)
        found = self.Score.with_user(self.bp_manager).search([("user_id", "in", (self.bp_user | self.bp_colleague).ids)])
        self.assertEqual(found, own | other)
        created = self._score_as(self.bp_manager, self.bp_third)
        self.assertEqual(created.user_id, self.bp_third)

    def test_profile_visible_to_user_only_as_aggregate(self):
        """A user without access to colleagues' scores still sees the role profile on the map."""
        self.role_sales.user_ids = self.bp_user | self.bp_colleague | self.bp_third
        self._score(self.bp_user, 1)
        self._score(self.bp_colleague, 3)
        roles = {role["id"]: role for role in self.Activity.with_user(self.bp_user).get_map_data()["roles"]}
        self.assertIs(roles[self.role_sales.id]["adkar"], False, "Two scores: no profile, also not for a user.")
        self._score(self.bp_third, 5)
        roles = {role["id"]: role for role in self.Activity.with_user(self.bp_user).get_map_data()["roles"]}
        self.assertEqual(roles[self.role_sales.id]["adkar"], [3.0] * 5)
        self.assertEqual(self.role_sales.with_user(self.bp_user)._get_adkar_profile(), [3.0] * 5)

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
