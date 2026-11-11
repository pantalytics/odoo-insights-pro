"""19.0.2.2.0: a flow's stage follows its subtasks (fix 1 of the 2.2 round,
docs/ux-test-2026-11-11.md). The roll-up runs when a subtask changes; this puts
the existing flows of projects with a map in their stage once, so the kanban
and the map agree right after the update."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    flows = (
        env["project.task"]
        .with_context(active_test=False)
        .search([("child_ids", "!=", False), ("project_id.pan_role_ids", "!=", False)])
    )
    flows._pan_rollup_flow_stage()
    _logger.info("[Blueprint] 19.0.2.2.0: %s flows now follow the stage of their subtasks.", len(flows))
