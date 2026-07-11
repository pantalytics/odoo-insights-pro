/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * Standard PostHog bootstrap stub. It queues calls until array.js has loaded,
 * then replays them against the real library. Adapted from the official
 * snippet, scoped so we only touch the global once.
 */
function installPosthogStub() {
    if (window.posthog && window.posthog.__loaded) {
        return window.posthog;
    }
    const ph = window.posthog || [];
    if (ph.__SV) {
        return ph;
    }
    window.posthog = ph;
    ph._i = [];
    ph.init = function (token, config, name) {
        function makeStub(target, method) {
            const parts = method.split(".");
            if (parts.length === 2) {
                target = target[parts[0]];
                method = parts[1];
            }
            target[method] = function () {
                target.push([method].concat(Array.prototype.slice.call(arguments, 0)));
            };
        }
        let instance = ph;
        if (typeof name !== "undefined") {
            instance = ph[name] = [];
        } else {
            name = "posthog";
        }
        instance.people = instance.people || [];
        instance.toString = function (noStub) {
            let str = "posthog";
            if (name !== "posthog") {
                str += "." + name;
            }
            if (!noStub) {
                str += " (stub)";
            }
            return str;
        };
        instance.people.toString = function () {
            return instance.toString(1) + ".people (stub)";
        };
        const methods = (
            "init capture register register_once register_for_session unregister " +
            "unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled " +
            "reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures " +
            "on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey " +
            "canRenderSurvey identify setPersonProperties group resetGroups " +
            "setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags " +
            "resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id " +
            "get_session_replay_url alias set_config startSessionRecording stopSessionRecording " +
            "sessionRecordingStarted captureException loadToolbar get_property getSessionProperty " +
            "createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing " +
            "has_opted_out_capturing clear_opt_in_out_capturing debug getPageViewId captureTraceFeedback " +
            "captureTraceMetric"
        ).split(" ");
        for (const method of methods) {
            makeStub(instance, method);
        }
        ph._i.push([token, config, name]);
    };
    ph.__SV = 1;
    return ph;
}

function loadArrayJs(apiHost) {
    const src = apiHost.replace(/\/+$/, "") + "/static/array.js";
    if (document.querySelector(`script[src="${src}"]`)) {
        return;
    }
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.async = true;
    script.src = src;
    const first = document.getElementsByTagName("script")[0];
    if (first && first.parentNode) {
        first.parentNode.insertBefore(script, first);
    } else {
        document.head.appendChild(script);
    }
}

/**
 * Insights Pro — injects PostHog into the Odoo backend.
 *
 * Fully dormant until a project key is configured under Settings > Insights Pro:
 * `cfg.enabled` is only true server-side when a key is present.
 */
export const insightsProService = {
    dependencies: [],
    start() {
        const cfg = session.insights_pro;
        if (!cfg || !cfg.enabled || !cfg.api_key) {
            return; // dormant — nothing set up yet
        }

        const posthog = installPosthogStub();
        loadArrayJs(cfg.api_host);

        posthog.init(cfg.api_key, {
            api_host: cfg.api_host,
            // Pseudonymous, per-database identity. No names, no emails.
            bootstrap: { distinctID: cfg.distinct_id, isIdentifiedID: true },
            person_profiles: "identified_only",
            autocapture: { element_attribute_ignorelist: ["value"] },
            mask_all_text: !!cfg.mask_all_text,
            mask_all_element_attributes: !!cfg.mask_all_text,
            disable_session_recording: !!cfg.disable_session_recording,
            capture_pageview: true,
            loaded: (ph) => {
                ph.identify(cfg.distinct_id);
                if (cfg.workspace) {
                    // Keep each customer's data in its own group.
                    ph.group("workspace", cfg.workspace, {
                        name: cfg.company || cfg.workspace,
                        odoo_version: cfg.odoo_version,
                    });
                }
            },
        });

        return posthog;
    },
};

registry.category("services").add("insights_pro.posthog", insightsProService);
