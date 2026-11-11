import { Component, useSubEnv } from "@odoo/owl";
import { SIZES } from "@web/core/ui/ui_service";
import { View } from "@web/views/view";

/**
 * The task itself in the map's side panel: Odoo's own task form (the
 * project's form view, with its status bar, fields and chatter), embedded.
 * The panel is never wider than a laptop screen, so the form is told the
 * screen is at most XL: the chatter goes under the form, as on a phone,
 * instead of beside it. The form does not rename the map's breadcrumb.
 * ``beforeLeave`` (a CallbackRecorder of the map) saves a changed task
 * before the panel closes, switches task or the map is left.
 */
export class BlueprintTaskPanel extends Component {
    static template = "pan_self_learning_blueprint.TaskPanel";
    static components = { View };
    static props = {
        resId: Number,
        context: Object,
        beforeLeave: Object,
        onOpen: Function,
        onClose: Function,
    };

    setup() {
        const ui = this.env.services.ui;
        const narrowUi = new Proxy(ui, {
            get: (target, key) => (key === "size" ? Math.min(target.size, SIZES.XL) : target[key]),
        });
        useSubEnv({
            services: Object.assign(Object.create(this.env.services), { ui: narrowUi }),
            config: {
                ...this.env.config,
                breadcrumbs: [],
                setDisplayName: () => {},
                historyBack: () => this.props.onClose(),
            },
        });
    }

    get viewProps() {
        return {
            type: "form",
            resModel: "project.task",
            resId: this.props.resId,
            context: this.props.context,
            display: { controlPanel: false },
            className: "o_pan_sl_task_form",
            __beforeLeave__: this.props.beforeLeave,
        };
    }
}
