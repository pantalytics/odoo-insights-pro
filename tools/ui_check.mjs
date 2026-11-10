#!/usr/bin/env node
// UI check for the Blueprint company map (pan_self_learning_blueprint).
//
// Logs in to a running Odoo at http://localhost:8069 as admin/admin, opens the
// company map client action, takes desktop (1440x900) and mobile (390x844)
// screenshots, selects the second option of the scenario select, clicks the
// first activity chip and checks that the side panel opens.
//
// Exits non-zero on any page error, console error, Odoo error dialog or
// missing element.
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
    emptyState: ".o_pan_sl_map .o_view_nocontent",
    scenarioSelect: ".o_pan_sl_scenario_select",
    chip: ".o_pan_sl_chip",
    panel: ".o_pan_sl_panel",
    errorDialog: ".o_error_dialog",
};

const VIEWPORTS = [
    { name: "desktop", width: 1440, height: 900 },
    { name: "mobile", width: 390, height: 844 },
];

function requireEnv(name) {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Environment variable ${name} is required (see the header of tools/ui_check.mjs).`);
    }
    return value;
}

class CheckError extends Error {}

async function expectVisible(page, selector, what) {
    try {
        await page.locator(selector).first().waitFor({ state: "visible", timeout: TIMEOUT });
    } catch {
        throw new CheckError(`Missing element: ${what} (${selector}) did not appear.`);
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

async function checkViewport(browser, db, out, viewport, problems) {
    const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
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
        await page.goto(`${BASE_URL}${MAP_PATH}`);
        await expectVisible(page, SEL.map, "company map");
        await page.waitForLoadState("networkidle");

        if (await page.locator(SEL.emptyState).count()) {
            await page.screenshot({ path: join(out, `${label}_empty.png`), fullPage: true });
            throw new CheckError(
                "The company map shows the empty state: load a template blueprint in this database first."
            );
        }
        await page.screenshot({ path: join(out, `${label}_map.png`), fullPage: true });

        await expectVisible(page, SEL.scenarioSelect, "scenario select");
        const select = page.locator(SEL.scenarioSelect).first();
        const optionCount = await select.locator("option").count();
        if (optionCount < 2) {
            throw new CheckError(
                `The scenario select has ${optionCount} option(s); at least one scenario is needed.`
            );
        }
        await select.selectOption({ index: 1 });
        await page.waitForTimeout(500);
        await page.screenshot({ path: join(out, `${label}_scenario.png`), fullPage: true });

        await expectVisible(page, SEL.chip, "activity chip");
        await page.locator(SEL.chip).first().click();
        await expectVisible(page, SEL.panel, "activity side panel");
        await page.screenshot({ path: join(out, `${label}_panel.png`), fullPage: true });

        if (await page.locator(SEL.errorDialog).count()) {
            throw new CheckError("Odoo shows an error dialog.");
        }
    } catch (error) {
        if (!(error instanceof CheckError)) {
            await page.screenshot({ path: join(out, `${label}_failure.png`), fullPage: true });
        }
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
        for (const viewport of VIEWPORTS) {
            await checkViewport(browser, db, out, viewport, problems);
        }
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
