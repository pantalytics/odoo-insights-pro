"""The company map in a real browser (data model v2.0: everything is a task).

One project with two phases, an internal and an external role, a flow with two
subtasks, one task outside the flow and one task without a place. The map is
opened from the project form and checked the way a user uses it: the three
zoom stops, the colour modes, the flow filter, the task and role panels and
the link to the tasks without a place. The screenshot script
``tools/ui_check.mjs`` covers pan, pinch, keyboard and phone layouts by hand.
"""

from odoo.tests import HttpCase, new_test_user, tagged

MAP_URL = "/odoo/action-pan_self_learning_blueprint.action_blueprint_map"

# Waits until a check returns something truthy; any thrown error fails the test.
WAIT_JS = """
const waitFor = async (check, label) => {
    for (let attempt = 0; attempt < 100; attempt++) {
        const found = check();
        if (found) {
            return found;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("Company map: not found: " + label);
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const stop = () => parseInt($(".o_pan_sl_svg").dataset.stop, 10);
const chip = (name) => $$(".o_pan_sl_chip").find((el) => el.querySelector("title").textContent === name);
const tone = (name) => [...chip(name).querySelector(".o_pan_sl_dot").classList].find((c) => c.startsWith("o_pan_sl_tone_"));
const expect = (condition, message) => {
    if (!condition) {
        throw new Error("Company map: " + message);
    }
};
const zoomTo = async (label, value) => {
    $$(".o_pan_sl_zoom_label").find((el) => el.textContent.trim() === label).click();
    await waitFor(() => stop() === value, "zoom stop " + label);
};
const choose = async (selector, value) => {
    const select = $(selector);
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 150));
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
        cls.project = cls.env["project.project"].create({"name": "UI map project"})
        phase_project, phase_sales = cls.env["pan.sl.phase"].create(
            [
                {"name": "UI phase one", "code": "t_ui_phase_1", "sequence": 1, "app_labels": "project"},
                {"name": "UI phase two", "code": "t_ui_phase_2", "sequence": 2, "app_labels": "t_ui_no_such_app"},
            ]
        )
        person = cls.env["res.partner"].create({"name": "UI person"})
        role, external = cls.env["pan.sl.role"].create(
            [
                {"name": "UI lane role", "code": "t_ui_role", "project_id": cls.project.id, "partner_ids": [(6, 0, person.ids)]},
                {"name": "UI customer", "code": "t_ui_customer", "project_id": cls.project.id, "is_external": True},
            ]
        )
        Task = cls.env["project.task"]
        cls.flow = Task.create({"name": "UI flow", "project_id": cls.project.id})
        common = {"project_id": cls.project.id, "pan_role_id": role.id}
        Task.create(
            [
                {
                    **common,
                    "name": "UI tested task",
                    "parent_id": cls.flow.id,
                    "pan_phase_id": phase_project.id,
                    "pan_rung": "3",
                    "user_ids": [(6, 0, cls.user.ids)],
                    "allocated_hours": 4,
                    "description": "<p>First line of the UI task</p><p>Second line</p>",
                },
                {**common, "name": "UI open task", "parent_id": cls.flow.id, "pan_phase_id": phase_project.id},
                {**common, "name": "UI lone task", "pan_phase_id": phase_sales.id, "pan_rung": "1"},
                {
                    "name": "UI customer task",
                    "project_id": cls.project.id,
                    "pan_role_id": external.id,
                    "pan_phase_id": phase_sales.id,
                },
                {**common, "name": "UI unplaced task"},
            ]
        )

    def test_map_without_project(self):
        """Opened without a project the map shows one muted line and nothing else."""
        code = WAIT_JS + """
