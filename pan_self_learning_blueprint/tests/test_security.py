"""Access per group, checked as real (non-super) users with ``with_user()``.

Users read phases and roles, open a project's map and set role, phase and
stage (so progress) on tasks; managers edit phases and roles and load, import and export
blueprints. ADKAR scores are personal: a user reads only the scores on their
own contact, a manager reads all, the note is manager-only, and the map shows
a role band only over at least three people. Project users without Blueprint
access see no Blueprint fields on tasks.
"""

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import BlueprintCase

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"
MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager"
TASK_FIELDS = ("pan_role_id", "pan_phase_id", "pan_rung", "pan_flow_progress")


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
        cls.project_only = new_test_user(
            cls.env, login="pan_sl_sec_project_only", name="Project only", groups="project.group_project_user"
        )
        cls.Score = cls.env["pan.sl.adkar.score"]

    def _score(self, user, value=3, note=False):
        vals = dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), value)
        return self.Score.create(dict(vals, partner_id=user.partner_id.id, note=note))

    # ------------------------------------------------------------------
    # Phases, roles, tasks and the map
    # ------------------------------------------------------------------

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_reads_and_sets_tasks_but_not_roles(self):
        project = self.project.with_user(self.bp_user)
        data = project.get_blueprint_map_data()
        self.assertEqual(len(data["tasks"]), 2)
        self.role_sales.with_user(self.bp_user).read(["name", "partner_ids"])
        self.phase_a.with_user(self.bp_user).read(["name", "code"])
        self.task_b.with_user(self.bp_user).write({"stage_id": self.stages["3"].id, "pan_phase_id": self.phase_a.id})
        self.assertEqual(self.flow.pan_flow_progress, 100)
        for record in (self.role_sales, self.phase_a):
            with self.subTest(model=record._name), self.assertRaises(AccessError):
                record.with_user(self.bp_user).write({"name": "Changed"})
        with self.assertRaises(AccessError):
            self.Role.with_user(self.bp_user).create({"name": "Mine", "code": "mine", "project_id": self.project.id})

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_user_cannot_change_role_holders_from_the_contact(self):
        """#27: who holds a role is the administrator's, from either side."""
        contacts = self.env.ref("base.group_partner_manager")
        (self.bp_user | self.bp_manager).write({"group_ids": [Command.link(contacts.id)]})
        partner = self.bp_user.partner_id
        with self.assertRaises(AccessError):
            partner.with_user(self.bp_user).write({"pan_role_ids": [Command.link(self.role_sales.id)]})
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.bp_user).create(
                {"name": "Smuggled in", "pan_role_ids": [Command.link(self.role_sales.id)]}
            )
        self.assertFalse(self.role_sales.partner_ids)
        partner.with_user(self.bp_user).write({"name": "Blueprint user renamed"})
        person = self.env["res.partner"].create({"name": "Warehouse worker without login"})
        person.with_user(self.bp_manager).write({"pan_role_ids": [Command.link(self.role_sales.id)]})
        self.assertEqual(self.role_sales.partner_ids, person)

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.models")
    def test_roles_follow_project_visibility(self):
        """#28: a role and its people are seen only with their project."""
        private = self.env["project.project"].create({"name": "Private project", "privacy_visibility": "followers"})
        role = self.Role.create({"name": "Secret role", "code": "t_secret", "project_id": private.id})
        role.partner_ids = self.bp_colleague.partner_id
        domain = [("id", "=", role.id)]
        self.assertFalse(self.Role.with_user(self.bp_user).search(domain))
        with self.assertRaises(AccessError):
            role.with_user(self.bp_user).read(["name", "partner_ids"])
        self.assertEqual(self.Role.with_user(self.bp_manager).search(domain), role)
        private.message_subscribe(partner_ids=self.bp_user.partner_id.ids)
        self.assertEqual(self.Role.with_user(self.bp_user).search(domain), role)
        # A task followed in a project the user cannot open still reads its role.
        private.message_unsubscribe(partner_ids=self.bp_user.partner_id.ids)
        task = self.Task.create({"name": "Followed task", "project_id": private.id, "pan_role_id": role.id})
        task.message_subscribe(partner_ids=self.bp_user.partner_id.ids)
        read = task.with_user(self.bp_user).web_read({"pan_role_id": {"fields": {"display_name": {}}}, "pan_role_people": {}})
        self.assertEqual(read[0]["pan_role_id"]["display_name"], "Secret role")
        self.assertEqual(read[0]["pan_role_people"], self.bp_colleague.partner_id.name)

    def test_manager_edits_roles(self):
        role = self.Role.with_user(self.bp_manager).create({"name": "Mine", "code": "mine", "project_id": self.project.id})
        role.write({"name": "Ours"})
        self.phase_a.with_user(self.bp_manager).write({"sequence": 5})

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_only_managers_load_import_and_export(self):
        project = self.project.with_user(self.bp_user)
        for method in ("action_blueprint_load_template", "action_blueprint_export"):
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(project, method)()
        with self.assertRaises(AccessError):
            self.env["pan.sl.blueprint"].with_user(self.bp_user).import_blueprint(
                self.project.id, {"format": "pantalytics-blueprint", "version": 2}
            )
        self.assertFalse(
            self.env["ir.model.access"].with_user(self.bp_user).check("pan.sl.blueprint.wizard", "read", False)
        )
        # #24: RPC tooling checks model access before calling a method.
        self.env["pan.sl.blueprint"].with_user(self.bp_manager).check_access("read")
        with self.assertRaises(AccessError):
            self.env["pan.sl.blueprint"].with_user(self.bp_user).check_access("read")
        exported = self.env["pan.sl.blueprint"].with_user(self.bp_manager).export_blueprint(self.project.id)
        self.assertEqual(len(exported["roles"]), 2)
        manager_project = self.project.with_user(self.bp_manager)
        self.assertEqual(manager_project.action_blueprint_export()["target"], "download")
        manager_project.action_blueprint_load_template()
        self.assertEqual(len(manager_project.get_blueprint_map_data()["roles"]), 10)

    def test_task_fields_carry_the_user_group(self):
        for name in TASK_FIELDS:
            with self.subTest(field=name):
                self.assertEqual(self.Task._fields[name].groups, USER_GROUP)
        self.assertFalse(set(TASK_FIELDS) & set(self.Task.with_user(self.project_only).fields_get()))

    def test_task_views_hide_blueprint_without_group(self):
        """A project user outside Blueprint opens task views and a placed task without errors."""
        Task = self.Task.with_user(self.project_only)
        views = Task.get_views([(False, "form"), (False, "list"), (False, "search")])
        for view_type, view in views["views"].items():
            with self.subTest(view=view_type):
                arch = etree.fromstring(view["arch"])
                self.assertFalse(arch.xpath("//*[starts-with(@name, 'pan_')]"), f"The {view_type} view shows map fields.")
        arch = etree.fromstring(views["views"]["form"]["arch"])
        fields = {node.get("name") for node in arch.iter("field")} & set(self.Task._fields)
        self.assertEqual(self.task_a.with_user(self.project_only).web_read({name: {} for name in fields})[0]["id"], self.task_a.id)
        views = self.Task.with_user(self.bp_user).get_views([(False, "form")])
        arch = etree.fromstring(views["views"]["form"]["arch"])
        self.assertFalse(arch.xpath("//page[@name='pan_map_page']"), "No Map page any more (2.1).")
        tags = arch.xpath("//field[@name='tag_ids']")[0]
        following = [node.get("name") for node in tags.itersiblings("field")][:3]
        self.assertEqual(following, ["pan_role_id", "pan_phase_id", "pan_flow_progress"], "Role and phase sit next to the tags.")

    # ------------------------------------------------------------------
    # ADKAR: own scores only, notes for managers, band as aggregate
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
        project = self.project.with_user(self.bp_user)
        self.assertIs(project.get_blueprint_map_data()["roles"][0]["adkar"], False, "Two scores: no band.")
        self._score(self.bp_third, 5)
        self.assertEqual(project.get_blueprint_map_data()["roles"][0]["adkar"], "medium")
