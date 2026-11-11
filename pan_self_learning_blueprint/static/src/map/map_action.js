import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// Projects > Map (and old map links): the map is the "Map" view of a
// project's tasks since 2.3. A link with a project opens that project's tasks
// in the Map view; the menu always shows the plain list of projects with the
// map on, so it never jumps into a project other than the one you came from.

const LIST_TAG = "pan_sl_blueprint_map_list";

async function openBlueprintMap(env, action) {
    const { params = {}, context = {} } = action;
    const orm = env.services.orm;
    const projectId = params.project_id || (context.active_model === "project.project" && context.active_id) || false;
    if (!projectId) {
        return { type: "ir.actions.client", tag: LIST_TAG, name: action.name };
    }
    return orm.call("project.project", "action_open_blueprint_map", [[projectId]]);
}

export class BlueprintMapList extends Component {
    static template = "pan_self_learning_blueprint.MapList";
    static props = { ...standardActionServiceProps };
    static components = { Layout };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ projects: [] });
        onWillStart(async () => {
            this.state.projects = await this.orm.call("project.project", "get_blueprint_map_projects", []);
        });
    }

    async open(project) {
        const action = await this.orm.call("project.project", "action_open_blueprint_map", [[project.id]]);
        await this.actionService.doAction(action);
    }
}

registry.category("actions").add("pan_sl_blueprint_map", openBlueprintMap);
registry.category("actions").add(LIST_TAG, BlueprintMapList);
