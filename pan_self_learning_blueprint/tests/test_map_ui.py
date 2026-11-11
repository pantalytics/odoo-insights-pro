"""The map in a real browser (Blueprint 2.3.1, docs/ux-test-2026-11-11.md, round 5).

One project with five progress stages (Open to Trained), two phases, an
internal and an external role, a late flow (one task of three tested, late a
day; one without a place), a finished flow (its one task Trained), a task
outside any flow, a loose task without a place, two milestones (one reached),
and the company in one page with keywords, systems and dates. The map is a
zoomable stage with levels of detail z0 (company) to z4 (task); the tests
zoom with + and -, Ctrl + wheel and clicks, and check which layers show at
each level. ``tools/ui_check.mjs`` covers the iPad (pinch) and the phone.
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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const text = (el) => (el ? el.textContent : "").replace(/\\s+/g, " ").trim();
const lines = (el) => el.innerText.split("\\n").map((line) => line.trim()).filter(Boolean).join(" / ");
const chip = (name) => $$(".o_pan_sl_chip").find((el) => text(el) === name);
const chips = () => $$(".o_pan_sl_chip").map(text).sort().join("|");
const zoom = () => Number($(".o_pan_sl_frame").dataset.zoom);
const layers = () => [...new Set($$("[data-layer]").map((el) => el.dataset.layer))].sort().join(",");
const crumbs = () => $$(".o_pan_sl_crumb, .o_pan_sl_crumb_current").map(text).join(" › ");
const atZoom = (level) => waitFor(() => $(".o_pan_sl_frame") && zoom() === level && /^(scale\\(1\\))?$/.test($(".o_pan_sl_lod").style.transform), "zoom " + level);
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
    const item = await waitFor(() => $$(".o_pan_sl_project").find((el) => text(el) === "UI map project"), "the project list");
    item.click();
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_frame"), "the map");
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
        cls.project.allow_milestones = True
        today = fields.Date.today()
        cls.env["project.milestone"].create(
            [
                {"name": "UI kickoff", "project_id": cls.project.id, "deadline": today - timedelta(days=30), "is_reached": True},
                {"name": "UI go-live", "project_id": cls.project.id, "deadline": today + timedelta(days=10)},
            ]
        )
        cls.project.write(
            {
                "pan_brief": "<p>UI Machines builds packaging lines. Forty people.</p><p>Second paragraph.</p>",
                "pan_keywords": "machines, sheet metal, projects, extra",
                "pan_from_systems": "UI old system",
                "pan_to_systems": "Odoo 19",
                "date_start": today - timedelta(days=60),
                "date": today + timedelta(days=60),
            }
        )
        cls.late_flow.write({"pan_summary": "UI late summary", "pan_keywords": "alpha, beta, gamma, delta"})
        cls.role, cls.external, cls.phase_one, cls.phase_two, cls.stage = role, external, phase_one, phase_two, stage

    def test_levels_of_detail(self):
        """Menu > Map opens at z0; each level shows only its layers; + and - change level."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    expect($(".o_switch_view.o_pan_blueprint.active"), "Map is not the active view in the switcher");
    expect($(".o_pan_sl_map .o_searchview"), "no search bar");
    await atZoom(0);
    expect(layers() === "company,systems,timeline", "z0 layers: " + layers());
    expect(text($(".o_pan_sl_headline")) === "UI Machines builds packaging lines.", "headline: " + text($(".o_pan_sl_headline")));
    expect($$(".o_pan_sl_keywords li").map(text).join("|") === "machines|sheet metal|projects", "keywords");
    expect(text($(".o_pan_sl_systems")).replace("→to", "→") === "UI old system → Odoo 19", "systems: " + text($(".o_pan_sl_systems")));
    expect($$(".o_pan_sl_tick").length === 2 && $(".o_pan_sl_tick_reached") && $(".o_pan_sl_today"), "timeline ticks and today");
    expect(crumbs() === "Company", "crumbs: " + crumbs());
    expect($(".o_pan_sl_zoom_out").disabled && !$(".o_pan_sl_zoom_in").disabled, "zoom buttons at z0");
    expect(!$(".o_pan_sl_missing"), "a user sees the managers' hint");

    $(".o_pan_sl_zoom_in").click();
    await atZoom(1);
    // z1 (round 6): the burn-up replaces the timeline, the verdict is its own.
    expect(layers() === "burnup,caption,legend,projectBar,systems", "z1 layers: " + layers());
    expect($$(".o_pan_sl_legend li").map(text).join("|") === "Open|Decided|Built|Tested|Trained|Live", "legend");
    // Started 60 days ago: nine weekly points and today.
    expect($(".o_pan_sl_burnup_actual").getAttribute("points").trim().split(" ").length === 10, "burn-up points");
    expect(getComputedStyle($(".o_pan_sl_burnup_ideal")).strokeDasharray !== "none", "ideal line dashed");
    expect($$(".o_pan_sl_burnup_tick").length === 2 && $(".o_pan_sl_burnup_tick_reached"), "milestone ticks");
    expect(text($(".o_pan_sl_burnup_today")) === "Today" && text($(".o_pan_sl_burnup_value")) === "30%", "today and value");
    // 9 steps of 30 done (30%) against 50% planned: the ideal was at 30% 24 days ago.
    const caption = text($(".o_pan_sl_caption"));
    expect(/^UI go-live · Due .+Behind · 3 weeks$/.test(caption), "caption: " + caption);
    expect($(".o_pan_sl_caption_status.o_pan_sl_status_late"), "more than two weeks behind is red");
    const parts = $$(".o_pan_sl_project_bar .o_pan_sl_stack > span").map((el) => el.className.match(/s\\d/)[0] + ":" + el.style.flexGrow);
    expect(parts.join("|") === "s0:2|s1:2|s3:1|s4:1", "project bar: " + parts.join("|"));

    $(".o_pan_sl_zoom_in").click();
    await atZoom(2);
    expect(layers() === "caption,flows,legend,projectBar,unplaced", "z2 layers: " + layers());
    expect(crumbs() === "Company › Project › Flows", "crumbs: " + crumbs());
    const rows = $$(".o_pan_sl_flow");
    expect(rows.map((el) => text(el.querySelector(".o_pan_sl_flow_name"))).join("|") === "UI late flow|UI done flow", "flow order");
    const summary = rows[0].querySelector(".o_pan_sl_flow_summary");
    const words = [...summary.querySelectorAll(".o_pan_sl_keyword")].map(text).join("|");
    expect(summary.firstChild.textContent.trim() === "UI late summary" && words === "alpha|beta|gamma", "summary: " + text(summary));
    expect(text(rows[0].querySelector(".o_pan_sl_flow_open")) === "2 open" && text(rows[0].querySelector(".o_pan_sl_late")) === "Late · 1 day", "late flow: " + text(rows[0]));
    expect(!text(rows[1].querySelector(".o_pan_sl_late")) && !text(rows[1].querySelector(".o_pan_sl_flow_open")), "done flow: " + text(rows[1]));
    expect(!$(".o_pan_sl_chip") && !$(".o_pan_sl_headline"), "task names or the company at z2");

    // + at z2 flies into the worst flow; - and - again back to z1.
    $(".o_pan_sl_zoom_in").click();
    await atZoom(3);
    expect(crumbs() === "Company › Project › Flows › UI late flow", "crumbs at z3: " + crumbs());
    $(".o_pan_sl_zoom_out").click();
    await atZoom(2);
    $(".o_pan_sl_zoom_out").click();
    await atZoom(1);
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_wheel_and_keyboard(self):
        """Ctrl + wheel zooms (and snaps to a level); a plain wheel scrolls and never zooms."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    await atZoom(0);
    const stage = $(".o_pan_sl_stage");
    const wheel = (ctrlKey, deltaY) =>
        stage.dispatchEvent(new WheelEvent("wheel", { deltaY, ctrlKey, bubbles: true, cancelable: true, clientX: 600, clientY: 400 }));
    wheel(false, -300);
    await sleep(700);
    expect(zoom() === 0, "a plain wheel zoomed to " + zoom());
    wheel(true, -250);
    await atZoom(1);
    wheel(true, -250);
    await atZoom(2);
    wheel(true, 250);
    await atZoom(1);
    // The breadcrumb zooms back out.
    $(".o_pan_sl_zoom_in").click();
    await atZoom(2);
    $$(".o_pan_sl_crumb").find((el) => text(el) === "Company").click();
    await atZoom(0);
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_fly_to_flow_and_task(self):
        """Clicking a flow flies to its swimlane (z3); a chip flies to the task (z4):
        its own form, chatter under it, over the map, saved when you leave it; the
        breadcrumb goes back; back from the full-screen form the map is where it was."""
        self.env["project.task"].create(
            {
                "name": "UI customer step",
                "project_id": self.project.id,
                "parent_id": self.late_flow.id,
                "pan_role_id": self.external.id,
                "pan_phase_id": self.phase_two.id,
                "stage_id": self.stage["0"].id,
                "user_ids": [Command.clear()],
                "sequence": 50,
            }
        )
        code = WAIT_JS + """
