"""The 19.0.1.2.0 migration: people move from users to contacts (D4), default data loses its XML ids (D7),
and the tables of removed many2many fields are dropped (E9).

The scripts are run on a cursor prepared like a 19.0.1.1.0 database: an ADKAR
score with only ``user_id``, the old role-user table and the tables of the
removed ``role.group_ids`` and ``phase.model_ids``, each with its
``ir_model_relation`` record. DDL is transactional in PostgreSQL, so the test
transaction rolls the prepared state back.
"""

import importlib.util

from odoo.tests import new_test_user, tagged
from odoo.tools import file_path, sql

from .common import BlueprintCase

MODULE = "pan_self_learning_blueprint"
# Relation tables of removed many2many fields: (table, model, column 1, column 2).
OLD_RELATIONS = (
    ("pan_sl_role_res_users_rel", "pan.sl.role", "role_id", "user_id"),
    ("pan_sl_role_res_groups_rel", "pan.sl.role", "role_id", "group_id"),
    ("ir_model_pan_sl_phase_rel", "pan.sl.phase", "pan_sl_phase_id", "ir_model_id"),
)


def _load(name):
    path = file_path(f"{MODULE}/migrations/19.0.1.2.0/{name}.py")
    spec = importlib.util.spec_from_file_location(f"pan_sl_migration_{name.replace('-', '_')}", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


@tagged("post_install", "-at_install")
class TestMigration(BlueprintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pre = _load("pre-migrate")
        cls.post = _load("post-migrate")
        cls.old_user = new_test_user(cls.env, login="pan_sl_migration_user", name="Migrated person")

    def _prepare_old_state(self):
        """Put the 19.0.1.1.0 layout back: scores keyed on user_id, roles linked to users."""
        cr = self.env.cr
        score = self.env["pan.sl.adkar.score"].create(
            dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 3)
            | {"partner_id": self.old_user.partner_id.id}
        )
        self.env.flush_all()
        cr.execute("ALTER TABLE pan_sl_adkar_score ALTER COLUMN partner_id DROP NOT NULL")
        cr.execute("ALTER TABLE pan_sl_adkar_score ADD COLUMN IF NOT EXISTS user_id INTEGER")
        cr.execute(
            "UPDATE pan_sl_adkar_score SET user_id = %s, partner_id = NULL WHERE id = %s",
            (self.old_user.id, score.id),
        )
        cr.execute("DELETE FROM pan_sl_role_res_partner_rel WHERE role_id = %s", (self.role_sales.id,))
        module_id = self.env["ir.module.module"].search([("name", "=", MODULE)]).id
        for table, model, column1, column2 in OLD_RELATIONS:
            cr.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS %s (%s INTEGER NOT NULL, %s INTEGER NOT NULL, PRIMARY KEY (%s, %s))",
                    sql.SQL.identifier(table),
                    sql.SQL.identifier(column1),
                    sql.SQL.identifier(column2),
                    sql.SQL.identifier(column1),
                    sql.SQL.identifier(column2),
                )
            )
            cr.execute(
                """
                INSERT INTO ir_model_relation (name, model, module, create_date, write_date)
                VALUES (%s, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC')
                """,
                (table, self.env["ir.model"]._get_id(model), module_id),
            )
        cr.execute(
            "INSERT INTO pan_sl_role_res_users_rel (role_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (self.role_sales.id, self.old_user.id),
        )
        self.env["ir.model.data"].create(
            [
                {"module": MODULE, "name": "t_chain_lead_to_cash", "model": "pan.sl.chain", "res_id": self.chain.id},
                {"module": MODULE, "name": "t_phase_quotation", "model": "pan.sl.phase", "res_id": self.phase_a.id},
            ]
        )
        self.env.flush_all()
        self.env.invalidate_all()
        return score

    def test_fresh_install_does_nothing(self):
        score = self._prepare_old_state()
        self.pre.migrate(self.env.cr, None)
        self.post.migrate(self.env.cr, None)
        self.env.cr.execute("SELECT partner_id FROM pan_sl_adkar_score WHERE id = %s", (score.id,))
        self.assertIsNone(self.env.cr.fetchone()[0])
        for table, *_columns in OLD_RELATIONS:
            self.assertTrue(sql.table_exists(self.env.cr, table))

    def test_upgrade_moves_people_to_contacts(self):
        score = self._prepare_old_state()
        cr = self.env.cr
        partner = self.old_user.partner_id

        self.pre.migrate(cr, "19.0.1.1.0")
        cr.execute("SELECT partner_id FROM pan_sl_adkar_score WHERE id = %s", (score.id,))
        self.assertEqual(cr.fetchone()[0], partner.id, "The score moves to the user's contact.")
        cr.execute("SELECT partner_id FROM pan_sl_role_res_partner_rel WHERE role_id = %s", (self.role_sales.id,))
        self.assertEqual([row[0] for row in cr.fetchall()], [partner.id], "The role member moves to the contact.")
        self.assertFalse(
            self.env["ir.model.data"].search(
                [("module", "=", MODULE), ("model", "in", ("pan.sl.chain", "pan.sl.phase"))]
            ),
            "Default chains and phases lose their XML ids.",
        )
        self.assertTrue(self.chain.exists())
        self.assertTrue(self.phase_a.exists())

        self.post.migrate(cr, "19.0.1.1.0")
        self.assertFalse(sql.column_exists(cr, "pan_sl_adkar_score", "user_id"))
        self._assert_old_relations_gone()

        self.env.invalidate_all()
        self.assertEqual(score.partner_id, partner)
        self.assertEqual(self.role_sales.partner_ids, partner)
        self.assertIn(self.role_sales, score.role_ids)

    def test_upgrade_is_safe_to_run_twice(self):
        """A rerun (an interrupted upgrade) finds the new layout and changes nothing."""
        score = self._prepare_old_state()
        cr = self.env.cr
        for _attempt in range(2):
            self.pre.migrate(cr, "19.0.1.1.0")
            self.post.migrate(cr, "19.0.1.1.0")
        self._assert_old_relations_gone()
        self.env.invalidate_all()
        self.assertEqual(score.partner_id, self.old_user.partner_id)
        self.assertEqual(self.role_sales.partner_ids, self.old_user.partner_id)

    def test_orphan_relation_tables_are_dropped(self):
        """E9: the tables of removed role.group_ids and phase.model_ids go, with their relation records."""
        self._prepare_old_state()
        cr = self.env.cr
        self.pre.migrate(cr, "19.0.1.1.0")
        self.assertTrue(sql.table_exists(cr, "pan_sl_role_res_groups_rel"), "The pre-migration leaves them.")
        self.post.migrate(cr, "19.0.1.1.0")
        self._assert_old_relations_gone()
        self.assertTrue(
            sql.table_exists(cr, "pan_sl_role_res_partner_rel"), "The table of the live role.partner_ids stays."
        )

    def _assert_old_relations_gone(self):
        cr = self.env.cr
        for table, *_columns in OLD_RELATIONS:
            with self.subTest(table=table):
                self.assertFalse(sql.table_exists(cr, table), f"{table} must be dropped.")
        cr.execute("SELECT name FROM ir_model_relation WHERE name IN %s", (tuple(row[0] for row in OLD_RELATIONS),))
        self.assertFalse(cr.fetchall(), "No relation record of a dropped table may stay.")
