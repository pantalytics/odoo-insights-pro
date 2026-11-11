from datetime import datetime, time, timedelta

from lxml import html as lxml_html

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import html2plaintext

from .ir_ui_view import MAP_VIEW_TYPE
from .project_task import USER_GROUP
from .structure import CANCELLED_STATE, TESTED_RUNG, TRAINED_RUNG

def _keywords(text, limit=3):
    """"a, b , c, d" -> ["a", "b", "c"]: the first few non-empty keywords."""
    return [word.strip() for word in (text or "").split(",") if word.strip()][:limit]


# The burn-up (round 6): one point per week, a task's progress is its step out of five.
BURNUP_WEEK = timedelta(days=7)
MAX_RUNG = 5

# Block elements whose text counts as one line of a description.
_LINE_TAGS = ("li", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre")


class ProjectProject(models.Model):
    """A project is a company map: its roles are the lanes, the shared phases
    the columns, its parent tasks the flows and its other tasks the chips."""

    _inherit = "project.project"

    pan_role_ids = fields.One2many(
        "pan.sl.role",
        "project_id",
        string="Map roles",
        groups=USER_GROUP,
        help="The roles (map rows) of this project. A project with roles has a map.",
    )
    # Level 0 of the map (round 5): the company in one page and where the
    # programme goes from and to; its start and target are the project's
    # own date_start and date.
    pan_brief = fields.Html(
        string="Company in one page",
        sanitize=True,
        groups=USER_GROUP,
        help="What the company does, its people, what it sells and how, its customers and suppliers. Shown on top of the map.",
    )
    pan_keywords = fields.Char(
        string="Keywords",
        groups=USER_GROUP,
        help="What the company is about in a few words, separated by commas, shown with the company on the map.",
    )
    pan_from_systems = fields.Char(
        string="From systems",
        groups=USER_GROUP,
        help="The systems the company leaves, e.g. BEMET/PDC-Win, Excel.",
    )
    pan_to_systems = fields.Char(
        string="To systems",
        groups=USER_GROUP,
        help="The systems the company moves to, e.g. Odoo 19, UNS.",
    )

    def _pan_has_stage_ladder(self):
        """True when no two stages of the project share a progress step, as
        with the six template stages. Only then may a flow's stage follow its
        tasks; a shared workflow (Icebox, Backlog, Estimated all at Open) is
        left alone."""
        self.ensure_one()
        rungs = self.env["project.task.type"].sudo().search([("project_ids", "in", self.id)]).mapped("pan_rung")
        return len(rungs) == len(set(rungs))

    @api.model
    def get_blueprint_map_projects(self):
        """The projects with a map (at least one role) the user can read, by name."""
        projects = self.search([("pan_role_ids", "!=", False)], order="name, id")
        return [{"id": project.id, "name": project.name} for project in projects]

    def action_open_blueprint_map(self):
        """Open the project's tasks in the Map view (the map is a view type
        on project.task since 2.3, so the standard search bar works on it).
        All tasks, not only the open ones: the map shows progress up to Live."""
        self.ensure_one()
        action = self.action_view_tasks()
        views = action["views"]
        map_views = [view for view in views if view[1] == MAP_VIEW_TYPE] or [(False, MAP_VIEW_TYPE)]
        action["views"] = map_views + [view for view in views if view[1] != MAP_VIEW_TYPE]
        action["context"] = {key: value for key, value in action["context"].items() if key != "search_default_open_tasks"}
        action["mobile_view_mode"] = MAP_VIEW_TYPE  # phones open the map too, not the kanban
        return action

    def action_view_tasks(self):
        """The Map view sits in the view switcher of a project with a map, for
        Blueprint users; other projects and users do not see it."""
        action = super().action_view_tasks()
        if not (self.env.user.has_group(USER_GROUP) and self.sudo().pan_role_ids):
            action["views"] = [view for view in action["views"] if view[1] != MAP_VIEW_TYPE]
        return action

    # ------------------------------------------------------------------
    # Map data (contract: docs/data-model.md)
    # ------------------------------------------------------------------

    def get_blueprint_map_data(self, domain=None, order=None):
        """Everything the map (and an agent) needs for this project, in one call.

        ``domain`` (optional, a task domain such as the map view's search)
        restricts the listed tasks; a flow keeps its progress and open count
        over all its tasks but lists only matching ones, and a flow without a
        matching task is left out. ``order`` (optional) orders ``tasks`` (the
        chips within a cell); a flow's ``task_ids`` always follow sequence.

        Records are read as recordsets, so related values are fetched in
        batches and the query count does not grow with the number of tasks.
        """
        self.ensure_one()
        phases = self.env["pan.sl.phase"].search([])
        roles = self.pan_role_ids.sorted()
        base = [("project_id", "=", self.id), ("state", "!=", CANCELLED_STATE)]
        tasks = self.env["project.task"].search(base, order="sequence, id")
        flows = tasks.filtered("child_ids")
        if domain:
            matching = self.env["project.task"].search(Domain.AND([base, domain]), order=order or "sequence, id")
        elif order:
            matching = self.env["project.task"].search(base, order=order)
        else:
            matching = tasks
        work = matching - flows
        flow_tasks, open_counts, training, rung_sums = {}, {}, {}, {}
        for task in tasks - flows:
            if task.parent_id in flows:
                rung = int(task.pan_rung or 0)
                open_counts[task.parent_id.id] = open_counts.get(task.parent_id.id, 0) + (rung < TESTED_RUNG)
                total, count = rung_sums.get(task.parent_id.id, (0, 0))
                rung_sums[task.parent_id.id] = (total + rung, count + 1)
        for task in work.sorted(lambda task: (task.sequence, task.id)):
            rung = int(task.pan_rung or 0)
            if task.parent_id in flows:
                flow_tasks.setdefault(task.parent_id.id, []).append(task.id)
            if task.pan_role_id and rung < TRAINED_RUNG:
                training.setdefault(task.pan_role_id.id, []).append(task.id)
        if domain:
            flows = flows.filtered(lambda flow: flow.id in flow_tasks)

        # One search for all roles; only a band word per role, never a score.
        adkar_bands = roles._get_adkar_bands()
        today = fields.Date.context_today(self)
        flow_rows = []
        for flow in flows:
            deadline = flow.date_deadline and fields.Datetime.context_timestamp(self, flow.date_deadline).date()
            late = bool(deadline and deadline < today and flow.pan_flow_progress < 100)
            flow_rows.append(
                {
                    "id": flow.id,
                    "name": flow.name,
                    "summary": flow.pan_summary or self._blueprint_first_line(flow.description),
                    "keywords": _keywords(flow.pan_keywords),
                    "progress": flow.pan_flow_progress,
                    "deadline": deadline and deadline.isoformat(),
                    "late": late,
                    "days_late": (today - deadline).days if late else 0,
                    "open_count": open_counts.get(flow.id, 0),
                    "mean_rung": round(rung_sums[flow.id][0] / rung_sums[flow.id][1], 2) if flow.id in rung_sums else 0.0,
                    "task_ids": flow_tasks.get(flow.id, []),
                }
            )
        # Worst first (round 5): lowest mean step over its tasks (work runs in
        # parallel and goes back and forth, so every step counts, not only
        # Tested), late before on time, more open tasks first; ``tasks`` is
        # already in sequence order and the sort is stable, so sequence breaks
        # the last tie.
        flow_rows.sort(key=lambda row: (row["mean_rung"], not row["late"], -row["open_count"]))

        milestones = self.env["project.milestone"].search(
            [("project_id", "=", self.id)], order="deadline asc nulls last, id"
        )
        burnup = self._blueprint_burnup(work, tasks - flows, today)
        return {
            "project": {
                "id": self.id,
                "name": self.name,
                "brief": self.pan_brief or False,
                "keywords": _keywords(self.pan_keywords),
                "from_systems": self.pan_from_systems or False,
                "to_systems": self.pan_to_systems or False,
                "date_start": self.date_start and self.date_start.isoformat(),
                "date_end": self.date and self.date.isoformat(),
            },
            "milestones": [
                {
                    "id": milestone.id,
                    "name": milestone.name,
                    "deadline": milestone.deadline and milestone.deadline.isoformat(),
                    "reached": milestone.is_reached,
                }
                for milestone in milestones
            ],
            "phases": [{"id": phase.id, "code": phase.code, "name": phase.name} for phase in phases],
            "roles": [
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "is_external": role.is_external,
                    "people": role.partner_ids.mapped("name"),
                    "adkar": adkar_bands[role.id],
                    "open_training_task_ids": training.get(role.id, []),
                }
                for role in roles
            ],
            "flows": flow_rows,
            "tasks": [
                {
                    "id": task.id,
                    "name": task.name,
                    "role_id": task.pan_role_id.id,
                    "phase_id": task.pan_phase_id.id,
                    "flow_id": task.parent_id.id if task.parent_id in flows else False,
                    "stage": task.stage_id.name or False,
                    "rung": int(task.pan_rung or 0),
                    "user_names": task.user_ids.mapped("name"),
                    "planned_hours": task.allocated_hours,
                    "spent_hours": task.effective_hours,
                    "summary": task.pan_summary or False,
                    "keywords": _keywords(task.pan_keywords),
                    "apps": [
                        {"name": app.name, "label": app.shortdesc} for app in task.pan_app_ids.sorted("shortdesc")
                    ],
                }
                for task in work
            ],
            **burnup,
        }

    # ------------------------------------------------------------------
    # Burn-up (round 6): progress over time against a straight ideal line
    # ------------------------------------------------------------------

    def _blueprint_burnup(self, work, all_work, today):
        """``progress_history``, ``ideal``, ``verdict`` and ``weeks_behind``
        for the tasks ``work`` (the map's search, flows and cancelled tasks
        already left out).

        The programme runs from the project's start (else the first create
        date of its tasks, ``all_work``, so a search does not move the axis)
        to its target date. Each weekly point, and a last one today, is the
        mean over ``work`` of (step at that date / 5). A task's step at a date
        is its stage's ``pan_rung`` then, rebuilt from the stage tracking: the
        new stage of the last change on or before that date, else the old
        stage of the first change after it, else (no tracking) the current
        stage. A task created after the date counts as Open (0) there, so the
        number of tasks is the same at every point and adding tasks never
        makes the line jump. Without a target date, a start or tasks: no chart
        (empty history, ``ideal`` and ``verdict`` false).
        """
        none = {"progress_history": [], "ideal": False, "verdict": False, "weeks_behind": 0}
        start = self.date_start or (all_work and min(all_work.mapped("create_date")).date())
        end = self.date
        if not (start and end and work):
            return none
        span = max(1, (end - start).days)

        # One search over the stage tracking of all tasks, oldest first. Only
        # administrators may read tracking values; the tasks are the user's.
        stage_field = self.env["ir.model.fields"]._get("project.task", "stage_id")
        trackings = (
            self.env["mail.tracking.value"]
            .sudo()
            .search(
                [
                    ("field_id", "=", stage_field.id),
                    ("mail_message_id.model", "=", "project.task"),
                    ("mail_message_id.res_id", "in", work.ids),
                ],
                order="create_date, id",
            )
        )
        changes = {}
        for tracking in trackings:
            changes.setdefault(tracking.mail_message_id.res_id, []).append(
                (tracking.create_date, tracking.old_value_integer, tracking.new_value_integer)
            )
        stage_ids = {stage_id for events in changes.values() for _when, old, new in events for stage_id in (old, new)}
        rungs = {
            stage.id: int(stage.pan_rung or 0)
            for stage in self.env["project.task.type"].sudo().browse(stage_ids - {0}).exists()
        }
        rows = [
            (task.create_date, changes.get(task.id), int(task.pan_rung or 0)) for task in work
        ]

        def value_at(day):
            """Mean step / 5 at the end of ``day`` (UTC), 0..1."""
            bound = datetime.combine(day + timedelta(days=1), time.min)
            total = 0
            for created, events, current in rows:
                if created and created >= bound:
                    continue  # not there yet: Open
                if not events:
                    total += current
                    continue
                stage_id = None
                for when, old, new in events:
                    if when >= bound:
                        stage_id = old if stage_id is None else stage_id
                        break
                    stage_id = new
                total += rungs.get(stage_id, 0)
            return round(total / (MAX_RUNG * len(rows)), 3)

        days = []
        day = start
        while day <= today:
            days.append(day)
            day += BURNUP_WEEK
        if days and days[-1] != today:
            days.append(today)
        history = [{"date": day.isoformat(), "value": value_at(day)} for day in days]
        latest = history[-1]["value"] if history else value_at(today)
        elapsed = (today - start).days
        ideal_today = min(1.0, max(0.0, elapsed / span))
        if latest >= ideal_today:
            verdict, weeks_behind = "on_track", 0
        else:
            # The ideal line was at the current value on start + latest * span.
            verdict, weeks_behind = "behind", max(1, round((elapsed - latest * span) / 7))
        return {
            "progress_history": history,
            "ideal": [{"date": start.isoformat(), "value": 0.0}, {"date": end.isoformat(), "value": 1.0}],
            "verdict": verdict,
            "weeks_behind": weeks_behind,
        }

    def action_blueprint_training(self):
        """Still to train: the project's tasks of internal roles below Trained,
        grouped by role (groups open), with the role's people. The condition is
        the search filter "Still to train", so it shows in the search bar."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Still to train"),
            "res_model": "project.task",
            "view_mode": "list,form",
            "views": [(self.env.ref("pan_self_learning_blueprint.view_task_list_training").id, "list"), (False, "form")],
            "domain": [("project_id", "=", self.id)],
            "context": {
                "search_default_pan_still_to_train": 1,
                "search_default_pan_groupby_role": 1,
                "default_project_id": self.id,
            },
        }

    def _blueprint_first_line(self, html):
        """First line of an HTML description as plain text, ``False`` when empty."""
        if not html or not html2plaintext(html).strip():
            return False
        root = lxml_html.fragment_fromstring(str(html), create_parent="div")
        for element in root.iter(*_LINE_TAGS):
            if element is root:
                continue
            # Skip wrappers whose text lives in nested blocks (e.g. a div around a list).
            if any(child.tag in _LINE_TAGS + ("ol", "ul") for child in element):
                continue
            text = " ".join(element.text_content().split())
            if text:
                return text
        for line in html2plaintext(html).splitlines():
            if line.strip():
                return line.strip()
        return False

    # ------------------------------------------------------------------
    # Blueprint buttons (managers, project form header)
    # ------------------------------------------------------------------

    def action_blueprint_load_template(self):
        """Fill this project from the bundled template, then open its map."""
        self.ensure_one()
        Blueprint = self.env["pan.sl.blueprint"]
        summary = Blueprint.import_blueprint(self, Blueprint._read_template(), fill_empty_only=True)
        return Blueprint._notify_and_open_map(self.env._("Template loaded"), summary, self)

    def action_blueprint_import(self):
        """Open the small dialog to import a blueprint file into this project."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Import blueprint"),
            "res_model": "pan.sl.blueprint.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_blueprint_export(self):
        """Download this project as blueprint.json."""
        self.ensure_one()
        return self.env["pan.sl.blueprint"]._download(self)
