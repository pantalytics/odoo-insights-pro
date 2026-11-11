"""Menus as each group really sees them (E2), and the Export download (E3).

Odoo hides a menu whose server action is bound to a model the user cannot
read (``ir.ui.menu._visible_menu_ids``), so the menus are checked through that
filter, not by running the actions.
"""

import json

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"
MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager"
MAP_MENUS = ("menu_blueprint_root", "menu_blueprint_map", "menu_blueprint_model", "menu_blueprint_activity")
MANAGER_MENUS = (
    "menu_blueprint_blueprint",
    "menu_blueprint_load_template",
    "menu_blueprint_import",
    "menu_blueprint_export",
)


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

    def _visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_manager_sees_the_three_blueprint_actions(self):
        """E2: one "Import / export" menu holds Load template, Import file and Export, in that order."""
        visible = self._visible(self.bp_manager)
        for name in MAP_MENUS + MANAGER_MENUS:
            with self.subTest(menu=name):
                self.assertIn(self._menu(name).id, visible, f"A Blueprint administrator must see {name}.")
        parent = self._menu("menu_blueprint_blueprint")
        self.assertEqual(parent.name, "Import / export")
        self.assertEqual(parent.child_id.sorted("sequence").mapped("name"), ["Load template", "Import file", "Export"])

    def test_user_sees_the_map_and_the_model_only(self):
        """E2: a Blueprint user sees the map and the model, none of the manager actions."""
        visible = self._visible(self.bp_user)
        for name in MAP_MENUS:
            with self.subTest(menu=name):
                self.assertIn(self._menu(name).id, visible)
        for name in MANAGER_MENUS:
            with self.subTest(menu=name):
                self.assertNotIn(self._menu(name).id, visible, f"A Blueprint user must not see {name}.")

    def test_map_lives_in_the_projects_app(self):
        """#22: no app of its own; the map menu sits in Projects and every project opens its map."""
        self.assertEqual(self._menu("menu_blueprint_root").parent_id, self.env.ref("project.menu_main_pm"))
        self.assertIn(self.env.ref("project.group_project_user"), self.bp_user.all_group_ids)
        project = self.env["project.project"].create({"name": "Map project"})
        action = project.with_user(self.bp_user).action_open_blueprint_map()
        self.assertEqual(action["tag"], "pan_sl_blueprint_map")
        self.assertEqual(action["params"], {"project_id": project.id})

    def test_menus_are_in_the_web_client_menu_tree(self):
        """What the web client loads: the manager actions are in it for managers, not for users."""
        export = self._menu("menu_blueprint_export").id
        self.assertIn(export, self.env["ir.ui.menu"].with_user(self.bp_manager).load_menus(debug=False))
        self.assertNotIn(export, self.env["ir.ui.menu"].with_user(self.bp_user).load_menus(debug=False))


@tagged("post_install", "-at_install")
class TestExportDownload(HttpCase):
    """E3: Export is a direct download of blueprint.json, for managers only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bp_user = new_test_user(cls.env, login="pan_sl_dl_user", name="Download user", groups=USER_GROUP)
        cls.bp_manager = new_test_user(
            cls.env, login="pan_sl_dl_manager", name="Download manager", groups=MANAGER_GROUP
        )
        cls.env["pan.sl.chain"].create({"name": "Download chain", "code": "t_dl_chain"})

    def test_export_downloads_the_blueprint(self):
        action = self.env.ref("pan_self_learning_blueprint.action_blueprint_export").with_user(self.bp_manager).run()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["target"], "download", "Export downloads at once, without a dialog.")

        self.authenticate(self.bp_manager.login, self.bp_manager.login)
        response = self.url_open(action["url"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("blueprint.json", response.headers.get("Content-Disposition", ""))
        data = json.loads(response.content)
        self.assertEqual(data["format"], "pantalytics-blueprint")
        self.assertIn("t_dl_chain", [chain["code"] for chain in data["chains"]])

        self.authenticate(self.bp_user.login, self.bp_user.login)
        response = self.url_open(action["url"])
        self.assertNotEqual(response.status_code, 200, "A Blueprint user cannot download the export.")
