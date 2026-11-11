#!/usr/bin/env node
// UI check for the company map (pan_self_learning_blueprint, data model v2.0).
//
// Logs in to a running Odoo as admin/admin, opens a project form and clicks
// "Map". At desktop (1440x900), iPad (1024x768) and phone (390x844) width it
// screenshots the three zoom stops (Company, Tasks, Detail), colour by
// Training, a flow selected, the task panel and the role panel, and checks:
//
// - each stop draws what it should (blocks with counts; chips; detail lines);
// - colour by offers exactly Progress and Training, with the right tones;
// - every flow, once selected, has all of its tasks in view and the rest dimmed,
//   and the choice is announced;
// - the task panel has one primary button, "Open task", and Esc closes it;
// - the role panel lists the role's people and its ADKAR band;
// - the "N tasks without a place" link matches the data;
// - drag pans, a two-finger pinch zooms, arrow keys pan and Home fits (desktop);
// - a page refresh keeps zoom, centre, flow and colour mode (desktop);
// - the page never scrolls sideways (phone);
// - no SVG shape is painted black (an undefined CSS variable in an SVG fill).
//
// Never waits for "networkidle": Odoo's bus long-polls. It waits for the
// map's own elements. Exits non-zero on any page error, console error, Odoo
// error dialog or failed check.
//
// Usage:
//   DB=mydb OUT=/tmp/ui [URL=http://localhost:8069] [PROJECT=14] node tools/ui_check.mjs
//
// PROJECT defaults to the first project that has map roles.

import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE_URL = process.env.URL || "http://localhost:8069";
const TIMEOUT = 30000;
const VIEWPORTS = [
    { name: "desktop", width: 1440, height: 900, full: true },
    { name: "ipad", width: 1024, height: 768, full: false },
    { name: "phone", width: 390, height: 844, full: false },
];
const STOPS = [
    { value: 1, label: "Company" },
    { value: 2, label: "Tasks" },
    { value: 3, label: "Detail" },
];
const TRAINED_RUNG = 4;
const TESTED_RUNG = 3;

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

/** From the project form ("Map"); on a phone the button sits in a menu, so the map URL is opened. */
async function openMap(page, projectId, mapUrl) {
    if (mapUrl) {
        await page.goto(mapUrl);
    } else {
        await page.goto(`${BASE_URL}/odoo/project.project/${projectId}`);
        await page.locator("button[name=action_open_blueprint_map]").click({ timeout: TIMEOUT });
    }
    await page.locator(".o_pan_sl_map .o_pan_sl_svg").waitFor({ timeout: TIMEOUT });
    await page.waitForTimeout(300);
    return page.url();
}

async function svgState(page) {
    return page.locator(".o_pan_sl_svg").evaluate((el) => ({
        stop: parseInt(el.dataset.stop, 10),
        zoom: parseFloat(el.dataset.zoom),
        viewBox: el.getAttribute("viewBox").split(" ").map(parseFloat),
    }));
}

async function zoomTo(page, stop) {
    await page.locator(".o_pan_sl_zoom_label", { hasText: stop.label }).click();
    await page.waitForFunction((value) => document.querySelector(".o_pan_sl_svg")?.dataset.stop === String(value), stop.value);
    await page.waitForTimeout(150);
}

async function blackShapes(page) {
    return page.evaluate(() => {
        const black = new Set(["rgb(0, 0, 0)", "#000000", "black"]);
        return [...document.querySelectorAll(".o_pan_sl_map svg rect, .o_pan_sl_map svg circle, .o_pan_sl_map svg path")]
            .filter((el) => !el.closest("clipPath"))
            .filter((el) => {
                const style = getComputedStyle(el);
                return black.has(style.fill) || (style.stroke !== "none" && black.has(style.stroke));
            })
            .map((el) => `${el.tagName}.${el.getAttribute("class") || ""}`);
    });
}

async function shot(page, out, viewport, name) {
    const found = await blackShapes(page);
    check(!found.length, `${viewport.name} ${name}: ${found.length} SVG shape(s) painted black, e.g. ${found.slice(0, 3).join("; ")}`);
    check(!(await page.locator(".o_error_dialog").count()), `${viewport.name} ${name}: Odoo shows an error dialog.`);
    await page.screenshot({ path: join(out, `${viewport.name}_${name}.png`) });
}

