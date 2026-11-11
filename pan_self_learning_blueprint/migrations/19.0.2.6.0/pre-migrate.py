"""19.0.2.6.0: the map uses the Project app's roles, no groups of its own.

Blueprint User becomes Project User, Blueprint Administrator becomes Project
Administrator. The update deletes the two Blueprint groups; before it does,
everyone in them (directly or through another group) gets the matching
Project group explicitly, so nobody loses access to Projects or to the map."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MAPPING = (
    ("group_blueprint_manager", "project.group_project_manager"),
    ("group_blueprint_user", "project.group_project_user"),
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for old_name, new_xmlid in MAPPING:
        old = env.ref(f"pan_self_learning_blueprint.{old_name}", raise_if_not_found=False)
        if not old:
            continue
        new = env.ref(new_xmlid)
        # Explicitly: Project User may have come only through the Blueprint group.
        users = old.all_user_ids.filtered(lambda user: not user.share) - new.user_ids
        if users:
            new.user_ids |= users
        _logger.info("%s -> %s: %s user(s) added", old_name, new_xmlid, len(users))
