import base64
import json
from urllib.parse import parse_qs, urlparse

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.misc import file_open

from ..models.blueprint import MAX_FILE_BYTES, MAX_RECORDS
from .common import BlueprintCase

SECTIONS = ("chains", "phases", "roles", "processes", "activities", "scenarios")
SECTION_MODELS = {
    "chains": "pan.sl.chain",
    "phases": "pan.sl.phase",
    "roles": "pan.sl.role",
    "processes": "pan.sl.process",
    "activities": "pan.sl.activity",
    "scenarios": "pan.sl.scenario",
}
TEMPLATE_PATH = "pan_self_learning_blueprint/data/blueprints/generic_manufacturing.json"


@tagged("post_install", "-at_install")
class TestBlueprint(BlueprintCase):
    """Open blueprint format: idempotent round trip, clear refusals, bundled template."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Blueprint = cls.env["pan.sl.blueprint"]
        cls.Wizard = cls.env["pan.sl.blueprint.wizard"]
        partner_model = cls.env["ir.model"]._get("res.partner")
        cls.phase_a.app_labels = "Contacts, Sales"
        cls.act_a.write(
            {
                "model_id": partner_model.id,
                "choice_state": "fixed",
                "open_point": "Check the payment terms.",
                "click_path": "<ol><li>Contacts, New</li></ol>",
            }
        )
        cls.scenario = cls.Scenario.create(
            {
                "name": "Test route",
                "code": "t_route",
                "description": "Goal of the test route.",
                "step_ids": [
                    Command.create({"sequence": 10, "activity_id": cls.act_b.id}),
                    Command.create({"sequence": 20, "activity_id": cls.act_a.id, "note": "Second step"}),
                    Command.create({"sequence": 30, "activity_id": cls.act_c.id}),
                ],
            }
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _wipe(self):
        """Remove every blueprint record, so the database holds a clean set."""
        for section in ("scenarios", "activities", "processes", "roles", "phases", "chains"):
            self.env[SECTION_MODELS[section]].search([]).unlink()
        self.env.flush_all()
        for section in SECTIONS:
            self.assertFalse(self.env[SECTION_MODELS[section]].search_count([]))

    def _counts(self):
        counts = {section: self.env[SECTION_MODELS[section]].search_count([]) for section in SECTIONS}
        counts["steps"] = self.Step.search_count([])
        return counts

    def _minimal(self, **overrides):
        data = {
            "format": "pantalytics-blueprint",
            "version": 1,
            "name": "Minimal test blueprint",
            "chains": [{"code": "t_bp_chain", "name": "Chain"}],
            "phases": [{"code": "t_bp_phase", "name": "Phase", "apps": ["Contacts"]}],
            "roles": [{"code": "t_bp_role", "name": "Role", "external": False}],
            "processes": [{"code": "t_bp_process", "name": "Process", "chain": "t_bp_chain", "owner_role": "t_bp_role"}],
            "activities": [
                {
                    "code": "t_bp_act",
                    "name": "Activity",
                    "process": "t_bp_process",
                    "role": "t_bp_role",
                    "phase": "t_bp_phase",
                    "model": "res.partner",
                    "choice_state": "proposal",
                }
            ],
            "scenarios": [{"code": "t_bp_scen", "name": "Scenario", "steps": ["t_bp_act"]}],
        }
        data.update(overrides)
        return data

    def _import_file(self, content, filename="blueprint.json"):
        """Import through the "Import file" dialog; return the notification message."""
        wizard = self.Wizard.create({"file": base64.b64encode(content), "filename": filename})
        action = wizard.action_import()
        return action["params"]["message"]

    def _load_template(self):
        """Run "Load template"; return the notification action."""
        action = self.Blueprint.action_load_template()
        self.assertEqual(action["tag"], "display_notification")
        return action

    # ------------------------------------------------------------------
    # export / import round trip
    # ------------------------------------------------------------------

    def test_export_header_and_content(self):
        data = self.Blueprint.export_blueprint()
        self.assertEqual(data["format"], "pantalytics-blueprint")
        self.assertEqual(data["version"], 1)
        for section in SECTIONS:
            self.assertIsInstance(data[section], list)
        activity = next(item for item in data["activities"] if item["code"] == "t_act_a")
        self.assertEqual(activity["process"], "t_process")
        self.assertEqual(activity["role"], "t_sales")
        self.assertEqual(activity["phase"], "t_phase_a")
        self.assertEqual(activity["model"], "res.partner")
        self.assertEqual(activity["choice_state"], "fixed")
        phase = next(item for item in data["phases"] if item["code"] == "t_phase_a")
        self.assertNotIn("models", phase, "D6: phases no longer export Odoo models.")
        self.assertEqual(phase["apps"], ["Contacts", "Sales"])
        role = next(item for item in data["roles"] if item["code"] == "t_customer")
        self.assertTrue(role["external"])
        scenario = next(item for item in data["scenarios"] if item["code"] == "t_route")
        step_codes = [step if isinstance(step, str) else step["activity"] for step in scenario["steps"]]
        self.assertEqual(step_codes, ["t_act_b", "t_act_a", "t_act_c"])

    def test_export_has_no_personal_data(self):
        person = self.env["res.partner"].create({"name": "T export person"})
        self.role_sales.partner_ids = person | self.env.user.partner_id
        text = json.dumps(self.Blueprint.export_blueprint())
        self.assertNotIn(self.env.user.login, text)
        self.assertNotIn("T export person", text)
        self.assertNotIn('"users"', text)
        self.assertNotIn("adkar", text.lower())

    def test_round_trip_into_clean_set_is_idempotent(self):
        exported = self.Blueprint.export_blueprint()
        self._wipe()

        self.Blueprint.import_blueprint(exported)
        counts = self._counts()
        for section in SECTIONS:
            self.assertEqual(counts[section], len(exported[section]), f"{section} after first import")
        ids_first = {section: self.env[SECTION_MODELS[section]].search([]).ids for section in SECTIONS}

        self.Blueprint.import_blueprint(exported)
        self.assertEqual(self._counts(), counts, "A second import must create nothing.")
        ids_second = {section: self.env[SECTION_MODELS[section]].search([]).ids for section in SECTIONS}
        self.assertEqual(ids_second, ids_first)

        self.assertEqual(self.Blueprint.export_blueprint(), exported, "Export after import must match.")

        route = self.Scenario.search([("code", "=", "t_route")])
        self.assertEqual(route.activity_ids.mapped("code"), ["t_act_b", "t_act_a", "t_act_c"])

    def test_import_updates_and_never_deletes(self):
        self.Blueprint.import_blueprint(self._minimal())
        activity = self.Activity.search([("code", "=", "t_bp_act")])
        self.assertEqual(activity.name, "Activity")
        self.assertEqual(activity.model_id.model, "res.partner")

        data = self._minimal()
        data["activities"][0]["name"] = "Renamed activity"
        data["activities"][0]["choice_state"] = "revised"
        self.Blueprint.import_blueprint(data)
        self.assertEqual(activity.name, "Renamed activity")
        self.assertEqual(activity.choice_state, "revised")
        self.assertEqual(self.Activity.search_count([("code", "=", "t_bp_act")]), 1)

        self.Blueprint.import_blueprint(self._minimal(activities=[], scenarios=[]))
        self.assertTrue(activity.exists(), "Import must never delete records missing from the file.")
        self.assertTrue(self.act_a.exists())

    def test_import_references_existing_database_codes(self):
        data = self._minimal(
            chains=[],
            roles=[],
            phases=[],
            processes=[{"code": "t_bp_process", "name": "Process", "chain": "t_chain"}],
            activities=[
                {
                    "code": "t_bp_act",
                    "name": "Activity",
                    "process": "t_bp_process",
                    "role": "t_sales",
                    "phase": "t_phase_b",
                }
            ],
            scenarios=[{"code": "t_bp_scen", "name": "Scenario", "steps": ["t_act_a", "t_bp_act"]}],
        )
        self.Blueprint.import_blueprint(data)
        activity = self.Activity.search([("code", "=", "t_bp_act")])
        self.assertEqual(activity.chain_id, self.chain)
        self.assertEqual(activity.role_id, self.role_sales)
        scenario = self.Scenario.search([("code", "=", "t_bp_scen")])
        self.assertEqual(scenario.activity_ids, self.act_a | activity)
        self.assertEqual(scenario.activity_ids.ids, [self.act_a.id, activity.id])

    # ------------------------------------------------------------------
    # refusals
    # ------------------------------------------------------------------

    def test_unknown_reference_code_names_the_code(self):
        cases = {
            "t_missing_chain": self._minimal(
                processes=[{"code": "t_bp_process", "name": "Process", "chain": "t_missing_chain"}]
            ),
            "t_missing_role": self._minimal(
                activities=[
                    {
                        "code": "t_bp_act",
                        "name": "Activity",
                        "process": "t_bp_process",
                        "role": "t_missing_role",
                        "phase": "t_bp_phase",
                    }
                ]
            ),
            "t_missing_phase": self._minimal(
                activities=[
                    {
                        "code": "t_bp_act",
                        "name": "Activity",
                        "process": "t_bp_process",
                        "role": "t_bp_role",
                        "phase": "t_missing_phase",
                    }
                ]
            ),
            "t_missing_process": self._minimal(
                activities=[
                    {
                        "code": "t_bp_act",
                        "name": "Activity",
                        "process": "t_missing_process",
                        "role": "t_bp_role",
                        "phase": "t_bp_phase",
                    }
                ]
            ),
            "t_missing_activity": self._minimal(
                scenarios=[{"code": "t_bp_scen", "name": "Scenario", "steps": ["t_bp_act", "t_missing_activity"]}]
            ),
        }
        for code, data in cases.items():
            with self.subTest(code=code):
                with self.assertRaises(UserError) as caught:
                    self.Blueprint.import_blueprint(data)
                self.assertIn(code, str(caught.exception))

    def test_unknown_model_refused_in_strict_import(self):
        data = self._minimal()
        data["activities"][0]["model"] = "x_pan_sl_no_such.model"
        with self.assertRaises(UserError) as caught:
            self.Blueprint.import_blueprint(data)
        self.assertIn("x_pan_sl_no_such.model", str(caught.exception))
        self.assertFalse(self.Activity.search_count([("code", "=", "t_bp_act")]))

    def test_phase_models_key_is_ignored(self):
        """D6: older files list phase "models"; a strict import accepts and ignores them."""
        data = self._minimal()
        data["phases"][0]["models"] = ["res.partner", "x_pan_sl_missing.model"]
        self.Blueprint.import_blueprint(data)
        phase = self.Phase.search([("code", "=", "t_bp_phase")])
        self.assertEqual(phase.app_labels, "Contacts")
        self.assertNotIn("model_ids", self.Phase._fields)

    def test_record_limit(self):
        """D8: more than MAX_RECORDS records in total (steps included) are refused before anything is written."""
        self.assertEqual(MAX_RECORDS, 5000)
        filler = [{"code": f"t_bp_many_{index}", "name": "Chain"} for index in range(MAX_RECORDS - 7)]
        at_limit = self._minimal(chains=self._minimal()["chains"] + filler)
        # 1 + 4993 chains, 1 phase, 1 role, 1 process, 1 activity, 1 scenario with 1 step: 5000.
        self.Blueprint._check_record_count({section: at_limit[section] for section in SECTIONS})

        over = self._minimal(
            chains=[{"code": "t_bp_over_chain", "name": "Chain"}],
            scenarios=[{"code": "t_bp_scen", "name": "Scenario", "steps": ["t_bp_act"] * MAX_RECORDS}],
        )
        with self.assertRaises(UserError) as caught:
            self.Blueprint.import_blueprint(over)
        self.assertIn(str(MAX_RECORDS), str(caught.exception))
        self.assertFalse(self.Chain.search_count([("code", "=", "t_bp_over_chain")]))

    def test_wrong_format_or_version_refused(self):
        minimal = self._minimal()
        without_format = dict(minimal)
        del without_format["format"]
        without_version = dict(minimal)
        del without_version["version"]
        cases = {
            "other format": self._minimal(format="another-format"),
            "version 2": self._minimal(version=2),
            "version 0": self._minimal(version=0),
            "version as text": self._minimal(version="1"),
            "no format": without_format,
            "no version": without_version,
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(UserError):
                    self.Blueprint.import_blueprint(data)
        self.assertFalse(self.Chain.search_count([("code", "=", "t_bp_chain")]))

    def test_not_an_object_refused(self):
        with self.assertRaises(UserError):
            self.Blueprint.import_blueprint([])

    # ------------------------------------------------------------------
    # Load template (server action, managers)
    # ------------------------------------------------------------------

    def test_load_template_action(self):
        """D7/D8: one menu item for managers loads the bundled template and opens the map."""
        action = self.env.ref("pan_self_learning_blueprint.action_blueprint_load_template")
        self.assertEqual(action.model_id.model, "pan.sl.blueprint")
        self.assertEqual(
            action.group_ids, self.env.ref("pan_self_learning_blueprint.group_blueprint_manager")
        )
        result = action.run()
        self.assertEqual(result["tag"], "display_notification")
        self.assertTrue(result["params"]["message"])
        self.assertEqual(
            result["params"]["next"]["id"],
            self.env.ref("pan_self_learning_blueprint.action_blueprint_map").id,
            "After loading, the company map opens.",
        )

    def test_template_generic_manufacturing_loads(self):
        with file_open(TEMPLATE_PATH, "rb") as handle:
            template = json.loads(handle.read())
        action = self._load_template()
        self.assertIn("Created", action["params"]["message"])

        for section in SECTIONS:
            codes = [item["code"] for item in template[section]]
            found = self.env[SECTION_MODELS[section]].search([("code", "in", codes)])
            with self.subTest(section=section):
                self.assertEqual(sorted(found.mapped("code")), sorted(codes))

        for item in template["scenarios"]:
            scenario = self.Scenario.search([("code", "=", item["code"])])
            step_codes = [step if isinstance(step, str) else step["activity"] for step in item["steps"]]
            with self.subTest(scenario=item["code"]):
                self.assertEqual(scenario.activity_ids.mapped("code"), list(dict.fromkeys(step_codes)))

        counts = self._counts()
        again = self._load_template()
        self.assertEqual(self._counts(), counts, "Loading the template twice must create nothing.")
        self.assertTrue(
            again["params"]["message"].startswith("Nothing to change."),
            f"A second load writes nothing, so it reports nothing: {again['params']['message']!r}",
        )

    def test_no_default_structure_xml_ids(self):
        """D7: chains and phases come only from the template, not from module data."""
        data = self.env["ir.model.data"].search(
            [("module", "=", "pan_self_learning_blueprint"), ("model", "in", ("pan.sl.chain", "pan.sl.phase"))]
        )
        self.assertFalse(data, f"Module data still defines chains or phases: {data.mapped('name')}")

    # ------------------------------------------------------------------
    # loading a template again never overwrites company decisions
    # ------------------------------------------------------------------

    def test_template_reload_keeps_company_edits(self):
        self._load_template()
        activity = self.Activity.search([("code", "=", "customer_create")])
        self.assertTrue(activity)
        scenario = self.Scenario.search([("code", "=", "S01")])
        own_step_activity = self.act_c
        activity.write(
            {
                "choice_state": "revised",
                "click_path": "<p>Our own click path</p>",
                "open_point": "Our own open point",
                "name": "Our own name",
            }
        )
        scenario.step_ids.unlink()
        scenario.write({"step_ids": [Command.create({"sequence": 5, "activity_id": own_step_activity.id})]})
        role = activity.role_id
        role.is_external = not role.is_external
        external = role.is_external

        self._load_template()
        self.assertEqual(activity.choice_state, "revised")
        self.assertIn("Our own click path", activity.click_path)
        self.assertEqual(activity.open_point, "Our own open point")
        self.assertEqual(activity.name, "Our own name")
        self.assertEqual(scenario.activity_ids, own_step_activity, "A company's own route must be kept.")
        self.assertEqual(role.is_external, external)

    def test_template_reload_fills_empty_fields(self):
        self._load_template()
        activity = self.Activity.search([("code", "=", "customer_create")])
        self.assertEqual(activity.model_id.model, "res.partner")
        activity.write({"model_id": False, "click_path": False})
        scenario = self.Scenario.search([("code", "=", "S01")])
        scenario.step_ids.unlink()

        self._load_template()
        self.assertEqual(activity.model_id.model, "res.partner", "An empty model link is filled in again.")
        self.assertIn("Contacts, New", activity.click_path)
        self.assertEqual(scenario.activity_ids, activity, "A scenario without steps gets the template route.")

    def test_template_lists_missing_apps(self):
        """On a database without e.g. Sales the wizard names the app, not only the model."""
        Module = self.env["ir.module.module"].sudo()
        installed = Module.search([("state", "=", "installed")]).mapped("name")
        if "sale_management" in installed:
            self.skipTest("Sales is installed in this database, so nothing is missing.")
        params = self._load_template()["params"]
        self.assertEqual(params["type"], "warning")
        self.assertTrue(params["sticky"], "Missing apps must stay on screen until read.")
        self.assertIn("Not installed:", params["message"])
        sales = Module.search([("name", "=", "sale_management")])
        if sales:
            self.assertIn(sales.shortdesc, params["message"])
        unlinked = self.Activity.search(
            [("model_id", "=", False), ("code", "in", self._template_codes("activities"))]
        )
        self.assertTrue(unlinked, "Activities of missing apps are loaded without a model link.")

    def _template_codes(self, section):
        with file_open(TEMPLATE_PATH, "rb") as handle:
            return [item["code"] for item in json.loads(handle.read())[section]]

    def test_strict_import_still_overwrites(self):
        """A file import (not a template) stays the way to change decisions in bulk."""
        self.Blueprint.import_blueprint(self._minimal())
        activity = self.Activity.search([("code", "=", "t_bp_act")])
        activity.choice_state = "fixed"
        self.Blueprint.import_blueprint(self._minimal())
        self.assertEqual(activity.choice_state, "proposal")

    # ------------------------------------------------------------------
    # language
    # ------------------------------------------------------------------

    def test_export_is_in_english_whatever_the_user_language(self):
        self.env["res.lang"]._activate_lang("nl_NL")
        self.act_a.with_context(lang="en_US").name = "English name"
        self.act_a.with_context(lang="nl_NL").name = "Nederlandse naam"
        data = self.Blueprint.with_context(lang="nl_NL").export_blueprint()
        self.assertEqual(data["lang"], "en_US")
        item = next(item for item in data["activities"] if item["code"] == "t_act_a")
        self.assertEqual(item["name"], "English name")

        self.Blueprint.with_context(lang="nl_NL").import_blueprint(data)
        self.assertEqual(self.act_a.with_context(lang="en_US").name, "English name")
        self.assertEqual(self.act_a.with_context(lang="nl_NL").name, "Nederlandse naam")

    def test_import_writes_names_in_the_file_language(self):
        self.env["res.lang"]._activate_lang("nl_NL")
        self.Blueprint.import_blueprint(self._minimal())
        data = self._minimal(lang="nl_NL")
        data["activities"][0]["name"] = "Activiteit"
        self.Blueprint.import_blueprint(data)
        activity = self.Activity.search([("code", "=", "t_bp_act")])
        self.assertEqual(activity.with_context(lang="nl_NL").name, "Activiteit")
        self.assertEqual(activity.with_context(lang="en_US").name, "Activity")

    def test_import_refuses_inactive_language(self):
        with self.assertRaises(UserError) as caught:
            self.Blueprint.import_blueprint(self._minimal(lang="xx_XX"))
        self.assertIn("xx_XX", str(caught.exception))
        self.assertFalse(self.Chain.search_count([("code", "=", "t_bp_chain")]))

    # ------------------------------------------------------------------
    # Export and "Import file"
    # ------------------------------------------------------------------

    def test_export_then_import_file(self):
        action = self.Blueprint.action_export()
        self.assertEqual(action["type"], "ir.actions.act_url")
        query = parse_qs(urlparse(action["url"]).query)
        self.assertEqual(query["model"], ["pan.sl.blueprint.wizard"])
        holder = self.Wizard.browse(int(query["id"][0]))
        self.assertEqual(holder.filename, "blueprint.json")
        content = base64.b64decode(holder.file)
        data = json.loads(content)
        self.assertEqual(data["format"], "pantalytics-blueprint")
        self.assertIn("t_act_a", [item["code"] for item in data["activities"]])

        counts = self._counts()
        self.assertTrue(self._import_file(content))
        self.assertEqual(self._counts(), counts, "Re-importing an export must create nothing.")

    def test_import_file_reports_and_opens_the_map(self):
        wizard = self.Wizard.create(
            {"file": base64.b64encode(json.dumps(self._minimal()).encode()), "filename": "minimal.json"}
        )
        action = wizard.action_import()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")
        self.assertIn("Created", action["params"]["message"])
        self.assertEqual(
            action["params"]["next"]["id"], self.env.ref("pan_self_learning_blueprint.action_blueprint_map").id
        )
        self.assertEqual(self.Activity.search_count([("code", "=", "t_bp_act")]), 1)

    def test_import_file_requires_file(self):
        with self.assertRaises(UserError):
            self.Wizard.create({}).action_import()

    def test_import_file_invalid_json(self):
        with self.assertRaises(UserError) as caught:
            self._import_file(b"{not json", filename="broken.json")
        self.assertIn("broken.json", str(caught.exception))

    def test_import_file_size_limit(self):
        """D8: a file above MAX_FILE_BYTES is refused before it is parsed."""
        self.assertEqual(MAX_FILE_BYTES, 5 * 1024 * 1024)
        data = self._minimal()
        data["padding"] = "x" * MAX_FILE_BYTES
        with self.assertRaises(UserError) as caught:
            self._import_file(json.dumps(data).encode(), filename="big.json")
        self.assertIn("5 MB", str(caught.exception))
        self.assertFalse(self.Chain.search_count([("code", "=", "t_bp_chain")]))
