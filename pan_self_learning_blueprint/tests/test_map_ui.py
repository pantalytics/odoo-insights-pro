"""The map in a real browser (Blueprint 2.2, docs/ux-test-2026-11-11.md).

One project with five progress stages (Open to Trained), two phases, an
internal and an external role, a late flow (a third tested, late a day) with
two open subtasks, one of them without a place, a finished flow (its one task
Trained), a task outside any flow and a loose task without a place. The map is opened from the Projects menu and used the way a person
uses it: tap a flow, a chip, a role name and the tasks without a place. The
screenshot script ``tools/ui_check.mjs`` covers the iPad and phone layouts.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, new_test_user, tagged

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
    throw new Error("Map: not found: " + label);
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const text = (el) => (el ? el.textContent : "").replace(/\\s+/g, " ").trim();
const lines = (el) => el.innerText.split("\\n").map((line) => line.trim()).filter(Boolean).join(" / ");
const chip = (name) => $$(".o_pan_sl_chip").find((el) => text(el) === name);
const expect = (condition, message) => {
    if (!condition) {
        throw new Error("Map: " + message);
    }
};
const openMap = async () => {
    const menu = await waitFor(
        () => $$(".o_main_navbar .o_menu_sections a, .o_main_navbar .o_menu_sections button").find((el) => text(el) === "Map"),
        "Map in the Projects menu"
    );
    menu.click();
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_body"), "the map");
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
        stage = {
            rung: cls.env["project.task.type"].create(
                {"name": f"UI stage {rung}", "pan_rung": rung, "sequence": int(rung), "project_ids": [(4, cls.project.id)]}
            )
            for rung in "01234"
        }
        phase_one, phase_two = cls.env["pan.sl.phase"].create(
            [
                {"name": "UI phase one", "code": "t_ui_phase_1", "sequence": 1},
                {"name": "UI phase two", "code": "t_ui_phase_2", "sequence": 2},
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
        yesterday = fields.Datetime.now() - timedelta(days=1)
        cls.late_flow, cls.done_flow = Task.create(
            [
                {"name": "UI late flow", "project_id": cls.project.id, "date_deadline": yesterday, "sequence": 2},
                {"name": "UI done flow", "project_id": cls.project.id, "sequence": 1},
            ]
        )
        # Without user_ids a new task gets its creator as owner.
        common = {"project_id": cls.project.id, "pan_role_id": role.id, "user_ids": [Command.clear()]}
        Task.create(
            [
                {
                    **common,
                    "name": "UI tested task",
                    "parent_id": cls.late_flow.id,
                    "pan_phase_id": phase_one.id,
                    "stage_id": stage["3"].id,
                    "allocated_hours": 4,
                    "description": "<p>First line of the UI task</p><p>Second line</p>",
                },
                {
                    **common,
                    "name": "UI open task",
                    "parent_id": cls.late_flow.id,
                    "pan_phase_id": phase_one.id,
                    "stage_id": stage["0"].id,
                    "user_ids": [(6, 0, cls.user.ids)],
                },
                {
                    "name": "UI unplaced task",
                    "project_id": cls.project.id,
                    "user_ids": [Command.clear()],
                    "parent_id": cls.late_flow.id,
                    "stage_id": stage["1"].id,
                },
                {
                    "name": "UI customer task",
                    "project_id": cls.project.id,
                    "user_ids": [Command.clear()],
                    "parent_id": cls.done_flow.id,
                    "pan_role_id": external.id,
                    "pan_phase_id": phase_two.id,
                    "stage_id": stage["4"].id,
                },
                {**common, "name": "UI lone task", "pan_phase_id": phase_two.id, "stage_id": stage["1"].id},
                {"name": "UI loose task", "project_id": cls.project.id, "user_ids": [Command.clear()], "stage_id": stage["0"].id},
            ]
        )

    def test_flows(self):
        """Menu > Map opens the one project; flows worst first; a tap shows a flow's open tasks."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    expect(!$(".o_pan_sl_projects") && !$(".o_pan_sl_project_select"), "a project choice with only one project");

    // Worst first, as the server sorts them: the late flow (33%) above the finished one.
    expect(text($(".o_pan_sl_flow_summary")) === "1 of 2 flows late", "summary: " + text($(".o_pan_sl_flow_summary")));
    const flows = $$(".o_pan_sl_flow");
    expect(flows.map((el) => text(el.querySelector(".o_pan_sl_flow_name"))).join("|") === "UI late flow|UI done flow", "flow order");
    expect(text(flows[0]).includes("Tested 33%") && text(flows[0]).includes("2 open"), "late flow: " + text(flows[0]));
    expect(text(flows[0].querySelector(".o_pan_sl_late")) === "Late · 1 day", "late label: " + text(flows[0]));
    expect(/^Due (\\d{1,2} \\S+|\\S+ \\d{1,2})$/.test(text(flows[0].querySelector(".o_pan_sl_due"))), "due: " + text(flows[0]));
    expect(text(flows[1]).includes("Tested 100%") && !flows[1].querySelector(".o_pan_sl_late"), "done flow: " + text(flows[1]));
    expect(!flows[1].querySelector(".o_pan_sl_flow_open"), "a done flow shows no open count");

    // Four colours with plain words.
    expect($$(".o_pan_sl_legend li").map(text).join("|") === "Open|Decided or Built|Tested|Trained or Live", "legend");

    // Grid: placed tasks only, each with a dot in its progress colour.
    expect($$(".o_pan_sl_phase").map(text).join("|") === "UI phase one|UI phase two", "phase columns");
    expect($$(".o_pan_sl_role").map(text).join("|") === "UI lane role|UI customer", "role rows");
    expect($$(".o_pan_sl_chip").length === 4, $$(".o_pan_sl_chip").length + " chips, expected 4");
    expect(chip("UI tested task").querySelector(".o_pan_sl_tone_ok"), "a tested task is not green");
    expect(chip("UI lone task").querySelector(".o_pan_sl_tone_warn"), "a decided task is not amber");
    expect(chip("UI open task").querySelector(".o_pan_sl_tone_off"), "an open task is not grey");
    expect(chip("UI customer task").querySelector(".o_pan_sl_tone_done"), "a trained task is not dark green");

    // Tap a flow: its chips stay, the rest dims, its open tasks (also without a place) listed with owners.
    flows[0].click();
    await waitFor(() => text($(".o_pan_sl_status")) === "Showing flow UI late flow, 2 open tasks", "announcement");
    expect(flows[0].getAttribute("aria-pressed") === "true", "the flow is not marked as selected");
    expect(chip("UI lone task").classList.contains("o_pan_sl_dim"), "a task outside the flow is not dimmed");
    expect(!chip("UI open task").classList.contains("o_pan_sl_dim"), "a task of the flow is dimmed");
    const listed = $$(".o_pan_sl_flows .o_pan_sl_open_task").map(lines);
    expect(
        listed.join("|") === "UI open task / Map UI user / 00:00 of 00:00 h|UI unplaced task / No owner / 00:00 of 00:00 h",
        "open tasks: " + listed.join("|")
    );
    expect(flows[0].nextElementSibling.matches(".o_pan_sl_open_tasks"), "the open tasks are not right under the flow");

    // Tap again: cleared.
    flows[0].click();
    await waitFor(() => !$(".o_pan_sl_chip.o_pan_sl_dim") && !$(".o_pan_sl_flows .o_pan_sl_open_task"), "flow cleared");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_panels(self):
        """A chip opens the task panel with Open task; a role name opens its people and training."""
        self.env["project.task.type"].search([("name", "=", "UI stage 1")]).name = "Decided"
        code = WAIT_JS + """
(async () => {
    await openMap();

    // Role panel: people, what to train on, ADKAR.
    $$(".o_pan_sl_role").find((el) => text(el) === "UI lane role").click();
    const role = await waitFor(() => $(".o_pan_sl_role_panel"), "role panel");
    expect($$(".o_pan_sl_role_people li").map(text).join("|") === "UI person", "role people");
    const training = $$(".o_pan_sl_role_training li").map(text).sort().join("|");
    expect(training === "UI lone task|UI open task|UI tested task", "to train on: " + training);
    expect(text(role.querySelector(".o_pan_sl_role_adkar")) === "Needs three scored people", "role ADKAR");

    // Task panel: the facts, the first line, one primary button.
    chip("UI tested task").click();
    const panel = await waitFor(() => $(".o_pan_sl_task_panel"), "task panel");
    expect(!$(".o_pan_sl_role_panel"), "two panels open");
    expect(text(panel.querySelector(".o_pan_sl_panel_title")) === "UI tested task", "panel title");
    const facts = Object.fromEntries($$(".o_pan_sl_facts dt").map((dt) => [text(dt), text(dt.nextElementSibling)]));
    const want = { Flow: "UI late flow", Role: "UI lane role", Phase: "UI phase one", Progress: "UI stage 3 (Tested)", Owners: "No owner", Hours: "00:00 of 04:00 h" };
    for (const [key, value] of Object.entries(want)) {
        expect(facts[key] === value, key + " reads " + facts[key]);
    }
    expect(text(panel.querySelector(".o_pan_sl_description")) === "First line of the UI task", "description");
    const primary = $$(".o_pan_sl_map .btn-primary");
    expect(primary.length === 1 && text(primary[0]) === "Open task", "primary buttons: " + primary.length);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await waitFor(() => !$(".o_pan_sl_panel"), "panel closed after Escape");

    // A stage named after its step is said once.
    chip("UI lone task").click();
    await waitFor(() => text($(".o_pan_sl_task_panel .o_pan_sl_panel_title")) === "UI lone task", "lone task panel");
    const progress = $$(".o_pan_sl_facts dt").find((dt) => text(dt) === "Progress").nextElementSibling;
    expect(text(progress) === "Decided", "progress reads " + text(progress));
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await waitFor(() => !$(".o_pan_sl_panel"), "panel closed");

    chip("UI tested task").click();
    (await waitFor(() => $(".o_pan_sl_task_panel .btn-primary"), "Open task")).click();
    await waitFor(() => $(".o_form_view") && text($(".o_breadcrumb")).includes("UI tested task"), "task form");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_chip_opens_panel_anywhere(self):
        """Fix 2: a chip low in a tall grid opens a panel that is in view (it
        opened above the fold before); a chip opened from the list and then
        in the grid stays open. Fix 7: a wide grid fades at the right edge."""
        phases = self.env["pan.sl.phase"].create(
            [{"name": f"UI wide phase {index}", "code": f"t_ui_wide_{index}", "sequence": 10 + index} for index in range(6)]
        )
        for index in range(12):
            role = self.env["pan.sl.role"].create(
                {"name": f"UI tall role {index:02d}", "code": f"t_ui_tall_{index}", "project_id": self.project.id}
            )
            self.env["project.task"].create(
                {
                    "name": f"UI tall task {index:02d}",
                    "project_id": self.project.id,
                    "pan_role_id": role.id,
                    "pan_phase_id": phases[index % 6].id,
                    "user_ids": [Command.clear()],
                }
            )
        code = WAIT_JS + """
