"""Day types for a border post: what counts as a 'normal' day depends on the calendar.

SSB knows these in advance: weekly haat (market) days, festivals, and election or other border
seals (e.g. the 72-hour seals before polls). The baseline learns each day type separately, and
on a seal day every fence crossing alerts regardless of the budget.
"""
import datetime as dt
import json
from pathlib import Path

NORMAL, HAAT, FESTIVAL, SEAL = "normal", "haat", "festival", "seal"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class PostCalendar:
    def __init__(self, haat_weekdays=(), haat_dates=(), festivals=(), seals=()):
        self.haat_weekdays = {WEEKDAYS.index(d[:3].lower()) for d in haat_weekdays}
        self.haat_dates = {dt.date.fromisoformat(d) for d in haat_dates}
        self.festivals = {dt.date.fromisoformat(d) for d in festivals}
        # seals: [{"from": "2025-11-08T18:00", "to": "2025-11-11T18:00"}]
        self.seals = [(dt.datetime.fromisoformat(s["from"]), dt.datetime.fromisoformat(s["to"])) for s in seals]

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("haat_weekdays", ()), d.get("haat_dates", ()), d.get("festivals", ()), d.get("seals", ()))

    @classmethod
    def load(cls, path):
        path = Path(path)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")).get("calendar", {})) if path.exists() else cls()

    def sealed(self, t):
        when = dt.datetime.fromtimestamp(t)
        return any(a <= when <= b for a, b in self.seals)

    def day_type(self, t):
        if self.sealed(t):
            return SEAL
        day = dt.datetime.fromtimestamp(t).date()
        if day in self.festivals:
            return FESTIVAL
        if day in self.haat_dates or day.weekday() in self.haat_weekdays:
            return HAAT
        return NORMAL
