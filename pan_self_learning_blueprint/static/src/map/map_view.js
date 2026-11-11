import { Component, markup, onMounted, onPatched, onWillStart, onWillUnmount, onWillUpdateProps, useExternalListener, useRef, useState } from "@odoo/owl";
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

// The map of one project as a view type on project.task (Blueprint 2.3.1,
// docs/ux-test-2026-11-11.md, round 5). It works like a vector map: one stage
// with a continuous zoom from 0 to 4, and every element declares the zoom
// range it appears in (LAYERS), so each level shows only what matters there:
//   z0 Company   the brief's first sentence, keywords, from -> to, timeline
//   z1 Project   the burn-up (progress against the ideal line) and the bar by step
//   z2 Flows     every flow as a bar with a one-line summary and keywords
//   z3 Flow      the swimlane: its tasks by role and step, joined by arrows
//   z4 Task      owner, hours, stage, first line, "Move to <next stage>"
// + and - (44 px), pinch and Ctrl/Cmd + wheel zoom; a plain wheel or swipe
// scrolls. Clicking an element flies to it. Odoo's search bar filters every level.

export const MAP_VIEW_TYPE = "pan_blueprint";
const USER_GROUP = "pan_self_learning_blueprint.group_blueprint_user";
const MANAGER_GROUP = "pan_self_learning_blueprint.group_blueprint_manager";
const MEMORY_KEY = "pan_sl_blueprint_map:zoom:";
const TESTED_RUNG = 3;
const MAX_ZOOM = 4;
const FLY_MS = 220;
const SNAP_MS = 250;
export const PROGRESS_WORDS = [_t("Open"), _t("Decided"), _t("Built"), _t("Tested"), _t("Trained"), _t("Live")];
const ADKAR_WORDS = { low: _t("Low"), medium: _t("Medium"), high: _t("High") };

/** The zoom range of every layer (like minzoom/maxzoom in a vector tile set). */
export const LAYERS = {
    company: { minZoom: 0, maxZoom: 0 },
    systems: { minZoom: 0, maxZoom: 1 },
    timeline: { minZoom: 0, maxZoom: 1 }, // at z1 only without a burn-up, which carries the same axis
    burnup: { minZoom: 1, maxZoom: 1 },
    projectBar: { minZoom: 1, maxZoom: 2 },
    caption: { minZoom: 1, maxZoom: 2 },
    legend: { minZoom: 1, maxZoom: 4 },
    flows: { minZoom: 2, maxZoom: 2 },
    unplaced: { minZoom: 2, maxZoom: 2 },
    steps: { minZoom: 3, maxZoom: 3 },
    swimlane: { minZoom: 3, maxZoom: 4 },
    task: { minZoom: 4, maxZoom: 4 },
};
export const LEVEL_NAMES = [_t("Company"), _t("Project"), _t("Flows")];

/** One colour per step, a sequence from grey (Open) to dark green (Live):
 * the dots, the bars and the legend all use it. */
export function tone(rung) {
    return `s${Math.max(0, Math.min(5, rung || 0))}`;
}

const STEPS = [0, 1, 2, 3, 4, 5];
const isPlaced = (task) => Boolean(task.role_id && task.phase_id);
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

/** Zoom and focus last used on this project, for this browser tab. */
function memory(projectId, value) {
    try {
        const key = MEMORY_KEY + projectId;
        if (value === undefined) {
            return JSON.parse(browser.sessionStorage.getItem(key) || "null") || {};
        }
        browser.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
        // Private mode or blocked storage: the map works without memory.
    }
    return {};
}

