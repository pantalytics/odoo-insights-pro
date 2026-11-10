from lxml import html as lxml_html

from odoo import api, models
from odoo.tools import html2plaintext

# Block elements whose text counts as one line of a click path.
_CLICK_PATH_LINE_TAGS = ("li", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre")

# From this rung on ("Trained") the users of an activity's role count as
# trained for it. The map answers "who still needs training" with this rule;
# individual ADKAR scores never reach the map.
TRAINED_RUNG = 4


class PanSlActivity(models.Model):
    _inherit = "pan.sl.activity"

    @api.model
    def get_map_data(self):
        """Everything the company map needs, in one call.

        Returns a dict with ``phases`` (map columns), ``roles`` (map lanes),
        ``activities`` (chips) and ``scenarios`` (routes). Each activity also
        carries ``training``: the users of its role as ``{id, name, trained}``,
        ``trained`` meaning the activity reached rung ``TRAINED_RUNG``. Records are read
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
                    "training": [
                        {"id": user.id, "name": user.name, "trained": activity.rung >= TRAINED_RUNG}
                        for user in activity.role_id.user_ids
                    ],
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

    @api.model
    def get_map_details(self):
        """Detail level of the company map (zoom stop "Detail"), in one call.

        Kept apart from :meth:`get_map_data` so that contract stays as it is.
        Returns a list with one dict per activity: ``id``, ``tasks`` (linked
        project tasks as ``{id, name, rung}``, ``rung`` an int 0-5) and
        ``click_path`` (first line of the click path as plain text, or
        ``False``). Tasks are read with one search for all activities.
        """
        activities = self.search([])
        details = {
            activity.id: {
                "id": activity.id,
                "tasks": [],
                "click_path": self._map_first_line(activity.click_path),
            }
            for activity in activities
        }
        tasks = self.env["project.task"].search([("pan_activity_ids", "in", activities.ids)])
        for task in tasks:
            item = {"id": task.id, "name": task.name, "rung": int(task.pan_rung)}
            for activity_id in task.pan_activity_ids.ids:
                if activity_id in details:
                    details[activity_id]["tasks"].append(item)
        return list(details.values())

    @api.model
    def _map_first_line(self, click_path):
        """First step of an HTML click path as plain text, ``False`` when empty."""
        if not click_path or not html2plaintext(click_path).strip():
            return False
        root = lxml_html.fragment_fromstring(str(click_path), create_parent="div")
        for element in root.iter(*_CLICK_PATH_LINE_TAGS):
            if element is root:
                continue
            # Skip wrappers whose text lives in nested blocks (e.g. a div around a list).
            if any(child.tag in _CLICK_PATH_LINE_TAGS + ("ol", "ul") for child in element):
                continue
            text = " ".join(element.text_content().split())
            if text:
                return text
        # Plain text without block elements: its first non-empty line.
        for line in html2plaintext(click_path).splitlines():
            line = line.strip()
            if line:
                return line
        return False
