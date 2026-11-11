#!/usr/bin/env node
// UI check for the map (pan_self_learning_blueprint, Blueprint 2.3.1).
//
// Logs in to a running Odoo as admin/admin and opens Projects > Map (the "Map"
// view of the project's tasks). The map is one zoomable stage with levels of
// detail z0 (company) to z4 (task). At desktop (1440x900), iPad landscape
// (1024x768, touch) and phone (390x844, touch) it walks the levels and
// screenshots each (z0_company ... z4_task), and checks:
//
// - each level shows exactly its layers (data-layer); the legend has the six
//   steps; z1 shows the burn-up (actual and dashed ideal line, today, the
//   milestone ticks) instead of the timeline, and the server's verdict
//   ("On track" or "Behind · N weeks") next to the next milestone; z2 lists the flows in the server's order, without task names, and
//   at 1440x900 every flow row is in view;
// - zooming: Ctrl + wheel on desktop (a plain wheel does not zoom), a
//   two-finger pinch on the iPad, + on the phone; the breadcrumb and - zoom out;
// - clicking a flow flies to its swimlane: its placed tasks, N-1 arrows left
//   to right ending at their chips, its steps listed; a chip flies to the task:
//   its facts, one primary button, the panel docked beside the stage;
// - the page never scrolls (sideways or down) at any level; on touch every
//   button of the map is 44 px or taller; nothing in an undefined colour;
// - the map follows Odoo's dark colour variables (desktop_dark).
//
// Never waits for "networkidle" (Odoo's bus long-polls). Exits non-zero on a
// page error, console error, Odoo error dialog or failed check. For a big map
// seed with BLUEPRINT_SEED_SIZE=large (tools/seed_demo.py).
//
// Usage:
//   DB=mydb OUT=/tmp/ui [URL=http://localhost:8069] node tools/ui_check.mjs

import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE_URL = process.env.URL || "http://localhost:8069";
const MAP_URL = `${BASE_URL}/odoo/action-pan_self_learning_blueprint.action_blueprint_map`;
const TIMEOUT = 30000;
const VIEWPORTS = [
    { name: "desktop", width: 1440, height: 900, touch: false },
    { name: "ipad", width: 1024, height: 768, touch: true },
    { name: "phone", width: 390, height: 844, touch: true },
    { name: "desktop_dark", width: 1440, height: 900, touch: false, dark: true },
];

class CheckError extends Error {}

function check(condition, message) {
    if (!condition) {
        throw new CheckError(message);
    }
}

function requireEnv(name) {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Environment variable ${name} is required (see the header of tools/ui_check.mjs).`);
    }
    return value;
}

async function rpc(page, model, method, args, kwargs = {}) {
    return page.evaluate(
        async ({ model, method, args, kwargs }) => {
            const response = await fetch(`/web/dataset/call_kw/${model}/${method}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { model, method, args, kwargs } }),
            });
            const payload = await response.json();
            if (payload.error) {
                throw new Error(`${model}.${method}: ${payload.error.data?.message || payload.error.message}`);
            }
            return payload.result;
        },
        { model, method, args, kwargs }
    );
}

async function login(page, db) {
    await page.goto(`${BASE_URL}/web/login?db=${encodeURIComponent(db)}`);
    await page.fill("input[name=login]", "admin");
    await page.fill("input[name=password]", "admin");
    await Promise.all([
        page.waitForURL((url) => !url.pathname.startsWith("/web/login"), { timeout: TIMEOUT }),
        page.click("button[type=submit]"),
    ]);
}

async function shot(page, out, viewport, name) {
    await page.waitForTimeout(250);
    check(!(await page.locator(".o_error_dialog").count()), `${viewport.name} ${name}: Odoo shows an error dialog.`);
    await page.screenshot({ path: join(out, `${viewport.name}_${name}.png`) });
}

