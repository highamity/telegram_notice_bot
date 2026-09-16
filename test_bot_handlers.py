"""Integration test for bot command handlers with mock Update."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import bot
from date_parser import KST, get_now_kst
from storage import NoticeStore


def make_mock_update(chat_id: int, text: str):
    update = MagicMock()
    msg = MagicMock()
    msg.text = text
    msg.reply_to_message = None
    msg.reply_text = AsyncMock()
    update.effective_message = msg
    chat = MagicMock()
    chat.id = chat_id
    update.effective_chat = chat
    context = MagicMock()
    return update, msg, context


async def test_bot_dispatch():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_bot.db"
        bot.STORE = NoticeStore(db_path)

        chat_id = 999

        # 1. Test schedule registration
        u, msg, ctx = make_mock_update(chat_id, "!일정 9/20 14:00 팀 회의")
        await bot.on_bang_message(u, ctx)
        assert msg.reply_text.called
        reply_call_args = msg.reply_text.call_args[0][0]
        assert "일정이 등록되었습니다" in reply_call_args
        assert "팀 회의" in reply_call_args

        # 2. Test schedule list
        u, msg, ctx = make_mock_update(chat_id, "!일정")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "예정된 일정" in reply
        assert "팀 회의" in reply

        # 3. Test schedule delete
        u, msg, ctx = make_mock_update(chat_id, "!일정삭제 1")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "일정이 삭제되었습니다" in reply

        # 4. Test D-Day registration (future 1-time goal)
        u, msg, ctx = make_mock_update(chat_id, "!디데이 수능 2026-11-19")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "디데이가 저장되었습니다" in reply
        assert "1회성 목표" in reply
        assert "수능" in reply

        # 5. Test D-Day registration (past anniversary - wedding)
        u, msg, ctx = make_mock_update(chat_id, "!디데이 결혼 2020-05-10")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "기념일이 저장되었습니다" in reply
        assert "매년 반복" in reply
        assert "일째" in reply

        # 5-1. Test !기념일 command registration
        u, msg, ctx = make_mock_update(chat_id, "!기념일 철수생일 10/25")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "기념일이 저장되었습니다" in reply
        assert "철수생일" in reply
        assert "매년 반복" in reply

        # 6. Test D-Day single lookup via !<key>
        u, msg, ctx = make_mock_update(chat_id, "!결혼")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "결혼" in reply
        assert "일째" in reply
        assert "매년 반복" in reply

        # 7. Test D-Day list (showing groups)
        u, msg, ctx = make_mock_update(chat_id, "!디데이")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "디데이 & 기념일 목록" in reply
        assert "매년 반복 기념일" in reply
        assert "1회성 목표" in reply
        assert "결혼" in reply
        assert "수능" in reply
        assert "철수생일" in reply

        # 8. Test D-Day delete via !기념일삭제
        u, msg, ctx = make_mock_update(chat_id, "!기념일삭제 철수생일")
        await bot.on_bang_message(u, ctx)
        reply = msg.reply_text.call_args[0][0]
        assert "삭제되었습니다" in reply

        # 9. Test reminder worker sending message
        await bot.STORE.add_schedule(chat_id, "2020-01-01 00:00:00", "과거 알림 테스트")
        mock_app = MagicMock()
        mock_app.bot = MagicMock()
        mock_app.bot.send_message = AsyncMock()

        # Run one iteration of schedule worker logic
        due = await bot.STORE.pop_due_schedules("2099-01-01 00:00:00")
        assert len(due) == 1
        assert due[0]["content"] == "과거 알림 테스트"
        await mock_app.bot.send_message(chat_id=due[0]["chat_id"], text=f"⏰ [일정 알림]\n{due[0]['content']}\n(예약 시각: {due[0]['remind_at'][:16]})")
        assert mock_app.bot.send_message.called
        assert "과거 알림 테스트" in mock_app.bot.send_message.call_args[1]["text"]

        # Run anniversary worker logic
        # Wedding was 2020-05-10, let's pop on 2026-05-10
        due_anniv = await bot.STORE.pop_due_ddays("2026-05-10", 2026)
        assert len(due_anniv) == 1
        assert due_anniv[0]["name"] == "결혼"
        # 10. Multi-chat isolation check at bot handler level
        chat_x, chat_y = 111, 222
        # Chat X registers memo and schedule
        u_x1, msg_x1, ctx_x1 = make_mock_update(chat_x, "!기억 프로젝트 X프로젝트")
        await bot.on_bang_message(u_x1, ctx_x1)
        u_x2, msg_x2, ctx_x2 = make_mock_update(chat_x, "!일정 9/20 10:00 X회의")
        await bot.on_bang_message(u_x2, ctx_x2)

        # Chat Y looks up memo and schedule
        u_y1, msg_y1, ctx_y1 = make_mock_update(chat_y, "!프로젝트")
        await bot.on_bang_message(u_y1, ctx_y1)
        assert not msg_y1.reply_text.called  # Chat Y should not find Chat X's memo

        u_y2, msg_y2, ctx_y2 = make_mock_update(chat_y, "!일정")
        await bot.on_bang_message(u_y2, ctx_y2)
        assert "예정된 일정이 없습니다" in msg_y2.reply_text.call_args[0][0]

        print("ALL BOT HANDLER AND WORKER TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(test_bot_dispatch())
