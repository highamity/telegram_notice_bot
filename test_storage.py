"""Unit test for storage.py schedule and dday additions."""

import asyncio
import tempfile
from pathlib import Path

from storage import NoticeStore


async def test_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = NoticeStore(db_path)

        # 1. Test notice (regression check)
        await store.put(123, "회식", "금요일 7시")
        val = await store.get(123, "회식")
        assert val == "금요일 7시"
        keys = await store.list_keys(123)
        assert keys == ["회식"]

        # 2. Test schedules
        sid1 = await store.add_schedule(123, "2026-09-20 14:00:00", "회의")
        sid2 = await store.add_schedule(123, "2026-09-21 09:00:00", "출장")
        sid_other = await store.add_schedule(456, "2026-09-20 14:00:00", "다른방")

        upcoming = await store.list_upcoming_schedules(123)
        assert len(upcoming) == 2
        assert upcoming[0]["id"] == sid1
        assert upcoming[0]["content"] == "회의"

        # pop_due_schedules
        due = await store.pop_due_schedules("2026-09-20 15:00:00")
        assert len(due) == 2  # sid1 and sid_other
        assert {d["id"] for d in due} == {sid1, sid_other}

        # After pop, sid1 should not be pending
        upcoming2 = await store.list_upcoming_schedules(123)
        assert len(upcoming2) == 1
        assert upcoming2[0]["id"] == sid2

        # Delete schedule
        del_ok = await store.delete_schedule(123, sid2)
        assert del_ok is True
        assert len(await store.list_upcoming_schedules(123)) == 0

        # 3. Test ddays and anniversaries
        await store.put_dday(123, "결혼", "2020-05-10", repeat_yearly=1)
        await store.put_dday(123, "수능", "2026-11-19", repeat_yearly=0)
        target_val = await store.get_dday(123, "결혼")
        assert target_val is not None
        assert target_val["target_date"] == "2020-05-10"
        assert target_val["repeat_yearly"] == 1

        ddays = await store.list_ddays(123)
        assert len(ddays) == 2
        assert ddays[0]["name"] == "결혼"

        # Overwrite
        await store.put_dday(123, "수능", "2026-11-20", repeat_yearly=0)
        updated = await store.get_dday(123, "수능")
        assert updated is not None and updated["target_date"] == "2026-11-20"

        # Test pop_due_ddays
        # Wedding (2020-05-10, repeat_yearly=1) on 2026-05-10 -> should pop
        due_ddays = await store.pop_due_ddays("2026-05-10", 2026)
        assert len(due_ddays) == 1
        assert due_ddays[0]["name"] == "결혼"
        # Second call in same year should not pop again
        due_again = await store.pop_due_ddays("2026-05-10", 2026)
        assert len(due_again) == 0
        # Next year 2027-05-10 -> should pop
        due_next_year = await store.pop_due_ddays("2027-05-10", 2027)
        assert len(due_next_year) == 1

        # Delete
        del_dday_ok = await store.delete_dday(123, "수능")
        assert del_dday_ok is True
        assert len(await store.list_ddays(123)) == 1

        print("ALL STORAGE TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(test_storage())
