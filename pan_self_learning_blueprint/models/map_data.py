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
        """Everything the company map (and an agent) needs, in one call.

        Returns a dict with ``chains`` and ``processes`` (level 1 and 2, with
        their codes), ``phases`` (map columns, each with its Odoo ``apps`` as
        ``{name, module, installed}``), ``roles`` (map lanes, with their
        ``code``, the names of their people as ``users`` and the ADKAR band
        "low", "medium", "high" or False as ``adkar``), ``activities`` (chips,
        with process, chain, rung and hours) and ``scenarios`` (routes, with
        their ``progress`` as Tested %). Records are read as recordsets so
        related and computed values are fetched in batches (prefetching),
        never one query per activity.
        """
        chains = self.env["pan.sl.chain"].search([])
        processes = self.env["pan.sl.process"].search([])
        phases = self.env["pan.sl.phase"].search([])
        roles = self.env["pan.sl.role"].search([])
        activities = self.search([])
        scenarios = self.env["pan.sl.scenario"].search([])

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        app_values = {phase.id: self._map_split_app_labels(phase.app_labels) for phase in phases}
        modules = self._map_modules({value for values in app_values.values() for value in values})

        return {
            "chains": [
                {"id": chain.id, "code": chain.code, "name": chain.name}
                for chain in chains
            ],
            "processes": [
                {
                    "id": process.id,
                    "code": process.code,
                    "name": process.name,
                    "chain_id": process.chain_id.id,
                    "owner_role_id": process.owner_role_id.id or False,
                }
                for process in processes
            ],
            "phases": [
                {
                    "id": phase.id,
                    "name": phase.name,
                    "code": phase.code,
                    "apps": [self._map_app(value, modules) for value in app_values[phase.id]],
                }
                for phase in phases
            ],
            "roles": [
                {
                    "id": role.id,
                    "code": role.code,
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
                    "process_id": activity.process_id.id,
                    "chain_id": activity.chain_id.id,
                    "role_id": activity.role_id.id,
                    "phase_id": activity.phase_id.id,
                    "choice_state": activity.choice_state,
                    "rung": activity.rung,
                    "planned_hours": activity.planned_hours,
                    "spent_hours": activity.spent_hours,
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
    def _map_modules(self, values):
        """The modules a phase's ``app_labels`` refer to, keyed by each value.

        A value is a technical module name (``sale_management``). A value that
        is no module name is matched on the module's name (shortdesc) in
        en_US or in the user's language, so older labels such as "Sales" keep
        working. Values that match nothing are left out.
        """
        if not values:
            return {}
        # ir.module.module is technical metadata; reading it exposes no business data.
        Module = self.env["ir.module.module"].sudo()
        found = {module.name: module for module in Module.search([("name", "in", list(values))])}
        for lang in dict.fromkeys(["en_US", self.env.lang or "en_US"]):
            rest = [value for value in values if value not in found]
            if not rest:
                break
            for module in Module.with_context(lang=lang).search([("shortdesc", "in", rest)]):
                # Prefer the installed one when several modules share a name.
                current = found.get(module.shortdesc)
                if not current or (current.state != "installed" and module.state == "installed"):
                    found[module.shortdesc] = module
        return found

    @api.model
    def _map_app(self, value, modules):
        """One Odoo band chip: the module's name in the user's language."""
        module = modules.get(value)
        if not module:
            return {"name": value, "module": False, "installed": False}
        return {
            "name": module.with_context(lang=self.env.lang).shortdesc,
            "module": module.name,
            "installed": module.state == "installed",
        }

    @api.model
    def _map_split_app_labels(self, app_labels):
        """Turn the comma separated ``app_labels`` of a phase into a list of values."""
        if not app_labels:
            return []
        return [label.strip() for label in app_labels.split(",") if label.strip()]

    @api.model
    def get_map_details(self):
        """Detail level of the company map (zoom stop "Detail"), in one call.

        Kept apart from :meth:`get_map_data` so that contract stays as it is.
        Returns a list with one dict per activity: ``id``, ``tasks`` (linked
        project tasks as ``{id, name, rung}``, ``rung`` an int 0-5, cancelled
        tasks left out and archived tasks kept, like in the activity rung) and
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
        # Archived tasks count, like in the activity rung; only cancelled ones are left out.
        tasks = (
            self.env["project.task"]
            .with_context(active_test=False)
            .search([("pan_activity_ids", "in", activities.ids), ("state", "!=", CANCELLED_STATE)])
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
