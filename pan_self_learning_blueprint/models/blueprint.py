"""Open blueprint format: export and import the whole company model as JSON.

See ``docs/blueprint-format.md`` for the format. Records are matched on
``code``; import creates and updates, it never deletes.

Unknown Odoo models
-------------------
An activity or phase may name an Odoo model (``sale.order``) whose app is not
installed. ``import_blueprint(data)`` is strict by default and refuses the
file, naming the missing models, so a hand-made or exported blueprint never
loses information silently. The bundled templates are written for a full
installation; ``import_blueprint(data, strict=False)`` (used by the wizard's
"Load template") imports every record but leaves the model link empty for
models that are not installed, and lists those models in the result so the
user knows which apps to install and which links to set later.

Loading a template never overwrites the company's own work
-----------------------------------------------------------
``import_blueprint(data, fill_empty_only=True)`` (used by "Load template")
creates the records that are missing and only fills what is still empty on
the existing ones: an empty name, description, open point or click path, an
empty model link, and the phase models (added, never removed). It never
touches choice states, booleans, references or scenario steps a company
already has. So loading the template again after installing an app links the
new models without undoing any decision.

Language
--------
Names are translatable. An export always writes the English source values and
says so in ``lang``; an import writes the names in the language the file
declares (``en_US`` when the key is absent), so a Dutch user's export never
replaces the English source text.
"""

import base64
import json
import os

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_open, file_path, is_html_empty

BLUEPRINT_FORMAT = "pantalytics-blueprint"
BLUEPRINT_VERSION = 1
TEMPLATE_DIR = "pan_self_learning_blueprint/data/blueprints"
SOURCE_LANG = "en_US"

# The Odoo app (module) that provides a model, to tell a user which app to
# install instead of naming a technical model. Models not listed here are
# reported by their technical name, on a line of their own.
MODEL_APPS = {
    "account.analytic.line": "hr_timesheet",
    "account.move": "account",
    "crm.lead": "crm",
    "mrp.bom": "mrp",
    "mrp.production": "mrp",
    "product.template": "product",
    "purchase.order": "purchase",
    "sale.order": "sale_management",
    "stock.picking": "stock",
}

# Sections in dependency order: every section only refers to earlier ones.
SECTIONS = ("chains", "phases", "roles", "processes", "activities", "scenarios")
SECTION_MODELS = {
    "chains": "pan.sl.chain",
    "phases": "pan.sl.phase",
    "roles": "pan.sl.role",
    "processes": "pan.sl.process",
    "activities": "pan.sl.activity",
    "scenarios": "pan.sl.scenario",
}


# A company clears these on purpose (a resolved open point); a template reload
# must not bring them back.
NEVER_REFILL = frozenset({"open_point"})


