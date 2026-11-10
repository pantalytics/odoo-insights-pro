from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestStructureActivity(BlueprintCase):
    """Codes are unique per model and the contract's required fields are enforced."""

    def _assert_db_refuses(self, model, vals):
        """Creating ``vals`` must fail, either in the ORM (ValidationError) or in the database."""
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                self.env[model].create(vals)
                self.env.flush_all()
        except (IntegrityError, ValidationError):
            self.env.invalidate_all()
            return
        self.fail(f"{model} accepted invalid values {vals!r}")

    def test_chain_code_unique(self):
        self._assert_db_refuses("pan.sl.chain", {"name": "Duplicate", "code": "t_chain"})

    def test_phase_code_unique(self):
        self._assert_db_refuses("pan.sl.phase", {"name": "Duplicate", "code": "t_phase_a"})

    def test_role_code_unique(self):
        self._assert_db_refuses("pan.sl.role", {"name": "Duplicate", "code": "t_sales"})

    def test_process_code_unique(self):
        self._assert_db_refuses(
            "pan.sl.process", {"name": "Duplicate", "code": "t_process", "chain_id": self.chain.id}
        )

    def test_activity_code_unique(self):
        self._assert_db_refuses(
            "pan.sl.activity",
            {
                "name": "Duplicate",
                "code": "t_act_a",
                "process_id": self.process.id,
                "role_id": self.role_sales.id,
                "phase_id": self.phase_a.id,
            },
        )

    def test_scenario_code_unique(self):
        self._make_scenario("t_scen_unique", [])
        self._assert_db_refuses("pan.sl.scenario", {"name": "Duplicate", "code": "t_scen_unique"})

    def test_same_code_allowed_across_models(self):
        """Uniqueness is per model: a role may share a code with a chain."""
        role = self.Role.create({"name": "Same code as the chain", "code": "t_chain"})
        self.assertEqual(role.code, self.chain.code)

    def test_activity_required_fields(self):
        base = {
            "name": "Incomplete",
            "process_id": self.process.id,
            "role_id": self.role_sales.id,
            "phase_id": self.phase_a.id,
        }
        for index, missing in enumerate(("name", "process_id", "role_id", "phase_id")):
            with self.subTest(missing=missing):
                vals = dict(base, code=f"t_incomplete_{index}")
                del vals[missing]
                self._assert_db_refuses("pan.sl.activity", vals)

    def test_structure_required_fields(self):
        cases = [
            ("pan.sl.chain", {"name": "No code"}),
            ("pan.sl.chain", {"code": "t_no_name_chain"}),
            ("pan.sl.phase", {"code": "t_no_name_phase"}),
            ("pan.sl.role", {"code": "t_no_name_role"}),
            ("pan.sl.process", {"name": "No chain", "code": "t_no_chain"}),
        ]
        for model, vals in cases:
            with self.subTest(model=model, vals=vals):
                self._assert_db_refuses(model, vals)

    def test_activity_defaults_and_related_chain(self):
        self.assertEqual(self.act_a.choice_state, "proposal")
        self.assertEqual(self.act_a.chain_id, self.chain)

    def test_choice_state_values(self):
        states = [value for value, _label in self.Activity._fields["choice_state"].selection]
        self.assertEqual(states, ["proposal", "provisional", "fixed", "revised"])

    def test_one2many_inverses(self):
        self.assertIn(self.process, self.chain.process_ids)
        self.assertEqual(self.process.activity_ids, self.act_a | self.act_b | self.act_c)
        self.assertEqual(self.role_sales.activity_ids, self.act_a | self.act_b)
        self.assertEqual(self.phase_b.activity_ids, self.act_b | self.act_c)

    def test_order_by_sequence(self):
        late = self.Chain.create({"name": "Late chain", "code": "t_chain_late", "sequence": 1000})
        early = self.Chain.create({"name": "Early chain", "code": "t_chain_early", "sequence": -1000})
        chains = self.Chain.search([("code", "in", ["t_chain", "t_chain_late", "t_chain_early"])])
        self.assertEqual(chains.ids, [early.id, self.chain.id, late.id])

    def test_activity_has_chatter(self):
        self.assertIn("message_ids", self.Activity._fields)
        # The activity was created in this transaction; Odoo skips tracking for
        # records it is still creating, so finish creation first, like in real use.
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.act_a.choice_state = "fixed"
        self.env.flush_all()
        self.env.cr.precommit.run()  # tracking values are written at precommit
        tracked = self.act_a.message_ids.tracking_value_ids.filtered(
            lambda value: value.field_id.name == "choice_state"
        )
        self.assertTrue(tracked, "Changing the choice state must be tracked in the chatter.")

    def test_code_with_spaces_refused(self):
        """Process, activity and scenario use the structure mixin: no empty codes, no spaces."""
        cases = {
            "pan.sl.process": {"name": "Spaced", "chain_id": self.chain.id},
            "pan.sl.activity": {
                "name": "Spaced",
                "process_id": self.process.id,
                "role_id": self.role_sales.id,
                "phase_id": self.phase_a.id,
            },
            "pan.sl.scenario": {"name": "Spaced"},
            "pan.sl.chain": {"name": "Spaced"},
        }
        for model, vals in cases.items():
            for code in ("t has space", " t_leading", "t_trailing ", "   "):
                with self.subTest(model=model, code=code):
                    with self.assertRaises(ValidationError):
                        self.env[model].create(dict(vals, code=code))

    def test_code_rename_with_space_refused(self):
        with self.assertRaises(ValidationError):
            self.act_a.code = "t act a"

    def test_process_activity_count_and_action(self):
        self.assertEqual(self.process.activity_count, 3)
        action = self.process.action_view_activities()
        self.assertEqual(action["res_model"], "pan.sl.activity")
        self.assertEqual(self.Activity.search(action["domain"]), self.act_a | self.act_b | self.act_c)
        self.assertEqual(action["context"], {"default_process_id": self.process.id})
