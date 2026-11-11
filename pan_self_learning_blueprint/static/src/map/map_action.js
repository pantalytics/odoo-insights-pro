import { Component, onWillStart, onWillUnmount, useEffect, useExternalListener, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { formatFloatTime } from "@web/views/fields/formatters";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// The company map of one project (data model v2.0, docs/data-model.md):
// columns are phases, lanes are roles, chips are tasks.

// ----------------------------------------------------------------------
// Semantic zoom: three stops, each with its own geometry (SVG user units).
// ----------------------------------------------------------------------

export const STOP_COMPANY = 1;
export const STOP_TASKS = 2;
export const STOP_DETAIL = 3;
const ALL_STOPS = [STOP_COMPANY, STOP_TASKS, STOP_DETAIL];

const LINE_H = 15; // detail lines under a chip name
const DETAIL_LINES = 3; // rung and hours, assignees, description
const STOP_GEOMETRY = {
    [STOP_COMPANY]: { labelW: 150, colW: 150, chipH: 34, chipGap: 0, lanePad: 8 },
    [STOP_TASKS]: { labelW: 160, colW: 190, chipH: 28, chipGap: 6, lanePad: 10 },
    [STOP_DETAIL]: { labelW: 160, colW: 240, chipH: 28 + DETAIL_LINES * LINE_H + 4, chipGap: 8, lanePad: 10 },
};
const HEADER_H = 36;

// Zoom is continuous from MIN_ZOOM (fit) to MAX_ZOOM; the stops start at the thresholds.
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;
export const STOP_THRESHOLDS = [1, 2, 3];
const MAX_SCALE = 1.6; // pixels per user unit at MAX_ZOOM
const FIT_MIN_SCALE = 0.55; // below this text gets unreadable: pan instead
const FIT_MAX_SCALE = 1.25;
const NARROW_W = 576; // phones: readable text, narrow label column, pan sideways
const FIT_MIN_SCALE_NARROW = 0.8;
const COMPACT_LABEL_W = 100;
const DRAG_THRESHOLD = 4; // px before a press becomes a pan
const KEY_PAN_PX = 80;
const KEY_ZOOM_STEP = 0.25;
const WHEEL_ZOOM_SPEED = 0.0015;
const PINCH_WHEEL_SPEED = 0.01; // trackpad pinch: ctrl + wheel with small deltas
const WHEEL_PAN_COMMIT_MS = 120;
// The side panel (.o_pan_sl_panel): 340px plus gaps on desktop, a bottom sheet on phones.
const PANEL_W = 364;
const SHEET_SHARE = 0.65;
const SMALL_SCREEN_MEDIA = "(max-width: 767.98px)";
const MARGIN = 24; // user units around a box that showBox centres

const CHIP_INSET = 8;
const CHAR_W = 6.4; // average glyph width at 12px
const SMALL_CHAR_W = 5.6; // at 10.5px
const APP_CHIP_H = 20;
const APP_CHIP_GAP = 4;
const APP_CHAR_W = 6.2;
const ODOO_PAD = 10;

const TESTED_RUNG = 3;
const TRAINED_RUNG = 4;

// Status per colour mode, in legend order. Brand: green works, amber needs
// the user, grey off or not started.
export const COLOR_MODES = ["progress", "training"];
const MODE_LEVELS = {
    progress: ["open", "building", "tested"],
    training: ["trained", "to_train", "no_people"],
};
const TONES = { open: "off", building: "warn", tested: "ok", trained: "ok", to_train: "warn", no_people: "off" };

/** Rung 0 Open, 1-2 Decided or Built, 3-5 Tested or further. */
export function progressLevel(rung) {
    if (rung >= TESTED_RUNG) {
        return "tested";
    }
    return rung > 0 ? "building" : "open";
}

/** Trained from rung 4; a role without people has nobody to train. */
export function trainingLevel(task, role) {
    if (!role.users.length) {
        return "no_people";
    }
    return task.rung >= TRAINED_RUNG ? "trained" : "to_train";
}

const toneClass = (tone) => `o_pan_sl_tone_${tone}`;

/** A second cue per tone, so status never depends on hue alone: ok a check, warn a half disc. */
function toneGlyph(tone, cx, cy, r) {
    const s = r * 0.55;
    if (tone === "ok") {
        return {
            className: "o_pan_sl_glyph",
            d: `M ${cx - s} ${cy + s * 0.05} L ${cx - s * 0.25} ${cy + s * 0.75} L ${cx + s} ${cy - s * 0.65}`,
        };
    }
    if (tone === "warn") {
        return { className: "o_pan_sl_glyph_half", d: `M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx} ${cy + r} Z` };
    }
    return false;
}

function truncate(text, width, charWidth = CHAR_W) {
    const length = Math.max(Math.floor(width / charWidth), 3);
    if (!text || text.length <= length) {
        return text || "";
    }
    return `${text.slice(0, length - 1)}…`;
}

/** Internal roles in sequence order, external roles (customer, supplier) at the bottom. */
export function orderRoles(roles) {
    return [...roles.filter((role) => !role.is_external), ...roles.filter((role) => role.is_external)];
}

/** The static geometry of the map at one stop. Colours and dimming are applied at render. */
export function computeLayout(data, stop, compact = false) {
    const { colW, chipH, chipGap, lanePad } = STOP_GEOMETRY[stop];
    const labelW = compact ? COMPACT_LABEL_W : STOP_GEOMETRY[stop].labelW;
    const chipW = colW - 2 * CHIP_INSET;
    const phases = data.phases;
    const width = labelW + Math.max(phases.length, 1) * colW;
    const columns = phases.map((phase, index) => ({
        phase,
        x: labelW + index * colW,
        label: truncate(phase.name, colW - 16, 7),
    }));
    const cells = new Map();
    for (const task of data.tasks) {
        const key = `${task.role_id}-${task.phase_id}`;
        cells.set(key, [...(cells.get(key) || []), task]);
    }

    let y = HEADER_H;
    const lanes = [];
    const chips = [];
    const blocks = [];
    for (const role of orderRoles(data.roles)) {
        let content = chipH;
        if (stop !== STOP_COMPANY) {
            for (const phase of phases) {
                const count = (cells.get(`${role.id}-${phase.id}`) || []).length;
                content = Math.max(content, count * (chipH + chipGap) - chipGap);
            }
        }
        const height = Math.max(content + lanePad * 2, 50);
        lanes.push({ role, y, height, label: truncate(role.name, labelW - 20, 6.8) });
        columns.forEach(({ phase, x }) => {
            const tasks = cells.get(`${role.id}-${phase.id}`) || [];
            if (!tasks.length) {
                return;
            }
            if (stop === STOP_COMPANY) {
                const by = y + (height - chipH) / 2;
                blocks.push({ key: `b${role.id}-${phase.id}`, role, phase, tasks, x: x + CHIP_INSET, y: by, width: chipW, height: chipH });
                return;
            }
            tasks.forEach((task, index) => {
                chips.push({
                    key: `c${task.id}`,
                    id: task.id,
                    task,
                    role,
                    x: x + CHIP_INSET,
                    y: y + lanePad + index * (chipH + chipGap),
                    width: chipW,
                    height: chipH,
                    label: truncate(task.name, chipW - 32),
                });
            });
        });
        y += height;
    }
    const lanesBottom = y;

    // Odoo band: app chips per phase, wrapped within the column.
    let rows = 1;
    const apps = [];
    columns.forEach(({ phase, x }) => {
        let rowX = 0;
        let row = 0;
        const maxW = colW - 2 * ODOO_PAD;
        for (const app of phase.apps) {
            const appW = Math.min(maxW, app.name.length * APP_CHAR_W + 18);
            if (rowX > 0 && rowX + appW > maxW) {
                row += 1;
                rowX = 0;
            }
            apps.push({
                key: `${phase.id}-${app.module}`,
                label: truncate(app.name, appW - 14, APP_CHAR_W),
                title: app.installed ? app.name : _t("%s (not installed)", app.name),
                installed: app.installed,
                x: x + ODOO_PAD + rowX,
                y: lanesBottom + ODOO_PAD + row * (APP_CHIP_H + APP_CHIP_GAP),
                width: appW,
            });
            rowX += appW + APP_CHIP_GAP;
        }
        rows = Math.max(rows, row + 1);
    });
    const odooHeight = 2 * ODOO_PAD + rows * APP_CHIP_H + (rows - 1) * APP_CHIP_GAP;
    return {
        stop,
        width,
        height: lanesBottom + odooHeight,
        labelW,
        colW,
        lanesBottom,
        odooHeight,
        columns,
        lanes,
        chips,
        blocks,
        apps,
        items: stop === STOP_COMPANY ? blocks : chips,
        chipById: new Map(chips.map((chip) => [chip.id, chip])),
    };
}

export function stopForZoom(zoom) {
    return STOP_THRESHOLDS.filter((threshold) => zoom >= threshold - 1e-6).length || STOP_COMPANY;
}

/** Map a point from one stop's layout to another's: same column and lane, same relative position. */
function mapPoint(from, to, x, y) {
    const nx = x < from.labelW ? (x / from.labelW) * to.labelW : to.labelW + ((x - from.labelW) / from.colW) * to.colW;
    let ny;
    if (y < HEADER_H) {
        ny = y;
    } else if (y >= from.lanesBottom) {
        ny = to.lanesBottom + ((y - from.lanesBottom) / from.odooHeight) * to.odooHeight;
    } else {
        const index = from.lanes.findIndex((lane) => y < lane.y + lane.height);
        const [lane, target] = [from.lanes[index], to.lanes[index]];
        ny = target.y + ((y - lane.y) / lane.height) * target.height;
    }
    return { x: nx, y: ny };
}

function boundingBox(items) {
    const xs = items.flatMap((item) => [item.x, item.x + item.width]);
    const ys = items.flatMap((item) => [item.y, item.y + item.height]);
    const [x, y] = [Math.min(...xs), Math.min(...ys)];
    return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

const boxOf = (item) => ({ x: item.x, y: item.y, w: item.width, h: item.height });

export class CompanyMap extends Component {
    static template = "pan_self_learning_blueprint.CompanyMap";
    static props = { ...standardActionServiceProps };
    static components = { Layout };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.svgRef = useRef("svg");
        this.bodyRef = useRef("body");
        this.geometry = { APP_CHIP_H, HEADER_H, STOP_COMPANY, STOP_DETAIL, MIN_ZOOM, MAX_ZOOM };
        const { params = {}, context = {} } = this.props.action;
        const contextId = !context.active_model || context.active_model === "project.project" ? context.active_id : false;
        this.projectId = params.project_id || params.active_id || contextId || false;
        this.sessionKey = `pan_sl_blueprint_map:${this.projectId}`;
        // Breadcrumb back: where the user was; page refresh: the session.
        const restored = (this.props.state && this.props.state.companyMap) || this.readSession();
        this.state = useState({
            loaded: false,
            flowId: restored.flowId || false,
            colorBy: COLOR_MODES.includes(restored.colorBy) ? restored.colorBy : "progress",
            selectedId: restored.selectedId || false,
            selectedRoleId: restored.selectedRoleId || false,
            zoom: restored.zoom || MIN_ZOOM,
            vx: restored.vx || 0,
            vy: restored.vy || 0,
            cw: 0, // container size in px
            ch: 0,
        });
        this.pendingCentre = restored.centre || null; // applied once the container is measured
        this.compact = window.innerWidth < NARROW_W;
        this.pointers = new Map();
        this.gesture = null;
        this.suppressClick = false;
        this.pressing = false;
        this.lastFocused = null;
        // Pan paints the camera straight onto the SVG and commits at the end.
        this.live = null;
        this.frame = null;
        this.wheelZoom = null;
        this.commitTimer = null;

        useSetupAction({
            getLocalState: () => ({
                companyMap: {
                    flowId: this.state.flowId,
                    colorBy: this.state.colorBy,
                    selectedId: this.state.selectedId,
                    selectedRoleId: this.state.selectedRoleId,
                    zoom: this.state.zoom,
                    ...this.camera,
                },
            }),
        });
        useExternalListener(window, "pointerup", () => (this.pressing = false));
        useHotkey("escape", () => this.closePanel(), {
            bypassEditableProtection: true,
            isAvailable: () => this.panelOpen,
        });
        onWillStart(() => this.projectId && this.load());
        onWillUnmount(() => {
            cancelAnimationFrame(this.frame);
            cancelAnimationFrame(this.wheelFrame);
            clearTimeout(this.commitTimer);
        });
        useEffect(
            (el) => {
                if (!el) {
                    return;
                }
                const update = () => {
                    this.commitPan();
                    const compact = el.clientWidth < NARROW_W;
                    if (compact !== this.compact) {
                        this.compact = compact;
                        this.computeLayouts();
                    }
                    this.state.cw = el.clientWidth;
                    this.state.ch = el.clientHeight;
                    if (this.pendingCentre && this.state.cw) {
                        const { w, h } = this.view;
                        this.state.vx = this.pendingCentre.x - w / 2;
                        this.state.vy = this.pendingCentre.y - h / 2;
                        this.pendingCentre = null;
                    }
                    this.clampView();
                };
                update();
                const observer = new ResizeObserver(update);
                observer.observe(el);
                return () => observer.disconnect();
            },
            () => [this.bodyRef.el]
        );
        useEffect(
            () => this.writeSession(),
            () => [this.state.zoom, this.state.vx, this.state.vy, this.state.flowId, this.state.colorBy]
        );
    }

    readSession() {
        try {
            return JSON.parse(browser.sessionStorage.getItem(this.sessionKey) || "{}");
        } catch {
            return {}; // blocked storage or a damaged value: start from the whole map
        }
    }

    writeSession() {
        if (!this.state.cw) {
            return; // not measured yet: the centre would be wrong
        }
        const { w, h } = this.view;
        const value = {
            zoom: this.state.zoom,
            centre: { x: this.state.vx + w / 2, y: this.state.vy + h / 2 },
            flowId: this.state.flowId,
            colorBy: this.state.colorBy,
        };
        try {
            browser.sessionStorage.setItem(this.sessionKey, JSON.stringify(value));
        } catch {
            // Storage blocked: the map still works, it just starts fresh.
        }
    }

    async load() {
        const data = await this.orm.call("project.project", "get_blueprint_map_data", [[this.projectId]]);
        this.data = data;
        this.roleById = new Map(data.roles.map((role) => [role.id, role]));
        this.phaseById = new Map(data.phases.map((phase) => [phase.id, phase]));
        this.flowById = new Map(data.flows.map((flow) => [flow.id, flow]));
        this.taskById = new Map(data.tasks.map((task) => [task.id, task]));
        this.computeLayouts();
        if (!this.flowById.has(this.state.flowId)) {
            this.state.flowId = false;
        }
        if (!this.taskById.has(this.state.selectedId)) {
            this.state.selectedId = false;
        }
        if (!this.roleById.has(this.state.selectedRoleId)) {
            this.state.selectedRoleId = false;
        }
        this.state.loaded = true;
    }

    computeLayouts() {
        this.layouts = Object.fromEntries(ALL_STOPS.map((stop) => [stop, computeLayout(this.data, stop, this.compact)]));
    }

    // ------------------------------------------------------------------
    // Camera
    // ------------------------------------------------------------------

    get stops() {
        return [_t("Company"), _t("Tasks"), _t("Detail")].map((label, index) => ({
            value: index + 1,
            label,
            zoom: STOP_THRESHOLDS[index],
            position: ((STOP_THRESHOLDS[index] - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * 100,
        }));
    }

    get stop() {
        return stopForZoom(this.state.zoom);
    }

    get stopLabel() {
        return this.stops[this.stop - 1].label;
    }

    get layout() {
        return this.layouts[this.stop];
    }

    /** Scale at which a stop's whole layout fits the container, kept readable. */
    fitOf(stop) {
        const layout = this.layouts[stop];
        if (!this.state.cw) {
            return 1;
        }
        const fit = Math.min(this.state.cw / layout.width, this.state.ch / layout.height);
        return Math.min(FIT_MAX_SCALE, Math.max(this.compact ? FIT_MIN_SCALE_NARROW : FIT_MIN_SCALE, fit));
    }

    /** The zoom-to-scale line, from the fit at MIN_ZOOM to the maximum at MAX_ZOOM. */
    baseScale(zoom) {
        const fit = this.fitOf(STOP_COMPANY);
        const max = Math.max(MAX_SCALE, fit * 1.5);
        return fit + ((zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * (max - fit);
    }

    /** Where the Tasks stop starts: at most where its whole layout fits, so a flow fits there. */
    get tasksStartScale() {
        return Math.min(this.baseScale(STOP_THRESHOLDS[1]), this.fitOf(STOP_TASKS));
    }

    /** Pixels per user unit: the base line, except the Tasks stop rises from tasksStartScale. */
    scaleFor(zoom) {
        if (stopForZoom(zoom) !== STOP_TASKS) {
            return this.baseScale(zoom);
        }
        const [from, to] = [STOP_THRESHOLDS[1], STOP_THRESHOLDS[2]];
        const start = this.tasksStartScale;
        return start + ((zoom - from) / (to - from)) * (this.baseScale(to) - start);
    }

    /** The zoom inside the Tasks stop that gives `scale`. */
    tasksZoomFor(scale) {
        const [from, to] = [STOP_THRESHOLDS[1], STOP_THRESHOLDS[2]];
        const start = this.tasksStartScale;
        const share = (scale - start) / (this.baseScale(to) - start);
        return Math.min(Math.max(from + share * (to - from), from), to - 0.01);
    }

    get scale() {
        return this.scaleFor(this.state.zoom);
    }

    viewAt(vx, vy) {
        const scale = this.scale;
        return { x: vx, y: vy, w: Math.max(this.state.cw, 1) / scale, h: Math.max(this.state.ch, 1) / scale };
    }

    get view() {
        return this.viewAt(this.state.vx, this.state.vy);
    }

    get viewBoxAttr() {
        const v = this.view;
        return `${v.x} ${v.y} ${v.w} ${v.h}`;
    }

    get camera() {
        return this.live || { vx: this.state.vx, vy: this.state.vy };
    }

    get panelOpen() {
        return Boolean(this.state.selectedId || this.state.selectedRoleId);
    }

    /** Screen pixels the open panel covers at the right (desktop) or bottom (phone). */
    get panelInsets() {
        if (!this.panelOpen) {
            return { right: 0, bottom: 0 };
        }
        if (browser.matchMedia(SMALL_SCREEN_MEDIA).matches) {
            return { right: 0, bottom: this.state.ch * SHEET_SHARE };
        }
        return { right: Math.min(PANEL_W, this.state.cw), bottom: 0 };
    }

    /** Keep the map in view: centred when narrower than the view, top-aligned when shorter. */
    clampValues(vx, vy) {
        const { w, h } = this.view;
        const { width, height } = this.layout;
        const insets = this.panelInsets;
        const freeW = w - insets.right / this.scale;
        const freeH = h - insets.bottom / this.scale;
        return {
            vx: width <= freeW ? (width - freeW) / 2 : Math.min(Math.max(vx, 0), width - freeW),
            vy: height <= freeH ? 0 : Math.min(Math.max(vy, 0), height - freeH),
        };
    }

    clampView() {
        Object.assign(this.state, this.clampValues(this.state.vx, this.state.vy));
    }

    /** Zoom, keeping the map point under (px, py) (container pixels) in place. */
    zoomAt(zoom, px = this.state.cw / 2, py = this.state.ch / 2) {
        this.commitPan();
        const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
        const from = this.layout;
        const world = { x: this.state.vx + px / this.scale, y: this.state.vy + py / this.scale };
        const to = this.layouts[stopForZoom(next)];
        const target = from === to ? world : mapPoint(from, to, world.x, world.y);
        this.state.zoom = next;
        this.state.vx = target.x - px / this.scale;
        this.state.vy = target.y - py / this.scale;
        this.clampView();
    }

    /** Zoom from the controls; a new stop always lands on content. */
    zoomTo(zoom) {
        const before = this.stop;
        this.zoomAt(zoom);
        if (this.stop !== before) {
            this.ensureContent();
        }
    }

    /** The free part of the view (user units): not under the sticky bands or the panel. */
    freeArea() {
        const { x, y, w, h } = this.view;
        const insets = this.panelInsets;
        const margin = 16 / this.scale;
        return {
            left: x + this.layout.labelW + margin,
            right: x + w - insets.right / this.scale - margin,
            top: y + HEADER_H + margin,
            bottom: y + h - insets.bottom / this.scale - margin,
        };
    }

    inView(item, area = this.freeArea()) {
        return item.x + item.width > area.left && item.x < area.right && item.y + item.height > area.top && item.y < area.bottom;
    }

    /** When nothing is in view, centre the item nearest the middle (phones: always land on one). */
    ensureContent() {
        const items = this.layout.items;
        const area = this.freeArea();
        if (!items.length || (!this.compact && items.some((item) => this.inView(item, area)))) {
            return;
        }
        const [mx, my] = [(area.left + area.right) / 2, (area.top + area.bottom) / 2];
        const distance = (item) => Math.hypot(item.x + item.width / 2 - mx, item.y + item.height / 2 - my);
        this.showBox(boxOf(items.reduce((best, item) => (distance(item) < distance(best) ? item : best))));
    }

    /** Centre a box in the free part of the view, or show its top-left when it does not fit. */
    showBox(box) {
        this.commitPan();
        const { w, h } = this.view;
        const insets = this.panelInsets;
        const labelW = this.layout.labelW;
        const freeW = w - labelW - insets.right / this.scale;
        const freeH = h - HEADER_H - insets.bottom / this.scale;
        this.state.vx = box.w + 2 * MARGIN <= freeW ? box.x + box.w / 2 - (labelW + freeW / 2) : box.x - labelW - MARGIN;
        this.state.vy = box.h + 2 * MARGIN <= freeH ? box.y + box.h / 2 - (HEADER_H + freeH / 2) : box.y - HEADER_H - MARGIN;
        this.clampView();
    }

    /** Pan as little as needed so the item sits in the free part of the view. */
    reveal(item) {
        this.commitPan();
        const area = this.freeArea();
        let { vx, vy } = this.state;
        if (item.x < area.left) {
            vx -= area.left - item.x;
        } else if (item.x + item.width > area.right) {
            vx += item.x + item.width - area.right;
        }
        if (item.y < area.top) {
            vy -= area.top - item.y;
        } else if (item.y + item.height > area.bottom) {
            vy += item.y + item.height - area.bottom;
        }
        Object.assign(this.state, this.clampValues(vx, vy));
    }

    pointInContainer(ev) {
        const rect = this.bodyRef.el.getBoundingClientRect();
        return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }

    /** Move the camera without a render; commitPan stores it. */
    panTo(vx, vy) {
        this.live = this.clampValues(vx, vy);
        if (!this.frame) {
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.paintLive();
            });
        }
    }

    commitPan() {
        clearTimeout(this.commitTimer);
        if (this.live) {
            cancelAnimationFrame(this.frame);
            this.frame = null;
            Object.assign(this.state, this.live);
            this.live = null;
        }
    }

    /** Paint the live camera onto the SVG: view box and the sticky bands. */
    paintLive() {
        const svg = this.svgRef.el;
        if (!this.live || !svg) {
            return;
        }
        const { vx, vy } = this.live;
        const v = this.viewAt(vx, vy);
        svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
        const [sx, sy] = [Math.max(vx, 0), Math.max(vy, 0)];
        svg.querySelector(".o_pan_sl_sticky_top")?.setAttribute("transform", `translate(0,${sy})`);
        svg.querySelector(".o_pan_sl_sticky_left")?.setAttribute("transform", `translate(${sx},0)`);
        svg.querySelector(".o_pan_sl_sticky_corner")?.setAttribute("transform", `translate(${sx},${sy})`);
        for (const label of svg.querySelectorAll(".o_pan_sl_role_label_group")) {
            const lane = this.layout.lanes[parseInt(label.dataset.lane, 10)];
            label.setAttribute("transform", `translate(0,${this.laneLabelY(lane, vy)})`);
        }
    }

    /** A role name stays in view inside a lane taller than the screen, but never leaves its lane. */
    laneLabelY(lane, vy = this.state.vy) {
        const bottom = lane.y + lane.height - (lane.role.is_external ? 24 : 8);
        return Math.max(lane.y + 22, Math.min(Math.max(vy, 0) + HEADER_H + 22, bottom));
    }

    get stickyX() {
        return Math.max(this.state.vx, 0);
    }

    get stickyY() {
        return Math.max(this.state.vy, 0);
    }

    // ------------------------------------------------------------------
    // Pointer, wheel and keyboard
    // ------------------------------------------------------------------

    onZoomInput(ev) {
        this.zoomTo(parseFloat(ev.target.value));
    }

    /** Slider arrows jump from stop to stop; Shift+arrow fine-tunes (native). */
    onZoomKeydown(ev) {
        const up = ["ArrowRight", "ArrowUp"].includes(ev.key);
        const down = ["ArrowLeft", "ArrowDown"].includes(ev.key);
        if ((!up && !down) || ev.shiftKey || ev.altKey || ev.ctrlKey || ev.metaKey) {
            return;
        }
        ev.preventDefault();
        const zoom = this.state.zoom;
        const target = up
            ? STOP_THRESHOLDS.find((t) => t > zoom + 1e-6) ?? MAX_ZOOM
            : [...STOP_THRESHOLDS].reverse().find((t) => t < zoom - 1e-6) ?? MIN_ZOOM;
        this.zoomTo(target);
    }

    onWheel(ev) {
        ev.preventDefault();
        if (!ev.ctrlKey && Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
            const { vx, vy } = this.camera;
            this.panTo(vx + ev.deltaX / this.scale, vy);
            clearTimeout(this.commitTimer);
            this.commitTimer = setTimeout(() => this.commitPan(), WHEEL_PAN_COMMIT_MS);
            return;
        }
        const pixels = ev.deltaY * (ev.deltaMode === 1 ? 20 : 1);
        const factor = Math.exp(-pixels * (ev.ctrlKey ? PINCH_WHEEL_SPEED : WHEEL_ZOOM_SPEED));
        const point = this.pointInContainer(ev);
        // At most one zoom (and render) per frame.
        if (this.wheelZoom) {
            this.wheelZoom.factor *= factor;
            this.wheelZoom.point = point;
            return;
        }
        this.wheelZoom = { factor, point };
        this.wheelFrame = requestAnimationFrame(() => {
            const { factor, point } = this.wheelZoom;
            this.wheelZoom = null;
            this.zoomAt(this.state.zoom * factor, point.x, point.y);
        });
    }

    /** Arrows pan (Shift: further), + and - zoom, Home fits the whole map. */
    onMapKeydown(ev) {
        if (ev.altKey || ev.ctrlKey || ev.metaKey) {
            return;
        }
        const step = (KEY_PAN_PX * (ev.shiftKey ? 3 : 1)) / this.scale;
        const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (ev.key in moves) {
            this.commitPan();
            const [dx, dy] = moves[ev.key];
            Object.assign(this.state, this.clampValues(this.state.vx + dx, this.state.vy + dy));
        } else if (ev.key === "+" || ev.key === "=") {
            this.zoomTo(this.state.zoom + KEY_ZOOM_STEP);
        } else if (ev.key === "-" || ev.key === "_") {
            this.zoomTo(this.state.zoom - KEY_ZOOM_STEP);
        } else if (ev.key === "Home") {
            this.commitPan();
            Object.assign(this.state, { zoom: MIN_ZOOM, vx: 0, vy: 0 });
            this.clampView();
        } else {
            return;
        }
        ev.preventDefault();
    }

    /** Keyboard focus on a block or chip moves the camera so it is not hidden. */
    onMapFocusin(ev) {
        const key = ev.target.dataset && ev.target.dataset.item;
        const item = key && this.layout.items.find((candidate) => candidate.key === key);
        if (item && !this.pressing) {
            this.reveal(item);
        }
    }

    onActivateKey(ev, activate) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            ev.stopPropagation();
            activate();
        }
    }

    // Drag to pan (mouse, pen, touch); two fingers pinch to zoom.
    onPointerDown(ev) {
        if (ev.pointerType === "mouse" && ev.button !== 0) {
            return;
        }
        this.pressing = true;
        this.pointers.set(ev.pointerId, this.pointInContainer(ev));
        if (this.pointers.size === 2) {
            this.commitPan();
            const [a, b] = [...this.pointers.values()];
            this.gesture = { type: "pinch", distance: Math.hypot(a.x - b.x, a.y - b.y), zoom: this.state.zoom };
            this.svgRef.el.setPointerCapture(ev.pointerId);
        } else if (this.pointers.size === 1) {
            this.gesture = { type: "press", start: this.pointers.get(ev.pointerId), ...this.camera };
        }
    }

    onPointerMove(ev) {
        if (!this.pointers.has(ev.pointerId) || !this.gesture) {
            return;
        }
        const point = this.pointInContainer(ev);
        this.pointers.set(ev.pointerId, point);
        const gesture = this.gesture;
        if (gesture.type === "pinch") {
            const [a, b] = [...this.pointers.values()];
            if (gesture.distance > 0) {
                const distance = Math.hypot(a.x - b.x, a.y - b.y);
                this.zoomAt(gesture.zoom * (distance / gesture.distance), (a.x + b.x) / 2, (a.y + b.y) / 2);
            }
            return;
        }
        const [dx, dy] = [point.x - gesture.start.x, point.y - gesture.start.y];
        if (gesture.type === "press" && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
            // Capture only once it is a drag, so a plain click still reaches the chip.
            gesture.type = "pan";
            this.svgRef.el.setPointerCapture(ev.pointerId);
        }
        if (gesture.type === "pan") {
            this.panTo(gesture.vx - dx / this.scale, gesture.vy - dy / this.scale);
        }
    }

    onPointerUp(ev) {
        this.pressing = false;
        if (!this.pointers.delete(ev.pointerId)) {
            return;
        }
        if (this.gesture && this.gesture.type !== "press") {
            this.suppressClick = true;
        }
        if (this.svgRef.el && this.svgRef.el.hasPointerCapture(ev.pointerId)) {
            this.svgRef.el.releasePointerCapture(ev.pointerId);
        }
        if (!this.pointers.size) {
            this.gesture = null;
            this.commitPan();
        } else if (this.gesture && this.gesture.type === "pinch") {
            // One finger left after a pinch: continue as a pan.
            const [start] = [...this.pointers.values()];
            this.gesture = { type: "pan", start, vx: this.state.vx, vy: this.state.vy };
        }
    }

    /** Swallow the click that ends a drag or pinch. */
    onClickCapture(ev) {
        if (this.suppressClick) {
            this.suppressClick = false;
            ev.stopPropagation();
            ev.preventDefault();
        }
    }

    // ------------------------------------------------------------------
    // Labels, colours and dimming
    // ------------------------------------------------------------------

    get rungLabels() {
        return [_t("Open"), _t("Decided"), _t("Built"), _t("Tested"), _t("Trained"), _t("Live")];
    }

    get levelLabels() {
        return {
            open: _t("Open"),
            building: _t("Decided or built"),
            tested: _t("Tested or further"),
            trained: _t("Trained"),
            to_train: _t("Still to train"),
            no_people: _t("Nobody in the role"),
        };
    }

    get legend() {
        return MODE_LEVELS[this.state.colorBy].map((key) => ({
            key,
            label: this.levelLabels[key],
            className: toneClass(TONES[key]),
            glyph: toneGlyph(TONES[key], 9, 6, 4.5),
        }));
    }

    level(task) {
        return this.state.colorBy === "progress"
            ? progressLevel(task.rung)
            : trainingLevel(task, this.roleById.get(task.role_id));
    }

    dot(task, cx, cy, r = 5.5) {
        const tone = TONES[this.level(task)];
        return { cx, cy, r, className: toneClass(tone), glyph: toneGlyph(tone, cx, cy, r) };
    }

    get selectedFlow() {
        return this.state.flowId ? this.flowById.get(this.state.flowId) : false;
    }

    isDimmed(task) {
        const flow = this.selectedFlow;
        return Boolean(flow) && !flow.task_ids.includes(task.id);
    }

    hours(task) {
        if (!task.planned_hours && !task.spent_hours) {
            return "";
        }
        return _t("%(planned)s planned · %(spent)s spent", {
            planned: formatFloatTime(task.planned_hours),
            spent: formatFloatTime(task.spent_hours),
        });
    }

    chipAriaLabel(chip) {
        const task = chip.task;
        const flow = this.flowById.get(task.flow_id);
        return [
            task.name,
            flow && flow.name,
            this.phaseById.get(task.phase_id).name,
            chip.role.name,
            this.rungLabels[task.rung],
            this.levelLabels[this.level(task)],
        ]
            .filter(Boolean)
            .join(", ");
    }

    /** Detail stop: rung and hours (spent of planned), assignees, first line of the description (computed once per chip). */
    detailLines(chip) {
        if (!chip.lines) {
            const { task, width } = chip;
            const hours = task.planned_hours || task.spent_hours
                ? _t("%(spent)s of %(planned)s h", {
                      spent: formatFloatTime(task.spent_hours),
                      planned: formatFloatTime(task.planned_hours),
                  })
                : "";
            chip.lines = [
                { key: "rung", text: this.rungLabels[task.rung], hours, hoursTitle: this.hours(task) },
                { key: "users", text: truncate(task.user_names.join(", "), width - 20, SMALL_CHAR_W) },
                { key: "desc", text: truncate(task.description || "", width - 20, SMALL_CHAR_W), muted: true },
            ].map((line, index) => ({ ...line, y: 36 + index * LINE_H }));
        }
        return chip.lines;
    }

    /** Company stop: the cell as stacked segments per status level, with its count. */
    blockView(block) {
        const counts = new Map();
        for (const task of block.tasks) {
            const level = this.level(task);
            counts.set(level, (counts.get(level) || 0) + 1);
        }
        const total = block.tasks.length;
        let x = block.x;
        const levels = MODE_LEVELS[this.state.colorBy].filter((level) => counts.has(level));
        const segments = levels.map((level) => {
            const width = (block.width * counts.get(level)) / total;
            const tone = TONES[level];
            const segment = {
                key: level,
                x,
                width,
                className: toneClass(tone),
                glyph: width >= 18 ? toneGlyph(tone, x + 9, block.y + 9, 5) : false,
            };
            x += width;
            return segment;
        });
        const summary = levels.map((level) => `${counts.get(level)} ${this.levelLabels[level]}`).join(", ");
        return {
            segments,
            count: total,
            dim: block.tasks.every((task) => this.isDimmed(task)),
            clipId: `o_pan_sl_clip_${block.key}`,
            title: _t("%(role)s in %(phase)s: %(count)s tasks (%(summary)s)", {
                role: block.role.name,
                phase: block.phase.name,
                count: total,
                summary,
            }),
        };
    }

    /** Spoken when the flow filter changes (aria-live). */
    get flowAnnouncement() {
        const flow = this.selectedFlow;
        if (!flow) {
            return _t("Showing all tasks");
        }
        return _t("Showing flow %(name)s, %(count)s tasks", { name: flow.name, count: flow.task_ids.length });
    }

    // ------------------------------------------------------------------
    // Controls
    // ------------------------------------------------------------------

    onFlowChange(ev) {
        this.selectFlow(ev.target.value ? parseInt(ev.target.value, 10) : false);
    }

    /** Select a flow: the Tasks stop, zoomed so all of its tasks are in view. */
    selectFlow(flowId) {
        this.state.flowId = flowId;
        if (!flowId) {
            return;
        }
        this.commitPan();
        const layout = this.layouts[STOP_TASKS];
        const chips = this.selectedFlow.task_ids.map((id) => layout.chipById.get(id)).filter(Boolean);
        if (!chips.length) {
            this.state.zoom = STOP_THRESHOLDS[1];
            this.clampView();
            return;
        }
        const box = boundingBox(chips);
        const insets = this.panelInsets;
        const fit = Math.min(
            (this.state.cw - insets.right) / (box.w + layout.labelW + 2 * MARGIN),
            (this.state.ch - insets.bottom) / (box.h + HEADER_H + 2 * MARGIN)
        );
        this.state.zoom = this.tasksZoomFor(fit);
        // Too long for this screen even at the start of the stop (a phone): begin at its first task.
        this.showBox(fit >= this.tasksStartScale ? box : boxOf(chips[0]));
    }

    onColorByChange(ev) {
        this.state.colorBy = ev.target.value;
    }

    /** Company stop: a cell zooms in to the Tasks stop on that cell. */
    onBlockClick(block) {
        this.commitPan();
        this.state.zoom = this.tasksZoomFor(this.baseScale(STOP_THRESHOLDS[1]));
        const chips = this.layout.chips.filter((chip) => chip.role.id === block.role.id && chip.task.phase_id === block.phase.id);
        this.showBox(boundingBox(chips));
    }

    // ------------------------------------------------------------------
    // Panels
    // ------------------------------------------------------------------

    openPanel(taskId = false, roleId = false) {
        if (!this.panelOpen) {
            this.lastFocused = document.activeElement;
        }
        Object.assign(this.state, { selectedId: taskId, selectedRoleId: roleId });
        const chip = taskId && this.layout.chipById.get(taskId);
        if (chip) {
            this.reveal(chip);
        }
        // Focus moves to the panel title once it is rendered.
        browser.requestAnimationFrame(() => this.bodyRef.el?.querySelector(".o_pan_sl_panel_title")?.focus({ preventScroll: true }));
    }

    closePanel() {
        Object.assign(this.state, { selectedId: false, selectedRoleId: false });
        this.clampView();
        if (this.lastFocused && this.lastFocused.isConnected) {
            this.lastFocused.focus({ preventScroll: true });
        }
        this.lastFocused = null;
    }

    get panel() {
        const task = this.state.selectedId && this.taskById.get(this.state.selectedId);
        if (!task) {
            return false;
        }
        const tone = TONES[progressLevel(task.rung)];
        return {
            task,
            flow: this.flowById.get(task.flow_id),
            role: this.roleById.get(task.role_id),
            phase: this.phaseById.get(task.phase_id),
            rungLabel: this.rungLabels[task.rung],
            rungDot: { cx: 7, cy: 7, r: 5.5, className: toneClass(tone), glyph: toneGlyph(tone, 7, 7, 5.5) },
            hours: this.hours(task),
        };
    }

    get rolePanel() {
        const role = this.state.selectedRoleId && this.roleById.get(this.state.selectedRoleId);
        if (!role) {
            return false;
        }
        const bands = { high: _t("High"), medium: _t("Medium"), low: _t("Low") };
        return {
            role,
            adkarBand: role.adkar ? bands[role.adkar] : false,
            taskCount: this.data.tasks.filter((task) => task.role_id === role.id).length,
        };
    }

    openTask() {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: this.state.selectedId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openUnplaced() {
        const action = await this.orm.call("project.project", "action_blueprint_unplaced_tasks", [[this.projectId]]);
        await this.actionService.doAction(action);
    }
}

registry.category("actions").add("pan_sl_blueprint_map", CompanyMap);