class PanSlBlueprint(models.AbstractModel):
    _name = "pan.sl.blueprint"
    _description = "Blueprint import and export"

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def export_blueprint(self):
        """Return the whole company model as a blueprint dict (format version 1).

        Translatable names are exported in the English source language,
        whatever the language of the exporting user, so the file is stable.
        """
        self = self.with_context(lang=SOURCE_LANG)
        chains = self.env["pan.sl.chain"].search([])
        phases = self.env["pan.sl.phase"].search([])
        roles = self.env["pan.sl.role"].search([])
        processes = self.env["pan.sl.process"].search([])
        activities = self.env["pan.sl.activity"].search([])
        scenarios = self.env["pan.sl.scenario"].search([])
        return {
            "format": BLUEPRINT_FORMAT,
            "version": BLUEPRINT_VERSION,
            "lang": SOURCE_LANG,
            "name": self.env.company.name,
            "chains": [
                {
                    "code": chain.code,
                    "name": chain.name,
                    "sequence": chain.sequence,
                    "description": chain.description or "",
                }
                for chain in chains
            ],
            "phases": [
                {
                    "code": phase.code,
                    "name": phase.name,
                    "sequence": phase.sequence,
                    "models": phase.model_ids.mapped("model"),
                    "apps": self._split_labels(phase.app_labels),
                }
                for phase in phases
            ],
            "roles": [
                {
                    "code": role.code,
                    "name": role.name,
                    "sequence": role.sequence,
                    "external": role.is_external,
                    "description": role.description or "",
                }
                for role in roles
            ],
            "processes": [
                {
                    "code": process.code,
                    "name": process.name,
                    "sequence": process.sequence,
                    "chain": process.chain_id.code,
                    "owner_role": process.owner_role_id.code or "",
                }
                for process in processes
            ],
            "activities": [
                {
                    "code": activity.code,
                    "name": activity.name,
                    "sequence": activity.sequence,
                    "process": activity.process_id.code,
                    "role": activity.role_id.code,
                    "phase": activity.phase_id.code,
                    "model": activity.model_id.model or "",
                    "choice_state": activity.choice_state,
                    "open_point": activity.open_point or "",
                    "click_path": activity.click_path or "",
                }
                for activity in activities
            ],
            "scenarios": [
                {
                    "code": scenario.code,
                    "name": scenario.name,
                    "sequence": scenario.sequence,
                    "description": scenario.description or "",
                    "open_point": scenario.open_point or "",
                    "steps": [
                        {"activity": step.activity_id.code, "note": step.note}
                        if step.note
                        else step.activity_id.code
                        for step in scenario.step_ids.sorted(lambda s: (s.sequence, s.id))
                    ],
                }
                for scenario in scenarios
            ],
        }

    @api.model
    def _split_labels(self, labels):
        return [label.strip() for label in (labels or "").split(",") if label.strip()]

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def import_blueprint(self, data, strict=True, fill_empty_only=False):
        """Create or update all records of a blueprint dict, matched on ``code``.

        :param dict data: the parsed blueprint (see docs/blueprint-format.md)
        :param bool strict: when True (default) an unknown Odoo model refuses
            the whole file; when False the model link is left empty and the
            model is reported in ``skipped_models``.
        :param bool fill_empty_only: when True (template loading) existing
            records are never overwritten: only empty fields are filled, phase
            models are added, and scenarios that already have steps keep them.
        :return: summary dict ``{"name", "chains": {"created", "updated"}, ...,
            "skipped_models": [str]}``
        :raise UserError: on a wrong format, version or language, a malformed
            record, a reference to an unknown code, or (strict) an unknown model.
        """
        self._check_header(data)
        self = self.with_context(lang=self._get_import_lang(data))
        sections = {key: self._get_section(data, key) for key in SECTIONS}
        model_map, missing_models = self._resolve_models(sections)
        if missing_models and strict:
            raise UserError(
                self.env._(
                    "This blueprint refers to Odoo models that are not installed: %(models)s. "
                    "Install the apps that provide them, or remove these models from the file.",
                    models=", ".join(missing_models),
                )
            )

        summary = {"name": data.get("name") or "", "skipped_models": missing_models}
        refs = {}
        summary["chains"] = self._upsert(
            "chains", sections["chains"], lambda item, is_new: self._chain_vals(item), refs, fill_empty_only
        )
        summary["phases"] = self._upsert(
            "phases",
            sections["phases"],
            lambda item, is_new: self._phase_vals(item, model_map, fill_empty_only),
            refs,
            fill_empty_only,
        )
        summary["roles"] = self._upsert(
            "roles", sections["roles"], lambda item, is_new: self._role_vals(item), refs, fill_empty_only
        )
        self._load_refs(refs, sections["processes"], (("chain", "chains"), ("owner_role", "roles")))
        summary["processes"] = self._upsert(
            "processes",
            sections["processes"],
            lambda item, is_new: self._process_vals(item, is_new, refs),
            refs,
            fill_empty_only,
        )
        self._load_refs(
            refs, sections["activities"], (("process", "processes"), ("role", "roles"), ("phase", "phases"))
        )
        summary["activities"] = self._upsert(
            "activities",
            sections["activities"],
            lambda item, is_new: self._activity_vals(item, model_map, is_new, refs),
            refs,
            fill_empty_only,
        )
        summary["scenarios"] = self._upsert(
            "scenarios", sections["scenarios"], lambda item, is_new: self._scenario_vals(item), refs, fill_empty_only
        )
        self._replace_scenario_steps(sections["scenarios"], refs, fill_empty_only)
        return summary

    @api.model
    def _get_import_lang(self, data):
        """The language the names in the file are written in (``en_US`` if not given)."""
        lang = data.get("lang", SOURCE_LANG)
        if lang == SOURCE_LANG:
            return lang
        installed = dict(self.env["res.lang"].get_installed())
        if not isinstance(lang, str) or lang not in installed:
            raise UserError(
                self.env._(
                    "The blueprint is written in language %(lang)r, which is not active in this "
                    "database. Activate it first, or export the file again in English.",
                    lang=lang,
                )
            )
        return lang

    @api.model
    def _check_header(self, data):
        if not isinstance(data, dict):
            raise UserError(self.env._("A blueprint must be a JSON object, not %(type)s.", type=type(data).__name__))
        if data.get("format") != BLUEPRINT_FORMAT:
            raise UserError(
                self.env._(
                    "This is not a blueprint file: 'format' is %(found)r, expected %(expected)r.",
                    found=data.get("format"),
                    expected=BLUEPRINT_FORMAT,
                )
            )
        if data.get("version") != BLUEPRINT_VERSION:
            raise UserError(
                self.env._(
                    "Blueprint version %(found)r is not supported; this module reads version %(expected)s.",
                    found=data.get("version"),
                    expected=BLUEPRINT_VERSION,
                )
            )

    @api.model
    def _get_section(self, data, key):
        items = data.get(key, [])
        if not isinstance(items, list):
            raise UserError(self.env._("The section '%(section)s' must be a list.", section=key))
        seen = set()
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise UserError(
                    self.env._("Item %(index)s of '%(section)s' must be an object.", index=index, section=key)
                )
            code = item.get("code")
            if not isinstance(code, str) or not code.strip():
                raise UserError(
                    self.env._("Item %(index)s of '%(section)s' has no code.", index=index, section=key)
                )
            if code in seen:
                raise UserError(
                    self.env._("The code '%(code)s' appears twice in '%(section)s'.", code=code, section=key)
                )
            seen.add(code)
        return items

    @api.model
    def _resolve_models(self, sections):
        """Map every technical model name in the file to its ``ir.model`` id.

        :return: (dict name -> id, sorted list of names that are not installed)
        """
        names = set()
        for phase in sections["phases"]:
            phase_models = phase.get("models", [])
            if not isinstance(phase_models, list):
                raise UserError(
                    self.env._("'models' of phase '%(code)s' must be a list.", code=phase["code"])
                )
            names.update(phase_models)
        names.update(activity["model"] for activity in sections["activities"] if activity.get("model"))
        for name in names:
            if not isinstance(name, str):
                raise UserError(self.env._("A model name must be text, found %(value)r.", value=name))
        # ir.model is technical metadata; reading it does not expose business data.
        found = self.env["ir.model"].sudo().search_read([("model", "in", list(names))], ["model"])
        model_map = {row["model"]: row["id"] for row in found}
        return model_map, sorted(names - set(model_map))

    @api.model
    def _codes_to_ids(self, section, codes):
        """Return {code: id} for the given codes; raise naming the first unknown one."""
        codes = set(codes)
        if not codes:
            return {}
        records = self.env[SECTION_MODELS[section]].search_read([("code", "in", list(codes))], ["code"])
        mapping = {row["code"]: row["id"] for row in records}
        missing = sorted(codes - set(mapping))
        if missing:
            raise UserError(
                self.env._(
                    "The blueprint refers to unknown %(section)s code(s): %(codes)s. "
                    "Add them to the file or create them first.",
                    section=section,
                    codes=", ".join(missing),
                )
            )
        return mapping

    @api.model
    def _load_refs(self, refs, items, keys):
        """Resolve every code that ``items`` refer to, one query per section.

        ``keys`` is a sequence of ``(item key, section)``. The ids are added to
        ``refs[section]``; an unknown code raises, naming all unknown codes.
        """
        for key, section in keys:
            codes = {item[key] for item in items if item.get(key)} - set(refs.get(section, {}))
            refs.setdefault(section, {}).update(self._codes_to_ids(section, codes))

    @api.model
    def _ref_id(self, refs, section, item, key, required):
        code = item.get(key)
        if not code:
            if required:
                raise UserError(
                    self.env._("'%(code)s' needs a '%(key)s'.", code=item["code"], key=key)
                )
            return False
        if code not in refs.get(section, {}):
            # Codes are resolved up front by _load_refs; reaching this is a bug.
            raise UserError(
                self.env._(
                    "The blueprint refers to unknown %(section)s code(s): %(codes)s. "
                    "Add them to the file or create them first.",
                    section=section,
                    codes=code,
                )
            )
        return refs[section][code]

    @api.model
    def _upsert(self, section, items, make_vals, refs, fill_empty_only=False):
        """Create or update the records of one section, matched on code.

        ``make_vals(item, is_new)`` returns the values to write; on update only
        the keys present in the item are written. With ``fill_empty_only`` an
        existing record only gets the values of fields that are still empty.
        Afterwards ``refs[section]`` maps every code of the section to its id.
        """
        refs.setdefault(section, {})
        if not items:
            return {"created": 0, "updated": 0}
        Model = self.env[SECTION_MODELS[section]]
        existing = {
            record.code: record for record in Model.search([("code", "in", [item["code"] for item in items])])
        }
        to_create = []
        updated = 0
        for item in items:
            record = existing.get(item["code"])
            vals = make_vals(item, not record)
            if record:
                if fill_empty_only:
                    vals = self._empty_only(record, vals)
                if vals:
                    record.write(vals)
                    updated += 1
            else:
                if not item.get("name"):
                    raise UserError(
                        self.env._(
                            "The new %(section)s record '%(code)s' needs a name.",
                            section=section,
                            code=item["code"],
                        )
                    )
                to_create.append(dict(vals, code=item["code"]))
        created = Model.create(to_create) if to_create else Model
        refs[section].update({record.code: record.id for record in existing.values()})
        refs[section].update({record.code: record.id for record in created})
        return {"created": len(to_create), "updated": updated}

    @api.model
    def _empty_only(self, record, vals):
        """Keep only the values that fill an empty field of ``record``.

        Booleans and selections always hold a decision (``is_external``,
        ``choice_state``), so they are never filled. x2many commands are kept:
        the callers only send additive ``link`` commands in this mode.
        """
        kept = {}
        for key, value in vals.items():
            if key in NEVER_REFILL:
                continue
            field = record._fields[key]
            if field.type in ("many2many", "one2many"):
                kept[key] = value
            elif field.type in ("boolean", "selection"):
                continue
            elif field.type == "html":
                if is_html_empty(record[key]):
                    kept[key] = value
            elif not record[key]:
                kept[key] = value
        return kept

    @api.model
    def _common_vals(self, item, keys):
        vals = {}
        for key in keys:
            if key in item:
                vals[key] = item[key] or False
        if "sequence" in item:
            if not isinstance(item["sequence"], int):
                raise UserError(
                    self.env._("The sequence of '%(code)s' must be a whole number.", code=item["code"])
                )
            vals["sequence"] = item["sequence"]
        return vals

    @api.model
    def _chain_vals(self, item):
        return self._common_vals(item, ("name", "description"))

    @api.model
    def _phase_vals(self, item, model_map, fill_empty_only=False):
        vals = self._common_vals(item, ("name",))
        if "models" in item:
            ids = [model_map[name] for name in item["models"] if name in model_map]
            if fill_empty_only:
                # Add the models that are installed now; keep the ones the company set.
                vals["model_ids"] = [fields.Command.link(model_id) for model_id in ids]
            else:
                vals["model_ids"] = [fields.Command.set(ids)]
        if "apps" in item:
            if not isinstance(item["apps"], list):
                raise UserError(self.env._("'apps' of phase '%(code)s' must be a list.", code=item["code"]))
            vals["app_labels"] = ", ".join(str(app).strip() for app in item["apps"] if str(app).strip()) or False
        return vals

    @api.model
    def _role_vals(self, item):
        vals = self._common_vals(item, ("name", "description"))
        if "external" in item:
            vals["is_external"] = bool(item["external"])
        return vals

    @api.model
    def _process_vals(self, item, is_new, refs):
        vals = self._common_vals(item, ("name",))
        if "chain" in item or is_new:
            vals["chain_id"] = self._ref_id(refs, "chains", item, "chain", required=True)
        if "owner_role" in item:
            vals["owner_role_id"] = self._ref_id(refs, "roles", item, "owner_role", required=False)
        return vals

    @api.model
    def _activity_vals(self, item, model_map, is_new, refs):
        vals = self._common_vals(item, ("name", "open_point", "click_path"))
        for key, section, field_name in (
            ("process", "processes", "process_id"),
            ("role", "roles", "role_id"),
            ("phase", "phases", "phase_id"),
        ):
            if key in item or is_new:
                vals[field_name] = self._ref_id(refs, section, item, key, required=True)
        if "model" in item:
            # Unknown models only get here in non-strict mode: leave the link empty.
            vals["model_id"] = model_map.get(item["model"], False) if item["model"] else False
        if "choice_state" in item:
            states = self.env["pan.sl.activity"]._fields["choice_state"].get_values(self.env)
            if item["choice_state"] not in states:
                raise UserError(
                    self.env._(
                        "Activity '%(code)s' has choice state %(state)r; use one of: %(states)s.",
                        code=item["code"],
                        state=item["choice_state"],
                        states=", ".join(states),
                    )
                )
            vals["choice_state"] = item["choice_state"]
        return vals

    @api.model
    def _scenario_vals(self, item):
        return self._common_vals(item, ("name", "description", "open_point"))

    @api.model
    def _replace_scenario_steps(self, items, refs, fill_empty_only=False):
        """Make the steps of every scenario that lists ``steps`` match the file order.

        With ``fill_empty_only`` only scenarios without steps get them; a
        company's own route is kept as it is.
        """
        parsed = {}
        for item in items:
            if "steps" not in item:
                continue
            if not isinstance(item["steps"], list):
                raise UserError(
                    self.env._("'steps' of scenario '%(code)s' must be a list.", code=item["code"])
                )
            steps = []
            for step in item["steps"]:
                if isinstance(step, str):
                    steps.append((step, False))
                elif isinstance(step, dict) and isinstance(step.get("activity"), str):
                    steps.append((step["activity"], step.get("note") or False))
                else:
                    raise UserError(
                        self.env._(
                            "A step of scenario '%(code)s' must be an activity code or "
                            "an object with 'activity' and 'note'; found %(step)r.",
                            code=item["code"],
                            step=step,
                        )
                    )
            parsed[item["code"]] = steps
        if not parsed:
            return
        activity_ids = self._codes_to_ids(
            "activities", {code for steps in parsed.values() for code, _note in steps}
        )
        scenarios = self.env["pan.sl.scenario"].browse([refs["scenarios"][code] for code in parsed])
        if fill_empty_only:
            scenarios = scenarios.filtered(lambda scenario: not scenario.step_ids)
        else:
            scenarios.step_ids.unlink()
        self.env["pan.sl.scenario.step"].create(
            [
                {
                    "scenario_id": scenario.id,
                    "sequence": (position + 1) * 10,
                    "activity_id": activity_ids[code],
                    "note": note,
                }
                for scenario in scenarios
                for position, (code, note) in enumerate(parsed[scenario.code])
            ]
        )


