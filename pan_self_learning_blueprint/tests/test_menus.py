"""Menus and buttons as each group really sees them, and the Export download."""

import json

from lxml import etree

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user"
MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager"
CONFIG_MENUS = ("menu_blueprint_phase", "menu_blueprint_role", "menu_blueprint_adkar_score")
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

    def test_map_menu_in_the_projects_app(self):
        """One place to start: Projects > Map (it opens the Map view of the one mapped project, or a list)."""
        menu = self._menu("menu_blueprint_map")
        self.assertEqual((menu.name, menu.parent_id), ("Map", self.env.ref("project.menu_main_pm")))
        action = menu.action
        self.assertEqual((action.name, action.tag, action.params), ("Map", "pan_sl_blueprint_map", False))
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(self.bp_user)._visible_menu_ids())
        self.assertFalse(self.env.ref("pan_self_learning_blueprint.menu_blueprint_root", raise_if_not_found=False))

    def test_phases_roles_and_scores_under_configuration(self):
        config = self.env.ref("project.menu_project_config")
        for name in CONFIG_MENUS:
            with self.subTest(menu=name):
                self.assertEqual(self._menu(name).parent_id, config)
        manager = new_test_user(
            self.env, login="pan_sl_menu_pm", name="PM", groups=f"{USER_GROUP},project.group_project_manager"
        )
        visible = self.env["ir.ui.menu"].with_user(manager)._visible_menu_ids()
        self.assertTrue(all(self._menu(name).id in visible for name in CONFIG_MENUS))

    def test_project_opens_its_map(self):
        """The map is the "Map" view of the project's tasks (2.3): first in the
        switcher, all tasks (no "open tasks" default filter)."""
        project = self.env["project.project"].create({"name": "Map project"})
        self.env["pan.sl.role"].create({"name": "Map role", "code": "t_map_role", "project_id": project.id})
        action = project.with_user(self.bp_user).action_open_blueprint_map()
        self.assertEqual((action["type"], action["res_model"]), ("ir.actions.act_window", "project.task"))
        self.assertEqual(action["views"][0], (self.env.ref("pan_self_learning_blueprint.view_task_map").id, "pan_blueprint"))
        self.assertEqual([view for view in action["views"] if view[1] == "pan_blueprint"], [action["views"][0]])
        self.assertIn("kanban", [view[1] for view in action["views"]])
        self.assertEqual(action["context"]["default_project_id"], project.id)
        self.assertNotIn("search_default_open_tasks", action["context"])

    def test_map_in_the_view_switcher(self):
        """Inside a project with a map, Map sits next to Kanban and List, for
        Blueprint users only; a project without roles does not offer it."""
        task_action = self.env.ref("project.act_project_project_2_project_task_all")
        self.assertIn("pan_blueprint", [mode for _id, mode in task_action.views])
        mapped = self.env["project.project"].create({"name": "Mapped"})
        self.env["pan.sl.role"].create({"name": "Mapped role", "code": "t_mapped", "project_id": mapped.id})
        plain = self.env["project.project"].create({"name": "Plain"})
        project_only = new_test_user(self.env, login="pan_sl_menu_po2", name="PO2", groups="project.group_project_user")

        def modes(project, user):
            return [mode for _id, mode in project.with_user(user).action_view_tasks()["views"]]

        self.assertIn("pan_blueprint", modes(mapped, self.bp_user))
        self.assertNotIn("pan_blueprint", modes(plain, self.bp_user))
        self.assertNotIn("pan_blueprint", modes(mapped, project_only))
        info = self.env["ir.ui.view"].get_view_info()["pan_blueprint"]
        self.assertEqual((info["display_name"], info["icon"]), ("Map", "fa fa-map-o"))
        arch = self.env["project.task"].with_user(self.bp_user).get_views([(False, "pan_blueprint")])["views"]["pan_blueprint"]["arch"]
        self.assertTrue(arch.startswith("<pan_blueprint"))

    def test_search_filters_for_the_map(self):
        search_view = self.env.ref("project.view_task_search_form")
        arch = self.env["project.task"].with_user(self.bp_user).get_views([(search_view.id, "search")])["views"]["search"]["arch"]
        names = {node.get("name"): node.get("string") for node in etree.fromstring(arch).iter("filter")}
        for name, label in (
            ("pan_activity", "Activity"),
            ("pan_unplaced", "No place on the map"),
            ("pan_not_decided", "Not decided"),
            ("pan_not_tested", "Not tested"),
            ("pan_still_to_train", "Still to train"),
            ("pan_groupby_role", "Role"),
            ("pan_groupby_phase", "Phase"),
        ):
            self.assertEqual(names.get(name), label, name)

    def test_kanban_card_has_a_visible_map_button(self):
        """On an iPad there is no hover: the card shows "Map" next to the task count."""
        arch = self.env["project.project"].with_user(self.bp_user).get_views([(False, "kanban")])["views"]["kanban"]["arch"]
        root = etree.fromstring(arch)
        self.assertTrue(root.xpath("//div[contains(@class, 'o_project_kanban_boxes')]//a[@name='action_open_blueprint_map']"))
        project_only = new_test_user(self.env, login="pan_sl_menu_po", name="PO", groups="project.group_project_user")
        arch = self.env["project.project"].with_user(project_only).get_views([(False, "kanban")])["views"]["kanban"]["arch"]
        self.assertNotIn("action_open_blueprint_map", arch)

    def test_stage_carries_progress(self):
        arch = self.env["project.task.type"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn('name="pan_rung"', arch)
        self.assertEqual(self.env["project.task.type"]._fields["pan_rung"].string, "Progress")

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

    def test_import_and_export_over_json_rpc(self):
        """#24: an agent with a Blueprint administrator login imports and exports over RPC."""
        bp_manager = new_test_user(self.env, login="pan_sl_rpc_manager", name="RPC manager", groups=MANAGER_GROUP)
        project = self.env["project.project"].create({"name": "RPC project"})
        self.authenticate(bp_manager.login, bp_manager.login)

        def call(method, *args):
            return self.make_jsonrpc_request(
                "/web/dataset/call_kw",
                {"model": "pan.sl.blueprint", "method": method, "args": list(args), "kwargs": {}},
            )

        data = {
            "format": "pantalytics-blueprint",
            "version": 2,
            "roles": [{"code": "t_rpc", "name": "RPC role"}],
        }
        summary = call("import_blueprint", project.id, data)
        self.assertEqual(summary["roles"], {"created": 1, "updated": 0})
        exported = call("export_blueprint", project.id)
        self.assertEqual([role["code"] for role in exported["roles"]], ["t_rpc"])

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
