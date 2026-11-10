#!/usr/bin/env node
// UI check for the Blueprint company map (pan_self_learning_blueprint).
//
// Logs in to a running Odoo at http://localhost:8069 as admin/admin and opens
// the company map client action. On desktop (1440x900, deviceScaleFactor 1)
// it moves the zoom slider to each of the four stops (Company, Processes,
// Activities, Detail) and screenshots each, checks that the stops draw what
// they should, selects a scenario and checks the numbered route badges,
// clicks an activity chip and checks the side panel, presses Esc and checks
// that the panel closes. On mobile (390x844) it checks that the page does not
// scroll sideways (the map scrolls inside its own container) and takes one
// screenshot with the panel open as a bottom sheet.
//
// Keyboard: arrow keys pan the focused map, + / - zoom and Home fits it; the
// slider's arrow keys jump from stop to stop; Tab walks every chip of the
// Detail stop (culled ones included) and each focused chip is in view; Enter
// on a Company block moves focus to a chip. State restore: after opening an
// activity from the panel and coming back through the breadcrumb, zoom, view,
// scenario, colour-by and the panel are as the user left them.
//
// At every stop it also checks that no SVG shape is painted black: an
// undefined CSS variable in an SVG fill falls back to black.
//
// Never waits for "networkidle": Odoo's bus long-polls, so the network is
// never idle. It waits for the map's own elements instead.
//
// Exits non-zero on any page error, console error, Odoo error dialog or
// failed check.
//
// Usage:
//   DB=mydb OUT=/tmp/ui node tools/ui_check.mjs
//
// Environment:
//   DB   (required) database name to log in to
//   OUT  (required) directory for the screenshots (created if missing)

import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE_URL = "http://localhost:8069";
const LOGIN = "admin";
const PASSWORD = "admin";
const MAP_PATH = "/odoo/action-pan_self_learning_blueprint.action_blueprint_map";
const TIMEOUT = 30000;

const SEL = {
    map: ".o_pan_sl_map",
    svg: ".o_pan_sl_map .o_pan_sl_svg",
    body: ".o_pan_sl_map .o_pan_sl_body",
    emptyState: ".o_pan_sl_map .o_view_nocontent",
    scenarioSelect: ".o_pan_sl_scenario_select",
    colorSelect: ".o_pan_sl_color_select",
    slider: ".o_pan_sl_zoom_slider",
    block: ".o_pan_sl_block",
    chip: ".o_pan_sl_chip",
    badge: ".o_pan_sl_badge",
    rung: ".o_pan_sl_chip .o_pan_sl_rung",
    detail: ".o_pan_sl_chip .o_pan_sl_detail text",
    counter: ".o_pan_sl_counter",
    panel: ".o_pan_sl_panel",
    panelOpenActivity: ".o_pan_sl_panel .card-footer .btn-primary",
    formView: ".o_form_view",
    breadcrumbMap: ".o_breadcrumb .breadcrumb-item a",
    errorDialog: ".o_error_dialog",
};

// A zoom factor inside each semantic stop (thresholds 1, 1.75, 2.5, 3.25; max 4).
const STOPS = [
    { value: 1, zoom: 1, name: "company" },
    { value: 2, zoom: 2, name: "processes" },
    { value: 3, zoom: 2.8, name: "activities" },
    { value: 4, zoom: 3.6, name: "detail" },
];

const DESKTOP = { name: "desktop", width: 1440, height: 900 };
const MOBILE = { name: "mobile", width: 390, height: 844 };