/** {taskId: tone} of every chip. */
async function chipTones(page) {
    return page.evaluate(() =>
        Object.fromEntries(
            [...document.querySelectorAll(".o_pan_sl_chip")].map((chip) => [
                chip.dataset.item.slice(1),
                [...chip.querySelector(".o_pan_sl_dot").classList].find((c) => c.startsWith("o_pan_sl_tone_"))?.slice(14),
            ])
        )
    );
}

/** Chip ids whose box lies wholly inside the free part of the map (not under the sticky bands). */
async function chipsInView(page) {
    return page.evaluate(() => {
        const body = document.querySelector(".o_pan_sl_body").getBoundingClientRect();
        return [...document.querySelectorAll(".o_pan_sl_chip")]
            .filter((chip) => {
                const r = chip.getBoundingClientRect();
                return r.left >= body.left - 1 && r.right <= body.right + 1 && r.top >= body.top - 1 && r.bottom <= body.bottom + 1;
            })
            .map((chip) => parseInt(chip.dataset.item.slice(1), 10));
    });
}

/** Click the first chip whose centre is not covered, like a user would. */
async function clickVisibleChip(page) {
    const point = await page.evaluate(() => {
        for (const chip of document.querySelectorAll(".o_pan_sl_chip")) {
            const r = chip.getBoundingClientRect();
            const [x, y] = [r.left + r.width / 2, r.top + Math.min(r.height / 2, 14)];
            const hit = document.elementFromPoint(x, y);
            if (hit && chip.contains(hit)) {
                return { x, y, id: parseInt(chip.dataset.item.slice(1), 10) };
            }
        }
        return null;
    });
    check(point, "No chip is visible to click.");
    await page.mouse.click(point.x, point.y);
    return point.id;
}

async function checkStops(page, out, viewport, data) {
    await zoomTo(page, STOPS[0]);
    const blocks = await page.locator(".o_pan_sl_block").count();
    check(blocks > 0 && !(await page.locator(".o_pan_sl_chip").count()), `${viewport.name}: Company shows ${blocks} blocks and chips.`);
    const counted = await page.locator(".o_pan_sl_block_count").allTextContents();
    const total = counted.reduce((sum, text) => sum + parseInt(text, 10), 0);
    check(total === data.tasks.length, `${viewport.name}: blocks count ${total} tasks, the data has ${data.tasks.length}.`);
    await shot(page, out, viewport, "1_company");

    await zoomTo(page, STOPS[1]);
    check((await page.locator(".o_pan_sl_chip").count()) === data.tasks.length, `${viewport.name}: Tasks does not draw a chip per task.`);
    check(!(await page.locator(".o_pan_sl_detail").count()), `${viewport.name}: Tasks shows detail lines.`);
    await shot(page, out, viewport, "2_tasks");

    await zoomTo(page, STOPS[2]);
    check((await page.locator(".o_pan_sl_detail").count()) === data.tasks.length, `${viewport.name}: Detail lacks detail lines.`);
    await shot(page, out, viewport, "3_detail");
}

async function checkColours(page, out, viewport, data) {
    await zoomTo(page, STOPS[1]);
    const modes = await page.locator(".o_pan_sl_color_select option").evaluateAll((els) => els.map((el) => el.value));
    check(modes.join(",") === "progress,training", `Colour by offers ${modes.join(",")}.`);
    const roles = new Map(data.roles.map((role) => [role.id, role]));
    const expected = {
        progress: (task) => (task.rung >= TESTED_RUNG ? "ok" : task.rung > 0 ? "warn" : "off"),
        training: (task) => (!roles.get(task.role_id).users.length ? "off" : task.rung >= TRAINED_RUNG ? "ok" : "warn"),
    };
    for (const mode of ["training", "progress"]) {
        await page.locator(".o_pan_sl_color_select").selectOption(mode);
        await page.waitForTimeout(100);
        const tones = await chipTones(page);
        for (const task of data.tasks) {
            check(tones[task.id] === expected[mode](task), `${mode}: "${task.name}" is ${tones[task.id]}, expected ${expected[mode](task)}.`);
        }
        check((await page.locator(".o_pan_sl_legend li").count()) === 3, `${mode}: the legend does not have three items.`);
        if (mode === "training") {
            await shot(page, out, viewport, "4_training");
        }
    }
}

