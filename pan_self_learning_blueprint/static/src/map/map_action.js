import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// ----------------------------------------------------------------------
// Semantic zoom: four stops, each with its own geometry (SVG user units)
// and its own physical scale (screen pixels per user unit).
// ----------------------------------------------------------------------

export const STOP_COMPANY = 1;
export const STOP_PROCESSES = 2;
export const STOP_ACTIVITIES = 3;
export const STOP_DETAIL = 4;
const ALL_STOPS = [STOP_COMPANY, STOP_PROCESSES, STOP_ACTIVITIES, STOP_DETAIL];

const STOP_GEOMETRY = {
    [STOP_COMPANY]: { labelW: 150, colW: 150, headerH: 56, chipH: 34, chipGap: 0, lanePad: 8 },
    [STOP_PROCESSES]: { labelW: 160, colW: 186, headerH: 36, chipH: 28, chipGap: 6, lanePad: 10 },
    [STOP_ACTIVITIES]: { labelW: 160, colW: 206, headerH: 36, chipH: 48, chipGap: 8, lanePad: 10 },
    [STOP_DETAIL]: { labelW: 160, colW: 226, headerH: 36, chipH: 48, chipGap: 10, lanePad: 10 },
};

// Zoom is continuous from MIN_ZOOM (fit) to MAX_ZOOM. The four stops are
// thresholds on that factor: content switches when the zoom crosses them.
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;
export const STOP_THRESHOLDS = [1, 1.75, 2.5, 3.25]; // zoom where stop 1..4 starts
// Pixels per user unit: the fit scale at MIN_ZOOM, growing linearly to
// MAX_SCALE at MAX_ZOOM (layouts differ per stop, so the scale is per unit
// of the current stop's layout, which keeps text sizes steady).
const MAX_SCALE = 1.6;
const FIT_MIN_SCALE = 0.55; // below this text gets unreadable: pan instead
const FIT_MAX_SCALE = 1.25;
const CULL_MARGIN = 200; // user units around the view that still get chips
const DRAG_THRESHOLD = 4; // px before a press becomes a pan
const DOUBLE_CLICK_ZOOM = 0.75;

const PROGRESS_H = 40;
const CHIP_INSET = 8; // chip inset within its column
const CHAR_W = 6.4; // average glyph width at 12px
const SMALL_CHAR_W = 5.6; // at 10.5px
const APP_CHIP_H = 20;
const APP_CHIP_GAP = 4;
const APP_CHAR_W = 6.2;
const ODOO_PAD = 10;
const LINE_H = 15; // detail lines under a chip (stop 4)
const MAX_TASK_LINES = 3;
const MAX_INITIALS = 3;
const INITIAL_STEP = 17;

const TESTED_RUNG = 3;
const MAX_RUNG = 5;
const WHEEL_ZOOM_SPEED = 0.0015; // zoom factor change per wheel pixel (exponential)
const PINCH_WHEEL_SPEED = 0.01; // trackpad pinch arrives as ctrl + wheel with small deltas

const CHOICE_STATES = ["proposal", "provisional", "fixed", "revised"];
const OPEN_CHOICES = ["proposal", "provisional"];
const RUNGS = [0, 1, 2, 3, 4, 5];
const PEOPLE_LEVELS = ["ready", "partly", "not_ready", "no_data"];

// Status tone per colour-by mode: ok green, warn amber, danger red, off grey;
// level 1-3 is how strong the tint is, dashed marks "nothing decided yet".
const CHOICE_TONES = {
    proposal: { tone: "off", level: 2, dashed: true },
    provisional: { tone: "warn", level: 2 },
    fixed: { tone: "ok", level: 2 },
    revised: { tone: "danger", level: 2 },
};
const RUNG_TONES = [
    { tone: "off", level: 2 },
    { tone: "warn", level: 1 },
    { tone: "warn", level: 2 },
    { tone: "ok", level: 1 },
    { tone: "ok", level: 2 },
    { tone: "ok", level: 3 },
];
const PEOPLE_TONES = {
    ready: { tone: "ok", level: 2 },
    partly: { tone: "warn", level: 2 },
    not_ready: { tone: "danger", level: 2 },
    no_data: { tone: "off", level: 2 },
};