/** Opens the map like the menu does; several projects show a list, so pick the one with the most tasks. */
async function openMap(page, project) {
    await page.goto(MAP_URL);
    await page.locator(".o_pan_sl_map .o_pan_sl_frame, .o_pan_sl_map .o_pan_sl_projects").first().waitFor({ timeout: TIMEOUT });
    if (await page.locator(".o_pan_sl_projects").count()) {
        await page.locator(".o_pan_sl_project", { hasText: project.name }).click();
    }
    await page.locator(".o_pan_sl_map .o_pan_sl_frame").waitFor({ timeout: TIMEOUT });
    check(await page.locator(".o_switch_view.o_pan_blueprint.active, .o_pan_sl_map .o_control_panel .fa-map-o").count(), "Map is not the active view.");
    check(await page.locator(".o_pan_sl_map .o_searchview, .o_pan_sl_map .o_searchview_toggler, .o_pan_sl_map .o_control_panel button .fa-search, .o_pan_sl_map .o_control_panel .oi-search").count(), "no search bar.");
}

/**
 * Community Odoo has no dark mode (web_enterprise brings the dark variables),
 * so set Odoo's own colour variables to dark values, as the dark bundle does,
 * and check that the map follows them.
 */
async function useDarkTokens(page) {
    await page.addStyleTag({
        content: `:root, .o_web_client { --body-bg: #262a36; --body-color: #e4e4e4; --border-color: #3c3e4b;
            --secondary-color: #a4a8b6; --o-view-background-color: #262a36; background: #262a36; color: #e4e4e4; }`,
    });
    const bg = await page.locator(".o_pan_sl_map").evaluate((el) => getComputedStyle(el).backgroundColor);
    check(bg === "rgb(38, 42, 54)", `dark: the map background is ${bg}, it ignores Odoo's colour variables.`);
}

/** Waits until the stage rests at a whole level (no transform left from a gesture). */
async function atZoom(page, viewport, level) {
    await page.waitForFunction(
        (want) => {
            const frame = document.querySelector(".o_pan_sl_frame");
            const lod = document.querySelector(".o_pan_sl_lod");
            return frame && Number(frame.dataset.zoom) === want && /^(scale\(1\))?$/.test(lod.style.transform);
        },
        level,
        { timeout: TIMEOUT }
    ).catch(async () => {
        const now = await page.locator(".o_pan_sl_frame").getAttribute("data-zoom");
        throw new CheckError(`${viewport.name}: expected zoom ${level}, the map is at ${now}.`);
    });
    await page.waitForTimeout(150);
}

async function layers(page) {
    return page.evaluate(() => [...new Set([...document.querySelectorAll("[data-layer]")].map((el) => el.dataset.layer))].sort().join(","));
}

/** No page scroll; on touch, every button of the map 44 px or taller; nothing in an undefined colour. */
async function checkLayout(page, viewport, label) {
    const layout = await page.evaluate(() => {
        const rect = (el) => el.getBoundingClientRect();
        const small = [...document.querySelectorAll(".o_pan_sl_map .o_content button")]
            .filter((el) => el.offsetParent && rect(el).height < 43.5)
            .map((el) => `${el.className.split(" ")[0]} "${el.textContent.trim().slice(0, 20)}" ${Math.round(rect(el).height)}px`);
        const black = [...document.querySelectorAll(".o_pan_sl_map .o_pan_sl_dot, .o_pan_sl_map .o_pan_sl_stack > span")]
            .filter((el) => getComputedStyle(el).backgroundColor === "rgb(0, 0, 0)").length;
        const doc = document.documentElement;
        return {
            scrollsX: doc.scrollWidth > window.innerWidth + 1,
            scrollsY: doc.scrollHeight > window.innerHeight + 1,
            small,
            black,
        };
    });
    check(!layout.scrollsX, `${viewport.name} ${label}: the page scrolls sideways.`);
    check(!layout.scrollsY, `${viewport.name} ${label}: the page scrolls down.`);
    check(!layout.black, `${viewport.name} ${label}: ${layout.black} dots or bars are black (undefined colour).`);
    if (viewport.touch) {
        check(!layout.small.length, `${viewport.name} ${label}: tap targets under 44 px: ${layout.small.slice(0, 5).join("; ")}`);
    }
}