async function checkFlows(page, out, viewport, data) {
    const select = page.locator(".o_pan_sl_flow_select");
    const placed = new Set(data.tasks.map((task) => task.id));
    let shown = false;
    for (const flow of data.flows) {
        await zoomTo(page, STOPS[0]);
        await select.selectOption(String(flow.id));
        await page.waitForTimeout(200);
        check((await svgState(page)).stop === 2, `Flow "${flow.name}": the map is not at the Tasks stop.`);
        const ids = flow.task_ids.filter((id) => placed.has(id));
        const inView = new Set(await chipsInView(page));
        const outside = ids.filter((id) => !inView.has(id));
        // A phone may be too narrow for a long flow: then it starts at the flow's first task.
        if (viewport.name !== "phone") {
            check(!outside.length, `${viewport.name}: flow "${flow.name}": ${outside.length} of ${ids.length} tasks out of view.`);
        } else {
            check(!ids.length || inView.has(ids[0]) || outside.length < ids.length, `phone: flow "${flow.name}": no task of it in view.`);
        }
        const dimmed = await page.locator(".o_pan_sl_chip.o_pan_sl_dim").count();
        check(dimmed === data.tasks.length - ids.length, `Flow "${flow.name}": ${dimmed} chips dimmed, expected ${data.tasks.length - ids.length}.`);
        const status = (await page.locator(".o_pan_sl_flow_status").textContent()).trim();
        check(status === `Showing flow ${flow.name}, ${flow.task_ids.length} tasks`, `Flow "${flow.name}": announced "${status}".`);
        if (!shown && ids.length > 1) {
            await shot(page, out, viewport, "5_flow");
            shown = true;
        }
    }
    await select.selectOption("");
    await page.waitForTimeout(100);
    check((await page.locator(".o_pan_sl_flow_status").textContent()).trim() === "Showing all tasks", "Clearing the flow is not announced.");
}

async function checkPanels(page, out, viewport, data) {
    await zoomTo(page, STOPS[1]);
    const taskId = await clickVisibleChip(page);
    const task = data.tasks.find((candidate) => candidate.id === taskId);
    await page.locator(".o_pan_sl_panel").waitFor();
    check((await page.locator(".o_pan_sl_panel_title").textContent()).trim() === task.name, "The task panel shows another task.");
    const primary = await page.locator(".o_pan_sl_map .btn-primary").allTextContents();
    check(primary.length === 1 && primary[0].trim() === "Open task", `Primary buttons: ${JSON.stringify(primary)}.`);
    await shot(page, out, viewport, "6_task_panel");
    await page.keyboard.press("Escape");
    await page.locator(".o_pan_sl_panel").waitFor({ state: "detached", timeout: 5000 });

    const label = page.locator(".o_pan_sl_role_label_group").first();
    const roleId = parseInt(await label.getAttribute("data-role"), 10);
    const role = data.roles.find((candidate) => candidate.id === roleId);
    await label.focus();
    await page.keyboard.press("Enter");
    await page.locator(".o_pan_sl_role_panel").waitFor();
    const people = (await page.locator(".o_pan_sl_role_people").textContent()).trim();
    check(people === (role.users.length ? role.users.join(", ") : "Nobody holds this role yet"), `Role panel lists "${people}".`);
    const adkar = (await page.locator(".o_pan_sl_role_adkar").textContent()).trim();
    check(role.adkar ? adkar.toLowerCase() === role.adkar : adkar === "Needs three scored people", `Role panel ADKAR "${adkar}".`);
    await shot(page, out, viewport, "7_role_panel");
    await page.keyboard.press("Escape");
    await page.locator(".o_pan_sl_role_panel").waitFor({ state: "detached", timeout: 5000 });

    const unplaced = page.locator(".o_pan_sl_unplaced");
    if (data.unplaced_count) {
        const text = (await unplaced.textContent()).replace(/\s+/g, " ").trim();
        const word = data.unplaced_count === 1 ? "task" : "tasks";
        check(text === `${data.unplaced_count} ${word} without a place`, `Unplaced link reads "${text}".`);
    } else {
        check(!(await unplaced.count()), "An unplaced link without unplaced tasks.");
    }
}

