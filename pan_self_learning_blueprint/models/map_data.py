from lxml import html as lxml_html

from odoo import api, models
from odoo.tools import html2plaintext

from .structure import CANCELLED_STATE

# Block elements whose text counts as one line of a click path.
_CLICK_PATH_LINE_TAGS = ("li", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre")


class PanSlActivity(models.Model):
    _inherit = "pan.sl.activity"

    @api.model
    def get_map_data(self):
        """Everything the company map needs, in one call.

        Returns a dict with ``phases`` (map columns, each with its ``apps`` as
        ``{name, installed}``), ``roles`` (map lanes, with the names of their
        people as ``users`` and the ADKAR band "low", "medium", "high" or
        False as ``adkar``), ``activities`` (chips) and ``scenarios`` (routes,
        with their ``progress`` in percent). Records are read as recordsets so
        related and computed values are fetched in batches (prefetching),
        never one query per activity.
        """
        phases = self.env["pan.sl.phase"].search([])
        roles = self.env["pan.sl.role"].search([])
        activities = self.search([])
        scenarios = self.env["pan.sl.scenario"].search([])

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        app_labels = {phase.id: self._map_split_app_labels(phase.app_labels) for phase in phases}
        installed_apps = self._map_installed_apps(
            {label for labels in app_labels.values() for label in labels}
        )

        return {
            "phases": [
                {
                    "id": phase.id,
                    "name": phase.name,
                    "code": phase.code,
                    "apps": [
                        {"name": label, "installed": label in installed_apps}
                        for label in app_labels[phase.id]
                    ],
                }
                for phase in phases
            ],
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "is_external": role.is_external,
                    "users": role.partner_ids.mapped("name"),
                    "adkar": adkar_bands[role.id],
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
                    "model": activity.model_name or False,
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
                    "progress": round(scenario.progress),
                    "activity_ids": scenario.activity_ids.ids,
                }
                for scenario in scenarios
            ],
        }

    @api.model
    def _map_installed_apps(self, labels):
        """The app labels that match the English name of an installed app."""
        if not labels:
            return set()
        # ir.module.module is technical metadata; reading it exposes no business data.
        modules = (
            self.env["ir.module.module"]
            .sudo()
            .with_context(lang="en_US")
            .search(
                [("shortdesc", "in", list(labels)), ("application", "=", True), ("state", "=", "installed")]
            )
        )
        return set(modules.mapped("shortdesc"))

    @api.model
    def _map_split_app_labels(self, app_labels):
        """Turn the comma separated ``app_labels`` of a phase into a list of names."""
        if not app_labels:
            return []
        return [label.strip() for label in app_labels.split(",") if label.strip()]

    @api.model
    def get_map_details(self):
        """Detail level of the company map (zoom stop "Detail"), in one call.

        Kept apart from :meth:`get_map_data` so that contract stays as it is.
        Returns a list with one dict per activity: ``id``, ``tasks`` (linked
        project tasks as ``{id, name, rung}``, ``rung`` an int 0-5, cancelled
        tasks left out like in the activity rung) and
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
        tasks = self.env["project.task"].search(
            [("pan_activity_ids", "in", activities.ids), ("state", "!=", CANCELLED_STATE)]
        )
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
