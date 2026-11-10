import base64
import json

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.misc import file_open

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
        cls.phase_a.write({"model_ids": [Command.set(partner_model.ids)], "app_labels": "Contacts, Sales"})
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
            "phases": [{"code": "t_bp_phase", "name": "Phase", "models": ["res.partner"], "apps": ["Contacts"]}],
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

    def _template_key(self):
        values = self.Wizard._fields["template"].get_values(self.env)
        keys = [value for value in values if value.startswith("generic_manufacturing")]
        self.assertEqual(len(keys), 1, f"Template generic_manufacturing not offered; choices: {values}")
        return keys[0]

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
        self.assertEqual(phase["models"], ["res.partner"])
        self.assertEqual(phase["apps"], ["Contacts", "Sales"])
        role = next(item for item in data["roles"] if item["code"] == "t_customer")
        self.assertTrue(role["external"])
        scenario = next(item for item in data["scenarios"] if item["code"] == "t_route")
        step_codes = [step if isinstance(step, str) else step["activity"] for step in scenario["steps"]]
        self.assertEqual(step_codes, ["t_act_b", "t_act_a", "t_act_c"])

    def test_export_has_no_personal_data(self):
        self.role_sales.user_ids = self.env.user
        text = json.dumps(self.Blueprint.export_blueprint())
        self.assertNotIn(self.env.user.login, text)
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

    def test_unknown_phase_model_refused_in_strict_import(self):
        data = self._minimal()
        data["phases"][0]["models"] = ["res.partner", "x_pan_sl_missing.model"]
        with self.assertRaises(UserError) as caught:
            self.Blueprint.import_blueprint(data)
        self.assertIn("x_pan_sl_missing.model", str(caught.exception))

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
    # wizard
    # ------------------------------------------------------------------

    def test_template_generic_manufacturing_loads_via_wizard(self):
        with file_open(TEMPLATE_PATH, "rb") as handle:
            template = json.loads(handle.read())
        wizard = self.Wizard.create({"mode": "template", "template": self._template_key()})
        wizard.action_load_template()
        self.assertTrue(wizard.result, "The wizard must report what it loaded.")

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
        again = self.Wizard.create({"mode": "template", "template": self._template_key()})
        again.action_load_template()
        self.assertEqual(self._counts(), counts, "Loading the template twice must create nothing.")

    def test_template_codes_match_default_structure(self):
        """The template's chains and phases update the default records, they do not duplicate them."""
        chain = self.env.ref("pan_self_learning_blueprint.chain_lead_to_cash")
        phase = self.env.ref("pan_self_learning_blueprint.phase_quotation")
        chains_before = self.Chain.search_count([])
        phases_before = self.Phase.search_count([])
        self.Wizard.create({"mode": "template", "template": self._template_key()}).action_load_template()
        self.assertEqual(self.Chain.search_count([("code", "=", chain.code)]), 1)
        self.assertEqual(self.Phase.search_count([("code", "=", phase.code)]), 1)
        self.assertEqual(self.Chain.search_count([]), chains_before)
        self.assertEqual(self.Phase.search_count([]), phases_before)

    def test_wizard_template_required(self):
        wizard = self.Wizard.create({"mode": "template"})
        with self.assertRaises(UserError):
            wizard.action_load_template()

    def test_wizard_export_then_import(self):
        wizard = self.Wizard.create({"mode": "export"})
        wizard.action_export()
        self.assertTrue(wizard.file)
        data = json.loads(base64.b64decode(wizard.file))
        self.assertEqual(data["format"], "pantalytics-blueprint")
        self.assertIn("t_act_a", [item["code"] for item in data["activities"]])

        counts = self._counts()
        importer = self.Wizard.create({"mode": "import", "file": wizard.file, "filename": "blueprint.json"})
        importer.action_import()
        self.assertTrue(importer.result)
        self.assertEqual(self._counts(), counts, "Re-importing an export must create nothing.")

    def test_wizard_import_requires_file(self):
        wizard = self.Wizard.create({"mode": "import"})
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_wizard_import_invalid_json(self):
        wizard = self.Wizard.create(
            {"mode": "import", "file": base64.b64encode(b"{not json"), "filename": "broken.json"}
        )
        with self.assertRaises(UserError) as caught:
            wizard.action_import()
        self.assertIn("broken.json", str(caught.exception))
