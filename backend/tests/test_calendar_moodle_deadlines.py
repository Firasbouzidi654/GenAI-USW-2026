from datetime import datetime, timezone

import pytest

from app.api.v1 import calendar as calendar_api


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values=None, rowcount=0):
        self._values = values or []
        self.rowcount = rowcount

    def scalars(self):
        return _ScalarResult(self._values)


class _FakeDb:
    def __init__(self, execute_result=None):
        self.execute_result = execute_result or _ExecuteResult()
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, _statement):
        return self.execute_result

    def add(self, event):
        self.added.append(event)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, event):
        event.id = len(self.added)
        event.created_at = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_sync_moodle_deadlines_creates_calendar_events_with_moodle_category(monkeypatch):
    async def fake_deadlines():
        return [
            {
                "title": "Submission Presentation 3",
                "course": "B5.3 Unternehmenssoftware",
                "course_id": "58776",
                "due_date": "2026-06-30T06:00:00+00:00",
                "type": "Moodle Deadline",
            }
        ]

    monkeypatch.setattr(calendar_api, "get_upcoming_moodle_deadlines", fake_deadlines)
    db = _FakeDb()

    result = await calendar_api.sync_moodle_deadlines_to_calendar(db)

    assert result.created == 1
    assert result.existing == 0
    assert db.committed is True
    event = db.added[0]
    assert event.source == "moodle"
    assert event.category == "Moodle Deadline"
    assert event.title == "Submission Presentation 3"
    assert event.location == "B5.3 Unternehmenssoftware"
    assert event.start_time.isoformat() == "2026-06-30T06:00:00+00:00"


@pytest.mark.asyncio
async def test_delete_moodle_deadlines_returns_deleted_count():
    db = _FakeDb(execute_result=_ExecuteResult(rowcount=2))

    result = await calendar_api.delete_moodle_deadlines_from_calendar(db)

    assert result.deleted == 2
    assert db.committed is True
