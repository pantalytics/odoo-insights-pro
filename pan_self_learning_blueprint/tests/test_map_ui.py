"""The map in a real browser (Blueprint 2.3, docs/ux-test-2026-11-11.md).

One project with five progress stages (Open to Trained), two phases, an
internal and an external role, a late flow (a third tested, late a day) with
two open subtasks, one of them without a place, a finished flow (its one task
Trained), a task outside any flow, a loose task without a place and two milestones (one
reached). The map, the "Map" view of the project's tasks, is opened from the
Projects menu and used the way a person uses it: read the overview band, tap
an answer, a flow (its swimlane with arrows), a chip, a role name and the
tasks without a place. ``tools/ui_check.mjs`` covers the iPad and phone.
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
const chips = () => $$(".o_pan_sl_chip").map(text).sort().join("|");
const answer = (key) => $(".o_pan_sl_answer_" + key);
const answerText = (key) => lines(answer(key));
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
        cls.project.allow_milestones = True
        today = fields.Date.today()
        cls.env["project.milestone"].create(
            [
                {"name": "UI kickoff", "project_id": cls.project.id, "deadline": today - timedelta(days=30), "is_reached": True},
                {"name": "UI go-live", "project_id": cls.project.id, "deadline": today + timedelta(days=10)},
            ]
        )
        cls.role, cls.external, cls.phase_one, cls.phase_two, cls.stage = role, external, phase_one, phase_two, stage

    def test_overview_and_flows(self):
        """Menu > Map opens the project's tasks in the Map view: five answers on
        top, flows worst first, the plain grid."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    expect($(".o_switch_view.o_pan_blueprint.active"), "Map is not the active view in the switcher");
    expect($(".o_switch_view.o_kanban") && $(".o_switch_view.o_list"), "Kanban and List are not next to Map");
    expect($(".o_pan_sl_map .o_searchview"), "no search bar");

    // Five plain answers over the tasks.
    expect($$(".o_pan_sl_answer_label").map(text).join("|") === "On schedule?|Still to do|Flows|Training|Choices", "answers");
    const schedule = answerText("schedule");
    expect(/^On schedule\\? \\/ UI go-live \\/ Due .+ · At risk \\/ 1 flow late$/.test(schedule), "schedule: " + schedule);
    expect(answerText("todo") === "Still to do / 4 open tasks / 3 without an owner", "todo: " + answerText("todo"));
    expect(answerText("flows") === "Flows / 1 of 2 flows tested / Worst: UI late flow", "flows: " + answerText("flows"));
    expect(answerText("training") === "Training / 0 of 3 tasks trained / 1 person still to train", "training: " + answerText("training"));
    expect(answerText("choices") === "Choices / 4 of 6 tasks decided / 2 still open", "choices: " + answerText("choices"));

    // Worst first, as the server sorts them: the late flow (33%) above the finished one.
    expect(text($(".o_pan_sl_flow_summary")) === "1 of 2 flows late", "summary: " + text($(".o_pan_sl_flow_summary")));
    const flows = $$(".o_pan_sl_flow");
    expect(flows.map((el) => text(el.querySelector(".o_pan_sl_flow_name"))).join("|") === "UI late flow|UI done flow", "flow order");
    expect(text(flows[0]).includes("Tested 33%") && text(flows[0]).includes("2 open"), "late flow: " + text(flows[0]));
    expect(text(flows[0].querySelector(".o_pan_sl_late")) === "Late · 1 day", "late label: " + text(flows[0]));
    expect(/^Due (\\d{1,2} \\S+|\\S+ \\d{1,2})$/.test(text(flows[0].querySelector(".o_pan_sl_due"))), "due: " + text(flows[0]));
    expect(text(flows[1]).includes("Tested 100%") && !flows[1].querySelector(".o_pan_sl_late"), "done flow: " + text(flows[1]));
    expect(!flows[1].querySelector(".o_pan_sl_flow_open"), "a done flow shows no open count");

    // Four colours with the stage words.
    expect($$(".o_pan_sl_legend li").map(text).join("|") === "Open|Decided or Built|Tested|Trained or Live", "legend");

    // Grid: placed tasks only, each with a dot in its progress colour; no breadcrumb on the whole map.
    expect(!$(".o_pan_sl_crumbs"), "a breadcrumb on the whole map");
    expect($$(".o_pan_sl_phase").map(text).join("|") === "UI phase one|UI phase two", "phase columns");
    expect($$(".o_pan_sl_role").map(text).join("|") === "UI lane role|UI customer", "role rows");
    expect(chips() === "UI customer task|UI lone task|UI open task|UI tested task", "chips: " + chips());
    expect(!$(".o_pan_sl_arrow"), "arrows on the whole map");
    expect(chip("UI tested task").querySelector(".o_pan_sl_tone_ok"), "a tested task is not green");
    expect(chip("UI lone task").querySelector(".o_pan_sl_tone_warn"), "a decided task is not amber");
    expect(chip("UI open task").querySelector(".o_pan_sl_tone_off"), "an open task is not grey");
    expect(chip("UI customer task").querySelector(".o_pan_sl_tone_done"), "a trained task is not dark green");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_search_filters_the_map(self):
        """The standard search bar filters the chips and the answers; an answer
        that is a filter shows as a facet; the switcher goes to Kanban and back."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    // "Choices" filters on the tasks still Open: a facet, fewer chips, answers over those tasks.
    answer("choices").click();
    await waitFor(() => $$(".o_searchview_facet").some((el) => text(el).includes("Not decided")), "Not decided facet");
    await waitFor(() => chips() === "UI open task", "chips after Not decided: " + chips());
    await waitFor(() => answerText("choices") === "Choices / 0 of 2 tasks decided / 2 still open", "choices after the filter");
    expect(answer("choices").getAttribute("aria-pressed") === "true", "the answer is not marked as a filter");
    // Under a filter only the rows and columns with a matching task.
    expect($$(".o_pan_sl_phase").map(text).join("|") === "UI phase one", "columns under a filter: " + $$(".o_pan_sl_phase").map(text).join("|"));
    expect($$(".o_pan_sl_role").map(text).join("|") === "UI lane role", "rows under a filter");
    expect(getComputedStyle(answer("choices")).cursor === "pointer" && answer("choices").querySelector(".o_pan_sl_answer_chevron"), "the answer does not look tappable");
    expect(answerText("flows") === "Flows / 0 of 1 flows tested / Worst: UI late flow", "flows after the filter: " + answerText("flows"));
    answer("choices").click();
    await waitFor(() => !$(".o_searchview_facet") && $$(".o_pan_sl_chip").length === 4, "filter removed");

    // "Still to do" is the filter of the same name.
    answer("todo").click();
    await waitFor(() => $$(".o_searchview_facet").some((el) => text(el).includes("Still to do")), "Still to do facet");
    await waitFor(() => chips() === "UI lone task|UI open task", "chips after Still to do: " + chips());
    await waitFor(() => answerText("todo") === "Still to do / 4 open tasks / 3 without an owner", "todo after the filter");

    // Any search: the progress step is searchable ("test" offers it), then a task name.
    $(".o_searchview_facet .o_facet_remove").click();
    await waitFor(() => $$(".o_pan_sl_chip").length === 4, "facet removed");
    const input = $(".o_searchview_input");
    input.value = "UI lone";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 300));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await waitFor(() => chips() === "UI lone task", "chips after a search: " + chips());
    await waitFor(() => answerText("choices") === "Choices / 1 of 1 tasks decided / 0 still open", "choices after a search");
    input.value = "test";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor(
        () => $$(".o_searchview_autocomplete, .o-dropdown--menu").some((el) => /Search Progress step for: test/i.test(text(el))),
        "Progress step offered for 'test'"
    );
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    // The view switcher: Kanban and back to Map.
    $(".o_switch_view.o_kanban").click();
    await waitFor(() => $(".o_kanban_view"), "kanban");
    $(".o_switch_view.o_pan_blueprint").click();
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_body"), "back on the map");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_flow_swimlane(self):
        """A flow opens as a swimlane: only its tasks, a column per step,
        joined by N-1 arrows in task order, left to right; all its steps listed under it; the breadcrumb
        "Map" goes back. The chip panel works there too."""
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
    const flow = $$(".o_pan_sl_flow").find((el) => text(el.querySelector(".o_pan_sl_flow_name")) === "UI late flow");
    flow.click();
    await waitFor(() => text($(".o_pan_sl_status")) === "Showing flow UI late flow, 3 open tasks", "announcement");
    expect(flow.getAttribute("aria-pressed") === "true", "the flow is not marked as selected");
    expect(lines($(".o_pan_sl_crumbs")) === "Map / › / UI late flow", "breadcrumb: " + lines($(".o_pan_sl_crumbs")));

    // Only the flow's placed tasks, in their role x phase cells.
    expect(chips() === "UI customer step|UI open task|UI tested task", "chips: " + chips());
    expect($$(".o_pan_sl_role").map(text).join("|") === "UI lane role|UI customer", "rows");
    const arrows = await waitFor(() => $$(".o_pan_sl_arrow").length === 2 && $$(".o_pan_sl_arrow"), "two arrows");
    const ids = { tested: chip("UI tested task").dataset.taskId, open: chip("UI open task").dataset.taskId, step: chip("UI customer step").dataset.taskId };
    const pairs = arrows.map((path) => path.dataset.from + ">" + path.dataset.to).join("|");
    expect(pairs === ids.tested + ">" + ids.open + "|" + ids.open + ">" + ids.step, "arrow order: " + pairs);
    expect(arrows.every((path) => path.getAttribute("marker-end") && /^M[\\d.]+,[\\d.]+ /.test(path.getAttribute("d"))), "arrow paths");

    // As in the client's charts: a column per step, the phase above it (adjacent steps merged);
    // arrows run left to right, straight within a role, an elbow when the role changes.
    const headers = $$(".o_pan_sl_phase").map((el) => text(el) + ":" + (el.style.gridColumn || "1"));
    expect(headers.join("|") === "UI phase one:span 2|UI phase two:1", "step headers: " + headers.join("|"));
    expect($$(".o_pan_sl_role")[0].parentElement.querySelectorAll(".o_pan_sl_cell").length === 6, "not one cell per step and role");
    const ends = arrows.map((path) => {
        const points = path.getAttribute("d").match(/-?[\\d.]+,-?[\\d.]+/g).map((pair) => pair.split(",").map(Number));
        return { first: points[0], last: points.at(-1) };
    });
    expect(ends.every(({ first, last }) => last[0] > first[0]), "an arrow runs right to left");
    expect(ends[0].first[1] === ends[0].last[1], "the step within one role is not a straight arrow");
    expect(ends[1].first[1] !== ends[1].last[1], "the step to another role is not an elbow");

    // The arrow ends at the target chip, also after the grid scrolls.
    const end = (path) => {
        const length = path.getTotalLength();
        const point = path.getPointAtLength(length);
        const svg = path.ownerSVGElement.getBoundingClientRect();
        return { x: svg.left + point.x, y: svg.top + point.y };
    };
    const near = (point, el) => {
        const rect = el.getBoundingClientRect();
        return point.x >= rect.left - 3 && point.x <= rect.right + 3 && point.y >= rect.top - 3 && point.y <= rect.bottom + 3;
    };
    expect(near(end(arrows[1]), chip("UI customer step")), "the second arrow does not end at its chip");

    // Its open tasks (also those without a place) listed right under it.
    const listed = $$(".o_pan_sl_flows .o_pan_sl_open_task").map(lines);
    expect(
        listed.join("|") ===
            "UI tested task / UI stage 3 (Tested) / No owner / 0:00 spent of 4:00 planned|UI open task / Map UI user / 0:00 spent of 0:00 planned|UI unplaced task / No owner / 0:00 spent of 0:00 planned|UI customer step / No owner / 0:00 spent of 0:00 planned",
        "steps: " + listed.join("|")
    );
    expect($(".o_pan_sl_flows .o_pan_sl_open_task").classList.contains("o_pan_sl_step_done"), "a tested step is not muted");
    expect(flow.nextElementSibling.matches(".o_pan_sl_open_tasks"), "the open tasks are not right under the flow");

    // The chip panel at the flow level.
    chip("UI tested task").click();
    const panel = await waitFor(() => $(".o_pan_sl_task_panel"), "task panel at the flow level");
    expect(text(panel.querySelector(".o_pan_sl_panel_title")) === "UI tested task", "panel title");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await waitFor(() => !$(".o_pan_sl_panel"), "panel closed");

    // Back from a task form: the flow is still open, highlighted and in view.
    chip("UI open task").click();
    (await waitFor(() => $(".o_pan_sl_task_panel .btn-primary"), "Open task")).click();
    await waitFor(() => $(".o_form_view"), "task form");
    (await waitFor(() => $$(".o_breadcrumb a").find((el) => text(el).includes("UI map project")), "breadcrumb to the map")).click();
    await waitFor(() => $(".o_pan_sl_crumbs") && $(".o_pan_sl_flow[aria-pressed='true']"), "flow kept after the form");
    const kept = $(".o_pan_sl_flow[aria-pressed='true']").getBoundingClientRect();
    const list = $(".o_pan_sl_flows").getBoundingClientRect();
    expect(kept.top >= list.top - 1 && kept.top < list.bottom, "the flow is out of view after the form");

    // Breadcrumb back to the whole map.
    $(".o_pan_sl_crumb").click();
    await waitFor(() => $$(".o_pan_sl_chip").length === 5 && !$(".o_pan_sl_arrow") && !$(".o_pan_sl_crumbs"), "back on the whole map");
    expect(!$(".o_pan_sl_flows .o_pan_sl_open_task"), "the flow is still open");

    // The "Flows" answer opens the worst flow; tapping the flow again goes back.
    answer("flows").click();
    await waitFor(() => $$(".o_pan_sl_arrow").length === 2, "worst flow from the answer");
    $$(".o_pan_sl_flow")[0].click();
    await waitFor(() => !$(".o_pan_sl_crumbs"), "second tap back on the map");
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

    // Task panel: the facts, the first line, one primary button in the map.
    chip("UI tested task").click();
    const panel = await waitFor(() => $(".o_pan_sl_task_panel"), "task panel");
    expect(!$(".o_pan_sl_role_panel"), "two panels open");
    expect(text(panel.querySelector(".o_pan_sl_panel_title")) === "UI tested task", "panel title");
    const facts = Object.fromEntries($$(".o_pan_sl_facts dt").map((dt) => [text(dt), text(dt.nextElementSibling)]));
    const want = { Flow: "UI late flow", Role: "UI lane role", Phase: "UI phase one", Progress: "UI stage 3 (Tested)", Owners: "No owner", Hours: "0:00 spent of 4:00 planned" };
    for (const [key, value] of Object.entries(want)) {
        expect(facts[key] === value, key + " reads " + facts[key]);
    }
    expect(text(panel.querySelector(".o_pan_sl_description")) === "First line of the UI task", "description");
    const primary = $$(".o_pan_sl_map .o_content .btn-primary");
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

    // The panel docks beside the chart; one tap moves a task to the next stage.
    chip("UI tested task").click();
    const docked = (await waitFor(() => $(".o_pan_sl_task_panel"), "panel")).getBoundingClientRect();
    expect(docked.left >= $(".o_pan_sl_grid_wrap").getBoundingClientRect().right - 1, "the panel covers the chart");
    expect($(".o_pan_sl_close").getBoundingClientRect().height >= 44, "close button under 44 px");
    const move = $(".o_pan_sl_move");
    expect(move && text(move) === "Move to UI stage 4", "move button: " + (move && text(move)));
    move.click();
    await waitFor(() => chip("UI tested task").querySelector(".o_pan_sl_tone_done"), "the chip is not Trained after the move");
    const moved = $$(".o_pan_sl_facts dt").find((dt) => text(dt) === "Progress").nextElementSibling;
    expect(text(moved) === "UI stage 4 (Trained)", "progress after the move: " + text(moved));
    expect(!$(".o_pan_sl_move"), "a move past the last stage is offered");
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
    expect(!$(".o_pan_sl_crumbs"), "the map opened on a flow");
    expect(content.scrollHeight <= content.clientHeight + 1, "the page scrolls; the grid should scroll on its own");

    // A chip at the bottom of a tall grid.
    const last = chip("UI tall task 11");
    last.scrollIntoView({ block: "end" });
    await new Promise((resolve) => setTimeout(resolve, 100));
    last.click();
    const panel = await waitFor(() => $(".o_pan_sl_task_panel"), "task panel from a low chip");
    expect(text(panel.querySelector(".o_pan_sl_panel_title")) === "UI tall task 11", "panel title");
    expect(inView(panel), "the panel opened out of view");

    // From the side list first, then the same task in the grid (the flow's swimlane): the panel stays open.
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
    $(".o_pan_sl_crumb").click();
    await waitFor(() => !$(".o_pan_sl_crumbs"), "back on the whole map");
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
        """The tasks without a place are one tap away; the Training answer opens the training list."""
        code = WAIT_JS + """
