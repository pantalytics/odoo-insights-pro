import { Component, onMounted, onPatched, onWillStart, onWillUnmount, onWillUpdateProps, useExternalListener, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { deserializeDate, today } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { formatFloatTime } from "@web/views/fields/formatters";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";

// The map of one project as a view type on project.task (Blueprint 2.3,
// docs/ux-test-2026-11-11.md). Odoo's search bar filters the tasks; on top an
// overview band answers five questions; below, the flows (worst first) and a
// plain grid of phases (columns) by roles (rows) with a chip per task.
// Clicking a flow shows it as a swimlane: only its tasks, joined by arrows in
// task order, like the client's swimlane charts.

export const MAP_VIEW_TYPE = "pan_blueprint";
const USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user";
const FLOW_KEY = "pan_sl_blueprint_map:flow:";
const DECIDED_RUNG = 1;
const TESTED_RUNG = 3;
const TRAINED_RUNG = 4;
export const UNPLACED = "unplaced";
export const PROGRESS_WORDS = [_t("Open"), _t("Decided"), _t("Built"), _t("Tested"), _t("Trained"), _t("Live")];
const ADKAR_WORDS = { low: _t("Low"), medium: _t("Medium"), high: _t("High") };

/** Four colours named after the stages: grey Open, amber Decided or Built,
 * green Tested, dark green Trained or Live. */
export function tone(rung) {
    if (rung >= TRAINED_RUNG) {
        return "done";
    }
    if (rung >= TESTED_RUNG) {
        return "ok";
    }
    return rung > 0 ? "warn" : "off";
}

const isPlaced = (task) => Boolean(task.role_id && task.phase_id);

/** The flow last opened on this project, for this browser tab. */
function rememberedFlow(projectId, value) {
    try {
        const key = FLOW_KEY + projectId;
        if (value === undefined) {
            return JSON.parse(browser.sessionStorage.getItem(key) || "false");
        }
        browser.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
        // Private mode or blocked storage: the map works without memory.
    }
    return false;
}

/**
 * An SVG path from box ``a`` to box ``b`` (x, y, w, h in the grid's own
 * coordinates), as in a swimlane chart: out of the side facing the target,
 * straight lines with rounded corners, the turn just before the target so
 * the line runs in the gap between columns (or rows). Within one column, a
 * step that skips other chips (``others``) goes round them on the right, in
 * its own ``lane``, instead of through them.
 */
export function arrowPath(a, b, others = [], lane = 0) {
    const round = (value) => Math.round(value * 10) / 10;
    const elbow = (x1, y1, x2, y2, horizontal) => {
        const [p1, q1, p2, q2] = horizontal ? [x1, y1, x2, y2] : [y1, x1, y2, x2];
        const along = Math.sign(p2 - p1) || 1;
        const across = Math.sign(q2 - q1);
        const turn = p2 - along * Math.min(16, Math.abs(p2 - p1) / 2);
        const radius = Math.min(8, Math.abs(q2 - q1) / 2, Math.abs(turn - p1));
        const point = (p, q) => (horizontal ? `${round(p)},${round(q)}` : `${round(q)},${round(p)}`);
        if (!across || radius < 1) {
            return across ? `M${point(p1, q1)} L${point(turn, q1)} L${point(turn, q2)} L${point(p2, q2)}` : `M${point(p1, q1)} L${point(p2, q2)}`;
        }
        return [
            `M${point(p1, q1)}`,
            `L${point(turn - along * radius, q1)}`,
            `Q${point(turn, q1)} ${point(turn, q1 + across * radius)}`,
            `L${point(turn, q2 - across * radius)}`,
            `Q${point(turn, q2)} ${point(turn + along * radius, q2)}`,
            `L${point(p2, q2)}`,
        ].join(" ");
    };
    const gap = 8;
    if (b.x >= a.x + a.w + gap) {
        return elbow(a.x + a.w, a.y + a.h / 2, b.x, b.y + b.h / 2, true);
    }
    if (b.x + b.w <= a.x - gap) {
        return elbow(a.x, a.y + a.h / 2, b.x + b.w, b.y + b.h / 2, true);
    }
    const [top, bottom] = b.y >= a.y ? [a.y + a.h, b.y] : [b.y + b.h, a.y];
    const between = others.some(
        (box) => box.x < Math.max(a.x + a.w, b.x + b.w) && box.x + box.w > Math.min(a.x, b.x) && box.y >= top - 1 && box.y + box.h <= bottom + 1
    );
    if (between) {
        const x1 = a.x + a.w;
        const x2 = b.x + b.w;
        const y1 = round(a.y + a.h / 2);
        const y2 = round(b.y + b.h / 2);
        const side = round(Math.max(x1, x2) + 10 + 7 * (lane % 3));
        const r = Math.min(6, Math.abs(y2 - y1) / 2);
        const dy = Math.sign(y2 - y1);
        return [
            `M${round(x1)},${y1}`,
            `L${side - r},${y1}`,
            `Q${side},${y1} ${side},${y1 + dy * r}`,
            `L${side},${y2 - dy * r}`,
            `Q${side},${y2} ${side - r},${y2}`,
            `L${round(x2)},${y2}`,
        ].join(" ");
    }
    if (b.y >= a.y + a.h) {
        return elbow(a.x + a.w / 2, a.y + a.h, b.x + b.w / 2, b.y, false);
    }
    return elbow(a.x + a.w / 2, a.y, b.x + b.w / 2, b.y + b.h, false);
}

let markerCount = 0;

export class BlueprintMapController extends Component {
    static template = "pan_self_learning_blueprint.MapView";
    static props = { ...standardViewProps };
    static components = { Layout, SearchBar };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        const restored = this.props.state?.blueprintMap || {};
        this.state = useState({
            allowed: true,
            data: null,
            flowId: restored.flowId || false,
            selected: null, // { type: "task" | "role", id }
        });
        this.arrows = useState({ width: 0, height: 0, paths: [] });
        this.markerId = `o_pan_sl_arrow_${++markerCount}`;
        this.tones = [
            { tone: "off", label: _t("Open") },
            { tone: "warn", label: _t("Decided or Built") },
            { tone: "ok", label: _t("Tested") },
            { tone: "done", label: _t("Trained or Live") },
        ];
        this.root = useRef("root");
        this.gridArea = useRef("gridArea");
        this.grid = useRef("grid");
        this.searchBarToggler = useSearchBarToggler();
        this.scrollFlowIntoView = Boolean(restored.flowId);
        this.fade = useState({ right: false });
        this.resizeObserver = new ResizeObserver(() => this.redraw());
        useExternalListener(window, "resize", () => this.redraw());
        onMounted(() => {
            this.redraw();
            if (this.scrollFlowIntoView) {
                this.scrollFlowIntoView = false;
                this.root.el?.querySelector(".o_pan_sl_flow[aria-pressed='true']")?.scrollIntoView({ block: "start" });
            }
        });
        onPatched(() => {
            this.redraw();
            if (this.scrollFlowIntoView) {
                this.scrollFlowIntoView = false;
                this.root.el?.querySelector(".o_pan_sl_flow[aria-pressed='true']")?.scrollIntoView({ block: "start" });
            }
        });
        onWillUnmount(() => this.resizeObserver.disconnect());
        useSetupAction({
            rootRef: this.root,
            getLocalState: () => ({ blueprintMap: { flowId: this.state.flowId } }),
        });
        useHotkey("escape", () => (this.state.selected = null), {
            bypassEditableProtection: true,
            isAvailable: () => Boolean(this.state.selected),
        });
        onWillStart(async () => {
            this.state.allowed = await user.hasGroup(USER_GROUP);
            if (this.state.allowed && this.projectId) {
                await this.load(this.props, restored.flowId ?? rememberedFlow(this.projectId));
            }
        });
        onWillUpdateProps(async (next) => {
            if (this.state.allowed && this.projectId) {
                await this.load(next, this.state.flowId);
            }
        });
    }

    /** The project comes from the action, as for the other task views of a project. */
    get projectId() {
        const { context } = this.props;
        return context.default_project_id || (context.active_model === "project.project" && context.active_id) || false;
    }

    async load(props, flowId) {
        const order = props.orderBy.map((item) => `${item.name} ${item.asc ? "ASC" : "DESC"}`).join(", ");
        const data = await this.orm.call("project.project", "get_blueprint_map_data", [[this.projectId]], {
            domain: props.domain,
            order: order || null,
        });
        const known = flowId === UNPLACED || data.flows.some((flow) => flow.id === flowId);
        Object.assign(this.state, { data, flowId: known ? flowId : false });
        if (this.state.selected?.type === "task" && !data.tasks.some((task) => task.id === this.state.selected.id)) {
            this.state.selected = null;
        }
    }

    // ------------------------------------------------------------------
    // Derived data
    // ------------------------------------------------------------------

    get tasksById() {
        return Object.fromEntries(this.state.data.tasks.map((task) => [task.id, task]));
    }

    get unplaced() {
        return this.state.data.tasks.filter((task) => !isPlaced(task));
    }

    get selectedFlow() {
        return this.state.data.flows.find((flow) => flow.id === this.state.flowId);
    }

    /** At the flow level, the swimlane of one flow; otherwise the whole map. */
    get isFlowLevel() {
        return Boolean(this.selectedFlow);
    }

    /** The placed tasks on the grid: all of them, or the selected flow's in task order. */
    get gridTasks() {
        const placed = this.state.data.tasks.filter(isPlaced);
        if (!this.isFlowLevel) {
            return placed;
        }
        const byId = Object.fromEntries(placed.map((task) => [task.id, task]));
        return this.selectedFlow.task_ids.map((id) => byId[id]).filter(Boolean);
    }

    /**
     * The grid columns. On the whole map: the phases, a cell per role and
     * phase. At the flow level, as in the client's swimlane charts: one
     * column per step (task) of the flow, left to right in task order, so
     * every arrow runs to the right.
     */
    get columns() {
        if (!this.isFlowLevel) {
            return this.phases.map((phase) => ({ key: `phase-${phase.id}`, match: (task) => task.phase_id === phase.id }));
        }
        return this.gridTasks.map((step) => ({ key: `step-${step.id}`, match: (task) => task.id === step.id }));
    }

    /** All phases; under a search only those with a matching task, so a filter shrinks the grid. */
    get phases() {
        const { phases } = this.state.data;
        if (!this.env.searchModel?.facets?.length) {
            return phases;
        }
        const used = new Set(this.gridTasks.map((task) => task.phase_id));
        return phases.filter((phase) => used.has(phase.id));
    }

    /** Column headers: the phases; at the flow level the phase of each step, adjacent steps of one phase merged. */
    get headers() {
        const { phases } = this.state.data;
        if (!this.isFlowLevel) {
            return this.phases.map((phase) => ({ key: phase.id, name: phase.name, span: 1 }));
        }
        const headers = [];
        for (const task of this.gridTasks) {
            const last = headers.at(-1);
            if (last && last.phaseId === task.phase_id) {
                last.span++;
            } else {
                const phase = phases.find((item) => item.id === task.phase_id);
                headers.push({ key: `step-${task.id}`, phaseId: task.phase_id, name: phase?.name || "", span: 1 });
            }
        }
        return headers;
    }

    /** Internal roles first, external at the bottom; only roles with a task on the grid. */
    get rows() {
        const { roles } = this.state.data;
        const tasks = this.gridTasks;
        const columns = this.columns;
        const ordered = [...roles.filter((role) => !role.is_external), ...roles.filter((role) => role.is_external)];
        return ordered
            .map((role) => ({
                role,
                cells: columns.map((column) => ({
                    key: column.key,
                    tasks: tasks.filter((task) => task.role_id === role.id && column.match(task)),
                })),
            }))
            .filter((row) => row.cells.some((cell) => cell.tasks.length));
    }

    get gridStyle() {
        const width = this.isFlowLevel ? "minmax(9rem, 11rem)" : "minmax(9rem, 1fr)";
        return `grid-template-columns: minmax(8.5rem, 10rem) repeat(${this.columns.length}, ${width})`;
    }

    /** Every step of the selected flow in task order (as in its chart), or every task without a place. */
    get listedTasks() {
        if (this.state.flowId === UNPLACED) {
            return this.unplaced;
        }
        const byId = this.tasksById;
        return (this.selectedFlow?.task_ids || []).map((id) => byId[id]).filter(Boolean);
    }

    /** A step at Tested or further: muted in the list, with its stage word. */
    isDone(task) {
        return task.rung >= TESTED_RUNG;
    }

    get announcement() {
        if (this.state.flowId === UNPLACED) {
            return _t("Showing %s tasks without a place", this.unplaced.length);
        }
        const open = this.listedTasks.filter((task) => !this.isDone(task)).length;
        return this.selectedFlow ? _t("Showing flow %(flow)s, %(count)s open tasks", { flow: this.selectedFlow.name, count: open }) : "";
    }

    /** "3 of 10 flows late" */
    get flowSummary() {
        const { flows } = this.state.data;
        return _t("%(late)s of %(total)s flows late", { late: flows.filter((flow) => flow.late).length, total: flows.length });
    }

    /** "6 Nov", day and month in the user's language. */
    dayMonth(date) {
        return deserializeDate(date).toLocaleString({ day: "numeric", month: "short" });
    }

    /** "Due 6 Nov" */
    deadline(flow) {
        return flow.deadline ? _t("Due %s", this.dayMonth(flow.deadline)) : "";
    }

    lateDays(days) {
        return days === 1 ? _t("Late · 1 day") : _t("Late · %s days", days);
    }

    lateLabel(flow) {
        return this.lateDays(flow.days_late);
    }

    openLabel(flow) {
        return _t("%s open", flow.open_count);
    }

    /** "0:00 spent of 5:00 planned" */
    hours(task) {
        const clock = (hours) => formatFloatTime(hours).replace(/^0(?=\d:)/, "");
        return _t("%(spent)s spent of %(planned)s planned", { spent: clock(task.spent_hours), planned: clock(task.planned_hours) });
    }

    // ------------------------------------------------------------------
    // Overview band: five plain answers over the tasks of the search
    // ------------------------------------------------------------------

    get overview() {
        const { tasks, flows, roles, milestones } = this.state.data;
        const count = (list, check) => list.filter(check).length;
        const open = tasks.filter((task) => task.rung < TESTED_RUNG);
        const internal = new Set(roles.filter((role) => !role.is_external).map((role) => role.id));
        const trainable = tasks.filter((task) => internal.has(task.role_id));
        const people = new Set(
            roles.filter((role) => internal.has(role.id) && role.open_training_task_ids.length).flatMap((role) => role.people)
        );
        return [
            { key: "schedule", label: _t("On schedule?"), ...this.schedule(milestones, flows) },
            {
                key: "todo",
                label: _t("Still to do"),
                value: open.length === 1 ? _t("1 open task") : _t("%s open tasks", open.length),
                detail: _t("%s without an owner", count(open, (task) => !task.user_names.length)),
                filter: "pan_not_tested",
            },
            {
                key: "flows",
                label: _t("Flows"),
                value: _t("%(done)s of %(total)s flows tested", { done: count(flows, (flow) => flow.progress >= 100), total: flows.length }),
                detail: flows.length ? _t("Worst: %s", flows[0].name) : _t("No flows yet"),
            },
            {
                key: "training",
                label: _t("Training"),
                value: _t("%(done)s of %(total)s tasks trained", { done: count(trainable, (task) => task.rung >= TRAINED_RUNG), total: trainable.length }),
                detail: people.size === 1 ? _t("1 person still to train") : _t("%s people still to train", people.size),
            },
            {
                key: "choices",
                label: _t("Choices"),
                value: _t("%(done)s of %(total)s tasks decided", { done: count(tasks, (task) => task.rung >= DECIDED_RUNG), total: tasks.length }),
                detail: _t("%s still open", count(tasks, (task) => task.rung < DECIDED_RUNG)),
                filter: "pan_not_decided",
            },
        ];
    }

    /**
     * The next milestone not reached and one verdict: "Late · N days" (red)
     * when its date has passed; else "At risk" (amber) when a flow is late;
     * else "On track".
     */
    schedule(milestones, flows) {
        const next = milestones.find((milestone) => !milestone.reached);
        const lateFlows = flows.filter((flow) => flow.late).length;
        const days = next?.deadline ? Math.round(today().diff(deserializeDate(next.deadline), "days").days) : 0;
        let verdict = { word: _t("On track"), tone: "ok" };
        if (days > 0) {
            verdict = { word: this.lateDays(days), tone: "late" };
        } else if (lateFlows) {
            verdict = { word: _t("At risk"), tone: "risk" };
        }
        const value = next ? next.name : milestones.length ? _t("All milestones reached") : _t("No milestones");
        const due = next?.deadline ? `${_t("Due %s", this.dayMonth(next.deadline))} · ` : "";
        return {
            value,
            status: due + verdict.word,
            tone: verdict.tone,
            detail: lateFlows === 1 ? _t("1 flow late") : lateFlows ? _t("%s flows late", lateFlows) : _t("No flows late"),
        };
    }

    searchItem(name) {
        return this.env.searchModel?.getSearchItems((item) => item.name === name)[0];
    }

    isActive(item) {
        return item.filter ? String(Boolean(this.searchItem(item.filter)?.isActive)) : undefined;
    }

    async onOverview(item) {
        if (item.filter) {
            const filter = this.searchItem(item.filter);
            if (filter) {
                this.env.searchModel.toggleSearchItem(filter.id);
            }
        } else if (item.key === "schedule") {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                name: _t("Milestones"),
                res_model: "project.milestone",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: [["project_id", "=", this.projectId]],
                context: { default_project_id: this.projectId },
            });
        } else if (item.key === "flows") {
            const flow = this.state.data.flows[0];
            if (flow) {
                this.openFlow(flow.id);
            }
        } else if (item.key === "training") {
            await this.onTraining();
        }
    }

    // ------------------------------------------------------------------
    // Grid helpers
    // ------------------------------------------------------------------

    owners(task) {
        return task.user_names.length ? task.user_names.join(", ") : _t("No owner");
    }

    toneOf(task) {
        return tone(task.rung);
    }

    chipLabel(task) {
        return `${task.name}, ${PROGRESS_WORDS[task.rung]}`;
    }

    get selectedTask() {
        const { selected } = this.state;
        return selected?.type === "task" ? this.tasksById[selected.id] : null;
    }

    get selectedRole() {
        const { selected, data } = this.state;
        return selected?.type === "role" ? data.roles.find((role) => role.id === selected.id) : null;
    }

    taskFacts(task) {
        const name = (records, id) => records.find((record) => record.id === id)?.name || _t("None");
        const { data } = this.state;
        return [
            [_t("Flow"), name(data.flows, task.flow_id)],
            [_t("Role"), name(data.roles, task.role_id)],
            [_t("Phase"), name(data.phases, task.phase_id)],
            [_t("Progress"), this.progressWord(task)],
            [_t("Owners"), this.owners(task)],
            [_t("Hours"), this.hours(task)],
        ];
    }

    /** The stage, said once: "Built", or "Review (Built)" when the stage has another name. */
    progressWord(task) {
        const word = String(PROGRESS_WORDS[task.rung]); // _t gives a lazy string
        return task.stage && task.stage !== word ? `${task.stage} (${word})` : word;
    }

    /** The project's next stage by sequence with a higher step, or nothing at the end. */
    nextStage(task) {
        const { stages } = this.state.data;
        const index = stages.findIndex((stage) => stage.id === task.stage_id);
        return stages.slice(index + 1).find((stage) => stage.rung > task.rung) || null;
    }

    moveLabel(stage) {
        return _t("Move to %s", stage.name);
    }

    /** One step forward without leaving the map: a normal write with the user's rights, then a refresh. */
    async moveTask(task) {
        const stage = this.nextStage(task);
        if (!stage) {
            return;
        }
        await this.orm.write("project.task", [task.id], { stage_id: stage.id });
        await this.load(this.props, this.state.flowId);
    }

    firstLine(text) {
        return (text || "").trim().split("\n")[0];
    }

    roleTraining(role) {
        const byId = this.tasksById;
        return role.open_training_task_ids.map((id) => byId[id]).filter(Boolean);
    }

    adkarWord(role) {
        return role.adkar ? ADKAR_WORDS[role.adkar] : _t("Needs three scored people");
    }

    // ------------------------------------------------------------------
    // Drawing: the right-edge fade and the flow's arrows
    // ------------------------------------------------------------------

    redraw() {
        this.updateFade();
        const grid = this.grid.el;
        if (grid && grid !== this.observed) {
            this.resizeObserver.disconnect();
            this.resizeObserver.observe(grid);
            this.observed = grid;
        }
        this.updateArrows();
    }

    /** A fade at the right edge while the grid can scroll further right. */
    updateFade() {
        const el = this.gridArea.el;
        const right = Boolean(el) && el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
        if (this.fade.right !== right) {
            this.fade.right = right;
        }
    }

    /**
     * Arrows between the chips of the flow, in task order. Measured with
     * offsets inside the grid (which is the SVG's box too), so they scroll
     * with the grid and ignore the zoom-in animation's transform.
     */
    updateArrows() {
        const grid = this.grid.el;
        let next = { width: 0, height: 0, paths: [] };
        if (grid && this.isFlowLevel) {
            const box = (el) => ({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
            const chips = this.gridTasks.map((task) => grid.querySelector(`.o_pan_sl_chip[data-task-id="${task.id}"]`)).filter(Boolean);
            const boxes = chips.map(box);
            const paths = chips.slice(1).map((chip, index) => ({
                key: `${chips[index].dataset.taskId}-${chip.dataset.taskId}`,
                from: chips[index].dataset.taskId,
                to: chip.dataset.taskId,
                d: arrowPath(boxes[index], boxes[index + 1], boxes.filter((_, other) => other !== index && other !== index + 1), index),
            }));
            next = { width: grid.scrollWidth, height: grid.scrollHeight, paths };
        }
        const same =
            next.width === this.arrows.width &&
            next.height === this.arrows.height &&
            next.paths.map((path) => path.key + path.d).join() === this.arrows.paths.map((path) => path.key + path.d).join();
        if (!same) {
            Object.assign(this.arrows, next);
        }
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    isSelected(type, id) {
        const { selected } = this.state;
        return String(Boolean(selected && selected.type === type && selected.id === id));
    }

    /** A flow opens as a swimlane; tapping it again goes back to the map. */
    toggleFlow(flowId) {
        if (this.state.flowId === flowId) {
            this.backToMap();
        } else {
            this.openFlow(flowId);
        }
    }

    openFlow(flowId) {
        this.state.flowId = flowId;
        this.scrollFlowIntoView = true;
        rememberedFlow(this.projectId, flowId);
        const area = this.gridArea.el;
        if (area) {
            area.scrollTo({ left: 0, top: 0 });
        }
    }

    backToMap() {
        this.state.flowId = false;
        rememberedFlow(this.projectId, false);
    }

    /** Opens the panel of a task or role; a tap never closes it (Close or Esc does). */
    select(type, id) {
        this.state.selected = { type, id };
    }

    async onTraining() {
        const action = await this.orm.call("project.project", "action_blueprint_training", [[this.projectId]]);
        await this.actionService.doAction(action);
    }

    openTask(task) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: task.id,
            views: [[false, "form"]],
        });
    }
}

export const blueprintMapView = {
    type: MAP_VIEW_TYPE,
    multiRecord: true,
    Controller: BlueprintMapController,
    searchMenuTypes: ["filter", "groupBy", "favorite"],
};

registry.category("views").add(MAP_VIEW_TYPE, blueprintMapView);