(async () => {
    await openMap();
    $(".o_pan_sl_zoom_in").click();
    await atZoom(1);
    $(".o_pan_sl_zoom_in").click();
    await atZoom(2);
    $$(".o_pan_sl_flow").find((el) => text(el.querySelector(".o_pan_sl_flow_name")) === "UI late flow").click();
    await atZoom(3);
    expect(layers() === "legend,steps,swimlane", "z3 layers: " + layers());
    await waitFor(() => text($(".o_pan_sl_status")) === "Showing flow UI late flow, 3 open tasks", "announcement");

    // The swimlane: a column per step, N-1 arrows left to right, ending at their chips.
    expect(chips() === "UI customer step|UI open task|UI tested task", "chips: " + chips());
    expect($$(".o_pan_sl_role").map(text).join("|") === "UI lane role|UI customer", "rows");
    const arrows = await waitFor(() => $$(".o_pan_sl_arrow").length === 2 && $$(".o_pan_sl_arrow"), "two arrows");
    const ids = { tested: chip("UI tested task").dataset.taskId, open: chip("UI open task").dataset.taskId, step: chip("UI customer step").dataset.taskId };
    const pairs = arrows.map((path) => path.dataset.from + ">" + path.dataset.to).join("|");
    expect(pairs === ids.tested + ">" + ids.open + "|" + ids.open + ">" + ids.step, "arrow order: " + pairs);
    const ends = arrows.map((path) => path.getAttribute("d").match(/-?[\\d.]+,-?[\\d.]+/g).map((pair) => pair.split(",").map(Number)));
    expect(ends.every((points) => points.at(-1)[0] > points[0][0]), "an arrow runs right to left");
    const end = arrows[1].getPointAtLength(arrows[1].getTotalLength());
    const svg = arrows[1].ownerSVGElement.getBoundingClientRect();
    const box = chip("UI customer step").getBoundingClientRect();
    expect(Math.abs(svg.left + end.x - box.left) < 4 && svg.top + end.y > box.top && svg.top + end.y < box.bottom, "the arrow does not end at its chip");
    expect(chip("UI tested task").title === "UI tested task", "no full name in the chip's title");

    // The steps listed with owner and hours, done ones muted with their stage word.
    const listed = $$(".o_pan_sl_open_task").map(lines);
    expect(
        listed.join("|") ===
            "UI tested task / UI stage 3 (Tested) / No owner / 0:00 spent of 4:00 planned|UI open task / Map UI user / 0:00 spent of 0:00 planned|UI unplaced task / No owner / 0:00 spent of 0:00 planned|UI customer step / No owner / 0:00 spent of 0:00 planned",
        "steps: " + listed.join("|")
    );

    // A chip flies to the task: z4, the task itself (Odoo's form, chatter under it) over the map.
    chip("UI tested task").click();
    await atZoom(4);
    expect(layers() === "legend,swimlane", "z4 layers: " + layers());
    expect(crumbs() === "Company › Project › Flows › UI late flow › UI tested task", "crumbs at z4: " + crumbs());
    const panelTask = () => $(".o_pan_sl_task_panel .o_form_view .o_field_widget[name='name'] :is(input, textarea)")?.value;
    await waitFor(() => panelTask() === "UI tested task", "the task form in the panel");
    const panel = $(".o_pan_sl_task_panel");
    await Promise.all(panel.getAnimations().map((animation) => animation.finished));
    const sheet = await waitFor(() => panel.querySelector(".o_form_sheet_bg"), "form sheet");
    const chatter = await waitFor(() => panel.querySelector(".o-mail-Form-chatter"), "chatter in the panel");
    expect(chatter.getBoundingClientRect().top >= sheet.getBoundingClientRect().bottom - 1, "the chatter is not under the form");
    expect(text(panel.querySelector(".o_field_widget[name='description']")).includes("First line of the UI task"), "description");
    const over = panel.getBoundingClientRect();
    const stage = $(".o_pan_sl_stage").getBoundingClientRect();
    expect(over.left < stage.right - 1 && Math.abs(over.right - stage.right) < 2, "the panel does not slide over the map");
    expect($(".o_breadcrumb").textContent.includes("UI map project"), "the form renamed the map's breadcrumb");
    expect(!$(".o_pan_sl_zoom"), "zoom buttons over the task form");

    // A change is saved when the panel closes (zooming out to z3), and the chip follows.
    const name = $(".o_pan_sl_task_panel .o_field_widget[name='name'] :is(input, textarea)");
    name.value = "UI tested task renamed";
    name.dispatchEvent(new Event("input", { bubbles: true }));
    name.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(0); // a person's click comes after the change, not in the same tick
    $(".o_pan_sl_task_panel .o_pan_sl_close").click();
    await atZoom(3);
    await waitFor(() => !$(".o_pan_sl_task_panel") && chip("UI tested task renamed"), "the map does not show the saved name");

    // The stage moves in the form's own status bar; the chip follows when leaving the task.
    chip("UI tested task renamed").click();
    await atZoom(4);
    await waitFor(() => panelTask() === "UI tested task renamed", "the renamed task form");
    const next = await waitFor(
        () => $$(".o_pan_sl_task_panel .o_statusbar_status button").find((el) => text(el).startsWith("UI stage 4")),
        "stage 4 in the status bar"
    );
    next.click();
    await waitFor(
        () => $(".o_pan_sl_task_panel .o_statusbar_status button.o_arrow_button_current")?.textContent.includes("UI stage 4"),
        "stage 4 current"
    );
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await atZoom(3);
    await waitFor(() => chip("UI tested task renamed")?.querySelector(".o_pan_sl_tone_s4"), "the chip is not Trained");

    // Full screen, then back: still at z4 on that task.
    chip("UI tested task renamed").click();
    await atZoom(4);
    await waitFor(() => panelTask() === "UI tested task renamed", "panel");
    $(".o_pan_sl_expand").click();
    await waitFor(() => $(".o_form_view") && !$(".o_pan_sl_map"), "task form full screen");
    (await waitFor(() => $$(".o_breadcrumb a").find((el) => text(el).includes("UI map project")), "breadcrumb to the map")).click();
    await waitFor(() => $(".o_pan_sl_task_panel") && zoom() === 4, "back at z4");

    // The breadcrumb zooms out to the flows.
    $$(".o_pan_sl_crumb").find((el) => text(el) === "Flows").click();
    await atZoom(2);
    expect(!$(".o_pan_sl_chip") && $(".o_pan_sl_flow[aria-current='true']"), "the flow is not marked at z2");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_search_filters_every_level(self):
        """A search filter narrows the bars and the flows; z2 keeps only flows with matching tasks."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    $(".o_pan_sl_zoom_in").click();
    await atZoom(1);
    $(".o_pan_sl_zoom_in").click();
    await atZoom(2);
    $(".o_searchview_dropdown_toggler").click();
    (await waitFor(() => $$(".o_filter_menu .o-dropdown-item, .o_filter_menu .dropdown-item").find((el) => text(el) === "Not decided"), "Not decided filter")).click();
    await waitFor(() => $$(".o_searchview_facet").some((el) => text(el).includes("Not decided")), "facet");
    await waitFor(() => $$(".o_pan_sl_flow").length === 1, "one flow left");
    expect(text($(".o_pan_sl_flow_name")) === "UI late flow", "flow under the filter");
    expect($(".o_pan_sl_project_bar").getAttribute("aria-label") === "2 tasks by step", "project bar: " + $(".o_pan_sl_project_bar").getAttribute("aria-label"));
    // The verdict follows the search: two tasks at Open, nine weeks behind.
    expect(text($(".o_pan_sl_caption_status")) === "Behind · 9 weeks", "verdict under the filter: " + text($(".o_pan_sl_caption_status")));
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_role_unplaced_and_training(self):
        """A role name opens its people and training (and the Still to train list); the
        tasks without a place are one tap away at z2."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    $(".o_pan_sl_zoom_in").click();
    await atZoom(1);
    $(".o_pan_sl_zoom_in").click();
    await atZoom(2);
    const link = $(".o_pan_sl_unplaced");
    expect(link && text(link) === "2 tasks without a place", "unplaced link: " + (link && text(link)));
    link.click();
    const panel = await waitFor(() => $(".o_pan_sl_unplaced_panel"), "panel without a place");
    expect($$(".o_pan_sl_unplaced_panel .o_pan_sl_chip").map(text).join("|") === "UI unplaced task|UI loose task", "tasks without a place");
    panel.querySelector(".o_pan_sl_close").click();
    await waitFor(() => !$(".o_pan_sl_panel"), "panel closed");

    $(".o_pan_sl_zoom_in").click();
    await atZoom(3);
    $$(".o_pan_sl_role").find((el) => text(el) === "UI lane role").click();
    const role = await waitFor(() => $(".o_pan_sl_role_panel"), "role panel");
    expect($$(".o_pan_sl_role_people li").map(text).join("|") === "UI person", "role people");
    const training = $$(".o_pan_sl_role_training li").map(text).sort().join("|");
    expect(training === "UI lone task|UI open task|UI tested task", "to train on: " + training);
    expect(text(role.querySelector(".o_pan_sl_role_adkar")) === "Needs three scored people", "role ADKAR");
    role.querySelector(".o_pan_sl_training").click();
    await waitFor(() => $(".o_list_view") && text($(".o_breadcrumb")).includes("Still to train"), "still to train list");
    const rows = await waitFor(() => $$(".o_data_row").length === 3 && $$(".o_data_row"), "expanded group rows");
    const people = rows[0].querySelector("td.o_pan_sl_wrap");
    expect(people && text(people) === "UI person" && getComputedStyle(people).whiteSpace === "normal", "people do not wrap");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_no_dates_no_burnup(self):
        """Without start and target dates z1 has no chart and keeps the milestone verdict."""
        self.project.write({"date_start": False, "date": False})
        code = WAIT_JS + """
(async () => {
    await openMap();
    $(".o_pan_sl_zoom_in").click();
    await atZoom(1);
    expect(layers() === "caption,legend,projectBar,systems", "z1 layers: " + layers());
    expect(text($(".o_pan_sl_caption_status")) === "At risk (1 flow late)", "verdict: " + text($(".o_pan_sl_caption_status")));
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_managers_hint(self):
        """Without the company page, managers see one muted line; users nothing."""
        self.project.pan_brief = False
        code = WAIT_JS + """
(async () => {
    await openMap();
    await atZoom(0);
    expect(text($(".o_pan_sl_missing")) === "Add the company in one page on the project", "managers' hint");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        manager = new_test_user(
            self.env, login="pan_sl_map_ui_manager", name="Map UI manager", groups="pan_self_learning_blueprint.group_blueprint_manager"
        )
        self.browser_js("/odoo/project", code, login=manager.login)

    def test_project_list(self):
        """Projects > Map is a plain list, also with one project with the map on:
        clicking Map from another project never jumps into this one."""
        self.env["project.project"].create({"name": "UI project without a map"})
        code = WAIT_JS + """
(async () => {
    const menu = await waitFor(
        () => $$(".o_main_navbar .o_menu_sections a, .o_main_navbar .o_menu_sections button").find((el) => text(el) === "Map"),
        "Map in the Projects menu"
    );
    menu.click();
    await waitFor(() => $$(".o_pan_sl_projects .o_pan_sl_project").length, "project list");
    const items = $$(".o_pan_sl_project").map(text);
    expect(items.includes("UI map project") && !items.includes("UI project without a map"), "projects: " + items.join("|"));
    $$(".o_pan_sl_project").find((el) => text(el) === "UI map project").click();
    await waitFor(() => $(".o_pan_sl_headline") && text($(".o_breadcrumb")).includes("UI map project"), "map of the chosen project");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_old_map_link(self):
        """The old map action with a project (2.2 links and buttons) opens that project's Map view."""
        code = WAIT_JS + """
(async () => {
    const env = await waitFor(() => odoo.__WOWL_DEBUG__?.root?.env, "web client");
    await env.services.action.doAction({ type: "ir.actions.client", tag: "pan_sl_blueprint_map", params: { project_id: %(project)s } });
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_frame"), "the map from an old link");
    expect($(".o_switch_view.o_pan_blueprint.active"), "not the Map view");
    console.log("test successful");
})().catch((error) => console.error(error.message));
""" % {"project": self.project.id}
        self.browser_js("/odoo/project", code, login=self.user.login)
