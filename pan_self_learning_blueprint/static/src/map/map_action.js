import {
    Component,
    onPatched,
    onWillPatch,
    onWillStart,
    onWillUnmount,
    useEffect,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
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
// Narrow containers (phones): text stays readable at the Company stop and the
// label column gets narrower; the user pans the map sideways instead.
const NARROW_W = 576;
const FIT_MIN_SCALE_NARROW = 0.8;
const COMPACT_LABEL_W = 100;
const FIT_MAX_SCALE = 1.25;
const CULL_MARGIN = 200; // user units around the view that still get chips
const DRAG_THRESHOLD = 4; // px before a press becomes a pan
const DOUBLE_CLICK_ZOOM = 0.75;
const KEY_PAN_PX = 80; // arrow keys pan this many screen pixels (Shift: 3x)
const KEY_ZOOM_STEP = 0.25; // + and - change the zoom factor by this much
const WHEEL_PAN_COMMIT_MS = 120; // a sideways scroll is done after this pause
// The side panel (see .o_pan_sl_panel in the SCSS): 340px wide with a 12px
// gap on desktop, a bottom sheet of at most 65% of the map on phones.
const PANEL_W = 340;
const PANEL_GAP = 12;
const SHEET_SHARE = 0.65;
const SMALL_SCREEN_MEDIA = "(max-width: 767.98px)";
const REVEAL_MARGIN_PX = 16;

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
const TASK_PILL_W = 46; // the rung word of a task at stop 4

const TESTED_RUNG = 3;
const MAX_RUNG = 5;
const WHEEL_ZOOM_SPEED = 0.0015; // zoom factor change per wheel pixel (exponential)
const PINCH_WHEEL_SPEED = 0.01; // trackpad pinch arrives as ctrl + wheel with small deltas

// Status per colour-by mode, at most three, in legend order. Tones follow the
// brand: ok green (works), warn amber (needs the user), off grey (no data or
// not started). Red means broken and is never a status on the map.
const SETTLED_CHOICE = "fixed";
const CHOICE_LEVELS = ["settled", "not_settled"];
const PROGRESS_LEVELS = ["open", "building", "tested"];
const PEOPLE_LEVELS = ["high", "lower", "no_data"];
const TONES = {
    settled: "ok",
    not_settled: "warn",
    open: "off",
    building: "warn",
    tested: "ok",
    high: "ok",
    lower: "warn",
    no_data: "off",
};

export function choiceLevel(activity) {
    return activity.choice_state === SETTLED_CHOICE ? "settled" : "not_settled";
}

/** Rung 0 Open, 1-2 Decided or Built, 3-5 Tested or further. */
export function progressLevel(rung) {
    if (rung >= TESTED_RUNG) {
        return "tested";
    }
    return rung > 0 ? "building" : "open";
}

/** ADKAR band of the role (lowest element): high, medium or low; false without enough scores. */
export function peopleLevel(role) {
    if (!role.adkar) {
        return "no_data";
    }
    return role.adkar === "high" ? "high" : "lower";
}

export function toneClass(tone) {
    return `o_pan_sl_tone_${tone}`;
}

/**
 * Second visual cue per tone, so status never depends on hue alone: ok is a
 * check, warn a half-filled disc; off has no glyph.
 * Returns {className, d} for an SVG path centred on (cx, cy), or false.
 */
export function toneGlyph(tone, cx, cy, r) {
    const s = r * 0.55;
    if (tone === "ok") {
        return {
            className: "o_pan_sl_glyph",
            d: `M ${cx - s} ${cy + s * 0.05} L ${cx - s * 0.25} ${cy + s * 0.75} L ${cx + s} ${cy - s * 0.65}`,
        };
    }
    if (tone === "warn") {
        return {
            className: "o_pan_sl_glyph_half",
            d: `M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx} ${cy + r} Z`,
        };
    }
    return false;
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
export function computeLayout(data, details, stop, compact = false) {
    const geo = STOP_GEOMETRY[stop];
    const { colW, headerH, lanePad } = geo;
    const labelW = compact ? COMPACT_LABEL_W : geo.labelW;
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

    // Header: phase names, plus the choices not settled per phase (stop 1).
    const columns = phases.map((phase, index) => {
        const inPhase = data.activities.filter((a) => a.phase_id === phase.id);
        return {
            phase,
            x: labelW + index * colW,
            label: truncate(phase.name, charsFor(colW - 16, 7)),
            notSettled: inPhase.filter((a) => choiceLevel(a) === "not_settled").length,
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
                    key: `b${role.id}-${phase.id}`,
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
                    key: `c${activity.id}`,
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
            const chipWidth = Math.min(maxRowWidth, app.name.length * APP_CHAR_W + 18);
            if (rowX > 0 && rowX + chipWidth > maxRowWidth) {
                row += 1;
                rowX = 0;
            }
            apps.push({
                key: `${phase.id}-${app.name}`,
                label: truncate(app.name, charsFor(chipWidth - 14, APP_CHAR_W)),
                title: app.installed ? app.name : _t("%s (not installed)", app.name),
                installed: app.installed,
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
        // Keyboard order: blocks at stop 1, chips at stops 2-4 (lane by lane).
        items: stop === STOP_COMPANY ? blocks : chips,
        itemByKey: new Map([...blocks, ...chips].map((item) => [item.key, item])),
        apps,
        notSettled: data.activities.filter((a) => choiceLevel(a) === "not_settled").length,
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

/** A chip's box widened to the left for its numbered route badge. */
function withBadgeRoom(chip) {
    return { x: chip.x - 14, y: chip.y, width: chip.width + 14, height: chip.height };
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
            TASK_PILL_W,
            STOP_COMPANY,
            STOP_PROCESSES,
            STOP_ACTIVITIES,
            STOP_DETAIL,
            MIN_ZOOM,
            MAX_ZOOM,
        };
        // Coming back to the map (breadcrumb) restores where the user was.
        const restored = (this.props.state && this.props.state.companyMap) || {};
        // The camera: zoom factor and the top-left of the view in user units
        // of the current stop's layout; cw/ch is the container size in px.
        this.state = useState({
            loaded: false,
            revision: 0, // bumped when the (non-reactive) map data is reloaded
            scenarioId: restored.scenarioId || false,
            colorBy: restored.colorBy || "choices",
            selectedId: restored.selectedId || false,
            zoom: restored.zoom || MIN_ZOOM,
            vx: restored.vx || 0,
            vy: restored.vy || 0,
            cw: 0,
            ch: 0,
        });
        this.compact = window.innerWidth < NARROW_W;
        this.pointers = new Map(); // active pointers, for drag and pinch
        this.gesture = null;
        this.suppressClick = false;
        this.lastFocused = null;
        this.returnKey = null; // map item that gets focus back when the panel closes
        this.focusedKey = null; // focused map item: always rendered, even when culled
        this.pendingFocus = null; // selector focused after the next render
        this.pressing = false; // a pointer is down: focus comes from a click, not the keyboard
        // Pan runs outside the OWL render: the live camera is painted straight
        // onto the SVG and only committed to the state (re-cull, re-render)
        // when it moved far enough or the gesture ended.
        this.live = null;
        this.frame = null;
        this.wheelZoom = null;
        this.wheelFrame = null;
        this.commitTimer = null;

        useSetupAction({
            getLocalState: () => {
                const camera = this.live || this.state;
                return {
                    companyMap: {
                        scenarioId: this.state.scenarioId,
                        colorBy: this.state.colorBy,
                        selectedId: this.state.selectedId,
                        zoom: this.state.zoom,
                        vx: camera.vx,
                        vy: camera.vy,
                    },
                };
            },
        });

        // A press that ends outside the map still ends.
        useExternalListener(window, "pointerup", () => (this.pressing = false));

        useHotkey("escape", () => this.closePanel(), {
            bypassEditableProtection: true,
            isAvailable: () => this.panelOpen,
        });

        onWillStart(async () => {
            const [isManager] = await Promise.all([
                user.hasGroup("pan_self_learning_blueprint.group_blueprint_manager"),
                this.load(),
            ]);
            this.isManager = isManager;
        });

        // Culling re-orders the chip list; a moved DOM node loses focus, so the
        // focused map item gets it back after the patch.
        onWillPatch(() => {
            const active = document.activeElement;
            const svg = this.svgRef.el;
            this.focusBeforePatch =
                svg && active && svg.contains(active) && active.dataset.item ? active.dataset.item : null;
        });
        onPatched(() => {
            let selector = this.pendingFocus;
            this.pendingFocus = null;
            if (!selector && this.focusBeforePatch) {
                const svg = this.svgRef.el;
                const active = document.activeElement;
                if (!svg || !active || !svg.contains(active) || active.dataset.item !== this.focusBeforePatch) {
                    selector = `[data-item="${this.focusBeforePatch}"]`;
                }
            }
            this.focusBeforePatch = null;
            const el = selector && this.queryMap(selector);
            if (el) {
                el.focus({ preventScroll: true });
            }
        });

        onWillUnmount(() => {
            cancelAnimationFrame(this.frame);
            cancelAnimationFrame(this.wheelFrame);
            clearTimeout(this.commitTimer);
        });

        // Track the container size; the fit scale and the view follow it.
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

    /** Load (or reload) the map data and drop a restored selection that no longer exists. */
    async load() {
        const [data, details] = await Promise.all([
            this.orm.call("pan.sl.activity", "get_map_data", []),
            this.orm.call("pan.sl.activity", "get_map_details", []),
        ]);
        this.data = data;
        this.details = new Map(details.map((detail) => [detail.id, detail]));
        this.roleById = new Map(data.roles.map((role) => [role.id, role]));
        this.scenarioById = new Map(data.scenarios.map((s) => [s.id, s]));
        this.activityById = new Map(data.activities.map((a) => [a.id, a]));
        this.phaseById = new Map(data.phases.map((phase) => [phase.id, phase]));
        this.computeLayouts();
        if (this.state.scenarioId && !this.scenarioById.has(this.state.scenarioId)) {
            this.state.scenarioId = false;
        }
        if (this.state.selectedId && !this.activityById.has(this.state.selectedId)) {
            this.state.selectedId = false;
        }
        this.state.loaded = true;
        this.state.revision += 1;
    }

    computeLayouts() {
        this.layouts = Object.fromEntries(
            ALL_STOPS.map((stop) => [stop, computeLayout(this.data, this.details, stop, this.compact)])
        );
    }

    queryMap(selector) {
        const root = this.bodyRef.el && this.bodyRef.el.closest(".o_pan_sl_map");
        return root ? root.querySelector(selector) : null;
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
        const minScale = this.compact ? FIT_MIN_SCALE_NARROW : FIT_MIN_SCALE;
        return Math.min(FIT_MAX_SCALE, Math.max(minScale, fit));
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

    viewAt(vx, vy) {
        const scale = this.scale;
        return {
            x: vx,
            y: vy,
            w: Math.max(this.state.cw, 1) / scale,
            h: Math.max(this.state.ch, 1) / scale,
        };
    }

    get view() {
        return this.viewAt(this.state.vx, this.state.vy);
    }

    get viewBoxAttr() {
        const v = this.view;
        return `${v.x} ${v.y} ${v.w} ${v.h}`;
    }

    /** Map width in screen pixels at the current zoom (for checks and the wider-than-view test). */
    get mapPixelWidth() {
        return Math.round(this.layout.width * this.scale);
    }

    get panelOpen() {
        return Boolean(this.state.selectedId);
    }

    /** Screen pixels the open side panel covers at the right (desktop) or bottom (phone). */
    get panelInsets() {
        if (!this.panelOpen) {
            return { right: 0, bottom: 0 };
        }
        if (window.matchMedia(SMALL_SCREEN_MEDIA).matches) {
            return { right: 0, bottom: this.state.ch * SHEET_SHARE };
        }
        return { right: Math.min(PANEL_W + 2 * PANEL_GAP, this.state.cw), bottom: 0 };
    }

    /**
     * Keep the map in view: centred when narrower than the view, top-aligned
     * when shorter. While the side panel is open the part it covers does not
     * count, so the last column can still be moved out from under it.
     */
    clampValues(vx, vy) {
        const { w, h } = this.view;
        const layout = this.layout;
        const insets = this.panelInsets;
        const freeW = w - insets.right / this.scale;
        const freeH = h - insets.bottom / this.scale;
        return {
            vx:
                layout.width <= freeW
                    ? (layout.width - freeW) / 2
                    : Math.min(Math.max(vx, 0), layout.width - freeW),
            vy: layout.height <= freeH ? 0 : Math.min(Math.max(vy, 0), layout.height - freeH),
        };
    }

    clampView() {
        const { vx, vy } = this.clampValues(this.state.vx, this.state.vy);
        this.state.vx = vx;
        this.state.vy = vy;
    }

    /** Zoom to `zoom`, keeping the map point under (px, py) (container pixels) in place. */
    zoomAt(zoom, px = this.state.cw / 2, py = this.state.ch / 2) {
        this.commitPan();
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
     * Zoom from the controls (slider, stop labels, keys): around the centre,
     * and when the stop changes while a scenario is selected, bring its
     * route back into view.
     */
    zoomTo(zoom) {
        const before = this.stop;
        this.zoomAt(zoom);
        if (this.stop !== before) {
            this.revealRoute();
        }
    }

    /**
     * Centre a box (user units of the current layout) in the part of the view
     * not covered by the sticky header and label column, or show its
     * top-left when it does not fit.
     */
    showBox(box) {
        this.commitPan();
        const { w, h } = this.view;
        const layout = this.layout;
        const margin = 24;
        const insets = this.panelInsets;
        const freeW = w - layout.labelW - insets.right / this.scale;
        const freeH = h - layout.lanesTop - insets.bottom / this.scale;
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

    /** The free part of the view (user units): not under the sticky bands or the panel. */
    freeArea(vx = this.state.vx, vy = this.state.vy) {
        const { w, h } = this.view;
        const layout = this.layout;
        const insets = this.panelInsets;
        const margin = REVEAL_MARGIN_PX / this.scale;
        return {
            left: vx + layout.labelW + margin,
            right: vx + w - insets.right / this.scale - margin,
            top: vy + layout.lanesTop + margin,
            bottom: vy + h - insets.bottom / this.scale - margin,
        };
    }

    /** Pan as little as needed so the box sits in the free part of the view. */
    reveal(box) {
        this.commitPan();
        const area = this.freeArea();
        let { vx, vy } = this.state;
        if (box.x < area.left || box.w > area.right - area.left) {
            vx -= area.left - box.x;
        } else if (box.x + box.w > area.right) {
            vx += box.x + box.w - area.right;
        }
        if (box.y < area.top || box.h > area.bottom - area.top) {
            vy -= area.top - box.y;
        } else if (box.y + box.h > area.bottom) {
            vy += box.y + box.h - area.bottom;
        }
        if (vx !== this.state.vx || vy !== this.state.vy) {
            this.state.vx = vx;
            this.state.vy = vy;
            this.clampView();
        }
    }

    boxOf(item) {
        return { x: item.x, y: item.y, w: item.width, h: item.height };
    }

    boundingBox(items) {
        const xs = items.flatMap((item) => [item.x, item.x + item.width]);
        const ys = items.flatMap((item) => [item.y, item.y + item.height]);
        const x = Math.min(...xs);
        const y = Math.min(...ys);
        return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
    }

    pointInContainer(ev) {
        const rect = this.bodyRef.el.getBoundingClientRect();
        return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }

    // ------------------------------------------------------------------
    // Pan outside the render path
    // ------------------------------------------------------------------

    /** Move the camera without a render; commits once it left the culled margin. */
    panTo(vx, vy) {
        const next = this.clampValues(vx, vy);
        this.live = next;
        if (
            Math.abs(next.vx - this.state.vx) > CULL_MARGIN / 2 ||
            Math.abs(next.vy - this.state.vy) > CULL_MARGIN / 2
        ) {
            this.commitPan();
            return;
        }
        if (!this.frame) {
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.paintLive();
            });
        }
    }

    get camera() {
        return this.live || { vx: this.state.vx, vy: this.state.vy };
    }

    commitPan() {
        clearTimeout(this.commitTimer);
        this.commitTimer = null;
        if (!this.live) {
            return;
        }
        cancelAnimationFrame(this.frame);
        this.frame = null;
        const { vx, vy } = this.live;
        this.live = null;
        this.state.vx = vx;
        this.state.vy = vy;
    }

    /** Paint the live camera straight onto the SVG: view box, sticky bands, lane labels. */
    paintLive() {
        const svg = this.svgRef.el;
        if (!this.live || !svg) {
            return;
        }
        const { vx, vy } = this.live;
        const v = this.viewAt(vx, vy);
        svg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
        const sx = Math.max(vx, 0);
        const sy = Math.max(vy, 0);
        svg.querySelector(".o_pan_sl_sticky_top")?.setAttribute("transform", `translate(0,${sy})`);
        svg.querySelector(".o_pan_sl_sticky_left")?.setAttribute("transform", `translate(${sx},0)`);
        svg.querySelector(".o_pan_sl_sticky_corner")?.setAttribute("transform", `translate(${sx},${sy})`);
        const lanes = this.layout.lanes;
        for (const label of svg.querySelectorAll(".o_pan_sl_role_label_group")) {
            const lane = lanes[parseInt(label.dataset.lane, 10)];
            if (lane) {
                label.setAttribute("transform", `translate(0,${this.laneLabelY(lane, vy)})`);
            }
        }
    }

    // ------------------------------------------------------------------
    // Pointer, wheel and keyboard
    // ------------------------------------------------------------------

    onZoomInput(ev) {
        this.zoomTo(parseFloat(ev.target.value));
    }

    /** Slider keys: arrows jump to the next or previous stop, Shift+arrow fine-tunes (native). */
    onZoomKeydown(ev) {
        const up = ["ArrowRight", "ArrowUp"].includes(ev.key);
        const down = ["ArrowLeft", "ArrowDown"].includes(ev.key);
        if ((!up && !down) || ev.shiftKey || ev.altKey || ev.ctrlKey || ev.metaKey) {
            return;
        }
        ev.preventDefault();
        const zoom = this.state.zoom;
        const target = up
            ? STOP_THRESHOLDS.find((threshold) => threshold > zoom + 1e-6) ?? MAX_ZOOM
            : [...STOP_THRESHOLDS].reverse().find((threshold) => threshold < zoom - 1e-6) ?? MIN_ZOOM;
        this.zoomTo(target);
    }

    onWheel(ev) {
        ev.preventDefault();
        const point = this.pointInContainer(ev);
        if (!ev.ctrlKey && Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
            // Sideways trackpad swipe: pan, committed after a short pause.
            const { vx, vy } = this.camera;
            this.panTo(vx + ev.deltaX / this.scale, vy);
            clearTimeout(this.commitTimer);
            this.commitTimer = setTimeout(() => this.commitPan(), WHEEL_PAN_COMMIT_MS);
            return;
        }
        const pixels = ev.deltaY * (ev.deltaMode === 1 ? 20 : 1);
        const speed = ev.ctrlKey ? PINCH_WHEEL_SPEED : WHEEL_ZOOM_SPEED;
        // Coalesce wheel events: at most one zoom (and render) per frame.
        const factor = Math.exp(-pixels * speed);
        if (this.wheelZoom) {
            this.wheelZoom.factor *= factor;
            this.wheelZoom.point = point;
            return;
        }
        this.wheelZoom = { factor, point };
        this.wheelFrame = requestAnimationFrame(() => {
            const pending = this.wheelZoom;
            this.wheelZoom = null;
            this.wheelFrame = null;
            this.zoomAt(this.state.zoom * pending.factor, pending.point.x, pending.point.y);
        });
    }

    onDoubleClick(ev) {
        if (ev.target.closest(".o_pan_sl_chip")) {
            return;
        }
        const point = this.pointInContainer(ev);
        this.zoomAt(this.state.zoom + DOUBLE_CLICK_ZOOM, point.x, point.y);
    }

    /**
     * Keyboard on the map: arrows pan (Shift: further), Page Up/Down pan a
     * screen, + and - zoom around the centre, Home fits the whole map.
     */
    onMapKeydown(ev) {
        if (ev.altKey || ev.ctrlKey || ev.metaKey) {
            return;
        }
        const step = (KEY_PAN_PX * (ev.shiftKey ? 3 : 1)) / this.scale;
        const page = (this.view.h - this.layout.lanesTop) * 0.8;
        const moves = {
            ArrowLeft: [-step, 0],
            ArrowRight: [step, 0],
            ArrowUp: [0, -step],
            ArrowDown: [0, step],
            PageUp: [0, -page],
            PageDown: [0, page],
        };
        if (ev.key in moves) {
            ev.preventDefault();
            this.commitPan();
            const [dx, dy] = moves[ev.key];
            this.state.vx += dx;
            this.state.vy += dy;
            this.clampView();
        } else if (ev.key === "+" || ev.key === "=") {
            ev.preventDefault();
            this.zoomTo(this.state.zoom + KEY_ZOOM_STEP);
        } else if (ev.key === "-" || ev.key === "_") {
            ev.preventDefault();
            this.zoomTo(this.state.zoom - KEY_ZOOM_STEP);
        } else if (ev.key === "Home") {
            ev.preventDefault();
            this.commitPan();
            this.state.zoom = MIN_ZOOM;
            this.state.vx = 0;
            this.state.vy = 0;
            this.clampView();
        }
    }

    /** Keyboard focus on a block or chip moves the camera so it is not hidden. */
    onMapFocusin(ev) {
        const el = ev.target.closest && ev.target.closest("[data-item]");
        if (!el) {
            return;
        }
        this.focusedKey = el.dataset.item;
        const item = this.layout.itemByKey.get(el.dataset.item);
        if (item && !this.pressing) {
            this.reveal(this.boxOf(item));
        }
    }

    /** Focus a map item that may be culled: reveal it, then focus it after the render. */
    focusItem(item) {
        this.focusedKey = item.key;
        this.reveal(this.boxOf(item));
        const selector = `[data-item="${item.key}"]`;
        const el = this.queryMap(selector);
        if (el) {
            el.focus({ preventScroll: true });
        } else {
            this.pendingFocus = selector;
            this.state.revision += 1;
        }
    }

    /**
     * Tab and Shift+Tab walk every block or chip of the stop in map order,
     * culled ones included; past the first or last the browser takes over.
     */
    onItemKeydown(ev, item, activate) {
        if (ev.key === "Tab" && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
            const items = this.layout.items;
            const next = items[items.indexOf(item) + (ev.shiftKey ? -1 : 1)];
            if (next) {
                ev.preventDefault();
                this.focusItem(next);
            }
        } else if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            ev.stopPropagation();
            activate();
        }
    }

    // Drag to pan (mouse, pen and touch); two fingers pinch to zoom.
    onPointerDown(ev) {
        if (ev.pointerType === "mouse" && ev.button !== 0) {
            return;
        }
        this.pressing = true;
        this.pointers.set(ev.pointerId, this.pointInContainer(ev));
        if (this.pointers.size === 2) {
            this.commitPan();
            const [a, b] = [...this.pointers.values()];
            this.gesture = {
                type: "pinch",
                distance: Math.hypot(a.x - b.x, a.y - b.y),
                zoom: this.state.zoom,
            };
            this.svgRef.el.setPointerCapture(ev.pointerId);
        } else if (this.pointers.size === 1) {
            const point = this.pointers.get(ev.pointerId);
            const { vx, vy } = this.camera;
            this.gesture = { type: "press", pointerId: ev.pointerId, start: point, vx, vy };
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
            this.panTo(gesture.vx - dx / this.scale, gesture.vy - dy / this.scale);
        }
    }

    onPointerUp(ev) {
        this.pressing = false;
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
            this.commitPan();
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

    visibleItems(items) {
        const v = this.view; // once per render, not once per item
        const keep = new Set([this.focusedKey, this.state.selectedId && `c${this.state.selectedId}`]);
        return items.filter(
            (item) =>
                keep.has(item.key) ||
                (item.x + item.width >= v.x - CULL_MARGIN &&
                    item.x <= v.x + v.w + CULL_MARGIN &&
                    item.y + item.height >= v.y - CULL_MARGIN &&
                    item.y <= v.y + v.h + CULL_MARGIN)
        );
    }

    get visibleChips() {
        return this.visibleItems(this.layout.chips);
    }

    get visibleBlocks() {
        return this.visibleItems(this.layout.blocks);
    }

    /** Sticky header and label column: they follow the view like map labels. */
    get stickyX() {
        return Math.max(this.state.vx, 0);
    }

    get stickyY() {
        return Math.max(this.state.vy, 0);
    }

    /**
     * A role name stays in view inside a lane taller than the screen, like a
     * sticky section header: below the sticky header, but never past its lane.
     */
    laneLabelY(lane, vy = this.state.vy) {
        const top = lane.y + 22;
        const bottom = lane.y + lane.height - (lane.role.is_external ? 24 : 8);
        return Math.max(top, Math.min(Math.max(vy, 0) + this.layout.lanesTop + 22, bottom));
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

    /** The rung as a word (rung_state), the only notation of a rung on the map. */
    get rungLabels() {
        return [_t("Open"), _t("Decided"), _t("Built"), _t("Tested"), _t("Trained"), _t("Live")];
    }

    get adkarBandLabels() {
        return { high: _t("high"), medium: _t("medium"), low: _t("low") };
    }

    /** Legend label of each status level, per colour-by mode. */
    get levelLabels() {
        return {
            settled: _t("Settled"),
            not_settled: _t("Not settled"),
            open: _t("Open"),
            building: _t("Decided or built"),
            tested: _t("Tested or further"),
            high: _t("ADKAR high"),
            lower: _t("ADKAR medium or low"),
            no_data: _t("No ADKAR data"),
        };
    }

    get levels() {
        if (this.state.colorBy === "choices") {
            return CHOICE_LEVELS;
        }
        if (this.state.colorBy === "progress") {
            return PROGRESS_LEVELS;
        }
        return PEOPLE_LEVELS;
    }

    /** Only the active colour-by mode, at most three items. */
    get legend() {
        return this.levels.map((key) => ({
            key,
            label: this.levelLabels[key],
            className: toneClass(TONES[key]),
            glyph: toneGlyph(TONES[key], 9, 6, 4.5),
        }));
    }

    // ------------------------------------------------------------------
    // Colours, dimming and route
    // ------------------------------------------------------------------

    /** Status level of one activity in the current colour-by mode (a key of TONES). */
    level(activity) {
        if (this.state.colorBy === "choices") {
            return choiceLevel(activity);
        }
        if (this.state.colorBy === "progress") {
            return progressLevel(activity.rung);
        }
        return peopleLevel(this.roleById.get(activity.role_id));
    }

    /** The status dot of a chip: tone colour plus a glyph (check, half). */
    dotView(activity, cx, cy) {
        const tone = TONES[this.level(activity)];
        const r = 5.5;
        return { cx, cy, r, className: toneClass(tone), glyph: toneGlyph(tone, cx, cy, r) };
    }

    /** Accessible name of a chip: everything the chip shows, not only its colour. */
    chipAriaLabel(chip) {
        const activity = chip.activity;
        const parts = [
            activity.name,
            this.levelLabels[this.level(activity)],
            this.rungLabels[activity.rung],
        ];
        if (activity.open_point) {
            parts.push(_t("open point: %s", activity.open_point));
        }
        parts.push(chip.role.name);
        return parts.join(", ");
    }

    get selectedScenario() {
        return this.state.scenarioId ? this.scenarioById.get(this.state.scenarioId) : false;
    }

    inScenario(activityId) {
        const scenario = this.selectedScenario;
        return !scenario || scenario.activity_ids.includes(activityId);
    }

    /** Faded out: not in the selected scenario. */
    isDimmed(activity) {
        return !this.inScenario(activity.id);
    }

    chipClass(chip) {
        const classes = [];
        if (this.isDimmed(chip.activity)) {
            classes.push("o_pan_sl_dim");
        }
        if (this.state.selectedId === chip.id) {
            classes.push("o_pan_sl_selected");
        }
        return classes.join(" ");
    }

    /** Stop 1: the cell as stacked segments, one per status level, in legend order. */
    blockView(block) {
        const counts = new Map();
        for (const activity of block.activities) {
            const level = this.level(activity);
            counts.set(level, (counts.get(level) || 0) + 1);
        }
        const total = block.activities.length;
        let x = block.x;
        const groups = this.levels.filter((level) => counts.has(level));
        const segments = groups.map((level) => {
            const width = (block.width * counts.get(level)) / total;
            const tone = TONES[level];
            const glyph = width >= 18 ? toneGlyph(tone, x + 9, block.y + 9, 5) : false;
            const segment = { key: level, x, width, className: toneClass(tone), glyph };
            x += width;
            return segment;
        });
        const summary = groups
            .map((level) => `${counts.get(level)} ${this.levelLabels[level]}`)
            .join(", ");
        const dim = block.activities.every((a) => this.isDimmed(a));
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

    /** Stop 3+: what a chip shows besides its name (static per layout: computed once). */
    chipExtras(chip) {
        if (chip.extras) {
            return chip.extras;
        }
        chip.extras = {
            rungSegments: Array.from({ length: MAX_RUNG }, (_, index) => ({
                key: index,
                x: 10 + index * 9,
                filled: index < chip.activity.rung,
            })),
            rungLabel: this.rungLabels[chip.activity.rung],
            rungLabelX: 10 + MAX_RUNG * 9 + 2,
        };
        return chip.extras;
    }

    /** Stop 4: lines under a chip (tasks, then the first step of the click path); computed once. */
    chipDetailLines(chip) {
        if (chip.detailLines) {
            return chip.detailLines;
        }
        const detail = chip.detail || { tasks: [], click_path: false };
        const chars = charsFor(chip.width - TASK_PILL_W - 22, SMALL_CHAR_W);
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
                title: `${task.name} (${this.rungLabels[task.rung]})`,
                rung: this.rungLabels[task.rung],
                rungClass: toneClass(TONES[progressLevel(task.rung)]),
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
        chip.detailLines = lines;
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

    /** When no chip of the scenario route is in view, show the whole route, or its first chip. */
    revealRoute() {
        const route = this.route;
        const chips = route ? route.stops : [];
        if (!chips.length) {
            return;
        }
        const area = this.freeArea();
        const inView = chips.some(
            (chip) =>
                chip.x + chip.width > area.left &&
                chip.x < area.right &&
                chip.y + chip.height > area.top &&
                chip.y < area.bottom
        );
        if (inView) {
            return;
        }
        const box = this.boundingBox(chips.map(withBadgeRoom));
        const free = this.freeArea(0, 0);
        const fits = box.w <= free.right - free.left && box.h <= free.bottom - free.top;
        this.showBox(fits ? box : this.boxOf(chips[0]));
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
        this.commitPan();
        this.state.zoom = STOP_THRESHOLDS[STOP_PROCESSES - 1];
        const route = this.route;
        if (route && route.stops.length) {
            this.showBox(this.boundingBox(route.stops.map(withBadgeRoom)));
        }
    }

    onColorByChange(ev) {
        this.state.colorBy = ev.target.value;
    }

    /** Stop 1: clicking a cell zooms in to "Processes" on that cell. */
    onBlockClick(block, { focus = false } = {}) {
        this.commitPan();
        this.state.zoom = STOP_THRESHOLDS[STOP_PROCESSES - 1];
        const cellChips = this.layout.chips.filter(
            (chip) => chip.role.id === block.role.id && chip.activity.phase_id === block.phase.id
        );
        this.showBox(this.boundingBox(cellChips));
        if (focus && cellChips.length) {
            // Keyboard: the block is gone at this stop; focus moves to its first chip.
            this.focusedKey = cellChips[0].key;
            this.pendingFocus = `[data-item="${cellChips[0].key}"]`;
        }
    }

    // ------------------------------------------------------------------
    // Side panel: one activity
    // ------------------------------------------------------------------

    rememberFocus() {
        if (!this.panelOpen) {
            const active = document.activeElement;
            this.lastFocused = active;
            this.returnKey = active && active.dataset ? active.dataset.item || null : null;
        }
    }

    focusPanelTitle(changed) {
        if (changed) {
            this.pendingFocus = ".o_pan_sl_panel_title";
        } else {
            this.queryMap(".o_pan_sl_panel_title")?.focus({ preventScroll: true });
        }
    }

    openPanel(activityId) {
        this.rememberFocus();
        const changed = this.state.selectedId !== activityId;
        this.state.selectedId = activityId;
        // Keep the chip visible next to the panel, not under it.
        const chip = this.layout.chipById.get(activityId);
        if (chip) {
            this.reveal(this.boxOf(chip));
        }
        this.focusPanelTitle(changed);
    }

    closePanel() {
        this.state.selectedId = false;
        this.clampView();
        const item = this.returnKey && this.layout.itemByKey.get(this.returnKey);
        if (item) {
            this.focusItem(item);
        } else if (this.lastFocused && this.lastFocused.isConnected) {
            this.lastFocused.focus({ preventScroll: true });
        }
        this.lastFocused = null;
        this.returnKey = null;
    }

    get panel() {
        if (!this.state.selectedId) {
            return false;
        }
        const activity = this.activityById.get(this.state.selectedId);
        const role = this.roleById.get(activity.role_id);
        const detail = this.details.get(activity.id) || { tasks: [], click_path: false };
        const tone = TONES[choiceLevel(activity)];
        return {
            activity,
            role,
            phase: this.phaseById.get(activity.phase_id),
            choiceLabel: this.choiceLabels[activity.choice_state],
            choiceDot: { cx: 7, cy: 7, r: 5.5, className: toneClass(tone), glyph: toneGlyph(tone, 7, 7, 5.5) },
            rungLabel: this.rungLabels[activity.rung],
            tasks: detail.tasks.map((task) => ({ ...task, rungLabel: this.rungLabels[task.rung] })),
            clickPath: detail.click_path,
            scenarios: activity.scenario_ids
                .map((id) => this.scenarioById.get(id))
                .filter((scenario) => scenario),
            adkarBand: role.adkar ? this.adkarBandLabels[role.adkar] : false,
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

    /** Empty state (managers): load the bundled template; its action reloads the map. */
    async loadTemplate() {
        await this.actionService.doAction("pan_self_learning_blueprint.action_blueprint_load_template");
    }
}

registry.category("actions").add("pan_sl_blueprint_map", CompanyMap);
