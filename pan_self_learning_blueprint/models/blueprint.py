"""Open blueprint format (version 2): one project as JSON.

See ``docs/blueprint-format.md``. Phases match on code (shared by all
projects), roles on code within the project, flows on name within the
project, tasks on name within their flow. Import creates and updates, never
deletes; loading the template only fills what is empty. A project without
progress stages gets the six stages Open ... Live. Every refusal is a
plain-language ``UserError`` and rolls the whole import back.
"""

import base64
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import file_open, html_sanitize, is_html_empty

from .structure import RUNG_SELECTION

BLUEPRINT_FORMAT = "pantalytics-blueprint"
BLUEPRINT_VERSION = 2
TEMPLATE_FILE = "pan_self_learning_blueprint/data/blueprints/generic_manufacturing.json"
SOURCE_LANG = "en_US"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 5000
MANAGER_GROUP = "project.group_project_manager"
SECTIONS = ("stages", "phases", "roles", "flows", "tasks")

# Per section: file key -> (field, type). "html" is text stored as HTML.
# A phase's "apps" (2.0) is still accepted and ignored.
PHASE_KEYS = {"name": ("name", str), "sequence": ("sequence", int)}
ROLE_KEYS = {
    "name": ("name", str),
    "sequence": ("sequence", int),
    "external": ("is_external", bool),
    "description": ("description", str),
}
FLOW_KEYS = {"name": ("name", str), "sequence": ("sequence", int), "description": ("description", "html")}
TASK_KEYS = {"name": ("name", str), "description": ("description", "html")}


