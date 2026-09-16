"""Test strict isolation between different chat rooms."""

import asyncio
import tempfile
from pathlib import Path

from storage import NoticeStore


async def test_chat_isolation():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = NoticeStore(Path(tmpdir) / "isolation.db")

        CHAT_A = 1001
        CHAT_B = 2002

        # 1. Notices isolation
        await store.put(CHAT_A, "공지", "방 A의 공지입니다")
        await store.put(CHAT_B, "공지", "방 B의 공지입니다")

        assert await store.get(CHAT_A, "공지") == "방 A의 공지입니다"
        assert await store.get(CHAT_B, "공지") == "방 B의 공지입니다"
        assert await store.list_keys(CHAT_A) == ["공지"]
        assert await store.list_keys(CHAT_B) == ["공지"]

        # Delete in Chat A should not affect Chat B
        await store.delete(CHAT_A, "공지")
        assert await store.get(CHAT_A, "공지") is None
        assert await store.get(CHAT_B, "공지") == "방 B의 공지입니다"

        # 2. Schedules isolation
        s_id_a = await store.add_schedule(CHAT_A, "2026-09-20 14:00:00", "방 A 회의")
        s_id_b = await store.add_schedule(CHAT_B, "2026-09-20 14:00:00", "방 B 회의")

        sched_a = await store.list_upcoming_schedules(CHAT_A)
        sched_b = await store.list_upcoming_schedules(CHAT_B)

        assert len(sched_a) == 1 and sched_a[0]["content"] == "방 A 회의"
        assert len(sched_b) == 1 and sched_b[0]["content"] == "방 B 회의"

        # Chat A cannot delete Chat B's schedule
        del_attempt = await store.delete_schedule(CHAT_A, s_id_b)
        assert del_attempt is False  # Cannot delete schedule of another chat
        assert len(await store.list_upcoming_schedules(CHAT_B)) == 1

        # 3. D-Days isolation
        await store.put_dday(CHAT_A, "기념일", "2020-01-01")
        await store.put_dday(CHAT_B, "기념일", "2024-05-01")

        res_a = await store.get_dday(CHAT_A, "기념일")
        res_b = await store.get_dday(CHAT_B, "기념일")
        assert res_a is not None and res_a["target_date"] == "2020-01-01"
        assert res_b is not None and res_b["target_date"] == "2024-05-01"

        ddays_a = await store.list_ddays(CHAT_A)
        ddays_b = await store.list_ddays(CHAT_B)
        assert len(ddays_a) == 1 and ddays_a[0]["target_date"] == "2020-01-01"
        assert len(ddays_b) == 1 and ddays_b[0]["target_date"] == "2024-05-01"

        # Deleting in Chat A does not affect Chat B
        del_dday_a = await store.delete_dday(CHAT_A, "기념일")
        assert del_dday_a is True
        assert await store.get_dday(CHAT_A, "기념일") is None
        res_b_after = await store.get_dday(CHAT_B, "기념일")
        assert res_b_after is not None and res_b_after["target_date"] == "2024-05-01"

        print("ALL CHAT ISOLATION TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(test_chat_isolation())
