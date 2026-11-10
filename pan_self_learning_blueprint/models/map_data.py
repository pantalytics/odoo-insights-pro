from odoo import api, models


class PanSlActivity(models.Model):
    _inherit = "pan.sl.activity"

    @api.model
    def get_map_data(self):
        """Everything the company map needs, in one call.

        Returns a dict with ``phases`` (map columns), ``roles`` (map lanes),
        ``activities`` (chips) and ``scenarios`` (routes). Records are read
        as recordsets so related and computed values are fetched in batches
        (prefetching), never one query per activity.
        """
        phases = self.env["pan.sl.phase"].search([])
        roles = self.env["pan.sl.role"].search([])
        activities = self.search([])
        scenarios = self.env["pan.sl.scenario"].search([])

        # Batch variant of role._get_adkar_profile(): one search for all roles.
        profiles = roles._get_adkar_profiles()

        return {
            "phases": [
                {
                    "id": phase.id,
                    "name": phase.name,
                    "code": phase.code,
                    "apps": self._map_split_app_labels(phase.app_labels),
                }
                for phase in phases
            ],
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "is_external": role.is_external,
                    "users": role.user_ids.mapped("name"),
                    "adkar": profiles[role.id],
                }
                for role in roles
            ],
            "activities": [
                {
                    "id": activity.id,
                    "name": activity.name,
                    "code": activity.code,
                    "role_id": activity.role_id.id,
                    "phase_id": activity.phase_id.id,
                    "choice_state": activity.choice_state,
                    "rung": activity.rung,
                    "open_point": activity.open_point or False,
                    "scenario_ids": activity.scenario_ids.ids,
                    "model": activity.model_id.model or False,
                }
                for activity in activities
            ],
            "scenarios": [
                {
                    "id": scenario.id,
                    "code": scenario.code,
                    "name": scenario.name,
                    "description": scenario.description or False,
                    "open_point": scenario.open_point or False,
                    "rung": scenario.rung,
                    "activity_ids": scenario.activity_ids.ids,
                }
                for scenario in scenarios
            ],
        }

    @api.model
    def _map_split_app_labels(self, app_labels):
        """Turn the comma separated ``app_labels`` of a phase into a list of chips."""
        if not app_labels:
            return []
        return [label.strip() for label in app_labels.split(",") if label.strip()]