(async () => {
    await openMap();
    const inView = (el) => {
        const rect = el.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight && rect.left >= 0 && rect.right <= window.innerWidth;
    };
    const content = $(".o_pan_sl_map .o_content");
    expect(content.scrollHeight <= content.clientHeight + 1, "the page scrolls; the grid should scroll on its own");

    // A chip at the bottom of a tall grid.
    const last = chip("UI tall task 11");
    last.scrollIntoView({ block: "end" });
    await new Promise((resolve) => setTimeout(resolve, 100));
    last.click();
    const panel = await waitFor(() => $(".o_pan_sl_task_panel"), "task panel from a low chip");
    expect(text(panel.querySelector(".o_pan_sl_panel_title")) === "UI tall task 11", "panel title");
    expect(inView(panel), "the panel opened out of view");

    // From the side list first, then the same task in the grid: the panel stays open.
    $$(".o_pan_sl_flow")[0].click();
    const listed = await waitFor(
        () => $$(".o_pan_sl_flows .o_pan_sl_open_task").find((el) => el.textContent.includes("UI open task")),
        "listed task"
    );
    listed.click();
    await waitFor(() => text($(".o_pan_sl_task_panel .o_pan_sl_panel_title")) === "UI open task", "panel from the list");
    chip("UI open task").click();
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect($(".o_pan_sl_task_panel .o_pan_sl_panel_title") && text($(".o_pan_sl_task_panel .o_pan_sl_panel_title")) === "UI open task", "a second tap closed the panel");

    // Fix 7: eight phase columns do not fit; the right edge fades until scrolled to the end.
    const wrap = $(".o_pan_sl_grid_wrap");
    const area = $(".o_pan_sl_grid_area");
    expect(area.scrollWidth > area.clientWidth, "the grid does not scroll sideways");
    await waitFor(() => wrap.classList.contains("o_pan_sl_fade_right"), "fade at the right edge");
    area.scrollLeft = area.scrollWidth;
    await waitFor(() => !wrap.classList.contains("o_pan_sl_fade_right"), "fade gone at the end");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_unplaced_and_training(self):
        """The tasks without a place are one tap away; Training opens the training list."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    const link = $(".o_pan_sl_unplaced");
    expect(link && text(link) === "2 tasks without a place", "unplaced link: " + (link && text(link)));
    link.click();
    await waitFor(() => $(".o_pan_sl_flow_unplaced"), "pseudo-filter in the side list");
    const listed = $$(".o_pan_sl_flows .o_pan_sl_open_task").map(lines);
    expect(listed.join("|") === "UI unplaced task / No owner / 00:00 of 00:00 h|UI loose task / No owner / 00:00 of 00:00 h", "without a place: " + listed.join("|"));
    expect(text($(".o_pan_sl_status")) === "Showing 2 tasks without a place", "announcement");
    link.click();
    await waitFor(() => !$(".o_pan_sl_flow_unplaced"), "pseudo-filter cleared");

    // "Still to train (N)": tasks of internal roles below Trained (the customer's are left out).
    expect(text($(".o_pan_sl_training")) === "Still to train (3)", "button: " + text($(".o_pan_sl_training")));
    $(".o_pan_sl_training").click();
    await waitFor(() => $(".o_list_view") && text($(".o_breadcrumb")).includes("Still to train"), "still to train list");
    const facets = await waitFor(() => $$(".o_searchview_facet").length >= 2 && $$(".o_searchview_facet").map(text), "facets");
    expect(facets.some((facet) => facet.includes("Still to train")), "no visible filter: " + facets.join("|"));
    const groups = await waitFor(() => $$(".o_group_header").length && $$(".o_group_header").map(text), "role groups");
    expect(groups.length === 1 && groups[0].startsWith("UI lane role"), "groups: " + groups.join("|"));
    const rows = await waitFor(() => $$(".o_data_row").length === 3 && $$(".o_data_row"), "expanded group rows");
    const people = rows[0].querySelector("td.o_pan_sl_wrap");
    expect(people && text(people) === "UI person" && getComputedStyle(people).whiteSpace === "normal", "people do not wrap");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_project_list(self):
        """With several mapped projects the map starts with a plain list; the switcher changes project."""
        other = self.env["project.project"].create({"name": "UI second project"})
        self.env["pan.sl.role"].create({"name": "UI other role", "code": "t_ui_other", "project_id": other.id})
        code = WAIT_JS + """
(async () => {
    try { localStorage.clear(); } catch {}
    const menu = await waitFor(
        () => $$(".o_main_navbar .o_menu_sections a, .o_main_navbar .o_menu_sections button").find((el) => text(el) === "Map"),
        "Map in the Projects menu"
    );
    menu.click();
    await waitFor(() => $$(".o_pan_sl_projects .o_pan_sl_project").length, "project list");
    const items = $$(".o_pan_sl_project").map(text);
    expect(items.includes("UI map project") && items.includes("UI second project"), "projects: " + items.join("|"));
    $$(".o_pan_sl_project").find((el) => text(el) === "UI map project").click();
    const select = await waitFor(() => $(".o_pan_sl_project_select"), "project switcher");
    await waitFor(() => $$(".o_pan_sl_chip").length === 4, "map of the chosen project");
    select.value = "%(other)s";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => !$(".o_pan_sl_chip") && $(".o_pan_sl_grid_area .o_pan_sl_empty"), "map of the other project");
    console.log("test successful");
})().catch((error) => console.error(error.message));
""" % {"other": other.id}
        self.browser_js("/odoo/project", code, login=self.user.login)
