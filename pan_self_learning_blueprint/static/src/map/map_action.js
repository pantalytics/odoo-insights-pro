import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// Geometry of the map, in SVG user units.
const LABEL_W = 170; // role label column on the left
const COL_W = 210; // one phase column
const HEADER_H = 40; // phase names
const PROGRESS_H = 46; // progress band
const CHIP_W = COL_W - 20;
const CHIP_H = 26;
const CHIP_GAP = 6;
const LANE_PAD = 8;
const APP_CHIP_H = 20;
const APP_CHIP_GAP = 4;
const APP_CHAR_W = 6.5;
const ODOO_PAD = 10;
const CHIP_CHARS = 27;
const LABEL_CHARS = 22;
const MIN_ZOOM_SHARE = 0.15; // how far you can zoom in, as a share of the full map

const TESTED_RUNG = 3;

const CHOICE_STATES = ["proposal", "provisional", "fixed", "revised"];
const RUNGS = [0, 1, 2, 3, 4, 5];
const PEOPLE_LEVELS = ["ready", "partly", "not_ready", "no_data"];

function truncate(text, length) {
    if (!text || text.length <= length) {
        return text || "";
    }
    return `${text.slice(0, length - 1)}…`;
}

/**
 * Put external roles (customer, supplier) at the edges of the map. Roles
 * arrive ordered by sequence: an external role in the first half of that
 * order goes to the top, one in the second half to the bottom. Internal
 * roles keep their sequence order in between.
 */
export function orderRoles(roles) {
    const half = roles.length / 2;
    const top = [];
    const middle = [];
    const bottom = [];
    roles.forEach((role, index) => {
        if (!role.is_external) {
            middle.push(role);
        } else if (index < half) {
            top.push(role);
        } else {
            bottom.push(role);
        }
    });
    return [...top, ...middle, ...bottom];
}

/**
 * Compute the static geometry of the map from the server data. Colours,
 * dimming and the route depend on the controls and are applied at render.
 */
export function computeLayout(data) {
    const phases = data.phases;
    const roles = orderRoles(data.roles);
    const phaseIndex = new Map(phases.map((phase, index) => [phase.id, index]));
    const width = LABEL_W + Math.max(phases.length, 1) * COL_W;

    // Activities per cell (role x phase), in server order (sequence).
    const cells = new Map();
    for (const activity of data.activities) {
        const key = `${activity.role_id}-${activity.phase_id}`;
        if (!cells.has(key)) {
            cells.set(key, []);
        }
        cells.get(key).push(activity);
    }

    // Progress band: share of activities per phase at rung Tested or higher.
    const progress = phases.map((phase, index) => {
        const inPhase = data.activities.filter((a) => a.phase_id === phase.id);
        const done = inPhase.filter((a) => a.rung >= TESTED_RUNG).length;
        const share = inPhase.length ? done / inPhase.length : 0;
        return {
            id: phase.id,
            x: LABEL_W + index * COL_W,
            total: inPhase.length,
            done,
            share,
            barWidth: (COL_W - 20) * share,
            label: inPhase.length
                ? _t("%(percent)s tested (%(done)s/%(total)s)", {
                      percent: `${Math.round(share * 100)}%`,
                      done,
                      total: inPhase.length,
                  })
                : _t("No activities"),
        };
    });

    // Role lanes, their height follows the fullest cell.
    let y = HEADER_H + PROGRESS_H;
    const lanes = [];
    const chips = [];
    for (const role of roles) {
        let maxCount = 1;
        for (const phase of phases) {
            maxCount = Math.max(maxCount, (cells.get(`${role.id}-${phase.id}`) || []).length);
        }
        const height = LANE_PAD * 2 + maxCount * CHIP_H + (maxCount - 1) * CHIP_GAP;
        lanes.push({
            role,
            y,
            height,
            label: truncate(role.name, LABEL_CHARS),
        });
        for (const phase of phases) {
            const cellActivities = cells.get(`${role.id}-${phase.id}`) || [];
            cellActivities.forEach((activity, index) => {
                const chipX = LABEL_W + phaseIndex.get(phase.id) * COL_W + (COL_W - CHIP_W) / 2;
                const chipY = y + LANE_PAD + index * (CHIP_H + CHIP_GAP);
                chips.push({
                    id: activity.id,
                    activity,
                    role,
                    x: chipX,
                    y: chipY,
                    cx: chipX + CHIP_W / 2,
                    cy: chipY + CHIP_H / 2,
                    label: truncate(activity.name, CHIP_CHARS),
                });
            });
        }
        y += height;
    }
    const lanesBottom = y;

    // Odoo band: app chips per phase, wrapped within the column.
    let odooRows = 1;
    const apps = [];
    phases.forEach((phase, index) => {
        let rowX = 0;
        let row = 0;
        const maxRowWidth = COL_W - 2 * ODOO_PAD;
        for (const app of phase.apps) {
            const chipWidth = Math.min(maxRowWidth, app.length * APP_CHAR_W + 16);
            if (rowX > 0 && rowX + chipWidth > maxRowWidth) {
                row += 1;
                rowX = 0;
            }
            apps.push({
                key: `${phase.id}-${app}`,
                label: app,
                x: LABEL_W + index * COL_W + ODOO_PAD + rowX,
                y: lanesBottom + ODOO_PAD + row * (APP_CHIP_H + APP_CHIP_GAP),
                width: chipWidth,
            });
            rowX += chipWidth + APP_CHIP_GAP;
        }
        odooRows = Math.max(odooRows, row + 1);
    });
    const odooHeight = 2 * ODOO_PAD + odooRows * APP_CHIP_H + (odooRows - 1) * APP_CHIP_GAP;
    const height = lanesBottom + odooHeight;

    return {
        width,
        height,
        columns: phases.map((phase, index) => ({
            phase,
            x: LABEL_W + index * COL_W,
            label: truncate(phase.name, LABEL_CHARS + 4),
        })),
        progress,
        lanes,
        chips,
        chipById: new Map(chips.map((chip) => [chip.id, chip])),
        lanesTop: HEADER_H + PROGRESS_H,
        lanesBottom,
        odooHeight,
        apps,
    };
}

