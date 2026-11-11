"""Menus and buttons as each group really sees them, and the Export download."""

import json

from lxml import etree

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"
MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager"
MENUS = ("menu_blueprint_root", "menu_blueprint_phase", "menu_blueprint_role", "menu_blueprint_adkar_score")
MANAGER_BUTTONS = ("action_blueprint_load_template", "action_blueprint_import", "action_blueprint_export")


@tagged("post_install", "-at_install")
class TestMenus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bp_user = new_test_user(cls.env, login="pan_sl_menu_user", name="Menu user", groups=USER_GROUP)
        cls.bp_manager = new_test_user(
            cls.env, login="pan_sl_menu_manager", name="Menu manager", groups=MANAGER_GROUP
        )

    def _menu(self, name):
        return self.env.ref(f"pan_self_learning_blueprint.{name}")

    def test_company_map_menu_holds_phases_roles_and_scores(self):
        root = self._menu("menu_blueprint_root")
        self.assertEqual(root.child_id.sorted("sequence").mapped("name"), ["Phases", "Roles", "ADKAR scores"])
        visible = self.env["ir.ui.menu"].with_user(self.bp_user)._visible_menu_ids()
        for name in MENUS:
            with self.subTest(menu=name):
                self.assertIn(self._menu(name).id, visible)
        self.assertFalse(self.env.ref("pan_self_learning_blueprint.menu_blueprint_map", raise_if_not_found=False))

    def test_map_lives_in_the_projects_app(self):
        """#22: no app of its own; the menu sits in Projects and every project opens its map."""
        self.assertEqual(self._menu("menu_blueprint_root").parent_id, self.env.ref("project.menu_main_pm"))
        self.assertIn(self.env.ref("project.group_project_user"), self.bp_user.all_group_ids)
        project = self.env["project.project"].create({"name": "Map project"})
        action = project.with_user(self.bp_user).action_open_blueprint_map()
        self.assertEqual(action["tag"], "pan_sl_blueprint_map")
        self.assertEqual(action["params"], {"project_id": project.id})

    def test_project_form_buttons_for_managers_only(self):
        def buttons(user):
            arch = self.env["project.project"].with_user(user).get_views([(False, "form")])["views"]["form"]["arch"]
            return {node.get("name") for node in etree.fromstring(arch).iter("button")}

        self.assertTrue(set(MANAGER_BUTTONS) <= buttons(self.bp_manager))
        self.assertFalse(set(MANAGER_BUTTONS) & buttons(self.bp_user))
        self.assertIn("action_open_blueprint_map", buttons(self.bp_user))


@tagged("post_install", "-at_install")
class TestExportDownload(HttpCase):
    """Export is a direct download of blueprint.json, for managers only."""

    def test_export_downloads_the_blueprint(self):
        bp_user = new_test_user(self.env, login="pan_sl_dl_user", name="Download user", groups=USER_GROUP)
        bp_manager = new_test_user(self.env, login="pan_sl_dl_manager", name="Download manager", groups=MANAGER_GROUP)
        project = self.env["project.project"].create({"name": "Download project"})
        self.env["pan.sl.role"].create({"name": "Download role", "code": "t_dl_role", "project_id": project.id})
        action = project.with_user(bp_manager).action_blueprint_export()
        self.assertEqual((action["type"], action["target"]), ("ir.actions.act_url", "download"))

        self.authenticate(bp_manager.login, bp_manager.login)
        response = self.url_open(action["url"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("blueprint.json", response.headers.get("Content-Disposition", ""))
        data = json.loads(response.content)
        self.assertEqual((data["format"], data["version"]), ("pantalytics-blueprint", 2))
        self.assertEqual([role["code"] for role in data["roles"]], ["t_dl_role"])

        self.authenticate(bp_user.login, bp_user.login)
        self.assertNotEqual(self.url_open(action["url"]).status_code, 200, "A Blueprint user cannot download it.")
