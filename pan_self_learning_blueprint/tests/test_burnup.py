"""The burn-up of round 6 (docs/data-model.md): ``progress_history`` rebuilt
from the stage tracking, the straight ``ideal`` line and the ``verdict``."""

from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import BlueprintCase


@tagged("post_install", "-at_install")
class TestBurnup(BlueprintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env.user)
        cls.burn = cls.env["project.project"].create(
            {"name": "Burn-up project", "date_start": cls.today - timedelta(days=28), "date": cls.today + timedelta(days=28)}
        )
        Task = cls.env["project.task"]
        common = {"project_id": cls.burn.id}
        cls.burn_flow = Task.create({**common, "name": "S01 Burn flow", "stage_id": cls.stages["0"].id})
        # Moves Open -> Decided (20 days ago) -> Tested (10 days ago).
        cls.moving = Task.create({**common, "name": "Moving", "parent_id": cls.burn_flow.id, "stage_id": cls.stages["0"].id})
        # No stage history: its current stage (Built) counts at every point.
        cls.steady = Task.create({**common, "name": "Steady", "stage_id": cls.stages["2"].id})
        # Created five days ago, straight at Live: Open before that.
        cls.late_comer = Task.create({**common, "name": "Late comer", "stage_id": cls.stages["5"].id})
        # Cancelled: never counts.
        cls.cancelled = Task.create({**common, "name": "Cancelled", "stage_id": cls.stages["5"].id, "state": "1_canceled"})
        cls._backdate(cls.burn_flow | cls.moving | cls.steady | cls.cancelled, 30)
        cls._backdate(cls.late_comer, 5)
        cls._move(cls.moving, "1", 20)
        cls._move(cls.moving, "3", 10)

    @classmethod
    def _at(cls, days_ago):
        return datetime.combine(cls.today - timedelta(days=days_ago), time(12, 0))

    @classmethod
    def _backdate(cls, tasks, days_ago):
        cls.env.flush_all()
        cls.env.cr.execute("UPDATE project_task SET create_date = %s WHERE id IN %s", (cls._at(days_ago), tuple(tasks.ids)))
        cls.env.invalidate_all()

    @classmethod
    def _move(cls, task, rung, days_ago):
        """Change the stage and date the tracking value that records it ``days_ago``."""
        # Tracking compares with the values at the first change in the
        # transaction, so close what came before (such as the create) first.
        cls.env.flush_all()
        cls.env.cr.precommit.run()
        task.stage_id = cls.stages[rung]
        cls.env.flush_all()
        cls.env.cr.precommit.run()  # writes the tracking values
        tracking = cls.env["mail.tracking.value"].sudo().search(
            [
                ("field_id.name", "=", "stage_id"),
                ("mail_message_id.model", "=", "project.task"),
                ("mail_message_id.res_id", "=", task.id),
            ],
            order="id desc",
            limit=1,
        )
        cls.env.cr.execute("UPDATE mail_tracking_value SET create_date = %s WHERE id = %s", (cls._at(days_ago), tracking.id))
        cls.env.invalidate_all()

    def _history(self, data):
        return [(point["date"], point["value"]) for point in data["progress_history"]]

    def _day(self, days_ago):
        return (self.today - timedelta(days=days_ago)).isoformat()

    def test_history_from_tracking(self):
        """Weekly points from the start to today; moves, late tasks, cancelled and flows as documented."""
        data = self.burn.get_blueprint_map_data()
        # Three tasks count (not the flow, not the cancelled one): step / 5 / 3.
        self.assertEqual(
            self._history(data),
            [
                (self._day(28), round(2 / 15, 3)),  # Moving Open, Steady Built, Late comer not there yet
                (self._day(21), round(2 / 15, 3)),
                (self._day(14), round(3 / 15, 3)),  # Moving Decided
                (self._day(7), round(5 / 15, 3)),  # Moving Tested
                (self._day(0), round(10 / 15, 3)),  # Late comer Live
            ],
        )
        self.assertEqual(
            data["ideal"], [{"date": self._day(28), "value": 0.0}, {"date": (self.today + timedelta(days=28)).isoformat(), "value": 1.0}]
        )
        # 0.667 today against an ideal of 0.5.
        self.assertEqual((data["verdict"], data["weeks_behind"]), ("on_track", 0))

    def test_last_point_is_today(self):
        """When today is not a whole number of weeks after the start, the last point is today."""
        self.burn.date_start = self.today - timedelta(days=10)
        history = self._history(self.burn.get_blueprint_map_data())
        self.assertEqual([day for day, _value in history], [self._day(10), self._day(3), self._day(0)])
        # Ten days ago Moving had just reached Tested (20 and 10 days ago, at noon).
        self.assertEqual(history[0][1], round(5 / 15, 3))

    def test_behind(self):
        """Behind: how many weeks ago the ideal line stood at today's value, rounded."""
        self.burn.write({"date_start": self.today - timedelta(days=49), "date": self.today + timedelta(days=7)})
        data = self.burn.get_blueprint_map_data()
        self.assertEqual(len(data["progress_history"]), 8)
        # Ideal today 49/56; the ideal was at 0.667 on day 37.35, 11.65 days ago.
        self.assertEqual((data["verdict"], data["weeks_behind"]), ("behind", 2))

    def test_follows_the_search(self):
        """The map's search restricts the tasks the line is about."""
        data = self.burn.get_blueprint_map_data(domain=[("name", "=", "Steady")])
        self.assertEqual({value for _day, value in self._history(data)}, {0.4})
        self.assertEqual(data["verdict"], "behind")
        # A search without tasks: no chart.
        data = self.burn.get_blueprint_map_data(domain=[("name", "=", "Nothing like this")])
        self.assertEqual((data["progress_history"], data["ideal"], data["verdict"]), ([], False, False))

    def test_start_falls_back_to_first_task(self):
        """Without a start date the line starts at the first task's create date.
        (Odoo 19 clears both dates when one is cleared, so only data from
        elsewhere has a target without a start.)"""
        self.env.flush_all()
        self.env.cr.execute("UPDATE project_project SET date_start = NULL WHERE id = %s", (self.burn.id,))
        self.env.invalidate_all()
        data = self.burn.get_blueprint_map_data()
        self.assertEqual(data["progress_history"][0]["date"], self._day(30))
        self.assertEqual(data["ideal"][0], {"date": self._day(30), "value": 0.0})

    def test_no_target_date_no_chart(self):
        """Without a target date: no chart and no verdict."""
        self.burn.date = False
        data = self.burn.get_blueprint_map_data()
        self.assertEqual(
            {key: data[key] for key in ("progress_history", "ideal", "verdict", "weeks_behind")},
            {"progress_history": [], "ideal": False, "verdict": False, "weeks_behind": 0},
        )

    def test_one_tracking_search(self):
        """The history costs the same number of queries for three tasks or thirteen."""

        def count():
            self.env.invalidate_all()
            before = self.env.cr.sql_log_count
            self.burn.get_blueprint_map_data()
            return self.env.cr.sql_log_count - before

        count()  # warm the registry caches
        small = count()
        for index in range(10):
            task = self.env["project.task"].create({"name": f"Extra {index}", "project_id": self.burn.id, "stage_id": self.stages["0"].id})
            self._move(task, "2", 3)
        self.assertLessEqual(count(), small + 2)