class PanSlBlueprint(models.AbstractModel):
    _name = "pan.sl.blueprint"
    _description = "Blueprint import and export"

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(self.env._("Only a Project administrator can import or export a blueprint."))

    @api.model
    def _project(self, project):
        project = self.env["project.project"].browse(project) if isinstance(project, int) else project
        project.ensure_one()
        return project

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def export_blueprint(self, project):
        """Return the project as a blueprint dict (format version 2), names in English.

        Flows are the project's parent tasks with subtasks; tasks outside a
        flow are project work, not blueprint, and are left out.
        """
        self._check_manager()
        self = self.with_context(lang=SOURCE_LANG)
        project = self._project(project).with_context(lang=SOURCE_LANG)
        Task = self.env["project.task"]
        flows = Task.search(
            [("project_id", "=", project.id), ("parent_id", "=", False), ("child_ids", "!=", False)],
            order="sequence, id",
        )
        subtasks = Task.search([("parent_id", "in", flows.ids), ("state", "!=", "1_canceled")], order="sequence, id")
        return {
            "format": BLUEPRINT_FORMAT,
            "version": BLUEPRINT_VERSION,
            "lang": SOURCE_LANG,
            "name": project.name,
            "phases": [
                {"code": phase.code, "name": phase.name, "sequence": phase.sequence}
                for phase in self.env["pan.sl.phase"].search([])
            ],
            "roles": [
                {
                    "code": role.code,
                    "name": role.name,
                    "sequence": role.sequence,
                    "external": role.is_external,
                    "description": role.description or "",
                }
                for role in self.env["pan.sl.role"].search([("project_id", "=", project.id)])
            ],
            "flows": [
                {
                    "name": flow.name,
                    "sequence": flow.sequence,
                    "description": self._html_out(flow.description),
                    "tasks": [
                        {
                            "name": task.name,
                            "role": task.pan_role_id.code or "",
                            "phase": task.pan_phase_id.code or "",
                            "apps": task.pan_app_ids.sorted("name").mapped("name"),
                            "description": self._html_out(task.description),
                        }
                        for task in subtasks
                        if task.parent_id == flow
                    ],
                }
                for flow in flows
            ],
        }

    @api.model
    def _html_out(self, value):
        return "" if is_html_empty(value) else str(value)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def import_blueprint(self, project, data, fill_empty_only=False):
        """Create or update phases, roles, flows and tasks of ``data`` in ``project``.

        :param project: a project.project record or id
        :param dict data: the parsed blueprint (docs/blueprint-format.md)
        :param bool fill_empty_only: template loading: create what is
            missing and only fill empty values on what exists
        :return: ``{"name": str, "stages": {"created": n, "updated": n}, "phases": ..., "roles": ...,
            "flows": ..., "tasks": ...}``; linking an existing stage counts as updated
        """
        self._check_manager()
        project = self._project(project)
        self._check_size(self._serialized_size(data))
        self._check_header(data)
        self = self.with_context(lang=self._get_import_lang(data), active_test=False)
        phases = self._get_items(data, "phases", "code")
        roles = self._get_items(data, "roles", "code")
        flows = self._get_items(data, "flows", "name")
        tasks_per_flow = [self._get_items(flow, "tasks", "name", flow["name"]) for flow in flows]
        total = len(phases) + len(roles) + len(flows) + sum(len(tasks) for tasks in tasks_per_flow)
        if total > MAX_RECORDS:
            raise UserError(
                self.env._(
                    "This blueprint holds %(count)s records; at most %(max)s can be imported at once. "
                    "Split the file or remove records.",
                    count=total,
                    max=MAX_RECORDS,
                )
            )
        summary = {"name": data.get("name") or "", **{section: {"created": 0, "updated": 0} for section in SECTIONS}}
        Phase, Role, Task = self.env["pan.sl.phase"], self.env["pan.sl.role"], self.env["project.task"]
        # Before the tasks, so new tasks land in the first of these stages.
        self._ensure_stages(project, summary["stages"])

        existing = {phase.code: phase for phase in Phase.search([("code", "in", [item["code"] for item in phases])])}
        for item in phases:
            vals = self._vals(item, PHASE_KEYS, "phases")
            existing[item["code"]] = self._upsert(
                Phase, existing.get(item["code"]), dict(vals, code=item["code"]), summary["phases"], fill_empty_only
            )
        phase_ids = {code: phase.id for code, phase in existing.items()}

        existing = {
            role.code: role
            for role in Role.search([("project_id", "=", project.id), ("code", "in", [item["code"] for item in roles])])
        }
        for item in roles:
            vals = dict(self._vals(item, ROLE_KEYS, "roles"), code=item["code"], project_id=project.id)
            existing[item["code"]] = self._upsert(
                Role, existing.get(item["code"]), vals, summary["roles"], fill_empty_only
            )
        role_ids = {code: role.id for code, role in existing.items()}
        self._resolve_refs(tasks_per_flow, project, phase_ids, role_ids)
        app_ids = self._resolve_apps(tasks_per_flow)

        existing_flows = {}
        for flow in Task.search(
            [("project_id", "=", project.id), ("parent_id", "=", False), ("name", "in", [item["name"] for item in flows])],
            order="id desc",
        ):
            existing_flows[flow.name] = flow
        for item, tasks in zip(flows, tasks_per_flow):
            vals = dict(self._vals(item, FLOW_KEYS, "flows"), project_id=project.id)
            flow = self._upsert(Task, existing_flows.get(item["name"]), vals, summary["flows"], fill_empty_only)
            existing_tasks = {}
            for task in Task.search([("parent_id", "=", flow.id)], order="id desc"):
                existing_tasks[task.name] = task
            for position, task_item in enumerate(tasks, start=1):
                vals = dict(
                    self._vals(task_item, TASK_KEYS, "tasks"),
                    project_id=project.id,
                    parent_id=flow.id,
                    sequence=position * 10,
                )
                if task_item.get("role"):
                    vals["pan_role_id"] = role_ids[task_item["role"]]
                if task_item.get("phase"):
                    vals["pan_phase_id"] = phase_ids[task_item["phase"]]
                if "apps" in task_item:
                    vals["pan_app_ids"] = [app_ids[name] for name in task_item["apps"] if name in app_ids]
                self._upsert(Task, existing_tasks.get(task_item["name"]), vals, summary["tasks"], fill_empty_only)
        return summary

    @api.model
    def _ensure_stages(self, project, counts):
        """Give ``project`` the six progress stages (Open ... Live), unless one
        of its stages already carries a progress beyond Open.

        A stage with the same English name and progress that another project
        uses is linked instead of copied. Existing stages are never changed.
        """
        if project.type_ids.filtered(lambda stage: stage.pan_rung != "0"):
            return
        # sudo: a Project administrator may set up the map's stages without
        # being a project manager; only these six fixed stages are touched.
        Stage = self.env["project.task.type"].sudo().with_context(lang=SOURCE_LANG, active_test=True)
        langs = [lang for lang, _name in self.env["res.lang"].get_installed() if lang != SOURCE_LANG]
        for rung, name in RUNG_SELECTION:
            stage = Stage.search([("name", "=", name), ("pan_rung", "=", rung), ("user_id", "=", False)], limit=1)
            if stage:
                stage.project_ids = [(4, project.id)]
                counts["updated"] += 1
                continue
            stage = Stage.create(
                {"name": name, "pan_rung": rung, "sequence": 10 * (int(rung) + 1), "project_ids": [(4, project.id)]}
            )
            counts["created"] += 1
            # Named after its progress word, in every active language.
            words = {
                lang: dict(Stage._fields["pan_rung"]._description_selection(Stage.with_context(lang=lang).env))[rung]
                for lang in langs
            }
            if words:
                stage.update_field_translations("name", words)

    @api.model
    def _upsert(self, Model, record, vals, counts, fill_empty_only):
        """Create the record, or write only the values that really change.

        ``fill_empty_only`` writes only to fields that are still empty, and
        never touches numbers or booleans of an existing record.
        """
        if not record:
            counts["created"] += 1
            many2many = {name for name in vals if Model._fields[name].type == "many2many"}
            return Model.create({name: [(6, 0, v)] if name in many2many else v for name, v in vals.items()})
        changes = {}
        for name, value in vals.items():
            field = record._fields[name]
            current = record[name]
            if field.type == "many2one":
                current = current.id
            elif field.type == "many2many":
                current, value = sorted(current.ids), sorted(value)
            elif field.type == "html":
                current, value = ("" if is_html_empty(current) else str(current)), str(html_sanitize(value or ""))
            if fill_empty_only and (field.type in ("integer", "boolean") or current):
                continue
            if (current or False) != (value or False):
                changes[name] = [(6, 0, value)] if field.type == "many2many" else value
        if changes:
            record.write(changes)
            counts["updated"] += 1
        return record

    @api.model
    def _vals(self, item, keys, section):
        """Field values of one item, with the type of every given key checked."""
        vals = {}
        for key, (field_name, kind) in keys.items():
            if key not in item:
                continue
            value = item[key]
            expected = str if kind == "html" else kind
            # bool is a subclass of int; true/false is no sequence.
            valid = isinstance(value, expected) and not (expected is int and isinstance(value, bool))
            if not valid:
                raise UserError(
                    self.env._(
                        "In '%(section)s', '%(label)s' has a wrong value for '%(key)s'. "
                        "Use text between quotes, a whole number, true/false or a list of texts as documented, "
                        "and import again.",
                        section=section,
                        label=item.get("code") or item.get("name"),
                        key=key,
                    )
                )
            vals[field_name] = value
        return vals

    @api.model
    def _get_items(self, data, section, key, parent=None):
        """The list ``data[section]``; every item a dict with a unique, non-empty ``key``."""
        items = data.get(section, [])
        where = f"{parent} > {section}" if parent else section
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise UserError(
                self.env._(
                    "In this blueprint, '%(section)s' must be a list of records between [ ] and { }. "
                    "Fix the file and import it again.",
                    section=where,
                )
            )
        seen = set()
        for index, item in enumerate(items, start=1):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise UserError(
                    self.env._(
                        "Record %(index)s in '%(section)s' has no %(key)s. Add it as text and import again.",
                        index=index,
                        section=where,
                        key=key,
                    )
                )
            if key == "code" and any(char.isspace() for char in value):
                raise UserError(
                    self.env._(
                        "The code '%(code)s' in '%(section)s' has a space. Codes have no spaces; fix it and import again.",
                        code=value,
                        section=where,
                    )
                )
            if value in seen:
                raise UserError(
                    self.env._(
                        "'%(value)s' is used twice in '%(section)s'. Make every %(key)s unique and import again.",
                        value=value,
                        section=where,
                        key=key,
                    )
                )
            seen.add(value)
        return items

    @api.model
    def _resolve_refs(self, tasks_per_flow, project, phase_ids, role_ids):
        """Every task role and phase must name a code in the file or already here."""
        wanted = {"role": set(), "phase": set()}
        for tasks in tasks_per_flow:
            for task in tasks:
                for key in wanted:
                    value = task.get(key)
                    if value in (None, ""):
                        continue
                    if not isinstance(value, str):
                        raise UserError(
                            self.env._(
                                "Task '%(task)s' has a %(key)s that is not a code. Use the code as text and import again.",
                                task=task["name"],
                                key=key,
                            )
                        )
                    wanted[key].add(value)
        for code in wanted["phase"] - phase_ids.keys():
            phase = self.env["pan.sl.phase"].search([("code", "=", code)], limit=1)
            if phase:
                phase_ids[code] = phase.id
        for code in wanted["role"] - role_ids.keys():
            role = self.env["pan.sl.role"].search([("project_id", "=", project.id), ("code", "=", code)], limit=1)
            if role:
                role_ids[code] = role.id
        missing = sorted(wanted["phase"] - phase_ids.keys()) + sorted(wanted["role"] - role_ids.keys())
        if missing:
            raise UserError(
                self.env._(
                    "This blueprint refers to roles or phases that are neither in the file nor in this project: "
                    "%(codes)s. Add them to the file and import again.",
                    codes=", ".join(missing),
                )
            )

    @api.model
    def _resolve_apps(self, tasks_per_flow):
        """Module id per technical name in the tasks' ``apps``. A name that is
        no app here (an Enterprise app on Community, a typo) is skipped, so
        one file works on every Odoo."""
        names = set()
        for tasks in tasks_per_flow:
            for task in tasks:
                apps = task.get("apps", [])
                if not isinstance(apps, list) or not all(isinstance(name, str) for name in apps):
                    raise UserError(
                        self.env._(
                            "Task '%(task)s' has apps that are not a list of technical names, "
                            'such as ["sale_management", "stock"]. Fix it and import again.',
                            task=task["name"],
                        )
                    )
                names.update(apps)
        modules = (
            self.env["ir.module.module"].sudo().search([("name", "in", sorted(names)), ("application", "=", True)])
            if names
            else []
        )
        return {module.name: module.id for module in modules}

    @api.model
    def _get_import_lang(self, data):
        """The language the names in the file are written in (``en_US`` if not given)."""
        lang = data.get("lang", SOURCE_LANG)
        if lang != SOURCE_LANG and lang not in dict(self.env["res.lang"].get_installed()):
            raise UserError(
                self.env._(
                    "This blueprint is written in language %(lang)s, which is not active here. "
                    "Activate the language and import again, or export the file again in English.",
                    lang=lang,
                )
            )
        return lang

    @api.model
    def _serialized_size(self, data):
        """The size in bytes of ``data`` written as JSON, the same measure as a file."""
        try:
            return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError, RecursionError) as error:
            raise UserError(
                self.env._("This blueprint holds values that are not plain JSON. Export the file again and import that.")
            ) from error

    @api.model
    def _check_size(self, size):
        if size > MAX_FILE_BYTES:
            raise UserError(
                self.env._(
                    "This blueprint is %(size)s MB; at most %(max)s MB can be imported at once. "
                    "Split the file or remove records.",
                    size=round(size / 1024 / 1024, 1),
                    max=MAX_FILE_BYTES // 1024 // 1024,
                )
            )

    @api.model
    def _check_header(self, data):
        if not isinstance(data, dict) or data.get("format") != BLUEPRINT_FORMAT:
            raise UserError(
                self.env._("This is not a blueprint file. Choose a file exported from Blueprint, or load the template.")
            )
        if data.get("version") == 1:
            raise UserError(
                self.env._(
                    "This is a version 1 blueprint (chains, processes, activities and scenarios). "
                    "This app reads version 2, where everything is a task. "
                    "Load the template, or export the project again and import that."
                )
            )
        if data.get("version") != BLUEPRINT_VERSION:
            raise UserError(
                self.env._(
                    "This blueprint file has version %(found)s; this app reads version %(expected)s. "
                    "Export the project again with this app and import that.",
                    found=data.get("version"),
                    expected=BLUEPRINT_VERSION,
                )
            )

    @api.model
    def _parse_json(self, raw, label):
        try:
            return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except json.JSONDecodeError as error:
            raise UserError(
                self.env._(
                    "%(name)s is not a blueprint file: it breaks off or has a typo near line %(line)s. "
                    "Choose a file exported from Blueprint, or load the template.",
                    name=label,
                    line=error.lineno,
                )
            ) from error
        except (UnicodeDecodeError, ValueError, RecursionError) as error:
            raise UserError(
                self.env._(
                    "%(name)s is not a blueprint file. Choose a file exported from Blueprint, or load the template.",
                    name=label,
                )
            ) from error

    # ------------------------------------------------------------------
    # Helpers of the project buttons
    # ------------------------------------------------------------------

    @api.model
    def _read_template(self):
        with file_open(TEMPLATE_FILE, "rb", filter_ext=(".json",)) as handle:
            return self._parse_json(handle.read(), TEMPLATE_FILE.rsplit("/", 1)[-1])

    @api.model
    def _download(self, project):
        """An act_url that downloads the project as blueprint.json."""
        content = json.dumps(self.export_blueprint(project), indent=2, ensure_ascii=False) + "\n"
        holder = self.env["pan.sl.blueprint.wizard"].create(
            {
                "project_id": project.id,
                "file": base64.b64encode(content.encode("utf-8")),
                "filename": "blueprint.json",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={holder._name}&id={holder.id}&field=file"
            "&filename_field=filename&download=true",
            "target": "download",
        }

    @api.model
    def _notify_and_open_map(self, title, summary, project):
        """Say what an import changed, then open the project's map."""
        labels = {
            "stages": self.env._("stages"),
            "phases": self.env._("phases"),
            "roles": self.env._("roles"),
            "flows": self.env._("flows"),
            "tasks": self.env._("tasks"),
        }

        def counts(key):
            return ", ".join(f"{summary[s][key]} {labels[s]}" for s in SECTIONS if summary[s][key])

        created, updated = counts("created"), counts("updated")
        parts = []
        if created:
            parts.append(self.env._("Created %(counts)s.", counts=created))
        if updated:
            parts.append(self.env._("Updated %(counts)s.", counts=updated))
        # target "main": the map replaces the breadcrumbs instead of stacking.
        next_action = dict(project.action_open_blueprint_map(), target="main")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": " ".join(parts) or self.env._("Nothing to change."),
                "type": "success",
                "next": next_action,
            },
        }


class PanSlBlueprintWizard(models.TransientModel):
    _name = "pan.sl.blueprint.wizard"
    _description = "Blueprint file"

    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        ondelete="cascade",
        help="The project the blueprint is imported into or exported from.",
    )
    file = fields.Binary(
        string="Blueprint file",
        help="A blueprint JSON file (version 2) of at most 5 MB.",
    )
    filename = fields.Char(
        string="File name",
        help="Name of the blueprint file.",
    )

    def action_import(self):
        """Import the chosen file into the project, then open its map."""
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Choose a blueprint file to import."))
        raw = base64.b64decode(self.file)
        Blueprint = self.env["pan.sl.blueprint"]
        # Checked before parsing, so a huge file is never read into memory twice.
        Blueprint._check_size(len(raw))
        data = Blueprint._parse_json(raw, self.filename or self.env._("The file"))
        summary = Blueprint.import_blueprint(self.project_id, data)
        return Blueprint._notify_and_open_map(self.env._("Blueprint imported"), summary, self.project_id)