/** z1: the burn-up's lines and marks fit their box, and the caption carries the server's verdict. */
async function checkBurnup(page, viewport, data) {
    const chart = await page.evaluate(() => {
        const box = document.querySelector(".o_pan_sl_burnup_plot").getBoundingClientRect();
        const points = document.querySelector(".o_pan_sl_burnup_actual").getAttribute("points").trim().split(/\s+/);
        const inside = (el) => {
            const rect = el.getBoundingClientRect();
            return rect.left >= box.left - 8 && rect.right <= box.right + 8;
        };
        return {
            points: points.length,
            dashed: getComputedStyle(document.querySelector(".o_pan_sl_burnup_ideal")).strokeDasharray !== "none",
            ticks: document.querySelectorAll(".o_pan_sl_burnup_tick").length,
            today: inside(document.querySelector(".o_pan_sl_burnup_today")),
            height: box.height,
            status: document.querySelector(".o_pan_sl_caption_status").textContent.replace(/\s+/g, " ").trim(),
        };
    });
    check(chart.points === data.progress_history.length, `${viewport.name}: burn-up has ${chart.points} points, expected ${data.progress_history.length}.`);
    check(chart.dashed, `${viewport.name}: the ideal line is not dashed.`);
    check(chart.ticks === data.milestones.filter((milestone) => milestone.deadline).length, `${viewport.name}: milestone ticks ${chart.ticks}.`);
    check(chart.today && chart.height >= 80, `${viewport.name}: the burn-up is cut off (height ${chart.height}).`);
    const weeks = data.weeks_behind === 1 ? "Behind · 1 week" : `Behind · ${data.weeks_behind} weeks`;
    const want = data.verdict === "on_track" ? "On track" : weeks;
    check(chart.status === want, `${viewport.name}: verdict "${chart.status}", expected "${want}".`);
}

/** A two-finger pinch through the DevTools protocol (Playwright has no pinch). */
async function pinch(page, factor) {
    const client = await page.context().newCDPSession(page);
    const box = await page.locator(".o_pan_sl_stage").boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + Math.min(box.height / 2, 250);
    const points = (spread) => [
        { x: cx - spread, y: cy, id: 0 },
        { x: cx + spread, y: cy, id: 1 },
    ];
    await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: points(60) });
    for (let step = 1; step <= 8; step++) {
        await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: points(60 * factor ** (step / 8)) });
    }
    await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await client.detach();
}

