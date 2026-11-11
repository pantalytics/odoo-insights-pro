#!/usr/bin/env node
// UI check for the map (pan_self_learning_blueprint, Blueprint 2.3).
//
// Logs in to a running Odoo as admin/admin and opens the map action without a
// project (as the Projects menu "Map" does), which opens the "Map" view of the
// project's tasks. At desktop (1440x900), iPad landscape (1024x768, touch) and
// phone (390x844, touch) it screenshots the map, a flow's swimlane, a filter
// from the overview, the task panel, the role panel and the tasks without a
// place, and checks:
//
// - Map is the active view in the switcher and the search bar is there;
// - the overview band has five answers (On schedule?, Still to do, Flows,
//   Training, Choices) with the numbers of the server data; "Choices" puts
//   the "Not decided" filter in the search bar and the chips follow it;
// - the legend has four plain words; the flow list starts with "N of M flows
//   late" and follows the server order (worst first), with "Late · N days";
// - tapping a flow shows its swimlane: a column per step (left to right),
//   only its placed tasks, N-1 arrows running left to right
//   ending at their chips, a breadcrumb "Map > flow"; its open tasks (in view,
//   with hours) are listed right under it and announced; tapping again goes back;
// - the task panel has exactly one primary button, "Open task"; Esc closes it;
//   the last chip of the grid (bottom right) opens a panel that is in view;
// - the grid fades at the right edge while it can scroll sideways;
// - the "Training" answer counts the internal roles' tasks and opens the
//   "Still to train" list (screenshot 6_still_to_train);
// - the role panel lists people, "To train on" and the ADKAR line;
// - the "N tasks without a place" link matches the data;
// - the page never scrolls sideways; on the iPad the flow list and at least
//   four phase columns are in view; on touch, every button of the map is
//   44 px or taller;
// - nothing is painted with an undefined colour; the map follows Odoo's dark
//   colour variables (desktop_dark).
//
// Never waits for "networkidle" (Odoo's bus long-polls). Exits non-zero on a
// page error, console error, Odoo error dialog or failed check.
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

async function shot(page, out, viewport, name) {
    await page.waitForTimeout(250);
    check(!(await page.locator(".o_error_dialog").count()), `${viewport.name} ${name}: Odoo shows an error dialog.`);
    await page.screenshot({ path: join(out, `${viewport.name}_${name}.png`) });
}