(async () => {
    const empty = await waitFor(() => $(".o_pan_sl_map .o_pan_sl_empty"), "empty line");
    expect(empty.textContent.trim() === "Open the map from a project.", "empty line reads " + empty.textContent);
    expect(!$(".o_pan_sl_controls") && !$(".o_pan_sl_svg"), "controls or map shown without a project");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js(MAP_URL, code, login=self.user.login)

    def test_map_from_project(self):
        flow_id = self.flow.id
        code = WAIT_JS + """
(async () => {
    // The map opens from the project form ("Map").
    const button = await waitFor(() => $("button[name=action_open_blueprint_map]"), "Map button on the project");
    button.click();
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_svg"), "map svg");

    // Company: a coloured block per cell with its count, no chips; apps band.
    expect(stop() === 1, "the map does not open at the Company stop");
    await waitFor(() => $$(".o_pan_sl_block_count").some((el) => el.textContent.trim() === "2"), "block of 2 tasks");
    expect(!$(".o_pan_sl_chip"), "chips at the Company stop");
    const apps = $$(".o_pan_sl_app:not(.o_pan_sl_app_off) text").map((el) => el.textContent.trim());
    expect(apps.includes("Project"), "installed apps in the band: " + apps.join(", "));
    const lanes = $$(".o_pan_sl_role_label_group").map((el) => el.getAttribute("aria-label"));
    expect(lanes.join("|") === "UI lane role|UI customer", "lanes are " + lanes.join("|"));

    // Colour by: exactly Progress and Training.
    const modes = $$(".o_pan_sl_color_select option").map((el) => el.value);
    expect(modes.join(",") === "progress,training", "colour by offers " + modes.join(","));

    // Tasks: chips with names, coloured by progress.
    await zoomTo("Tasks", 2);
    expect($$(".o_pan_sl_chip").length === 4, $$(".o_pan_sl_chip").length + " chips, expected 4");
    expect(tone("UI tested task") === "o_pan_sl_tone_ok", "a tested task is not green");
    expect(tone("UI lone task") === "o_pan_sl_tone_warn", "a decided task is not amber");
    expect(tone("UI open task") === "o_pan_sl_tone_off", "an open task is not grey");
    const label = chip("UI tested task").getAttribute("aria-label");
    expect(label.includes("UI tested task") && label.includes("UI flow") && label.includes("Tested"), "chip name: " + label);

    // Training: amber below Trained, grey when the role has nobody.
    await choose(".o_pan_sl_color_select", "training");
    expect(tone("UI tested task") === "o_pan_sl_tone_warn", "training: a tested task is not amber");
    expect(tone("UI customer task") === "o_pan_sl_tone_off", "training: a role without people is not grey");
    const legend = $$(".o_pan_sl_legend li").map((el) => el.textContent.trim());
    expect(legend.join("|") === "Trained|Still to train|Nobody in the role", "training legend: " + legend.join("|"));
    await choose(".o_pan_sl_color_select", "progress");

    // Detail: assignees, hours and the first line of the description.
    await zoomTo("Detail", 3);
    const detail = chip("UI tested task").querySelector(".o_pan_sl_detail").textContent;
    for (const part of ["Tested", "00:00 of 04:00 h", "Map UI user", "First line of the UI task"]) {
        expect(detail.includes(part), "detail lacks " + part + ": " + detail);
    }
    expect(!detail.includes("Second line"), "detail shows more than the first line");

    // Flow filter: the Tasks stop with the flow in view, the rest dimmed, announced.
    await zoomTo("Company", 1);
    const option = $$(".o_pan_sl_flow_select option").find((el) => el.value === "%(flow_id)s");
    expect(option && option.textContent.replace(/\\s+/g, " ").trim() === "UI flow · Tested 50%%", "flow option: " + (option && option.textContent));
    await choose(".o_pan_sl_flow_select", "%(flow_id)s");
    expect(stop() === 2, "selecting a flow does not show its tasks");
    expect(chip("UI lone task").classList.contains("o_pan_sl_dim"), "a task outside the flow is not dimmed");
    expect(!chip("UI open task").classList.contains("o_pan_sl_dim"), "a task of the flow is dimmed");
    const body = $(".o_pan_sl_body").getBoundingClientRect();
    for (const name of ["UI tested task", "UI open task"]) {
        const r = chip(name).getBoundingClientRect();
        expect(r.left >= body.left && r.right <= body.right && r.top >= body.top && r.bottom <= body.bottom, name + " is out of view");
    }
    const status = $(".o_pan_sl_flow_status").textContent.trim();
    expect(status === "Showing flow UI flow, 2 tasks", "announced: " + status);
    await choose(".o_pan_sl_flow_select", "");

    // Task panel: one primary action.
    chip("UI tested task").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const panel = await waitFor(() => $(".o_pan_sl_panel"), "task panel");
    expect(panel.querySelector(".o_pan_sl_panel_title").textContent.trim() === "UI tested task", "panel title");
    expect(panel.querySelector(".o_pan_sl_assignees").textContent.trim() === "Map UI user", "panel assignees");
    const primary = $$(".o_pan_sl_map .btn-primary");
    expect(primary.length === 1 && primary[0].textContent.trim() === "Open task", "primary buttons: " + primary.length);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await waitFor(() => !$(".o_pan_sl_panel"), "panel closed after Escape");

    // Role panel from the lane name.
    $(".o_pan_sl_role_label_group").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const role = await waitFor(() => $(".o_pan_sl_role_panel"), "role panel");
    expect(role.querySelector(".o_pan_sl_role_people").textContent.trim() === "UI person", "role people");
    expect(role.querySelector(".o_pan_sl_role_adkar").textContent.trim() === "Needs three scored people", "role ADKAR");
    expect(role.querySelector(".o_pan_sl_role_tasks").textContent.trim() === "3", "role task count");

    // Tasks without a place: a muted link to their list.
    const link = $(".o_pan_sl_unplaced");
    expect(link && link.textContent.replace(/\\s+/g, " ").trim() === "1 task without a place", "unplaced link: " + (link && link.textContent));
    link.click();
    await waitFor(() => $(".o_list_view"), "unplaced list");
    // The task list may come grouped by stage: open the group.
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (!$(".o_data_row") && $(".o_group_header")) {
        $(".o_group_header").click();
    }
    await waitFor(() => $$(".o_list_view .o_data_row").some((row) => row.textContent.includes("UI unplaced task")), "unplaced list");
    console.log("test successful");
})().catch((error) => console.error(error.message));
""" % {"flow_id": flow_id}
        self.browser_js(f"/odoo/project.project/{self.project.id}", code, login=self.user.login)