/** Drag pans, a two-finger pinch zooms, arrows pan, Home fits. */
async function checkGestures(page) {
    await zoomTo(page, STOPS[2]);
    const box = await page.locator(".o_pan_sl_body").boundingBox();
    const before = await svgState(page);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height - 40);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 200, box.y + box.height - 140, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(100);
    const after = await svgState(page);
    check(after.viewBox[0] > before.viewBox[0] || after.viewBox[1] > before.viewBox[1], "Dragging does not pan the map.");

    const zoom = (await svgState(page)).zoom;
    await page.locator(".o_pan_sl_svg").evaluate((svg, rect) => {
        svg.setPointerCapture = () => {}; // synthetic pointers cannot be captured
        const fire = (type, id, x) =>
            svg.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", clientX: x, clientY: rect.y + rect.height / 2, bubbles: true }));
        const mid = rect.x + rect.width / 2;
        fire("pointerdown", 11, mid - 100);
        fire("pointerdown", 12, mid + 100);
        fire("pointermove", 11, mid - 80);
        fire("pointermove", 12, mid + 80);
        fire("pointerup", 11, mid - 80);
        fire("pointerup", 12, mid + 80);
    }, box);
    await page.waitForTimeout(150);
    check((await svgState(page)).zoom < zoom, "Pinching in does not zoom out.");

    await page.locator(".o_pan_sl_svg").focus();
    const start = await svgState(page);
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowDown");
    const moved = await svgState(page);
    check(moved.viewBox[0] !== start.viewBox[0] || moved.viewBox[1] !== start.viewBox[1], "Arrow keys do not pan the map.");
    await page.keyboard.press("Home");
    await page.waitForTimeout(100);
    check((await svgState(page)).stop === 1, "Home does not fit the whole map.");
}

/** A page refresh keeps zoom, centre, flow and colour mode. */
async function checkRefresh(page, data) {
    const flow = data.flows.find((candidate) => candidate.task_ids.length);
    if (flow) {
        await page.locator(".o_pan_sl_flow_select").selectOption(String(flow.id));
    }
    await page.locator(".o_pan_sl_color_select").selectOption("training");
    await page.waitForTimeout(200);
    const before = await svgState(page);
    await page.reload();
    await page.locator(".o_pan_sl_svg").waitFor({ timeout: TIMEOUT });
    await page.waitForTimeout(300);
    const after = await svgState(page);
    const centre = (box) => [box[0] + box[2] / 2, box[1] + box[3] / 2];
    const [[bx, by], [ax, ay]] = [centre(before.viewBox), centre(after.viewBox)];
    check(Math.abs(after.zoom - before.zoom) < 0.01, `Refresh: zoom ${before.zoom} -> ${after.zoom}.`);
    check(Math.abs(ax - bx) < 2 && Math.abs(ay - by) < 2, `Refresh: centre (${bx}, ${by}) -> (${ax}, ${ay}).`);
    if (flow) {
        check((await page.locator(".o_pan_sl_flow_select").inputValue()) === String(flow.id), "Refresh: flow not kept.");
    }
    check((await page.locator(".o_pan_sl_color_select").inputValue()) === "training", "Refresh: colour mode not kept.");
    await page.locator(".o_pan_sl_flow_select").selectOption("");
    await page.locator(".o_pan_sl_color_select").selectOption("progress");
}

async function runViewport(browser, db, out, viewport, problems, state) {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    const page = await context.newPage();
    page.on("pageerror", (error) => problems.push(`${viewport.name}: page error: ${error.message}`));
    page.on("console", (message) => {
        if (message.type() === "error") {
            problems.push(`${viewport.name}: console error: ${message.text()}`);
        }
    });
    try {
        await login(page, db);
        let projectId = parseInt(process.env.PROJECT || "0", 10);
        if (!projectId) {
            const [role] = await rpc(page, "pan.sl.role", "search_read", [[]], { fields: ["project_id"], limit: 1 });
            check(role, "No project has map roles: import a blueprint into a project first.");
            projectId = role.project_id[0];
        }
        const data = await rpc(page, "project.project", "get_blueprint_map_data", [[projectId]]);
        check(data.tasks.length, "The project has no tasks on the map.");
        state.mapUrl = await openMap(page, projectId, viewport.name === "phone" && state.mapUrl);
        await checkStops(page, out, viewport, data);
        await checkColours(page, out, viewport, data);
        await checkFlows(page, out, viewport, data);
        await checkPanels(page, out, viewport, data);
        if (viewport.full) {
            await checkGestures(page);
            await checkRefresh(page, data);
        }
        const scrolls = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        check(!scrolls, `${viewport.name}: the page scrolls sideways.`);
        console.log(`${viewport.name}: ok (${page.url()})`);
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
    const state = { mapUrl: false };
    try {
        for (const viewport of VIEWPORTS) {
            await runViewport(browser, db, out, viewport, problems, state);
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