export class CompanyMap extends Component {
    static template = "pan_self_learning_blueprint.CompanyMap";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.svgRef = useRef("svg");
        this.geometry = {
            LABEL_W,
            COL_W,
            HEADER_H,
            PROGRESS_H,
            CHIP_W,
            CHIP_H,
            APP_CHIP_H,
        };
        this.state = useState({
            loaded: false,
            scenarioId: false,
            colorBy: "choices",
            selectedId: false,
            viewBox: { x: 0, y: 0, w: 1, h: 1 },
        });
        this.drag = null;
        this.lastFocused = null;

        useHotkey("escape", () => this.closePanel(), {
            bypassEditableProtection: true,
            isAvailable: () => Boolean(this.state.selectedId),
        });

        onWillStart(async () => {
            this.data = await this.orm.call("pan.sl.activity", "get_map_data", []);
            this.roleById = new Map(this.data.roles.map((role) => [role.id, role]));
            this.scenarioById = new Map(this.data.scenarios.map((s) => [s.id, s]));
            this.layout = computeLayout(this.data);
            this.fit();
            this.state.loaded = true;
        });
    }

    // ------------------------------------------------------------------
    // Labels
    // ------------------------------------------------------------------

    get choiceLabels() {
        return {
            proposal: _t("Proposal"),
            provisional: _t("Provisional"),
            fixed: _t("Fixed"),
            revised: _t("Revised"),
        };
    }

    get rungLabels() {
        return [_t("Open"), _t("Decided"), _t("Built"), _t("Tested"), _t("Trained"), _t("Live")];
    }

    get peopleLabels() {
        return {
            ready: _t("Ready (ADKAR 4+)"),
            partly: _t("Partly ready (ADKAR 2+)"),
            not_ready: _t("Not ready"),
            no_data: _t("No ADKAR data"),
        };
    }

    get adkarLabels() {
        return [_t("Awareness"), _t("Desire"), _t("Knowledge"), _t("Ability"), _t("Reinforcement")];
    }

    get legend() {
        if (this.state.colorBy === "choices") {
            return CHOICE_STATES.map((key) => ({
                key,
                className: `o_pan_sl_c_${key}`,
                label: this.choiceLabels[key],
            }));
        }
        if (this.state.colorBy === "progress") {
            return RUNGS.map((rung) => ({
                key: String(rung),
                className: `o_pan_sl_r_${rung}`,
                label: `${rung} ${this.rungLabels[rung]}`,
            }));
        }
        return PEOPLE_LEVELS.map((key) => ({
            key,
            className: `o_pan_sl_p_${key}`,
            label: this.peopleLabels[key],
        }));
    }

    // ------------------------------------------------------------------
    // Colours, dimming and route
    // ------------------------------------------------------------------

    peopleLevel(role) {
        if (!role.adkar) {
            return "no_data";
        }
        const lowest = Math.min(...role.adkar);
        if (lowest >= 4) {
            return "ready";
        }
        if (lowest >= 2) {
            return "partly";
        }
        return "not_ready";
    }

    get selectedScenario() {
        return this.state.scenarioId ? this.scenarioById.get(this.state.scenarioId) : false;
    }

    chipClass(chip) {
        const classes = [];
        if (this.state.colorBy === "choices") {
            classes.push(`o_pan_sl_c_${chip.activity.choice_state}`);
        } else if (this.state.colorBy === "progress") {
            classes.push(`o_pan_sl_r_${chip.activity.rung}`);
        } else {
            classes.push(`o_pan_sl_p_${this.peopleLevel(chip.role)}`);
        }
        const scenario = this.selectedScenario;
        if (scenario && !scenario.activity_ids.includes(chip.id)) {
            classes.push("o_pan_sl_dim");
        }
        if (this.state.selectedId === chip.id) {
            classes.push("o_pan_sl_selected");
        }
        return classes.join(" ");
    }

    get route() {
        const scenario = this.selectedScenario;
        if (!scenario) {
            return false;
        }
        const stops = scenario.activity_ids
            .map((id) => this.layout.chipById.get(id))
            .filter((chip) => chip);
        const path = stops
            .map((chip, index) => `${index ? "L" : "M"} ${chip.cx} ${chip.cy}`)
            .join(" ");
        return {
            path,
            badges: stops.map((chip, index) => ({
                key: `${chip.id}-${index}`,
                number: index + 1,
                x: chip.x,
                y: chip.cy,
            })),
        };
    }

    // ------------------------------------------------------------------
    // Controls
    // ------------------------------------------------------------------

    onScenarioChange(ev) {
        const value = ev.target.value;
        this.state.scenarioId = value ? parseInt(value, 10) : false;
    }

    selectScenario(scenarioId) {
        this.state.scenarioId = scenarioId;
    }

    onColorByChange(ev) {
        this.state.colorBy = ev.target.value;
    }

    get viewBoxAttr() {
        const vb = this.state.viewBox;
        return `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;
    }

    fit() {
        Object.assign(this.state.viewBox, {
            x: 0,
            y: 0,
            w: this.layout.width,
            h: this.layout.height,
        });
    }

    zoom(factor) {
        const vb = this.state.viewBox;
        const minW = this.layout.width * MIN_ZOOM_SHARE;
        const w = Math.min(this.layout.width, Math.max(minW, vb.w * factor));
        const h = (w / vb.w) * vb.h;
        const cx = vb.x + vb.w / 2;
        const cy = vb.y + vb.h / 2;
        Object.assign(vb, { x: cx - w / 2, y: cy - h / 2, w, h });
        if (w >= this.layout.width) {
            this.fit();
        }
    }

    zoomIn() {
        this.zoom(0.8);
    }

    zoomOut() {
        this.zoom(1.25);
    }

    // Drag the map background to pan.
    onPointerDown(ev) {
        if (ev.button !== 0 || ev.target.closest(".o_pan_sl_chip")) {
            return;
        }
        const svg = this.svgRef.el;
        this.drag = {
            pointerId: ev.pointerId,
            x: ev.clientX,
            y: ev.clientY,
            vbX: this.state.viewBox.x,
            vbY: this.state.viewBox.y,
            // preserveAspectRatio "meet": the larger ratio sets the scale.
            scale: Math.max(
                this.state.viewBox.w / svg.clientWidth,
                this.state.viewBox.h / svg.clientHeight
            ),
        };
        svg.setPointerCapture(ev.pointerId);
    }

    onPointerMove(ev) {
        if (!this.drag || ev.pointerId !== this.drag.pointerId) {
            return;
        }
        this.state.viewBox.x = this.drag.vbX - (ev.clientX - this.drag.x) * this.drag.scale;
        this.state.viewBox.y = this.drag.vbY - (ev.clientY - this.drag.y) * this.drag.scale;
    }

    onPointerUp(ev) {
        if (this.drag && ev.pointerId === this.drag.pointerId) {
            this.svgRef.el.releasePointerCapture(ev.pointerId);
            this.drag = null;
        }
    }

    // ------------------------------------------------------------------
    // Side panel
    // ------------------------------------------------------------------

    openPanel(activityId) {
        this.lastFocused = document.activeElement;
        this.state.selectedId = activityId;
    }

    onChipKeydown(ev, activityId) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openPanel(activityId);
        }
    }

    closePanel() {
        this.state.selectedId = false;
        if (this.lastFocused && this.lastFocused.isConnected) {
            this.lastFocused.focus();
        }
        this.lastFocused = null;
    }

    get panel() {
        if (!this.state.selectedId) {
            return false;
        }
        const chip = this.layout.chipById.get(this.state.selectedId);
        const activity = chip.activity;
        const role = chip.role;
        return {
            activity,
            role,
            choiceLabel: this.choiceLabels[activity.choice_state],
            rungLabel: `${activity.rung} ${this.rungLabels[activity.rung]}`,
            scenarios: activity.scenario_ids
                .map((id) => this.scenarioById.get(id))
                .filter((scenario) => scenario),
            adkar: role.adkar
                ? role.adkar.map((value, index) => ({
                      label: this.adkarLabels[index],
                      value: value.toFixed(1),
                  }))
                : false,
        };
    }

    async openActivity() {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "pan.sl.activity",
            res_id: this.state.selectedId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openTemplateWizard() {
        await this.actionService.doAction("pan_self_learning_blueprint.action_blueprint_wizard");
    }
}

registry.category("actions").add("pan_sl_blueprint_map", CompanyMap);