function prefersReducedMotion() {
    return Boolean(browser.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/**
 * An SVG path from box ``a`` to box ``b`` (x, y, w, h in the grid's own
 * coordinates), as in a swimlane chart: out of the side facing the target,
 * straight lines with rounded corners, the turn just before the target.
 */
export function arrowPath(a, b) {
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
    if (b.x >= a.x + a.w + 8) {
        return elbow(a.x + a.w, a.y + a.h / 2, b.x, b.y + b.h / 2, true);
    }
    if (b.x + b.w <= a.x - 8) {
        return elbow(a.x, a.y + a.h / 2, b.x + b.w, b.y + b.h / 2, true);
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
        const restored = this.props.state?.blueprintMap;
        this.state = useState({
            allowed: true,
            isManager: false,
            data: null,
            zoom: 0, // continuous, 0..4
            flowId: false, // the flow in focus (z3)
            taskId: false, // the task in focus (z4)
            selected: null, // side panel: { type: "role" | "unplaced", id }
            briefOpen: false,
            origin: "50% 0",
        });
        this.restored = restored;
        this.arrows = useState({ width: 0, height: 0, paths: [] });
        this.markerId = `o_pan_sl_arrow_${++markerCount}`;
        this.tones = STEPS.map((rung) => ({ tone: tone(rung), label: PROGRESS_WORDS[rung] }));
        this.root = useRef("root");
        this.stage = useRef("stage");
        this.gridArea = useRef("gridArea");
        this.grid = useRef("grid");
        this.searchBarToggler = useSearchBarToggler();
        this.fade = useState({ right: false });
        this.flyTarget = null;
        this.pinch = null;
        this.wheelSum = 0;
        this.resizeObserver = new ResizeObserver(() => this.redraw());
        useExternalListener(window, "resize", () => this.redraw());
        onMounted(() => this.afterRender());
        onPatched(() => this.afterRender());
        onWillUnmount(() => {
            this.resizeObserver.disconnect();
            browser.clearTimeout(this.snapTimer);
            browser.cancelAnimationFrame(this.frame);
        });
        useSetupAction({
            rootRef: this.root,
            getLocalState: () => ({ blueprintMap: this.snapshot() }),
        });
        useHotkey(
            "escape",
            () => {
                if (this.state.selected) {
                    this.state.selected = null;
                } else {
                    this.zoomTo(this.level - 1);
                }
            },
            { bypassEditableProtection: true, isAvailable: () => Boolean(this.state.selected) || this.level >= 3 }
        );
        onWillStart(async () => {
            [this.state.allowed, this.state.isManager] = await Promise.all([user.hasGroup(USER_GROUP), user.hasGroup(MANAGER_GROUP)]);
            if (this.state.allowed && this.projectId) {
                const view = restored || memory(this.projectId);
                Object.assign(this.state, { zoom: view.zoom || 0, flowId: view.flowId || false, taskId: view.taskId || false });
                await this.load(this.props);
            }
        });
        onWillUpdateProps(async (next) => {
            if (this.state.allowed && this.projectId) {
                await this.load(next);
            }
        });
    }

    /** The project comes from the action, as for the other task views of a project. */
    get projectId() {
        const { context } = this.props;
        return context.default_project_id || (context.active_model === "project.project" && context.active_id) || false;
    }

    async load(props) {
        const order = props.orderBy.map((item) => `${item.name} ${item.asc ? "ASC" : "DESC"}`).join(", ");
        const data = await this.orm.call("project.project", "get_blueprint_map_data", [[this.projectId]], {
            domain: props.domain,
            order: order || null,
        });
        const flowId = data.flows.some((flow) => flow.id === this.state.flowId) ? this.state.flowId : false;
        const taskId = data.tasks.some((task) => task.id === this.state.taskId) ? this.state.taskId : false;
        Object.assign(this.state, { data, flowId, taskId });
        this.state.zoom = clamp(this.state.zoom, 0, this.maxZoom);
    }

    snapshot() {
        return { zoom: this.level, flowId: this.state.flowId, taskId: this.state.taskId };
    }

    // ------------------------------------------------------------------
    // Zoom: one continuous value, levels of detail at whole numbers
    // ------------------------------------------------------------------

    /** The level of detail shown: the zoom rounded to a whole level. */
    get level() {
        return clamp(Math.round(this.state.zoom), 0, MAX_ZOOM);
    }

    /** z3 needs a flow in focus, z4 a task. */
    get maxZoom() {
        return this.state.taskId ? 4 : this.state.flowId ? 3 : 2;
    }

    /** Whether an element of this layer shows at the current level. */
    show(layer) {
        const { minZoom, maxZoom } = LAYERS[layer];
        return this.level >= minZoom && this.level <= maxZoom;
    }

    /** Between two levels the stage scales a little, like a map between zoom levels. */
    get stageStyle() {
        const scale = clamp(2 ** (this.state.zoom - this.level), 0.85, 1.2);
        return `transform: scale(${scale.toFixed(3)}); transform-origin: ${this.state.origin};`;
    }

    get canZoomIn() {
        return this.level < MAX_ZOOM && (this.level < 2 || this.state.data.flows.length > 0);
    }

    get canZoomOut() {
        return this.level > 0;
    }

    /** Before zooming into z3 or z4, pick what to zoom into: what is under the point, else the obvious one. */
    focusFor(level, point) {
        const under = point && document.elementFromPoint(point.x, point.y);
        if (level >= 3 && !this.state.flowId) {
            const id = Number(under?.closest("[data-flow-id]")?.dataset.flowId);
            const flow = this.state.data.flows.find((item) => item.id === id) || this.state.data.flows[0];
            this.state.flowId = flow ? flow.id : false;
        }
        if (level >= 4 && !this.state.taskId) {
            const id = Number(under?.closest(".o_pan_sl_chip")?.dataset.taskId);
            const steps = this.listedTasks;
            const task = steps.find((item) => item.id === id) || steps.find((item) => item.rung < TESTED_RUNG) || steps[0];
            this.state.taskId = task ? task.id : false;
        }
    }

    /** Zoom (animated, unless reduced motion) to a whole level. */
    zoomTo(target, { point, flyTo } = {}) {
        target = clamp(Math.round(target), 0, MAX_ZOOM);
        this.focusFor(target, point);
        target = Math.min(target, this.maxZoom);
        if (target < 4) {
            this.state.taskId = false;
        }
        if (point) {
            this.setOrigin(point);
        }
        this.flyTarget = flyTo || null;
        browser.cancelAnimationFrame(this.frame);
        const from = this.state.zoom;
        if (prefersReducedMotion() || from === target) {
            this.state.zoom = target;
            this.remember();
            return;
        }
        const started = browser.performance?.now?.() ?? Date.now();
        const step = (now) => {
            const t = clamp((now - started) / FLY_MS, 0, 1);
            const eased = 1 - (1 - t) ** 3;
            this.state.zoom = from + (target - from) * eased;
            if (t < 1) {
                this.frame = browser.requestAnimationFrame(step);
            } else {
                this.state.zoom = target;
                this.remember();
            }
        };
        this.frame = browser.requestAnimationFrame(step);
    }

    /** A gesture (pinch, Ctrl + wheel) moves the zoom freely; it snaps to a level when the gesture rests. */
    zoomBy(delta, point) {
        const next = clamp(this.state.zoom + delta, 0, MAX_ZOOM);
        if (Math.round(next) > this.level) {
            this.focusFor(Math.round(next), point);
        }
        this.state.zoom = Math.min(next, this.maxZoom + 0.49);
        if (point) {
            this.setOrigin(point);
        }
        browser.clearTimeout(this.snapTimer);
        this.snapTimer = browser.setTimeout(() => this.zoomTo(this.state.zoom, { point }), SNAP_MS);
    }

    setOrigin(point) {
        const el = this.stage.el;
        if (el) {
            const box = el.getBoundingClientRect();
            this.state.origin = `${Math.round(point.x - box.left)}px ${Math.round(point.y - box.top + el.scrollTop)}px`;
        }
    }

    zoomIn() {
        this.zoomTo(this.level + 1);
    }

    zoomOut() {
        this.zoomTo(this.level - 1);
    }

    /** Ctrl/Cmd + wheel (and a trackpad pinch, which sends it) zooms; a plain wheel scrolls. */
    onWheel(ev) {
        if (!ev.ctrlKey && !ev.metaKey) {
            return;
        }
        ev.preventDefault();
        this.zoomBy(-ev.deltaY / 250, { x: ev.clientX, y: ev.clientY });
    }

    onTouchStart(ev) {
        if (ev.touches.length === 2) {
            this.pinch = { distance: this.touchDistance(ev.touches) };
        }
    }

    /** Two fingers zoom; one finger scrolls (the browser does that, see touch-action). */
    onTouchMove(ev) {
        if (!this.pinch || ev.touches.length !== 2) {
            return;
        }
        const distance = this.touchDistance(ev.touches);
        const [a, b] = ev.touches;
        this.zoomBy(Math.log2(distance / this.pinch.distance), { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 });
        this.pinch.distance = distance;
    }

    onTouchEnd(ev) {
        if (ev.touches.length < 2) {
            this.pinch = null;
        }
    }

    touchDistance([a, b]) {
        return Math.max(1, Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY));
    }

    /** Clicking an element flies to it: the next level, centred on it. */
    flyToFlow(flowId, ev) {
        Object.assign(this.state, { flowId, taskId: false });
        this.zoomTo(3, { point: ev && { x: ev.clientX, y: ev.clientY }, flyTo: `[data-fly="flow"]` });
    }

    flyToTask(task, ev) {
        Object.assign(this.state, { taskId: task.id, flowId: task.flow_id || false, selected: null });
        this.zoomTo(4, { point: ev && { x: ev.clientX, y: ev.clientY }, flyTo: `.o_pan_sl_chip[data-task-id="${task.id}"]` });
    }

    remember() {
        memory(this.projectId, this.snapshot());
    }

    /** The path so far; each crumb zooms back out to its level. */
    get crumbs() {
        const crumbs = LEVEL_NAMES.slice(0, Math.min(this.level, 2) + 1).map((label, zoom) => ({ label, zoom }));
        if (this.level >= 3 && this.selectedFlow) {
            crumbs.push({ label: this.selectedFlow.name, zoom: 3 });
        }
        if (this.level >= 4 && this.focusTask) {
            crumbs.push({ label: this.focusTask.name, zoom: 4 });
        }
        return crumbs;
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

    get focusTask() {
        return this.state.taskId ? this.tasksById[this.state.taskId] : null;
    }

    /** The placed tasks of the flow in focus, in task order: the swimlane's steps. */
    get gridTasks() {
        const byId = this.tasksById;
        return (this.selectedFlow?.task_ids || []).map((id) => byId[id]).filter((task) => task && isPlaced(task));
    }

    /** As in the client's swimlane charts: one column per step, left to right in task order. */
    get columns() {
        return this.gridTasks.map((step) => ({ key: `step-${step.id}`, match: (task) => task.id === step.id }));
    }

    /** The phase of each step, adjacent steps of one phase merged. */
    get headers() {
        const { phases } = this.state.data;
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

    /** Only the roles the flow uses: internal first, external at the bottom. */
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
        return `grid-template-columns: minmax(7rem, 9rem) repeat(${this.columns.length}, minmax(10rem, 13rem))`;
    }

    /** Every step of the flow in focus, in task order (also those without a place). */
    get listedTasks() {
        const byId = this.tasksById;
        return (this.selectedFlow?.task_ids || []).map((id) => byId[id]).filter(Boolean);
    }

    isDone(task) {
        return task.rung >= TESTED_RUNG;
    }

    get announcement() {
        const names = [_t("Company"), _t("Project"), _t("Flows")];
        if (this.level >= 4 && this.focusTask) {
            return _t("Task %s", this.focusTask.name);
        }
        if (this.level === 3 && this.selectedFlow) {
            const open = this.listedTasks.filter((task) => !this.isDone(task)).length;
            return _t("Showing flow %(flow)s, %(count)s open tasks", { flow: this.selectedFlow.name, count: open });
        }
        return names[this.level];
    }

    /** "6 Nov", day and month in the user's language. */
    dayMonth(date) {
        return deserializeDate(date).toLocaleString({ day: "numeric", month: "short" });
    }

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
    // z0 and z1: the company and the project
    // ------------------------------------------------------------------

    /** The brief's first sentence, the headline at z0. */
    get headline() {
        const { brief } = this.state.data.project;
        if (!brief) {
            return "";
        }
        // A space after each block, so paragraphs do not run into each other.
        const spaced = brief.replace(/<\/(p|div|li|h\d)>|<br\s*\/?>/gi, "$& ");
        const text = (new DOMParser().parseFromString(spaced, "text/html").body.textContent || "").replace(/\s+/g, " ").trim();
        const end = text.search(/[.!?](\s|$)/);
        return end > 0 ? text.slice(0, end + 1) : text;
    }

    get brief() {
        const { brief } = this.state.data.project;
        return brief ? markup(brief) : false;
    }

    get systems() {
        const { from_systems: from, to_systems: to } = this.state.data.project;
        return from || to ? { from: from || "?", to: to || "?" } : false;
    }

    /** From the project's start to its target: milestones as ticks, today as a line. False without both dates. */
    get timeline() {
        const { date_start: start, date_end: end } = this.state.data.project;
        if (!start || !end) {
            return false;
        }
        const from = deserializeDate(start);
        const span = Math.max(1, deserializeDate(end).diff(from, "days").days);
        const at = (date) => clamp((100 * deserializeDate(date).diff(from, "days").days) / span, 0, 100);
        const ticks = this.state.data.milestones
            .filter((milestone) => milestone.deadline)
            .map((milestone) => ({
                id: milestone.id,
                name: milestone.name,
                date: this.dayMonth(milestone.deadline),
                at: at(milestone.deadline),
                reached: milestone.reached,
            }));
        const now = clamp((100 * today().diff(from, "days").days) / span, 0, 100);
        return { start: this.dayMonth(start), end: this.dayMonth(end), today: now, ticks };
    }

    /**
     * The burn-up at z1 (round 6), drawn in a 100 x 100 box that stretches
     * (labels sit beside it in HTML, so text never stretches): x is time from
     * the start to the target (or today when later), y the mean step 0..1.
     * The actual line runs to today, the ideal line is dashed. False without
     * the server's ideal line (no dates or no tasks).
     */
    get burnup() {
        const { ideal, progress_history: history, milestones } = this.state.data;
        if (!ideal || !history.length) {
            return false;
        }
        const from = deserializeDate(ideal[0].date);
        const days = (date) => deserializeDate(date).diff(from, "days").days;
        const now = today().diff(from, "days").days;
        const span = Math.max(1, days(ideal[1].date), now);
        const x = (date) => clamp((100 * days(date)) / span, 0, 100);
        const y = (value) => 100 - 100 * clamp(value, 0, 1);
        const pair = (point) => `${x(point.date).toFixed(2)},${y(point.value).toFixed(2)}`;
        const last = history.at(-1);
        const ticks = milestones
            .filter((milestone) => milestone.deadline)
            .map((milestone) => ({
                id: milestone.id,
                at: x(milestone.deadline),
                reached: milestone.reached,
                title: `${milestone.name}, ${this.dayMonth(milestone.deadline)}`,
            }));
        const idealNow = clamp(now / Math.max(1, days(ideal[1].date)), 0, 1);
        const percent = (value) => `${Math.round(100 * value)}%`;
        return {
            actual: history.map(pair).join(" "),
            ideal: ideal.map(pair).join(" "),
            today: clamp((100 * now) / span, 0, 100),
            end: { x: x(last.date), y: y(last.value), label: percent(last.value) },
            ticks,
            start: this.dayMonth(ideal[0].date),
            target: this.dayMonth(ideal[1].date),
            label: _t("Progress over time: %(actual)s done today, %(ideal)s planned", {
                actual: percent(last.value),
                ideal: percent(idealNow),
            }),
        };
    }

    /** Managers see one muted line when the company page or the dates are missing. */
    get missingTop() {
        const { project } = this.state.data;
        return this.state.isManager && (!project.brief || !project.date_start || !project.date_end);
    }

    /** The share of tasks at each of the six steps, for a stacked bar. */
    parts(tasks) {
        return STEPS.map((rung) => ({ tone: tone(rung), count: tasks.filter((task) => task.rung === rung).length })).filter(
            (part) => part.count
        );
    }

    get project() {
        const { tasks, milestones, flows } = this.state.data;
        return {
            parts: this.parts(tasks),
            label: tasks.length === 1 ? _t("1 task by step") : _t("%s tasks by step", tasks.length),
            ...this.schedule(milestones, flows),
        };
    }

    flowTasks(flow) {
        const byId = this.tasksById;
        return flow.task_ids.map((id) => byId[id]).filter(Boolean);
    }

    /**
     * The next milestone not reached and one verdict. With a burn-up (round
     * 6) the verdict is the burn-up's: "On track" (green), else "Behind · N
     * weeks", amber up to two weeks, red beyond. Without one (no dates):
     * "Late · N days" (red) when the milestone's date has passed; else "At
     * risk" (amber) when a flow is late; else "On track".
     */
    schedule(milestones, flows) {
        const next = milestones.find((milestone) => !milestone.reached);
        const value = next ? next.name : milestones.length ? _t("All milestones reached") : _t("No milestones");
        const due = next?.deadline ? ` · ${_t("Due %s", this.dayMonth(next.deadline))}` : "";
        const { verdict: burnup, weeks_behind: weeks } = this.state.data;
        if (burnup) {
            const behind = weeks === 1 ? _t("Behind · 1 week") : _t("Behind · %s weeks", weeks);
            return {
                milestone: value + due,
                status: burnup === "on_track" ? _t("On track") : behind,
                tone: burnup === "on_track" ? "ok" : weeks > 2 ? "late" : "risk",
            };
        }
        const lateFlows = flows.filter((flow) => flow.late).length;
        const days = next?.deadline ? Math.round(today().diff(deserializeDate(next.deadline), "days").days) : 0;
        let verdict = { word: _t("On track"), tone: "ok" };
        if (days > 0) {
            verdict = { word: this.lateDays(days), tone: "late" };
        } else if (lateFlows) {
            verdict = { word: _t("At risk"), tone: "risk" };
        }
        const late = lateFlows === 1 ? _t("1 flow late") : lateFlows ? _t("%s flows late", lateFlows) : "";
        return {
            milestone: value + due,
            status: late && days <= 0 ? `${verdict.word} (${late})` : verdict.word,
            tone: verdict.tone,
        };
    }

    // ------------------------------------------------------------------
    // z3 and z4: the flow and the task
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
        await this.load(this.props);
    }

    roleTraining(role) {
        const byId = this.tasksById;
        return role.open_training_task_ids.map((id) => byId[id]).filter(Boolean);
    }

    adkarWord(role) {
        return role.adkar ? ADKAR_WORDS[role.adkar] : _t("Needs three scored people");
    }

    // ------------------------------------------------------------------
    // Drawing: arrows, the right-edge fade, flying to an element
    // ------------------------------------------------------------------

    afterRender() {
        this.redraw();
        if (this.flyTarget && Number.isInteger(this.state.zoom)) {
            const el = this.root.el?.querySelector(this.flyTarget);
            this.flyTarget = null;
            this.centre(el);
        }
    }

    /**
     * Brings the element in view without moving the page: the swimlane
     * centres it sideways; the stage scrolls only when it is out of view,
     * its top edge first.
     */
    centre(el) {
        if (!el) {
            return;
        }
        const area = this.gridArea.el;
        if (area && area.contains(el)) {
            const outer = area.getBoundingClientRect();
            const inner = el.getBoundingClientRect();
            area.scrollLeft += inner.left - outer.left - (outer.width - inner.width) / 2;
        }
        const stage = this.stage.el;
        if (stage && stage.contains(el)) {
            const outer = stage.getBoundingClientRect();
            const inner = el.getBoundingClientRect();
            if (inner.top < outer.top || inner.top > outer.bottom - 48) {
                stage.scrollTop += inner.top - outer.top - 8;
            }
        }
    }

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

    updateFade() {
        const el = this.gridArea.el;
        const right = Boolean(el) && el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
        if (this.fade.right !== right) {
            this.fade.right = right;
        }
    }

    /**
     * Arrows between the chips of the flow, in task order. Measured with
     * offsets inside the grid (the SVG's box too), so they scroll with the
     * grid and ignore the stage's zoom transform.
     */
    updateArrows() {
        const grid = this.grid.el;
        let next = { width: 0, height: 0, paths: [] };
        if (grid && this.show("swimlane")) {
            const box = (el) => ({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
            const chips = this.gridTasks.map((task) => grid.querySelector(`.o_pan_sl_chip[data-task-id="${task.id}"]`)).filter(Boolean);
            const paths = chips.slice(1).map((chip, index) => ({
                key: `${chips[index].dataset.taskId}-${chip.dataset.taskId}`,
                from: chips[index].dataset.taskId,
                to: chip.dataset.taskId,
                d: arrowPath(box(chips[index]), box(chip)),
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
    // Panels and actions
    // ------------------------------------------------------------------

    isSelected(type, id) {
        const { selected } = this.state;
        return String(Boolean(selected && selected.type === type && selected.id === id));
    }

    /** Opens the side panel of a role or of the tasks without a place (Close or Esc closes it). */
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