(async () => {
    await openMap();
    const link = $(".o_pan_sl_unplaced");
    expect(link && text(link) === "2 tasks without a place", "unplaced link: " + (link && text(link)));
    link.click();
    await waitFor(() => $(".o_pan_sl_flow_unplaced"), "pseudo-filter in the side list");
    const listed = $$(".o_pan_sl_flows .o_pan_sl_open_task").map(lines);
    expect(listed.join("|") === "UI unplaced task / No owner / 0:00 spent of 0:00 planned|UI loose task / No owner / 0:00 spent of 0:00 planned", "without a place: " + listed.join("|"));
    expect(text($(".o_pan_sl_status")) === "Showing 2 tasks without a place", "announcement");
    expect($$(".o_pan_sl_chip").length === 4, "the grid changed");
    link.click();
    await waitFor(() => !$(".o_pan_sl_flow_unplaced"), "pseudo-filter cleared");

    // "Training": tasks of internal roles; tap opens "Still to train" (the customer's are left out).
    answer("training").click();
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

    def test_schedule_opens_milestones(self):
        """"On schedule?" says how late the next milestone is and opens the project's milestones."""
        self.env["project.milestone"].search([("name", "=", "UI go-live")]).deadline = fields.Date.today() - timedelta(days=3)
        code = WAIT_JS + """
(async () => {
    await openMap();
    const schedule = answerText("schedule");
    expect(/^On schedule\\? \\/ UI go-live \\/ Due .+ · Late · 3 days \\/ 1 flow late$/.test(schedule), "schedule: " + schedule);
    expect(answer("schedule").querySelector(".o_pan_sl_status_late .o_pan_sl_tone_late"), "late is not marked red");
    answer("schedule").click();
    await waitFor(() => $(".o_list_view") && $$(".o_data_row").length === 2, "milestones list");
    expect($$(".o_data_row").map(text).join("|").includes("UI go-live"), "milestones listed");
    console.log("test successful");
})().catch((error) => console.error(error.message));
"""
        self.browser_js("/odoo/project", code, login=self.user.login)

    def test_project_list(self):
        """With several mapped projects, Projects > Map starts with a plain list."""
        other = self.env["project.project"].create({"name": "UI second project"})
        self.env["pan.sl.role"].create({"name": "UI other role", "code": "t_ui_other", "project_id": other.id})
        code = WAIT_JS + """
(async () => {
    const menu = await waitFor(
        () => $$(".o_main_navbar .o_menu_sections a, .o_main_navbar .o_menu_sections button").find((el) => text(el) === "Map"),
        "Map in the Projects menu"
    );
    menu.click();
    await waitFor(() => $$(".o_pan_sl_projects .o_pan_sl_project").length, "project list");
    const items = $$(".o_pan_sl_project").map(text);
    expect(items.includes("UI map project") && items.includes("UI second project"), "projects: " + items.join("|"));
    $$(".o_pan_sl_project").find((el) => text(el) === "UI second project").click();
    await waitFor(() => $(".o_pan_sl_grid_area .o_pan_sl_empty") && !$(".o_pan_sl_chip"), "map of the other project");
    expect(text($(".o_breadcrumb")).includes("UI second project"), "breadcrumb: " + text($(".o_breadcrumb")));
    $$(".o_breadcrumb a, .o_breadcrumb .o_back_button").find((el) => text(el) === "Map")?.click();
    await waitFor(() => $(".o_pan_sl_projects"), "back to the list");
    $$(".o_pan_sl_project").find((el) => text(el) === "UI map project").click();
    await waitFor(() => $$(".o_pan_sl_chip").length === 4, "map of the chosen project");
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
    await waitFor(() => $(".o_pan_sl_map .o_pan_sl_body"), "the map from an old link");
    expect($(".o_switch_view.o_pan_blueprint.active"), "not the Map view");
    expect($$(".o_pan_sl_chip").length === 4, "chips");
    console.log("test successful");
})().catch((error) => console.error(error.message));
""" % {"project": self.project.id}
        self.browser_js("/odoo/project", code, login=self.user.login)
