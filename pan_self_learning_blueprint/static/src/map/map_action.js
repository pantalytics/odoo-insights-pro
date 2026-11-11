import { Component, onMounted, onPatched, onWillStart, useExternalListener, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { deserializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloatTime } from "@web/views/fields/formatters";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// The map of one project (Blueprint 2.2, docs/ux-test-2026-11-11.md): flows on
// the left, worst first; a plain grid of phases (columns) by roles (rows) with
// a chip per task. Plain HTML, normal scrolling, no zoom. The flow list and the
// grid scroll on their own, so the panel stays in view whatever was tapped.

const LAST_PROJECT_KEY = "pan_sl_blueprint_map:last_project";
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

function storage(value) {
    try {
        if (value === undefined) {
            return parseInt(browser.localStorage.getItem(LAST_PROJECT_KEY), 10) || false;
        }
        browser.localStorage.setItem(LAST_PROJECT_KEY, String(value));
    } catch {
        // Private mode or blocked storage: the map works without memory.
    }
    return false;
}

export class BlueprintMap extends Component {
    static template = "pan_self_learning_blueprint.Map";
    static props = { ...standardActionServiceProps };
    static components = { Layout };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        const { params = {}, context = {} } = this.props.action;
        const contextId = context.active_model === "project.project" ? context.active_id : false;
        const restored = this.props.state?.blueprintMap || {};
        this.state = useState({
            projects: [],
            projectId: restored.projectId || params.project_id || contextId || false,
            data: null,
            flowId: restored.flowId || false,
            selected: null, // { type: "task" | "role", id }
        });
        this.tones = [
            { tone: "off", label: _t("Open") },
            { tone: "warn", label: _t("Decided or Built") },
            { tone: "ok", label: _t("Tested") },
            { tone: "done", label: _t("Trained or Live") },
        ];
        this.root = useRef("root");
        this.gridArea = useRef("gridArea");
        this.scrollFlowIntoView = false;
        this.fade = useState({ right: false });
        useExternalListener(window, "resize", () => this.updateFade());
        onMounted(() => this.updateFade());
        onPatched(() => {
            this.updateFade();
            if (this.scrollFlowIntoView) {
                this.scrollFlowIntoView = false;
                this.root.el?.querySelector(".o_pan_sl_flows .o_pan_sl_open_tasks")?.scrollIntoView({ block: "nearest" });
            }
        });
        useSetupAction({
            getLocalState: () => ({ blueprintMap: { projectId: this.state.projectId, flowId: this.state.flowId } }),
        });
        useHotkey("escape", () => (this.state.selected = null), {
            bypassEditableProtection: true,
            isAvailable: () => Boolean(this.state.selected),
        });
        onWillStart(() => this.start());
    }

    async start() {
        this.state.projects = await this.orm.call("project.project", "get_blueprint_map_projects", []);
        const ids = this.state.projects.map((project) => project.id);
        if (!this.state.projectId) {
            const last = storage();
            this.state.projectId = ids.includes(last) ? last : ids.length === 1 ? ids[0] : false;
        }
        if (this.state.projectId) {
            await this.load(this.state.projectId, this.state.flowId);
        }
    }

    async load(projectId, flowId = false) {
        const data = await this.orm.call("project.project", "get_blueprint_map_data", [[projectId]]);
        Object.assign(this.state, { projectId, data, flowId, selected: null });
        storage(projectId);
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

    /** Internal roles first, external at the bottom; only roles with a placed task. */
    get rows() {
        const { roles, phases, tasks } = this.state.data;
        const placed = tasks.filter(isPlaced);
        const ordered = [...roles.filter((role) => !role.is_external), ...roles.filter((role) => role.is_external)];
        return ordered
            .map((role) => ({
                role,
                cells: phases.map((phase) => ({
                    phase,
                    tasks: placed.filter((task) => task.role_id === role.id && task.phase_id === phase.id),
                })),
            }))
            .filter((row) => row.cells.some((cell) => cell.tasks.length));
    }

    get selectedFlow() {
        return this.state.data.flows.find((flow) => flow.id === this.state.flowId);
    }

    /** The open tasks of the selected flow (below Tested), or every task without a place. */
    get listedTasks() {
        if (this.state.flowId === UNPLACED) {
            return this.unplaced;
        }
        const byId = this.tasksById;
        return (this.selectedFlow?.task_ids || []).map((id) => byId[id]).filter((task) => task && task.rung < TESTED_RUNG);
    }

    get announcement() {
        if (this.state.flowId === UNPLACED) {
            return _t("Showing %s tasks without a place", this.unplaced.length);
        }
        return this.selectedFlow ? _t("Showing flow %(flow)s, %(count)s open tasks", { flow: this.selectedFlow.name, count: this.listedTasks.length }) : "";
    }

    isDim(task) {
        return Boolean(this.selectedFlow) && !this.selectedFlow.task_ids.includes(task.id);
    }

    /** "3 of 10 flows late" */
    get flowSummary() {
        const { flows } = this.state.data;
        return _t("%(late)s of %(total)s flows late", { late: flows.filter((flow) => flow.late).length, total: flows.length });
    }

    /** "Due 6 Nov", day and month in the user's language. */
    deadline(flow) {
        return flow.deadline ? _t("Due %s", deserializeDate(flow.deadline).toLocaleString({ day: "numeric", month: "short" })) : "";
    }

    lateLabel(flow) {
        return flow.days_late === 1 ? _t("Late · 1 day") : _t("Late · %s days", flow.days_late);
    }

    openLabel(flow) {
        return _t("%s open", flow.open_count);
    }

    hours(task) {
        return _t("%(spent)s of %(planned)s h", { spent: formatFloatTime(task.spent_hours), planned: formatFloatTime(task.planned_hours) });
    }

    /** Tasks of internal roles below Trained: what the "Still to train" list shows. */
    get trainingCount() {
        return this.state.data.roles.filter((role) => !role.is_external).reduce((count, role) => count + role.open_training_task_ids.length, 0);
    }

    get trainingLabel() {
        return _t("Still to train (%s)", this.trainingCount);
    }

    /** A fade at the right edge while the grid can scroll further right. */
    updateFade() {
        const el = this.gridArea.el;
        const right = Boolean(el) && el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
        if (this.fade.right !== right) {
            this.fade.right = right;
        }
    }

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
    // Actions
    // ------------------------------------------------------------------

    isSelected(type, id) {
        const { selected } = this.state;
        return String(Boolean(selected && selected.type === type && selected.id === id));
    }

    toggleFlow(flowId) {
        this.state.flowId = this.state.flowId === flowId ? false : flowId;
        this.scrollFlowIntoView = Boolean(this.state.flowId);
    }

    /** Opens the panel of a task or role; a tap never closes it (Close or Esc does). */
    select(type, id) {
        this.state.selected = { type, id };
    }

    onProjectChange(ev) {
        this.load(parseInt(ev.target.value, 10));
    }

    async onTraining() {
        const action = await this.orm.call("project.project", "action_blueprint_training", [[this.state.projectId]]);
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

registry.category("actions").add("pan_sl_blueprint_map", BlueprintMap);