class PanSlBlueprintWizard(models.TransientModel):
    _name = "pan.sl.blueprint.wizard"
    _description = "Blueprint import / export"

    mode = fields.Selection(
        [("import", "Import a file"), ("export", "Export"), ("template", "Load a template")],
        string="Action",
        required=True,
        default="import",
        help="Import a blueprint file, export the current model, or load one of the bundled templates.",
    )
    file = fields.Binary(
        string="Blueprint file",
        help="A blueprint JSON file (format 'pantalytics-blueprint', version 1). "
        "After an export this holds the exported file.",
    )
    filename = fields.Char(
        string="File name",
        help="Name of the blueprint file.",
    )
    template = fields.Selection(
        selection="_selection_template",
        string="Template",
        default=lambda self: self._default_template(),
        help="A blueprint shipped with the module (data/blueprints). Models of apps that are not "
        "installed are skipped and listed in the result.",
    )
    result = fields.Text(
        string="Result",
        readonly=True,
        help="Summary of the last import or export.",
    )
    warning = fields.Text(
        string="Warning",
        readonly=True,
        help="What the last template load could not do, such as the apps to install so that "
        "activities and phases can be linked to their Odoo documents.",
    )

    @api.model
    def _selection_template(self):
        directory = file_path(TEMPLATE_DIR)
        return [
            (name, os.path.splitext(name)[0].replace("_", " ").capitalize())
            for name in sorted(os.listdir(directory))
            if name.endswith(".json")
        ]

    @api.model
    def _default_template(self):
        """Preselect the template when the module ships exactly one."""
        templates = self._selection_template()
        return templates[0][0] if len(templates) == 1 else False

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Choose a blueprint file to import."))
        data = self._parse_json(base64.b64decode(self.file), self.filename or self.env._("the file"))
        summary = self.env["pan.sl.blueprint"].import_blueprint(data, strict=True)
        self.write({"result": self._format_summary(summary), "warning": False})
        return self._reopen()

    def action_load_template(self):
        self.ensure_one()
        if not self.template:
            raise UserError(self.env._("Choose a template to load."))
        if self.template not in dict(self._selection_template()):
            raise UserError(self.env._("The template %(name)s does not exist.", name=self.template))
        with file_open(f"{TEMPLATE_DIR}/{self.template}", "rb", filter_ext=(".json",)) as handle:
            data = self._parse_json(handle.read(), self.template)
        # Never overwrite the company's own decisions: only fill what is missing.
        summary = self.env["pan.sl.blueprint"].import_blueprint(data, strict=False, fill_empty_only=True)
        self.write(
            {
                "result": self._format_summary(summary),
                "warning": self._format_missing_apps(summary["skipped_models"]),
            }
        )
        return self._reopen()

    def action_export(self):
        self.ensure_one()
        data = self.env["pan.sl.blueprint"].export_blueprint()
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        self.write(
            {
                "file": base64.b64encode(content.encode("utf-8")),
                "filename": "blueprint.json",
                "warning": False,
                "result": self.env._(
                    "Exported %(chains)s chains, %(phases)s phases, %(roles)s roles, %(processes)s processes, "
                    "%(activities)s activities and %(scenarios)s scenarios.",
                    **{key: len(data[key]) for key in SECTIONS},
                ),
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={self._name}&id={self.id}&field=file"
            "&filename_field=filename&download=true",
            "target": "download",
        }

    def _parse_json(self, raw, label):
        try:
            return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (UnicodeDecodeError, ValueError) as error:
            raise UserError(
                self.env._("%(name)s is not a valid JSON file: %(error)s", name=label, error=error)
            ) from error

    def _format_summary(self, summary):
        lines = [self.env._("Imported blueprint %(name)s.", name=summary["name"] or "-")]
        for key in SECTIONS:
            counts = summary[key]
            lines.append(
                self.env._(
                    "%(section)s: %(created)s created, %(updated)s updated.",
                    section=key.capitalize(),
                    created=counts["created"],
                    updated=counts["updated"],
                )
            )
        return "\n".join(lines)

    def _format_missing_apps(self, skipped_models):
        """Name the apps to install for the models a template could not link, or False."""
        if not skipped_models:
            return False
        module_names = {MODEL_APPS[model] for model in skipped_models if model in MODEL_APPS}
        # ir.module.module is technical metadata; reading it does not expose business data.
        modules = self.env["ir.module.module"].sudo().search_read(
            [("name", "in", list(module_names))], ["name", "shortdesc"]
        )
        app_names = {row["name"]: row["shortdesc"] for row in modules}
        apps = sorted(
            {app_names[MODEL_APPS[model]] for model in skipped_models if MODEL_APPS.get(model) in app_names}
        )
        unknown = sorted(model for model in skipped_models if MODEL_APPS.get(model) not in app_names)
        lines = []
        if apps:
            lines.append(
                self.env._(
                    "Not installed: %(apps)s. The activities and phases that use these apps are "
                    "loaded without their Odoo link. Install the apps, then load the template again: "
                    "it only fills in the missing links and keeps your own changes.",
                    apps=", ".join(apps),
                )
            )
        if unknown:
            lines.append(
                self.env._(
                    "Also not installed (technical model names): %(models)s.",
                    models=", ".join(unknown),
                )
            )
        return "\n".join(lines)

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": self.env._("Blueprint"),
        }