async function checkLevels(page, out, viewport, data) {
    const placed = data.tasks.filter((task) => task.role_id && task.phase_id).map((task) => task.id);
    // z0: the company and the timeline.
    await atZoom(page, viewport, 0);
    check((await layers(page)) === "company,systems,timeline", `${viewport.name}: z0 layers ${await layers(page)}`);
    if (data.project.brief) {
        check(await page.locator(".o_pan_sl_headline").count(), `${viewport.name}: no headline at z0.`);
    }
    await checkLayout(page, viewport, "z0");
    await shot(page, out, viewport, "z0_company");

    // z1, with a pinch on touch, Ctrl + wheel on desktop, + on the phone.
    const stage = page.locator(".o_pan_sl_stage");
    if (viewport.name === "ipad") {
        await pinch(page, 2.2);
    } else if (!viewport.touch) {
        const box = await stage.boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + 200);
        await page.mouse.wheel(0, 400);
        await page.waitForTimeout(600);
        check((await page.locator(".o_pan_sl_frame").getAttribute("data-zoom")) === "0", `${viewport.name}: a plain wheel zoomed.`);
        await page.keyboard.down("Control");
        await page.mouse.wheel(0, -250);
        await page.keyboard.up("Control");
    } else {
        await page.locator(".o_pan_sl_zoom_in").click();
    }
    await atZoom(page, viewport, 1);
    const z1 = data.ideal ? "burnup,caption,legend,projectBar,systems" : "caption,legend,projectBar,systems,timeline";
    check((await layers(page)) === z1, `${viewport.name}: z1 layers ${await layers(page)}`);
    if (data.ideal) {
        await checkBurnup(page, viewport, data);
    }
    const legend = (await page.locator(".o_pan_sl_legend li").allTextContents()).map((item) => item.trim()).join("|");
    check(legend === "Open|Decided|Built|Tested|Trained|Live", `${viewport.name}: legend ${legend}`);
    await checkLayout(page, viewport, "z1");
    await shot(page, out, viewport, "z1_project");

    // z2: the flows, worst first, no task names.
    await page.locator(".o_pan_sl_zoom_in").click();
    await atZoom(page, viewport, 2);
    const names = await page.locator(".o_pan_sl_flow .o_pan_sl_flow_name").allTextContents();
    check(names.join("|") === data.flows.map((flow) => flow.name).join("|"), `${viewport.name}: flow order differs from the server.`);
    check(!(await page.locator(".o_pan_sl_chip").count()), `${viewport.name}: task chips at z2.`);
    await checkLayout(page, viewport, "z2");
    if (!viewport.touch) {
        // At 1440x900 every flow row is in view without scrolling.
        const hidden = await page.evaluate(() => {
            const stage = document.querySelector(".o_pan_sl_stage").getBoundingClientRect();
            return [...document.querySelectorAll(".o_pan_sl_flow")].filter((el) => el.getBoundingClientRect().bottom > stage.bottom + 1).length;
        });
        check(!hidden, `${viewport.name}: ${hidden} flow rows below the fold at z2.`);
    }
    await shot(page, out, viewport, "z2_flows");

    // z3: click the flow with the most placed tasks: it flies to its swimlane.
    const placedOf = (flow) => flow.task_ids.filter((id) => placed.includes(id)).length;
    const flow = data.flows.reduce((best, item) => (placedOf(item) > placedOf(best) ? item : best));
    await page.locator(`.o_pan_sl_flow[data-flow-id="${flow.id}"]`).click();
    await atZoom(page, viewport, 3);
    const steps = placedOf(flow);
    check((await page.locator(".o_pan_sl_chip").count()) === steps, `${viewport.name}: chips in the swimlane, expected ${steps}.`);
    await page.waitForFunction((count) => document.querySelectorAll(".o_pan_sl_arrow").length === count, Math.max(0, steps - 1), { timeout: TIMEOUT });
    const arrowsOk = await page.evaluate(() =>
        [...document.querySelectorAll(".o_pan_sl_arrow")].every((path) => {
            const point = path.getPointAtLength(path.getTotalLength());
            const svg = path.ownerSVGElement.getBoundingClientRect();
            const rect = document.querySelector(`.o_pan_sl_chip[data-task-id="${path.dataset.to}"]`).getBoundingClientRect();
            const xs = path.getAttribute("d").match(/-?[\d.]+,-?[\d.]+/g).map((pair) => Number(pair.split(",")[0]));
            const [x, y] = [svg.left + point.x, svg.top + point.y];
            return xs.at(-1) > xs[0] && x >= rect.left - 3 && x <= rect.right + 3 && y >= rect.top - 3 && y <= rect.bottom + 3;
        })
    );
    check(arrowsOk, `${viewport.name}: an arrow runs backwards or does not end at its chip.`);
    const crumbs = (await page.locator(".o_pan_sl_crumbs").innerText()).replace(/\s+/g, " ").trim();
    check(crumbs.endsWith(`› ${flow.name}`), `${viewport.name}: breadcrumb "${crumbs}"`);
    const listed = await page.locator(".o_pan_sl_open_task").count();
    const all = data.tasks.filter((task) => flow.task_ids.includes(task.id)).length;
    check(listed === all, `${viewport.name}: ${listed} steps listed, expected ${all}.`);
    await checkLayout(page, viewport, "z3");
    await shot(page, out, viewport, "z3_flow");

    // z4: a chip flies to its task: facts, one primary button, Move to.
    await page.locator(".o_pan_sl_chip").first().click();
    await atZoom(page, viewport, 4);
    const facts = await page.locator(".o_pan_sl_task_panel dt").allTextContents();
    check(facts.join("|") === "Flow|Role|Phase|Progress|Owners|Hours", `${viewport.name}: task facts ${facts.join("|")}`);
    const primary = await page.locator(".o_pan_sl_map .o_content .btn-primary").allTextContents();
    check(primary.length === 1 && primary[0].trim() === "Open task", `${viewport.name}: primary buttons: ${primary.join(", ")}`);
    if (viewport.name !== "phone") {
        const docked = await page.evaluate(
            () => document.querySelector(".o_pan_sl_task_panel").getBoundingClientRect().left >= document.querySelector(".o_pan_sl_stage").getBoundingClientRect().right - 1
        );
        check(docked, `${viewport.name}: the task panel covers the stage.`);
    }
    await checkLayout(page, viewport, "z4");
    await shot(page, out, viewport, "z4_task");

    // The breadcrumb zooms back out to the flows; - to the project.
    await page.locator(".o_pan_sl_crumb", { hasText: "Flows" }).click();
    await atZoom(page, viewport, 2);
    await page.locator(".o_pan_sl_zoom_out").click();
    await atZoom(page, viewport, 1);
}

