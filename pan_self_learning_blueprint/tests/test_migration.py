"""The 19.0.2.0.0 pre-migration: old tables and shared roles go, the rest stays.

The script runs on a cursor prepared like a 1.2 database. DDL is
transactional in PostgreSQL, so the test transaction rolls it back.
"""

import importlib.util

from odoo.tests import tagged
from odoo.tools import file_path, sql

from .common import BlueprintCase


def _load():
    path = file_path("pan_self_learning_blueprint/migrations/19.0.2.0.0/pre-migrate.py")
    spec = importlib.util.spec_from_file_location("pan_sl_migration_2_0", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


@tagged("post_install", "-at_install")
class TestMigration(BlueprintCase):
    def test_pre_migration(self):
        cr = self.env.cr
        cr.execute("CREATE TABLE pan_sl_activity (id SERIAL PRIMARY KEY, name VARCHAR)")
        cr.execute("INSERT INTO pan_sl_activity (name) VALUES ('Old activity')")
        cr.execute(
            "CREATE TABLE pan_sl_activity_project_task_rel ("
            "activity_id INTEGER REFERENCES pan_sl_activity ON DELETE CASCADE, task_id INTEGER)"
        )
        cr.execute("ALTER TABLE project_task ADD COLUMN pan_scenario_id INTEGER")
        score = self.env["pan.sl.adkar.score"].create(
            dict.fromkeys(("awareness", "desire", "knowledge", "ability", "reinforcement"), 3)
            | {"partner_id": self.env.user.partner_id.id}
        )
        self.env.flush_all()

        script = _load()
        script.migrate(cr, None)
        self.assertTrue(sql.table_exists(cr, "pan_sl_activity"), "A fresh install does nothing.")
        script.migrate(cr, "19.0.1.2.0")
        script.migrate(cr, "19.0.1.2.0")  # safe to run twice
        self.env.invalidate_all()

        self.assertFalse(sql.table_exists(cr, "pan_sl_activity"))
        self.assertFalse(sql.table_exists(cr, "pan_sl_activity_project_task_rel"))
        self.assertFalse(sql.column_exists(cr, "project_task", "pan_scenario_id"))
        self.assertFalse(self.Role.search([]), "Shared roles are removed; the template brings them back per project.")
        self.assertTrue(self.phase_a.exists(), "Phases stay.")
        self.assertTrue(score.exists() and self.task_a.exists(), "Scores and tasks stay.")
