"""19.0.2.1.0: progress is the stage (decision 4 of docs/ux-test-2026-11-11.md).

``project.task.pan_rung`` becomes the stage's progress (a stored related
field). Its column is dropped, so Odoo creates it again and fills it from the
stages: every existing stage starts at Open, so every task does. The old
per-task values are lost on purpose; production held them only on demo and
template data (checked 11-11). The phase's Odoo apps are gone (no app chips
on the map any more), so their column goes too.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("ALTER TABLE project_task DROP COLUMN IF EXISTS pan_rung")
    cr.execute("ALTER TABLE pan_sl_phase DROP COLUMN IF EXISTS app_labels")
    _logger.info("[Blueprint] 19.0.2.1.0: task progress now follows the stage; old per-task values dropped.")