async function runViewport(browser, db, out, viewport, problems) {
    const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        hasTouch: viewport.touch,
        isMobile: viewport.name === "phone",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => problems.push(`${viewport.name}: page error: ${error.message}`));
    page.on("console", (message) => {
        if (message.type() === "error") {
            problems.push(`${viewport.name}: console error: ${message.text()}`);
        }
    });
    try {
        await login(page, db);
        const projects = await rpc(page, "project.project", "get_blueprint_map_projects", []);
        check(projects.length, "No project has a map: load the template into a project first.");
        const all = await Promise.all(projects.map((project) => rpc(page, "project.project", "get_blueprint_map_data", [[project.id]])));
        const data = all.reduce((best, item) => (item.tasks.length > best.tasks.length ? item : best));
        // Start at z0: forget the zoom of an earlier run in this tab.
        await page.evaluate(() => sessionStorage.clear());
        await openMap(page, data.project);
        // A fresh database greets with an OdooBot chat window over the page.
        await page.addStyleTag({ content: ".o-mail-ChatWindow, .o-mail-ChatHub { display: none !important; }" });
        if (viewport.dark) {
            await useDarkTokens(page);
            await page.locator(".o_pan_sl_zoom_in").click();
            await atZoom(page, viewport, 1);
            await checkLayout(page, viewport, "z1");
            await shot(page, out, viewport, "z1_project");
            await page.locator(".o_pan_sl_zoom_in").click();
            await atZoom(page, viewport, 2);
            await checkLayout(page, viewport, "z2");
            await shot(page, out, viewport, "z2_flows");
        } else {
            await checkLevels(page, out, viewport, data);
        }
        console.log(`${viewport.name}: ok`);
    } catch (error) {
        problems.push(`${viewport.name}: ${error.message}`);
        await page.screenshot({ path: join(out, `${viewport.name}_failure.png`) }).catch(() => {});
    } finally {
        await context.close();
    }
}

async function main() {
    const db = requireEnv("DB");
    const out = requireEnv("OUT");
    mkdirSync(out, { recursive: true });
    const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
    const problems = [];
    try {
        for (const viewport of VIEWPORTS) {
            await runViewport(browser, db, out, viewport, problems);
        }
    } finally {
        await browser.close();
    }
    if (problems.length) {
        console.error(problems.join("\n"));
        process.exit(1);
    }
    console.log(`All checks passed. Screenshots in ${out}`);
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
