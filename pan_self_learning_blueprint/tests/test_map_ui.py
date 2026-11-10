"""Smoke test of the company map client action in a real browser.

The detailed UI checks (zoom stops, scenario route, side panel, mobile) live in
``tools/ui_check.mjs``; this test only proves, inside the module suite, that the
map loads for a plain Blueprint user without a JS or template error, and that
the empty state offers "Load a template".
"""

from odoo.tests import HttpCase, new_test_user, tagged

MAP_URL = "/odoo/action-pan_self_learning_blueprint.action_blueprint_map"

# Waits for a selector, then checks a condition; any thrown error fails the test.
WAIT_JS = """
const waitFor = async (check, label) => {
    for (let attempt = 0; attempt < 200; attempt++) {
        const found = check();
        if (found) {
            return found;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("Company map: not found: " + label);
};
"""


@tagged("post_install", "-at_install")
class TestMapUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env,
            login="pan_sl_map_ui_user",
            name="Map UI user",
            groups="pan_self_learning_blueprint.group_blueprint_user",
        )

    def _make_model(self):
        chain = self.env["pan.sl.chain"].create({"name": "UI chain", "code": "t_ui_chain"})
        phase = self.env["pan.sl.phase"].create({"name": "UI phase", "code": "t_ui_phase"})
        role = self.env["pan.sl.role"].create({"name": "UI lane role", "code": "t_ui_role"})
        process = self.env["pan.sl.process"].create({"name": "UI process", "code": "t_ui_process", "chain_id": chain.id})
        return self.env["pan.sl.activity"].create(
            [
                {
                    "name": f"UI activity {index}",
                    "code": f"t_ui_act_{index}",
                    "process_id": process.id,
                    "role_id": role.id,
                    "phase_id": phase.id,
                }
                for index in range(3)
            ]
        )

    def test_map_renders_for_a_blueprint_user(self):
        self._make_model()
        code = WAIT_JS + """
(async () => {
    await waitFor(() => document.querySelector(".o_pan_sl_map svg.o_pan_sl_svg"), "map svg");
    // Stop 1 (Company): the role x phase cell is one block counting its 3 activities.
    await waitFor(
        () => [...document.querySelectorAll(".o_pan_sl_block .o_pan_sl_block_count")].some(
            (el) => el.textContent.trim() === "3"
        ),
        "block with count 3"
    );
    await waitFor(() => document.body.textContent.includes("UI lane role"), "role lane label");
    if (document.querySelector(".o_pan_sl_map .o_view_nocontent")) {
        throw new Error("Company map: empty state shown although there are activities");
    }
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js(MAP_URL, code, login=self.user.login)

    def test_map_empty_state_offers_template(self):
        if self.env["pan.sl.activity"].search_count([]):
            self.skipTest("This database already has activities, so the map has no empty state.")
        code = WAIT_JS + """
(async () => {
    const empty = await waitFor(() => document.querySelector(".o_pan_sl_map .o_view_nocontent"), "empty state");
    const button = [...empty.querySelectorAll("button")].find((el) => el.textContent.includes("Load a template"));
    if (!button) {
        throw new Error("Company map: empty state has no 'Load a template' button");
    }
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js(MAP_URL, code, login=self.user.login)