function requireEnv(name) {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Environment variable ${name} is required (see the header of tools/ui_check.mjs).`);
    }
    return value;
}

class CheckError extends Error {}

function check(condition, message) {
    if (!condition) {
        throw new CheckError(message);
    }
}

async function expectVisible(page, selector, what) {
    try {
        await page.locator(selector).first().waitFor({ state: "visible", timeout: TIMEOUT });
    } catch {
        throw new CheckError(`Missing element: ${what} (${selector}) did not appear.`);
    }
}

async function expectGone(page, selector, what) {
    try {
        await page.locator(selector).first().waitFor({ state: "detached", timeout: 5000 });
    } catch {
        throw new CheckError(`${what} (${selector}) is still there.`);
    }
}

async function login(page, db) {
    await page.goto(`${BASE_URL}/web/login?db=${encodeURIComponent(db)}`);
    await page.fill("input[name=login]", LOGIN);
    await page.fill("input[name=password]", PASSWORD);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.startsWith("/web/login"), { timeout: TIMEOUT }),
        page.click("button[type=submit]"),
    ]);
}

async function openMap(page) {
    await page.goto(`${BASE_URL}${MAP_PATH}`);
    await expectVisible(page, SEL.map, "company map");
    // The map is ready when it shows either the SVG or the empty state.
    await page.locator(`${SEL.svg}, ${SEL.emptyState}`).first().waitFor({ state: "visible", timeout: TIMEOUT });
    if (await page.locator(SEL.emptyState).count()) {
        throw new CheckError(
            "The company map shows the empty state: load a template blueprint in this database first."
        );
    }
}

/** Move the zoom slider to a zoom factor the way a user drags it (input events). */
async function setZoom(page, zoom) {
    await page.locator(SEL.slider).evaluate((el, value) => {
        el.value = String(value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
    }, zoom);
    await page.waitForFunction(
        (value) => Math.abs(parseFloat(document.querySelector(".o_pan_sl_svg")?.dataset.zoom) - value) < 0.01,
        zoom,
        { timeout: 5000 }
    );
    await page.waitForTimeout(200);
}

async function svgData(page) {
    return page.locator(SEL.svg).evaluate((el) => ({
        stop: parseInt(el.dataset.stop, 10),
        zoom: parseFloat(el.dataset.zoom),
        scale: parseFloat(el.dataset.scale),
        mapWidth: parseInt(el.dataset.mapWidth, 10),
        chipTotal: parseInt(el.dataset.chipTotal, 10),
        viewBox: el.getAttribute("viewBox").split(" ").map(parseFloat),
    }));
}

/** SVG shapes whose computed fill or stroke is pure black (an undefined CSS variable). */
async function blackShapes(page) {
    return page.evaluate(() => {
        const black = new Set(["rgb(0, 0, 0)", "#000000", "black"]);
        const found = [];
        for (const el of document.querySelectorAll(
            ".o_pan_sl_map svg rect, .o_pan_sl_map svg circle, .o_pan_sl_map svg path, .o_pan_sl_map svg line"
        )) {
            if (el.closest("defs, clipPath")) {
                continue;
            }
            const style = getComputedStyle(el);
            // A line has no area: its fill is never painted.
            const fillBlack = el.tagName !== "line" && black.has(style.fill);
            const strokeBlack = style.stroke !== "none" && black.has(style.stroke);
            if (fillBlack || strokeBlack) {
                found.push(`${el.tagName}.${el.getAttribute("class") || ""} fill=${style.fill} stroke=${style.stroke}`);
            }
        }
        return found;
    });
}

async function expectNoBlack(page, label) {
    const found = await blackShapes(page);
    check(
        !found.length,
        `${label}: ${found.length} SVG shape(s) painted black (undefined colour variable?), e.g. ${found.slice(0, 3).join("; ")}`
    );
}

/**
 * Click the first chip matching `selector` whose centre is not covered (by
 * the sticky header or label column, or the panel), like a user would.
 */
async function clickVisibleChip(page, selector, what) {
    const point = await page.evaluate((sel) => {
        for (const chip of document.querySelectorAll(sel)) {
            const r = chip.getBoundingClientRect();
            const y = r.top + Math.min(r.height / 2, 14);
            // Try a few points along the chip: its left part may sit under the label column.
            for (const share of [0.25, 0.5, 0.75]) {
                const x = r.left + r.width * share;
                const hit = document.elementFromPoint(x, y);
                if (hit && chip.contains(hit)) {
                    return { x, y };
                }
            }
        }
        return null;
    }, selector);
    check(point, `No ${what} is visible on screen to click.`);
    await page.mouse.click(point.x, point.y);
}

async function expectNoErrorDialog(page) {
    check(!(await page.locator(SEL.errorDialog).count()), "Odoo shows an error dialog.");
}

async function count(page, selector) {
    return page.locator(selector).count();
}

/** Description of document.activeElement: which map item it is and whether it is in view. */
async function activeItem(page) {
    return page.evaluate(() => {
        const el = document.activeElement;
        const body = document.querySelector(".o_pan_sl_body")?.getBoundingClientRect();
        if (!el || !body) {
            return null;
        }
        const r = el.getBoundingClientRect();
        const cx = r.left + Math.min(r.width / 2, 40);
        const cy = r.top + Math.min(r.height / 2, 14);
        const hit = document.elementFromPoint(cx, cy);
        return {
            tag: el.tagName,
            item: el.dataset ? el.dataset.item || null : null,
            isChip: el.classList.contains("o_pan_sl_chip"),
            inView: cx >= body.left && cx <= body.right && cy >= body.top && cy <= body.bottom,
            // Not covered by the sticky header or label column.
            uncovered: Boolean(hit && el.contains(hit)),
        };
    });
}

async function checkKeyboard(page) {
    // Tab walks every chip at the Detail stop, culled ones included, each in
    // view: forward from a chip to the last one, then Shift+Tab back to the first.
    await setZoom(page, 3.6);
    const total = (await svgData(page)).chipTotal;
    await page.locator(SEL.chip).first().focus();
    const seen = new Set();
    let last = null;
    for (const key of ["Tab", "Shift+Tab"]) {
        if (last) {
            await page.locator(`[data-item="${last}"]`).focus();
        }
        for (let step = 0; step <= total; step++) {
            const active = await activeItem(page);
            if (!active || !active.isChip) {
                check(step > 0, `${key}: focus is not on a chip to start from (${active && active.tag}).`);
                break;
            }
            check(active.inView && active.uncovered, `${key} step ${step}: the focused chip ${active.item} is not visible.`);
            seen.add(active.item);
            last = active.item;
            await page.keyboard.press(key);
            await page.waitForTimeout(30);
        }
    }
    check(seen.size === total, `Tab and Shift+Tab reached ${seen.size} of the ${total} chips.`);

    // Arrow keys pan the focused map; + and - zoom; Home fits.
    await setZoom(page, 2.8);
    await page.locator(SEL.svg).focus();
    const start = (await svgData(page)).viewBox;
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(100);
    const right = (await svgData(page)).viewBox;
    check(right[0] > start[0], `ArrowRight does not pan the map (${start} -> ${right}).`);
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(100);
    const left = (await svgData(page)).viewBox;
    check(left[0] < right[0], `ArrowLeft does not pan the map back (${right} -> ${left}).`);
    const zoomBefore = (await svgData(page)).zoom;
    await page.keyboard.press("+");
    await page.waitForTimeout(100);
    check((await svgData(page)).zoom > zoomBefore, "The + key does not zoom in.");
    await page.keyboard.press("-");
    await page.keyboard.press("-");
    await page.waitForTimeout(100);
    check((await svgData(page)).zoom < zoomBefore, "The - key does not zoom out.");
    await page.keyboard.press("Home");
    await page.waitForTimeout(100);
    check((await svgData(page)).stop === 1, "Home does not fit the map (Company stop).");

    // The slider's arrow keys jump to the next stop.
    await page.locator(SEL.slider).focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(100);
    check((await svgData(page)).stop === 2, "ArrowRight on the zoom slider does not jump to the Processes stop.");

    // Enter on a Company block zooms in and moves focus to a chip of that cell.
    await setZoom(page, 1);
    await page.locator(SEL.block).first().focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(200);
    const afterBlock = await activeItem(page);
    check(afterBlock && afterBlock.isChip, `Enter on a block leaves focus on ${afterBlock && afterBlock.tag}, not a chip.`);
}

/** Leave the map through the panel and come back: everything is as the user left it. */
async function checkStateRestore(page) {
    await page.locator(SEL.colorSelect).selectOption("progress");
    await page.waitForTimeout(100);
    await clickVisibleChip(page, `${SEL.chip}:not(.o_pan_sl_dim)`, "route chip");
    await expectVisible(page, SEL.panel, "activity side panel (before leaving)");
    const before = await svgData(page);
    const scenario = await page.locator(SEL.scenarioSelect).inputValue();
    const title = await page.locator(`${SEL.panel} .o_pan_sl_panel_title`).textContent();
    await page.locator(SEL.panelOpenActivity).click();
    await expectVisible(page, SEL.formView, "activity form");
    await page.locator(SEL.breadcrumbMap).first().click();
    await expectVisible(page, SEL.svg, "company map after the breadcrumb");
    await expectVisible(page, SEL.panel, "side panel restored after the breadcrumb");
    await page.waitForTimeout(200);
    const after = await svgData(page);
    check(Math.abs(after.zoom - before.zoom) < 0.01, `Zoom not restored (${before.zoom} -> ${after.zoom}).`);
    check(
        after.viewBox.every((value, index) => Math.abs(value - before.viewBox[index]) < 1),
        `View not restored (${before.viewBox} -> ${after.viewBox}).`
    );
    check((await page.locator(SEL.scenarioSelect).inputValue()) === scenario, "Scenario not restored.");
    check((await page.locator(SEL.colorSelect).inputValue()) === "progress", "Colour-by not restored.");
    const titleAfter = await page.locator(`${SEL.panel} .o_pan_sl_panel_title`).textContent();
    check(titleAfter === title, `The panel shows "${titleAfter}" instead of "${title}".`);
    await page.keyboard.press("Escape");
    await expectGone(page, SEL.panel, "The side panel after pressing Esc (restored)");
}

async function checkDesktop(page, out) {
    const scales = [];
    for (const stop of STOPS) {
        await setZoom(page, stop.zoom);
        const label = `stop ${stop.value} (${stop.name})`;
        const info = await svgData(page);
        check(info.stop === stop.value, `${label}: zoom ${stop.zoom} shows stop ${info.stop}.`);
        await expectNoBlack(page, label);
        scales.push(info.scale);
        const blocks = await count(page, SEL.block);
        const chips = await count(page, SEL.chip);
        if (stop.value === 1) {
            check(blocks > 0, `${label}: no role x phase blocks drawn.`);
            check(chips === 0, `${label}: activity chips are drawn, the company view shows blocks only.`);
            check((await count(page, SEL.counter)) > 0, `${label}: open-choice and clash counters missing.`);
        } else {
            check(blocks === 0, `${label}: company blocks are still drawn.`);
            check(chips > 0, `${label}: no activity chips drawn.`);
            const rungs = await count(page, SEL.rung);
            check(stop.value >= 3 ? rungs > 0 : rungs === 0, `${label}: rung bars ${rungs ? "shown" : "missing"}.`);
            const detailLines = await count(page, SEL.detail);
            check(
                stop.value === 4 ? detailLines > 0 : detailLines === 0,
                `${label}: task / click path lines ${detailLines ? "shown" : "missing"}.`
            );
            if (stop.value === 4) {
                check(
                    chips < info.chipTotal,
                    `${label}: all ${info.chipTotal} chips are rendered although most are out of view (no culling).`
                );
            }
        }
        await page.screenshot({ path: join(out, `desktop_stop${stop.value}_${stop.name}.png`) });
    }
    check(
        scales.every((scale, index) => !index || scale > scales[index - 1]),
        `The map does not get physically larger with each stop (scales ${scales.join(", ")}).`
    );

    await checkKeyboard(page);
    await setZoom(page, 3.6);

    // Drag to pan.
    const box = await page.locator(SEL.body).boundingBox();
    const before = (await svgData(page)).viewBox;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2 - 120, { steps: 8 });
    await page.mouse.up();
    const after = (await svgData(page)).viewBox;
    check(after[0] > before[0] && after[1] > before[1], `Dragging does not pan the map (${before} -> ${after}).`);
    check(!(await count(page, SEL.panel)), "Ending a drag on a chip opened the panel.");

    // Wheel zooms out, centred on the cursor; the slider follows.
    await page.mouse.move(box.x + 300, box.y + 200);
    const zoomBeforeWheel = (await svgData(page)).zoom;
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(200);
    const zoomAfterWheel = (await svgData(page)).zoom;
    check(zoomAfterWheel < zoomBeforeWheel, `Wheel down does not zoom out (${zoomBeforeWheel} -> ${zoomAfterWheel}).`);
    const sliderValue = parseFloat(await page.locator(SEL.slider).inputValue());
    check(Math.abs(sliderValue - zoomAfterWheel) < 0.02, `The slider (${sliderValue}) does not follow the wheel zoom.`);
    check(
        Math.round(zoomAfterWheel * 100) % 25 !== 0,
        `Wheel zoom landed on ${zoomAfterWheel}: zoom should be continuous, not snap to positions.`
    );

    // Double-click on the background zooms in.
    await setZoom(page, 1);
    await page.mouse.dblclick(box.x + 80, box.y + box.height - 40);
    await page.waitForTimeout(200);
    check((await svgData(page)).zoom > 1.5, "Double-click does not zoom in.");

    // Back to the company view, then select a scenario: jumps to stop 2 with a numbered route.
    await setZoom(page, 1);
    const select = page.locator(SEL.scenarioSelect).first();
    const optionCount = await select.locator("option").count();
    check(optionCount >= 2, `The scenario select has ${optionCount} option(s); at least one scenario is needed.`);
    // The last scenario is the longest route in the generic template.
    await select.selectOption({ index: optionCount - 1 });
    await expectVisible(page, SEL.badge, "numbered route badges");
    const stopAfter = (await svgData(page)).stop;
    check(stopAfter === 2, `Selecting a scenario should jump to stop 2, the map is at stop ${stopAfter}.`);
    const badgeTexts = await page.locator(`${SEL.badge} text`).allTextContents();
    check(badgeTexts[0] === "1", `The first route badge reads "${badgeTexts[0]}" instead of "1".`);
    const badgeVisible = await page.locator(SEL.badge).first().evaluate((el) => {
        const r = el.getBoundingClientRect();
        const body = document.querySelector(".o_pan_sl_body").getBoundingClientRect();
        return r.left >= body.left && r.right <= body.right && r.top >= body.top && r.bottom <= body.bottom;
    });
    check(badgeVisible, "The first route badge is not in view (the route is not fitted).");
    await expectNoBlack(page, "scenario route");
    await page.screenshot({ path: join(out, "desktop_scenario.png") });

    // Click an activity on the route: the panel opens; Esc closes it.
    await clickVisibleChip(page, `${SEL.chip}:not(.o_pan_sl_dim)`, "route chip");
    await expectVisible(page, SEL.panel, "activity side panel");
    await page.screenshot({ path: join(out, "desktop_panel.png") });
    await page.keyboard.press("Escape");
    await expectGone(page, SEL.panel, "The side panel after pressing Esc");

    // Keyboard: a chip is focusable and Enter opens the panel.
    await page.locator(SEL.chip).first().focus();
    await page.keyboard.press("Enter");
    await expectVisible(page, SEL.panel, "activity side panel (opened with Enter)");
    await page.keyboard.press("Escape");
    await expectGone(page, SEL.panel, "The side panel after pressing Esc (keyboard)");
    await expectNoErrorDialog(page);

    await checkStateRestore(page);
    await expectNoErrorDialog(page);
}

async function checkMobile(page, out) {
    await setZoom(page, 2);
    const info = await svgData(page);
    const sizes = await page.evaluate(() => ({
        page: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
        body: document.querySelector(".o_pan_sl_body").clientWidth,
    }));
    check(
        sizes.page <= sizes.viewport,
        `The page scrolls sideways on mobile (${sizes.page}px wide in a ${sizes.viewport}px viewport).`
    );
    check(info.mapWidth > sizes.body, "On mobile the map should be wider than its container (and pan inside it).");
    await expectNoBlack(page, "mobile");
    await clickVisibleChip(page, SEL.chip, "activity chip");
    await expectVisible(page, SEL.panel, "activity side panel (mobile)");
    const sheet = await page.locator(SEL.panel).evaluate((el) => {
        const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, bottom: r.bottom, width: window.innerWidth, height: window.innerHeight };
    });
    check(
        sheet.left <= 1 && sheet.right >= sheet.width - 1 && Math.abs(sheet.bottom - sheet.height) <= 2,
        `On mobile the panel should be a bottom sheet, it sits at ${JSON.stringify(sheet)}.`
    );
    await page.screenshot({ path: join(out, "mobile.png") });
    await page.keyboard.press("Escape");
    await expectGone(page, SEL.panel, "The side panel after pressing Esc (mobile)");
    await expectNoErrorDialog(page);
}

async function runViewport(browser, db, out, viewport, run, problems) {
    const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: 1,
        hasTouch: viewport === MOBILE,
    });
    const page = await context.newPage();
    const label = viewport.name;
    page.on("pageerror", (error) => problems.push(`[${label}] page error: ${error.message}`));
    page.on("console", (msg) => {
        if (msg.type() === "error") {
            problems.push(`[${label}] console error: ${msg.text()}`);
        }
    });
    try {
        await login(page, db);
        await openMap(page);
        await run(page, out);
    } catch (error) {
        await page.screenshot({ path: join(out, `${label}_failure.png`) }).catch(() => {});
        problems.push(`[${label}] ${error.message}`);
    } finally {
        await context.close();
    }
}

async function main() {
    const db = requireEnv("DB");
    const out = requireEnv("OUT");
    mkdirSync(out, { recursive: true });

    const problems = [];
    const browser = await chromium.launch();
    try {
        await runViewport(browser, db, out, DESKTOP, checkDesktop, problems);
        await runViewport(browser, db, out, MOBILE, checkMobile, problems);
    } finally {
        await browser.close();
    }

    if (problems.length) {
        console.error(`UI check failed (${problems.length} problem(s)):`);
        for (const problem of problems) {
            console.error(`- ${problem}`);
        }
        process.exit(1);
    }
    console.log(`UI check passed. Screenshots in ${out}`);
}

main().catch((error) => {
    console.error(`UI check could not run: ${error.message}`);
    process.exit(2);
});