export function toneClass({ tone, level, dashed }) {
    return `o_pan_sl_tone_${tone} o_pan_sl_lvl_${level}${dashed ? " o_pan_sl_dashed" : ""}`;
}

function truncate(text, length) {
    if (!text || text.length <= length) {
        return text || "";
    }
    return `${text.slice(0, Math.max(length - 1, 1))}…`;
}

function charsFor(width, charWidth = CHAR_W) {
    return Math.max(Math.floor(width / charWidth), 3);
}

export function initials(name) {
    const words = (name || "").split(/\s+/).filter(Boolean);
    if (!words.length) {
        return "?";
    }
    const letters =
        words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[words.length - 1][0];
    return letters.toUpperCase();
}

/**
 * A clash: a choice that was fixed and had to be reopened (revised), or a
 * fixed choice that still carries an open point.
 */
export function isClash(activity) {
    return (
        activity.choice_state === "revised" ||
        (activity.choice_state === "fixed" && Boolean(activity.open_point))
    );
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

/** Number of detail lines under a chip at stop 4: tasks (or "none"), "+n more", click path. */
function detailLineCount(detail) {
    const taskCount = detail ? detail.tasks.length : 0;
    const taskLines = Math.max(1, Math.min(taskCount, MAX_TASK_LINES));
    return taskLines + (taskCount > MAX_TASK_LINES ? 1 : 0) + 1;
}

/** Height of one chip at a stop; at stop 4 it grows with its detail lines. */
function chipHeight(stop, detail) {
    const geo = STOP_GEOMETRY[stop];
    if (stop !== STOP_DETAIL) {
        return geo.chipH;
    }
    return geo.chipH + 8 + detailLineCount(detail) * LINE_H;
}

/**
 * Compute the static geometry of the map for one zoom stop. Colours,
 * dimming and the route depend on the controls and are applied at render.
 */
export function computeLayout(data, details, stop) {
    const geo = STOP_GEOMETRY[stop];
    const { labelW, colW, headerH, lanePad } = geo;
    const chipW = colW - 2 * CHIP_INSET;
    const phases = data.phases;
    const roles = orderRoles(data.roles);
    const phaseIndex = new Map(phases.map((phase, index) => [phase.id, index]));
    const width = labelW + Math.max(phases.length, 1) * colW;
    const progressTop = headerH;
    const lanesTop = headerH + PROGRESS_H;

    // Activities per cell (role x phase), in server order (sequence).
    const cells = new Map();
    for (const activity of data.activities) {
        const key = `${activity.role_id}-${activity.phase_id}`;
        if (!cells.has(key)) {
            cells.set(key, []);
        }
        cells.get(key).push(activity);
    }

    // Header: phase names, plus open choices and clashes per phase (stop 1).
    const columns = phases.map((phase, index) => {
        const inPhase = data.activities.filter((a) => a.phase_id === phase.id);
        return {
            phase,
            x: labelW + index * colW,
            label: truncate(phase.name, charsFor(colW - 16, 7)),
            open: inPhase.filter((a) => OPEN_CHOICES.includes(a.choice_state)).length,
            clashes: inPhase.filter(isClash).length,
        };
    });

    // Progress band: share of activities per phase at rung Tested or higher.
    const progress = phases.map((phase, index) => {
        const inPhase = data.activities.filter((a) => a.phase_id === phase.id);
        const done = inPhase.filter((a) => a.rung >= TESTED_RUNG).length;
        const share = inPhase.length ? done / inPhase.length : 0;
        const trackW = colW - 64;
        return {
            id: phase.id,
            x: labelW + index * colW,
            trackW,
            barWidth: trackW * share,
            percent: inPhase.length ? `${Math.round(share * 100)}%` : "–",
            title: inPhase.length
                ? _t("%(percent)s tested or further (%(done)s of %(total)s activities)", {
                      percent: `${Math.round(share * 100)}%`,
                      done,
                      total: inPhase.length,
                  })
                : _t("No activities in this phase"),
        };
    });

    // Role lanes; their height follows the fullest cell at this stop.
    let y = lanesTop;
    const lanes = [];
    const chips = [];
    const blocks = [];
    for (const role of roles) {
        let laneContent = geo.chipH;
        if (stop !== STOP_COMPANY) {
            for (const phase of phases) {
                const cellActivities = cells.get(`${role.id}-${phase.id}`) || [];
                const total = cellActivities.reduce(
                    (sum, activity) => sum + chipHeight(stop, details.get(activity.id)),
                    0
                );
                laneContent = Math.max(
                    laneContent,
                    total + Math.max(cellActivities.length - 1, 0) * geo.chipGap
                );
            }
        }
        const height = Math.max(laneContent + lanePad * 2, 50);
        lanes.push({
            role,
            y,
            height,
            label: truncate(role.name, charsFor(labelW - 20, 6.8)),
        });
        for (const phase of phases) {
            const cellActivities = cells.get(`${role.id}-${phase.id}`) || [];
            if (!cellActivities.length) {
                continue;
            }
            const cellX = labelW + phaseIndex.get(phase.id) * colW + CHIP_INSET;
            if (stop === STOP_COMPANY) {
                blocks.push({
                    key: `${role.id}-${phase.id}`,
                    role,
                    phase,
                    activities: cellActivities,
                    x: cellX,
                    y: y + (height - geo.chipH) / 2,
                    width: chipW,
                    height: geo.chipH,
                });
                continue;
            }
            let chipY = y + lanePad;
            for (const activity of cellActivities) {
                const detail = details.get(activity.id);
                const chipH = chipHeight(stop, detail);
                chips.push({
                    id: activity.id,
                    activity,
                    role,
                    detail,
                    x: cellX,
                    y: chipY,
                    width: chipW,
                    height: chipH,
                    cx: cellX + chipW / 2,
                    cy: chipY + geo.chipH / 2,
                    label: truncate(activity.name, charsFor(chipW - (stop === STOP_PROCESSES ? 32 : 50))),
                });
                chipY += chipH + geo.chipGap;
            }
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
        const maxRowWidth = colW - 2 * ODOO_PAD;
        for (const app of phase.apps) {
            const chipWidth = Math.min(maxRowWidth, app.length * APP_CHAR_W + 18);
            if (rowX > 0 && rowX + chipWidth > maxRowWidth) {
                row += 1;
                rowX = 0;
            }
            apps.push({
                key: `${phase.id}-${app}`,
                label: truncate(app, charsFor(chipWidth - 14, APP_CHAR_W)),
                title: app,
                x: labelW + index * colW + ODOO_PAD + rowX,
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
        stop,
        width,
        height,
        labelW,
        colW,
        chipW,
        headerH,
        progressTop,
        lanesTop,
        lanesBottom,
        odooHeight,
        columns,
        progress,
        lanes,
        chips,
        blocks,
        chipById: new Map(chips.map((chip) => [chip.id, chip])),
        apps,
        totals: {
            open: data.activities.filter((a) => OPEN_CHOICES.includes(a.choice_state)).length,
            clashes: data.activities.filter(isClash).length,
        },
    };
}

export function stopForZoom(zoom) {
    let stop = STOP_COMPANY;
    STOP_THRESHOLDS.forEach((threshold, index) => {
        if (zoom >= threshold - 1e-6) {
            stop = index + 1;
        }
    });
    return stop;
}

/**
 * Map a point from one stop's layout to another's, through the fixed grid:
 * the same phase column and role lane, at the same relative position.
 */
export function mapPoint(from, to, x, y) {
    let nx;
    if (x < from.labelW) {
        nx = (x / from.labelW) * to.labelW;
    } else {
        nx = to.labelW + ((x - from.labelW) / from.colW) * to.colW;
    }
    let ny;
    if (y < from.lanesTop) {
        ny = (y / from.lanesTop) * to.lanesTop;
    } else if (y >= from.lanesBottom) {
        ny = to.lanesBottom + ((y - from.lanesBottom) / from.odooHeight) * to.odooHeight;
    } else {
        const index = from.lanes.findIndex((lane) => y < lane.y + lane.height);
        const lane = from.lanes[index];
        const target = to.lanes[index];
        ny = target.y + ((y - lane.y) / lane.height) * target.height;
    }
    return { x: nx, y: ny };
}

export class CompanyMap extends Component {
    static template = "pan_self_learning_blueprint.CompanyMap";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.svgRef = useRef("svg");
        this.bodyRef = useRef("body");
        this.geometry = {
            PROGRESS_H,
            APP_CHIP_H,
            DETAIL_CHIP_H: STOP_GEOMETRY[STOP_DETAIL].chipH,
            STOP_COMPANY,
            STOP_PROCESSES,
            STOP_ACTIVITIES,
            STOP_DETAIL,
            MIN_ZOOM,
            MAX_ZOOM,
        };
        // The camera: zoom factor and the top-left of the view in user units
        // of the current stop's layout; cw/ch is the container size in px.
        this.state = useState({
            loaded: false,
            scenarioId: false,
            colorBy: "choices",
            selectedId: false,
            zoom: MIN_ZOOM,
            vx: 0,
            vy: 0,
            cw: 0,
            ch: 0,
        });
        this.pointers = new Map(); // active pointers, for drag and pinch
        this.gesture = null;
        this.suppressClick = false;
        this.lastFocused = null;

        useHotkey("escape", () => this.closePanel(), {
            bypassEditableProtection: true,
            isAvailable: () => Boolean(this.state.selectedId),
        });

        onWillStart(async () => {
            const [data, details] = await Promise.all([
                this.orm.call("pan.sl.activity", "get_map_data", []),
                this.orm.call("pan.sl.activity", "get_map_details", []),
            ]);
            this.data = data;
            this.details = new Map(details.map((detail) => [detail.id, detail]));
            this.roleById = new Map(data.roles.map((role) => [role.id, role]));
            this.scenarioById = new Map(data.scenarios.map((s) => [s.id, s]));
            this.layouts = Object.fromEntries(
                ALL_STOPS.map((stop) => [stop, computeLayout(data, this.details, stop)])
            );
            this.state.loaded = true;
        });

        // Track the container size; the fit scale and the view follow it.
        useEffect(
            (el) => {
                if (!el) {
                    return;
                }
                const update = () => {
                    this.state.cw = el.clientWidth;
                    this.state.ch = el.clientHeight;
                    this.clampView();
                };
                update();
                const observer = new ResizeObserver(update);
                observer.observe(el);
                return () => observer.disconnect();
            },
            () => [this.bodyRef.el]
        );
    }

    // ------------------------------------------------------------------
    // Camera: zoom, scale, view box
    // ------------------------------------------------------------------

    get stops() {
        return [
            { value: STOP_COMPANY, label: _t("Company"), hint: _t("Are we on track, where is it stuck?") },
            { value: STOP_PROCESSES, label: _t("Processes"), hint: _t("What happens where?") },
            { value: STOP_ACTIVITIES, label: _t("Activities"), hint: _t("Who, how far, what is open?") },
            { value: STOP_DETAIL, label: _t("Detail"), hint: _t("What exactly?") },
        ].map((stop) => ({
            ...stop,
            zoom: STOP_THRESHOLDS[stop.value - 1],
            position: ((STOP_THRESHOLDS[stop.value - 1] - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * 100,
        }));
    }

    get stop() {
        return stopForZoom(this.state.zoom);
    }

    get currentStop() {
        return this.stops[this.stop - 1];
    }

    get layout() {
        return this.layouts[this.stop];
    }

    get fitScale() {
        const layout = this.layouts[STOP_COMPANY];
        if (!this.state.cw) {
            return 1;
        }
        const fit = Math.min(this.state.cw / layout.width, this.state.ch / layout.height);
        return Math.min(FIT_MAX_SCALE, Math.max(FIT_MIN_SCALE, fit));
    }

    /** Pixels per user unit at a zoom factor. */
    scaleFor(zoom) {
        const fit = this.fitScale;
        const max = Math.max(MAX_SCALE, fit * 1.5);
        return fit + ((zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * (max - fit);
    }

    get scale() {
        return this.scaleFor(this.state.zoom);
    }

    get view() {
        const scale = this.scale;
        return {
            x: this.state.vx,
            y: this.state.vy,
            w: Math.max(this.state.cw, 1) / scale,
            h: Math.max(this.state.ch, 1) / scale,
        };
    }

    get viewBoxAttr() {
        const v = this.view;
        return `${v.x} ${v.y} ${v.w} ${v.h}`;
    }

    /** Map width in screen pixels at the current zoom (for checks and the wider-than-view test). */
    get mapPixelWidth() {
        return Math.round(this.layout.width * this.scale);
    }

    /** Keep the map in view: centred when narrower than the view, top-aligned when shorter. */
    clampView() {
        const { w, h } = this.view;
        const layout = this.layout;
        this.state.vx =
            layout.width <= w ? (layout.width - w) / 2 : Math.min(Math.max(this.state.vx, 0), layout.width - w);
        this.state.vy = layout.height <= h ? 0 : Math.min(Math.max(this.state.vy, 0), layout.height - h);
    }

    /** Zoom to `zoom`, keeping the map point under (px, py) (container pixels) in place. */
    zoomAt(zoom, px = this.state.cw / 2, py = this.state.ch / 2) {
        const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
        const from = this.layout;
        const oldScale = this.scale;
        const world = { x: this.state.vx + px / oldScale, y: this.state.vy + py / oldScale };
        const to = this.layouts[stopForZoom(next)];
        const target = from === to ? world : mapPoint(from, to, world.x, world.y);
        this.state.zoom = next;
        const newScale = this.scale;
        this.state.vx = target.x - px / newScale;
        this.state.vy = target.y - py / newScale;
        this.clampView();
    }

    /**
     * Centre a box (user units of the current layout) in the part of the view
     * not covered by the sticky header and label column, or show its
     * top-left when it does not fit.
     */
    showBox(box) {
        const { w, h } = this.view;
        const layout = this.layout;
        const margin = 24;
        const freeW = w - layout.labelW;
        const freeH = h - layout.lanesTop;
        this.state.vx =
            box.w + 2 * margin <= freeW
                ? box.x + box.w / 2 - (layout.labelW + freeW / 2)
                : box.x - layout.labelW - margin;
        this.state.vy =
            box.h + 2 * margin <= freeH
                ? box.y + box.h / 2 - (layout.lanesTop + freeH / 2)
                : box.y - layout.lanesTop - margin;
        this.clampView();
    }

    pointInContainer(ev) {
        const rect = this.bodyRef.el.getBoundingClientRect();
        return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }

    onZoomInput(ev) {
        this.zoomAt(parseFloat(ev.target.value));
    }

    onWheel(ev) {
        ev.preventDefault();
        const point = this.pointInContainer(ev);
        if (!ev.ctrlKey && Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
            // Sideways trackpad swipe: pan.
            this.state.vx += ev.deltaX / this.scale;
            this.clampView();
            return;
        }
        const pixels = ev.deltaY * (ev.deltaMode === 1 ? 20 : 1);
        const speed = ev.ctrlKey ? PINCH_WHEEL_SPEED : WHEEL_ZOOM_SPEED;
        this.zoomAt(this.state.zoom * Math.exp(-pixels * speed), point.x, point.y);
    }

    onDoubleClick(ev) {
        if (ev.target.closest(".o_pan_sl_chip")) {
            return;
        }
        const point = this.pointInContainer(ev);
        this.zoomAt(this.state.zoom + DOUBLE_CLICK_ZOOM, point.x, point.y);
    }

    // Drag to pan (mouse, pen and touch); two fingers pinch to zoom.
    onPointerDown(ev) {
        if (ev.pointerType === "mouse" && ev.button !== 0) {
            return;
        }
        this.pointers.set(ev.pointerId, this.pointInContainer(ev));
        if (this.pointers.size === 2) {
            const [a, b] = [...this.pointers.values()];
            this.gesture = {
                type: "pinch",
                distance: Math.hypot(a.x - b.x, a.y - b.y),
                zoom: this.state.zoom,
            };
            this.svgRef.el.setPointerCapture(ev.pointerId);
        } else if (this.pointers.size === 1) {
            const point = this.pointers.get(ev.pointerId);
            this.gesture = {
                type: "press",
                pointerId: ev.pointerId,
                start: point,
                vx: this.state.vx,
                vy: this.state.vy,
            };
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
            const distance = Math.hypot(a.x - b.x, a.y - b.y);
            if (gesture.distance > 0) {
                this.zoomAt(gesture.zoom * (distance / gesture.distance), (a.x + b.x) / 2, (a.y + b.y) / 2);
            }
            return;
        }
        const dx = point.x - gesture.start.x;
        const dy = point.y - gesture.start.y;
        if (gesture.type === "press" && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
            // Capture only once it is a drag, so a plain click still reaches the chip.
            gesture.type = "pan";
            this.svgRef.el.setPointerCapture(ev.pointerId);
        }
        if (gesture.type === "pan") {
            this.state.vx = gesture.vx - dx / this.scale;
            this.state.vy = gesture.vy - dy / this.scale;
            this.clampView();
        }
    }

    onPointerUp(ev) {
        if (!this.pointers.has(ev.pointerId)) {
            return;
        }
        this.pointers.delete(ev.pointerId);
        if (this.gesture && (this.gesture.type === "pan" || this.gesture.type === "pinch")) {
            this.suppressClick = true;
        }
        if (this.svgRef.el && this.svgRef.el.hasPointerCapture(ev.pointerId)) {
            this.svgRef.el.releasePointerCapture(ev.pointerId);
        }
        if (!this.pointers.size) {
            this.gesture = null;
        } else if (this.gesture && this.gesture.type === "pinch") {
            // One finger left after a pinch: continue as a pan from here.
            const [[pointerId, point]] = [...this.pointers.entries()];
            this.gesture = { type: "pan", pointerId, start: point, vx: this.state.vx, vy: this.state.vy };
        }
    }

    /** Capture-phase click: swallow the click that ends a drag or pinch. */
    onClickCapture(ev) {
        if (this.suppressClick) {
            this.suppressClick = false;
            ev.stopPropagation();
            ev.preventDefault();
        }
    }

    // ------------------------------------------------------------------
    // Culling: only what is in view (plus a margin) gets rendered
    // ------------------------------------------------------------------

    intersectsView(item) {
        const v = this.view;
        return (
            item.x + item.width >= v.x - CULL_MARGIN &&
            item.x <= v.x + v.w + CULL_MARGIN &&
            item.y + item.height >= v.y - CULL_MARGIN &&
            item.y <= v.y + v.h + CULL_MARGIN
        );
    }

    get visibleChips() {
        return this.layout.chips.filter((chip) => this.intersectsView(chip));
    }

    get visibleBlocks() {
        return this.layout.blocks.filter((block) => this.intersectsView(block));
    }

    /** Sticky header and label column: they follow the view like map labels. */
    get stickyX() {
        return Math.max(this.state.vx, 0);
    }

    get stickyY() {
        return Math.max(this.state.vy, 0);
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
                className: toneClass(CHOICE_TONES[key]),
                label: this.choiceLabels[key],
            }));
        }
        if (this.state.colorBy === "progress") {
            return RUNGS.map((rung) => ({
                key: String(rung),
                className: toneClass(RUNG_TONES[rung]),
                label: `${rung} ${this.rungLabels[rung]}`,
            }));
        }
        return PEOPLE_LEVELS.map((key) => ({
            key,
            className: toneClass(PEOPLE_TONES[key]),
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

    /** Status of one activity in the current colour-by mode: {key, tone, level, dashed}. */
    status(activity) {
        if (this.state.colorBy === "choices") {
            return { key: activity.choice_state, ...CHOICE_TONES[activity.choice_state] };
        }
        if (this.state.colorBy === "progress") {
            return { key: String(activity.rung), ...RUNG_TONES[activity.rung] };
        }
        const level = this.peopleLevel(this.roleById.get(activity.role_id));
        return { key: level, ...PEOPLE_TONES[level] };
    }

    statusLabel(status) {
        if (this.state.colorBy === "choices") {
            return this.choiceLabels[status.key];
        }
        if (this.state.colorBy === "progress") {
            return `${status.key} ${this.rungLabels[parseInt(status.key, 10)]}`;
        }
        return this.peopleLabels[status.key];
    }

    dotClass(activity) {
        return toneClass(this.status(activity));
    }

    get selectedScenario() {
        return this.state.scenarioId ? this.scenarioById.get(this.state.scenarioId) : false;
    }

    inScenario(activityId) {
        const scenario = this.selectedScenario;
        return !scenario || scenario.activity_ids.includes(activityId);
    }

    chipClass(chip) {
        const classes = [];
        if (!this.inScenario(chip.id)) {
            classes.push("o_pan_sl_dim");
        }
        if (this.state.selectedId === chip.id) {
            classes.push("o_pan_sl_selected");
        }
        return classes.join(" ");
    }

    /** Stop 1: the cell as stacked segments, one per status, in legend order. */
    blockView(block) {
        const order = this.legend.map((item) => item.key);
        const counts = new Map();
        for (const activity of block.activities) {
            const status = this.status(activity);
            if (!counts.has(status.key)) {
                counts.set(status.key, { status, count: 0 });
            }
            counts.get(status.key).count += 1;
        }
        const total = block.activities.length;
        let x = block.x;
        const groups = [...counts.values()].sort(
            (a, b) => order.indexOf(a.status.key) - order.indexOf(b.status.key)
        );
        const segments = groups.map(({ status, count }) => {
            const width = (block.width * count) / total;
            const segment = { key: status.key, x, width, className: toneClass(status) };
            x += width;
            return segment;
        });
        const summary = groups
            .map(({ status, count }) => `${count} ${this.statusLabel(status)}`)
            .join(", ");
        const dim = Boolean(this.selectedScenario) && !block.activities.some((a) => this.inScenario(a.id));
        return {
            segments,
            count: total,
            dim,
            clipId: `o_pan_sl_clip_${block.key}`,
            title: _t("%(role)s in %(phase)s: %(count)s activities (%(summary)s). Click to zoom in.", {
                role: block.role.name,
                phase: block.phase.name,
                count: total,
                summary,
            }),
        };
    }

    /** Stop 3+: what a chip shows besides its name. */
    chipExtras(chip) {
        const users = chip.role.users;
        const shown = users.slice(0, MAX_INITIALS);
        const extraUsers = users.length - shown.length;
        const rightEdge = chip.width - 12;
        const userItems = shown.map((name, index) => ({
            key: `${index}-${name}`,
            initials: initials(name),
            name,
            cx: rightEdge - (shown.length - 1 - index) * INITIAL_STEP,
        }));
        const usersW = shown.length ? shown.length * INITIAL_STEP + (extraUsers ? 16 : 0) : 22;
        const model = chip.activity.model || "";
        const modelX = 10 + MAX_RUNG * 9 + 26;
        return {
            users: userItems,
            noUsers: !users.length,
            noUsersX: rightEdge,
            extraUsers,
            extraUsersX: shown.length ? userItems[0].cx - 12 : 0,
            usersTitle: users.length ? users.join(", ") : _t("Nobody holds this role yet"),
            rungSegments: Array.from({ length: MAX_RUNG }, (_, index) => ({
                key: index,
                x: 10 + index * 9,
                filled: index < chip.activity.rung,
            })),
            rungLabel: `${chip.activity.rung}/${MAX_RUNG}`,
            rungLabelX: 10 + MAX_RUNG * 9 + 2,
            rungTitle: `${chip.activity.rung} ${this.rungLabels[chip.activity.rung]}`,
            modelX,
            model: model
                ? truncate(model, charsFor(chip.width - modelX - usersW - 6, SMALL_CHAR_W))
                : _t("no model"),
            hasModel: Boolean(model),
        };
    }

    /** Stop 4: lines under a chip (tasks, then the first step of the click path). */
    chipDetailLines(chip) {
        const detail = chip.detail || { tasks: [], click_path: false };
        const chars = charsFor(chip.width - 44, SMALL_CHAR_W);
        const lines = [];
        let y = STOP_GEOMETRY[STOP_DETAIL].chipH + 4 + 11;
        if (!detail.tasks.length) {
            lines.push({ key: "notask", y, kind: "empty", text: _t("No tasks linked yet") });
            y += LINE_H;
        }
        for (const task of detail.tasks.slice(0, MAX_TASK_LINES)) {
            lines.push({
                key: `t${task.id}`,
                y,
                kind: "task",
                text: truncate(task.name, chars),
                title: `${task.name} (${task.rung} ${this.rungLabels[task.rung]})`,
                rung: `R${task.rung}`,
                rungClass: toneClass(RUNG_TONES[task.rung]),
            });
            y += LINE_H;
        }
        if (detail.tasks.length > MAX_TASK_LINES) {
            lines.push({
                key: "more",
                y,
                kind: "empty",
                text: _t("+%(count)s more tasks", { count: detail.tasks.length - MAX_TASK_LINES }),
            });
            y += LINE_H;
        }
        lines.push({
            key: "path",
            y,
            kind: detail.click_path ? "path" : "empty",
            text: detail.click_path
                ? `› ${truncate(detail.click_path, chars + 4)}`
                : _t("No click path yet"),
            title: detail.click_path || _t("No click path yet"),
        });
        return lines;
    }

    get route() {
        const scenario = this.selectedScenario;
        if (!scenario || this.stop === STOP_COMPANY) {
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
            stops,
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
        this.selectScenario(value ? parseInt(value, 10) : false);
    }

    selectScenario(scenarioId) {
        this.state.scenarioId = scenarioId;
        if (!scenarioId) {
            return;
        }
        // Jump to "Processes" and fit the route.
        this.state.zoom = STOP_THRESHOLDS[STOP_PROCESSES - 1];
        const route = this.route;
        if (route && route.stops.length) {
            const xs = route.stops.flatMap((chip) => [chip.x - 14, chip.x + chip.width]);
            const ys = route.stops.flatMap((chip) => [chip.y, chip.y + chip.height]);
            const x = Math.min(...xs);
            const y = Math.min(...ys);
            this.showBox({ x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y });
        }
    }

    onColorByChange(ev) {
        this.state.colorBy = ev.target.value;
    }

    /** Stop 1: clicking a cell zooms in to "Processes" on that cell. */
    onBlockClick(block) {
        this.state.zoom = STOP_THRESHOLDS[STOP_PROCESSES - 1];
        const cellChips = this.layout.chips.filter(
            (chip) => chip.role.id === block.role.id && chip.activity.phase_id === block.phase.id
        );
        const x = Math.min(...cellChips.map((c) => c.x));
        const y = Math.min(...cellChips.map((c) => c.y));
        const x2 = Math.max(...cellChips.map((c) => c.x + c.width));
        const y2 = Math.max(...cellChips.map((c) => c.y + c.height));
        this.showBox({ x, y, w: x2 - x, h: y2 - y });
    }

    onBlockKeydown(ev, block) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.onBlockClick(block);
        }
    }

    // ------------------------------------------------------------------
    // Side panel
    // ------------------------------------------------------------------

    openPanel(activityId) {
        if (!this.state.selectedId) {
            this.lastFocused = document.activeElement;
        }
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
        const activity = this.data.activities.find((a) => a.id === this.state.selectedId);
        const role = this.roleById.get(activity.role_id);
        const detail = this.details.get(activity.id) || { tasks: [], click_path: false };
        return {
            activity,
            role,
            phase: this.data.phases.find((phase) => phase.id === activity.phase_id),
            choiceLabel: this.choiceLabels[activity.choice_state],
            choiceClass: toneClass(CHOICE_TONES[activity.choice_state]),
            rungLabel: `${activity.rung} ${this.rungLabels[activity.rung]}`,
            tasks: detail.tasks.map((task) => ({
                ...task,
                rungLabel: `${task.rung} ${this.rungLabels[task.rung]}`,
            })),
            clickPath: detail.click_path,
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

    async openTask(taskId) {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openTemplateWizard() {
        await this.actionService.doAction("pan_self_learning_blueprint.action_blueprint_wizard");
    }
}

registry.category("actions").add("pan_sl_blueprint_map", CompanyMap);