/** Opens the map like the menu does; several projects show a list, so pick the one with the most tasks. */
async function openMap(page, project) {
    await page.goto(MAP_URL);
    await page.locator(".o_pan_sl_map .o_pan_sl_body, .o_pan_sl_map .o_pan_sl_projects").first().waitFor({ timeout: TIMEOUT });
    if (await page.locator(".o_pan_sl_projects").count()) {
        await page.locator(".o_pan_sl_project", { hasText: project.name }).click();
    }
    await page.locator(".o_pan_sl_map .o_pan_sl_body").waitFor({ timeout: TIMEOUT });
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

async function checkLayout(page, viewport, data) {
    const layout = await page.evaluate(() => {
        const rect = (el) => el && el.getBoundingClientRect();
        const flows = rect(document.querySelector(".o_pan_sl_flows"));
        const phases = [...document.querySelectorAll(".o_pan_sl_phase")].map(rect);
        const small = [...document.querySelectorAll(".o_pan_sl_map .o_content button")]
            .filter((el) => el.offsetParent && rect(el).height < 43.5)
            .map((el) => `${el.className.split(" ")[0]} "${el.textContent.trim().slice(0, 20)}" ${Math.round(rect(el).height)}px`);
        const black = [...document.querySelectorAll(".o_pan_sl_map .o_pan_sl_dot, .o_pan_sl_map .o_pan_sl_bar > span")]
            .filter((el) => getComputedStyle(el).backgroundColor === "rgb(0, 0, 0)").length;
        return {
            pageScrolls: document.documentElement.scrollWidth > window.innerWidth + 1,
            flowsInView: flows && flows.left >= 0 && flows.right <= window.innerWidth,
            phasesInView: phases.filter((r) => r.left >= 0 && r.right <= window.innerWidth).length,
            small,
            black,
        };
    });
    check(!layout.pageScrolls, `${viewport.name}: the page scrolls sideways.`);
    check(!layout.black, `${viewport.name}: ${layout.black} dots or bars are black (undefined colour).`);
    if (viewport.name === "ipad") {
        check(layout.flowsInView, "ipad: the flow list is not in view.");
        check(layout.phasesInView >= Math.min(4, data.phases.length), `ipad: only ${layout.phasesInView} phase columns in view.`);
    }
    if (viewport.touch) {
        check(!layout.small.length, `${viewport.name}: tap targets under 44 px: ${layout.small.slice(0, 5).join("; ")}`);
    }
}

async function checkFlows(page, out, viewport, data) {
    const legend = await page.locator(".o_pan_sl_legend li").allTextContents();
    check(legend.map((item) => item.trim()).join("|") === "Open|Decided or Built|Tested|Trained or Live", `${viewport.name}: legend ${legend.join("|")}`);
    if (data.flows.length) {
        const summary = (await page.locator(".o_pan_sl_flow_summary").textContent()).trim();
        const late = data.flows.filter((flow) => flow.late).length;
        check(summary === `${late} of ${data.flows.length} flows late`, `${viewport.name}: summary "${summary}"`);
    }
    const names = await page.locator(".o_pan_sl_flow .o_pan_sl_flow_name").allTextContents();
    check(names.join("|") === data.flows.map((flow) => flow.name).join("|"), `${viewport.name}: flow order differs from the server.`);
    const late = await page.locator(".o_pan_sl_flow .o_pan_sl_late").count();
    check(late === data.flows.filter((flow) => flow.late).length, `${viewport.name}: ${late} Late tags.`);
    if (!data.flows.length) {
        return;
    }
    // The flow with the most placed tasks shows the most lines.
    const placedIds = data.tasks.filter((task) => task.role_id && task.phase_id).map((task) => task.id);
    const placedOf = (item) => item.task_ids.filter((id) => placedIds.includes(id)).length;
    const flow = data.flows.reduce((best, item) => (placedOf(item) > placedOf(best) ? item : best));
    const button = page.locator(`.o_pan_sl_flow[data-flow-id="${flow.id}"]`);
    await button.click();
    await page.waitForFunction((name) => document.querySelector(".o_pan_sl_status")?.textContent.includes(name), flow.name);
    const placed = placedOf(flow);
    const chips = await page.locator(".o_pan_sl_chip").count();
    check(chips === placed, `${viewport.name}: ${chips} chips in the swimlane, expected ${placed}.`);
    await page.waitForFunction((count) => document.querySelectorAll(".o_pan_sl_arrow").length === count, Math.max(0, placed - 1), { timeout: TIMEOUT });
    await page.waitForTimeout(300); // the swimlane fades in (180 ms)
    const crumbs = (await page.locator(".o_pan_sl_crumbs").innerText()).replace(/\s+/g, " ").trim();
    check(crumbs === `Map › ${flow.name}`, `${viewport.name}: breadcrumb "${crumbs}"`);
    const ends = await page.evaluate(() =>
        [...document.querySelectorAll(".o_pan_sl_arrow")].every((path) => {
            const point = path.getPointAtLength(path.getTotalLength());
            const svg = path.ownerSVGElement.getBoundingClientRect();
            const rect = document.querySelector(`.o_pan_sl_chip[data-task-id="${path.dataset.to}"]`).getBoundingClientRect();
            const [x, y] = [svg.left + point.x, svg.top + point.y];
            return x >= rect.left - 3 && x <= rect.right + 3 && y >= rect.top - 3 && y <= rect.bottom + 3;
        })
    );
    check(ends, `${viewport.name}: an arrow does not end at its chip.`);
    // A column per step: every arrow runs left to right, none bunch in one column.
    const rightward = await page.evaluate(() =>
        [...document.querySelectorAll(".o_pan_sl_arrow")].every((path) => {
            const xs = path.getAttribute("d").match(/-?[\d.]+,-?[\d.]+/g).map((pair) => Number(pair.split(",")[0]));
            return xs.at(-1) > xs[0];
        })
    );
    check(rightward, `${viewport.name}: an arrow runs right to left.`);
    const columns = await page.locator(".o_pan_sl_grid .o_pan_sl_role").first().evaluate((el) => {
        let count = 0;
        for (let next = el.nextElementSibling; next?.classList.contains("o_pan_sl_cell"); next = next.nextElementSibling) {
            count++;
        }
        return count;
    });
    check(columns === placed, `${viewport.name}: ${columns} step columns for ${placed} placed tasks.`);
    const open = data.tasks.filter((task) => flow.task_ids.includes(task.id) && task.rung < TESTED_RUNG).length;
    const listed = await page.locator(".o_pan_sl_flows .o_pan_sl_open_task").count();
    check(listed === open, `${viewport.name}: ${listed} open tasks listed, expected ${open}.`);
    if (open) {
        const list = page.locator(".o_pan_sl_flows .o_pan_sl_open_tasks");
        check(await list.evaluate((el) => el.previousElementSibling?.classList.contains("o_pan_sl_flow")), `${viewport.name}: open tasks not under the flow.`);
        const box = await list.boundingBox();
        check(box && box.y < viewport.height && box.y + 20 > 0, `${viewport.name}: the open tasks are out of view.`);
        const hours = await page.locator(".o_pan_sl_flows .o_pan_sl_hours").count();
        check(hours === open, `${viewport.name}: ${hours} hour lines for ${open} open tasks.`);
    }
    const status = (await page.locator(".o_pan_sl_status").textContent()).trim();
    check(status.includes(flow.name), `${viewport.name}: flow not announced: "${status}".`);
    await shot(page, out, viewport, "2_flow");
    await page.locator(".o_pan_sl_grid_area").evaluate((el) => el.scrollIntoView({ block: "start" }));
    await shot(page, out, viewport, "2b_flow_swimlane");
    await button.click();
    await page.waitForFunction(() => !document.querySelector(".o_pan_sl_status")?.textContent.trim());
    check(!(await page.locator(".o_pan_sl_crumbs").count()), `${viewport.name}: a second tap does not go back to the map.`);
    const all = await page.locator(".o_pan_sl_chip").count();
    check(all === placedIds.length, `${viewport.name}: ${all} chips on the map, expected ${placedIds.length}.`);
}

async function checkOverview(page, out, viewport, data) {
    const labels = await page.locator(".o_pan_sl_answer_label").allTextContents();
    check(labels.join("|") === "On schedule?|Still to do|Flows|Training|Choices", `${viewport.name}: answers ${labels.join("|")}`);
    const value = async (key) => (await page.locator(`.o_pan_sl_answer_${key} .o_pan_sl_answer_value`).textContent()).trim();
    const open = data.tasks.filter((task) => task.rung < TESTED_RUNG).length;
    check((await value("todo")) === (open === 1 ? "1 open task" : `${open} open tasks`), `${viewport.name}: still to do "${await value("todo")}"`);
    const tested = data.flows.filter((flow) => flow.progress >= 100).length;
    check((await value("flows")) === `${tested} of ${data.flows.length} flows tested`, `${viewport.name}: flows "${await value("flows")}"`);
    const decided = data.tasks.filter((task) => task.rung >= 1).length;
    check((await value("choices")) === `${decided} of ${data.tasks.length} tasks decided`, `${viewport.name}: choices "${await value("choices")}"`);
    const next = data.milestones.find((milestone) => !milestone.reached);
    if (next) {
        check((await value("schedule")) === next.name, `${viewport.name}: next milestone "${await value("schedule")}"`);
    }

    // "Choices" is the filter "Not decided": a facet, and only the tasks still Open.
    await page.locator(".o_pan_sl_answer_choices").click();
    const notDecided = data.tasks.filter((task) => task.rung < 1 && task.role_id && task.phase_id).length;
    await page.waitForFunction((count) => document.querySelectorAll(".o_pan_sl_chip").length === count, notDecided, { timeout: TIMEOUT });
    check((await page.locator(".o_pan_sl_answer_choices").getAttribute("aria-pressed")) === "true", `${viewport.name}: Choices not pressed.`);
    if (viewport.name !== "phone") {
        const facets = await page.locator(".o_searchview_facet").allTextContents();
        check(facets.some((facet) => facet.includes("Not decided")), `${viewport.name}: no "Not decided" facet: ${facets.join("|")}`);
    }
    await shot(page, out, viewport, "1b_filter_not_decided");
    await page.locator(".o_pan_sl_answer_choices").click();
    const placed = data.tasks.filter((task) => task.role_id && task.phase_id).length;
    await page.waitForFunction((count) => document.querySelectorAll(".o_pan_sl_chip").length === count, placed, { timeout: TIMEOUT });
}

async function checkPanels(page, out, viewport, data) {
    const chip = page.locator(".o_pan_sl_chip").first();
    if (await chip.count()) {
        await chip.click();
        const panel = page.locator(".o_pan_sl_task_panel");
        await panel.waitFor({ timeout: TIMEOUT });
        const primary = await page.locator(".o_pan_sl_map .o_content .btn-primary").allTextContents();
        check(primary.length === 1 && primary[0].trim() === "Open task", `${viewport.name}: primary buttons: ${primary.join(", ")}`);
        const facts = await panel.locator("dt").allTextContents();
        check(facts.join("|") === "Flow|Role|Phase|Progress|Owners|Hours", `${viewport.name}: task facts ${facts.join("|")}`);
        await shot(page, out, viewport, "3_task_panel");
        await page.keyboard.press("Escape");
        await panel.waitFor({ state: "detached", timeout: TIMEOUT });

        // The last chip (bottom right of the grid) opens a panel in view.
        const last = page.locator(".o_pan_sl_chip").last();
        await last.scrollIntoViewIfNeeded();
        await last.click();
        await panel.waitFor({ timeout: TIMEOUT });
        const box = await panel.boundingBox();
        check(box && box.y >= 0 && box.y + Math.min(box.height, 200) <= viewport.height, `${viewport.name}: the panel of the last chip is out of view.`);
        await shot(page, out, viewport, "3b_last_chip_panel");
        await page.keyboard.press("Escape");
        await panel.waitFor({ state: "detached", timeout: TIMEOUT });
    }
    const role = page.locator(".o_pan_sl_role").first();
    if (await role.count()) {
        await role.click();
        const panel = page.locator(".o_pan_sl_role_panel");
        await panel.waitFor({ timeout: TIMEOUT });
        const labels = await panel.locator(".o_pan_sl_panel_label").allTextContents();
        check(labels.join("|") === "People|To train on|ADKAR", `${viewport.name}: role panel sections ${labels.join("|")}`);
        await shot(page, out, viewport, "4_role_panel");
        await panel.locator(".o_pan_sl_close").click();
    }
}

async function checkUnplaced(page, out, viewport, data) {
    const count = data.tasks.filter((task) => !task.role_id || !task.phase_id).length;
    const link = page.locator(".o_pan_sl_unplaced");
    check((await link.count()) === (count ? 1 : 0), `${viewport.name}: unplaced link shown wrongly (${count} tasks).`);
    if (!count) {
        return;
    }
    const text = (await link.textContent()).replace(/\s+/g, " ").trim();
    check(text === `${count} ${count === 1 ? "task" : "tasks"} without a place`, `${viewport.name}: unplaced link "${text}"`);
    await link.click();
    await page.locator(".o_pan_sl_flow_unplaced").waitFor({ timeout: TIMEOUT });
    const listed = await page.locator(".o_pan_sl_flows .o_pan_sl_open_task").count();
    check(listed === count, `${viewport.name}: ${listed} tasks without a place listed, expected ${count}.`);
    await page.locator(".o_pan_sl_flows").scrollIntoViewIfNeeded();
    await shot(page, out, viewport, "5_unplaced");
    await link.click();
}

async function checkFade(page, viewport) {
    const area = page.locator(".o_pan_sl_grid_area");
    if (!(await area.count())) {
        return;
    }
    await area.evaluate((el) => el.scrollTo({ left: 0 }));
    await page.waitForTimeout(200);
    const { scrolls, fade } = await area.evaluate((el) => ({
        scrolls: el.scrollWidth > el.clientWidth + 1,
        fade: el.parentElement.classList.contains("o_pan_sl_fade_right"),
    }));
    check(scrolls === fade, `${viewport.name}: the grid ${scrolls ? "scrolls" : "does not scroll"} sideways, the fade is ${fade ? "on" : "off"}.`);
}

async function checkTraining(page, out, viewport, data) {
    const internal = data.roles.filter((role) => !role.is_external).map((role) => role.id);
    const tasks = data.tasks.filter((task) => internal.includes(task.role_id));
    const trained = tasks.filter((task) => task.rung >= 4).length;
    const button = page.locator(".o_pan_sl_answer_training");
    const label = (await button.locator(".o_pan_sl_answer_value").textContent()).trim();
    check(label === `${trained} of ${tasks.length} tasks trained`, `${viewport.name}: training answer "${label}"`);
    await button.click();
    await page.locator(".o_list_view .o_data_row").first().waitFor({ timeout: TIMEOUT });
    // Phones fold the search bar behind an icon, as everywhere in Odoo.
    const facets = await page.locator(".o_searchview_facet").allTextContents();
    check(viewport.name === "phone" || facets.some((facet) => facet.includes("Still to train")), `${viewport.name}: no "Still to train" filter: ${facets.join("|")}`);
    await shot(page, out, viewport, "6_still_to_train");
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
        await openMap(page, data.project);
        // A fresh database greets with an OdooBot chat window over the page.
        await page.addStyleTag({ content: ".o-mail-ChatWindow, .o-mail-ChatHub { display: none !important; }" });
        if (viewport.dark) {
            await useDarkTokens(page);
        }
        await shot(page, out, viewport, "1_map");
        await checkLayout(page, viewport, data);
        if (!viewport.dark) {
            await checkOverview(page, out, viewport, data);
            await checkFlows(page, out, viewport, data);
            await checkPanels(page, out, viewport, data);
            await checkUnplaced(page, out, viewport, data);
            await checkFade(page, viewport);
            await checkTraining(page, out, viewport, data);
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
