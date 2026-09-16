"""
Telegram bot: save and recall short notices per chat (group or private).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import MessageLimit
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from date_parser import (
    KST,
    DateParseError,
    calculate_dday_info,
    detect_repeat_yearly,
    format_dday_notification,
    get_now_kst,
    parse_dday_input,
    parse_schedule_input,
)
from storage import NoticeStore

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("notice_bot")

_default_db = Path(__file__).resolve().parent / "notices.db"
STORE = NoticeStore(Path(os.environ.get("NOTICE_DB_PATH", str(_default_db))))


def _parse_memory_message(text: str) -> tuple[str | None, str | None]:
    """Parse '!기억 <key> <value...>'; value may span multiple lines."""
    raw = (text or "").strip()
    if not raw:
        return None, None
    parts = raw.split()
    if len(parts) < 2:
        return None, None
    cmd = parts[0]
    if cmd != "!기억":
        return None, None
    key = parts[1]
    m = re.match(r"^\s*\S+\s+\S+\s*(.*)$", raw, flags=re.DOTALL)
    value = (m.group(1) or "").strip() if m else ""
    return key, value if value else None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📌 공지 및 일정 알림 봇 (이 채팅방 전용)\n\n"
        "【공지 메모】\n"
        "• !기억 <키> <내용...> — 공지 저장\n"
        "• (답장 후) !기억 <키> — 답장 메시지 본문 저장\n"
        "• !<키> — 저장된 공지 또는 디데이/기념일 조회\n"
        "• !목록 — 공지 키 목록\n"
        "• !삭제 <키> — 공지 삭제\n\n"
        "【일정 알림】\n"
        "• !일정 <날짜/시간> <내용...> — 일정 등록 및 알림 예약\n"
        "  예: !일정 9/20 14:00 팀 회의\n"
        "  예: !일정 9월20일 회식 (시간 생략 시 오전 09:00)\n"
        "  예: !일정 내일 10:00 치과\n"
        "• !일정목록 (또는 !일정) — 예정된 일정 목록\n"
        "• !일정삭제 <ID> — 일정 삭제\n\n"
        "【디데이 & 기념일】\n"
        "• !디데이 <이름> <날짜> — 디데이/기념일 등록\n"
        "  - 과거 날짜(결혼 2020-05-10)나 생일/기념일 키워드는 자동으로 [매년 반복 🔔]\n"
        "  - 미래 시험/목표(수능 2026-11-19)는 [1회성 목표 🎯]\n"
        "• !기념일 <이름> <날짜> — 매년 반복 알림 기념일로 명시적 등록\n"
        "  예: !기념일 철수생일 10/25 (매년 10월 25일 오전 09:00 축하 알림 발송)\n"
        "• !디데이 (또는 !기념일) — 등록된 디데이/기념일 전체 목록\n"
        "• !디데이 <이름> (또는 !<이름>) — 특정 디데이 단건 조회\n"
        "• !디데이삭제 <이름> (또는 !기념일삭제 <이름>) — 삭제\n\n"
        "【기타】\n"
        "• !도움말 (또는 /help) — 도움말 보기\n\n"
        "※ 그룹에서 메시지를 정상 수신하려면 BotFather에서 Privacy Mode를 꺼주세요."
    )
    if update.effective_message:
        await update.effective_message.reply_text(text)


async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    key, inline_value = _parse_memory_message(msg.text or "")
    if not key:
        await msg.reply_text("Usage: !기억 <key> <text...> or reply then !기억 <key>")
        return

    value: str | None = inline_value
    if msg.reply_to_message is not None:
        rm = msg.reply_to_message
        quoted = (rm.text or rm.caption or "").strip()
        if not quoted:
            await msg.reply_text("Replied message has no text or caption.")
            return
        if inline_value is not None:
            await msg.reply_text(
                "When using reply, send only: !기억 <key> (no extra text)."
            )
            return
        value = quoted

    if value is None:
        await msg.reply_text("No content. Use !기억 <key> <text...> or reply then !기억 <key>.")
        return

    if len(value) > 100_000:
        await msg.reply_text("Text is too long. Please shorten it.")
        return

    await STORE.put(chat.id, key, value)
    await msg.reply_text(f"Saved: {key}")


async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return
    args = context.args or []
    if len(args) != 1:
        await msg.reply_text("Usage: /get <key>")
        return
    key = args[0]
    text = await STORE.get(chat.id, key)
    if text is None:
        await msg.reply_text(f"No notice saved for key: {key}")
        return
    await _reply_long(msg, text)


async def _reply_long(msg, text: str) -> None:
    limit = MessageLimit.MAX_TEXT_LENGTH
    if len(text) <= limit:
        await msg.reply_text(text)
        return
    for i in range(0, len(text), limit):
        chunk = text[i : i + limit]
        await msg.reply_text(chunk)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return
    keys = await STORE.list_keys(chat.id)
    if not keys:
        await msg.reply_text("No notices saved yet.")
        return
    body = "\n".join(f"• {k}" for k in keys)
    await msg.reply_text(f"Keys ({len(keys)}):\n{body}")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return
    args = context.args or []
    if len(args) != 1:
        await msg.reply_text("Usage: !삭제 <key>")
        return
    key = args[0]
    ok = await STORE.delete(chat.id, key)
    if ok:
        await msg.reply_text(f"Deleted: {key}")
    else:
        await msg.reply_text(f"No notice for key: {key}")


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    args_text = raw[len("!일정"):].strip()
    if not args_text:
        await cmd_schedule_list(update, context)
        return

    try:
        remind_dt, content = parse_schedule_input(args_text)
        remind_str = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
        sid = await STORE.add_schedule(chat.id, remind_str, content)
        await msg.reply_text(
            f"✅ 일정이 등록되었습니다. (ID: {sid})\n"
            f"📅 {remind_dt.strftime('%Y-%m-%d %H:%M')} (KST)\n"
            f"📌 {content}"
        )
    except DateParseError as e:
        await msg.reply_text(f"⚠️ {e}")
    except Exception as e:
        logger.exception("Failed to add schedule: %s", e)
        await msg.reply_text("일정 등록 중 오류가 발생했습니다.")


async def cmd_schedule_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    schedules = await STORE.list_upcoming_schedules(chat.id)
    if not schedules:
        await msg.reply_text("예정된 일정이 없습니다.\n등록 예: !일정 9/20 14:00 회의")
        return

    lines = ["📅 예정된 일정:"]
    for s in schedules:
        remind_display = s["remind_at"][:16]  # "YYYY-MM-DD HH:MM"
        lines.append(f"• [ID: {s['id']}] {remind_display} | {s['content']}")
    lines.append("\n(일정 삭제: !일정삭제 <ID>)")
    await msg.reply_text("\n".join(lines))


async def cmd_schedule_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().isdigit():
        await msg.reply_text("사용법: !일정삭제 <ID>\n예: !일정삭제 1")
        return

    schedule_id = int(parts[1].strip())
    ok = await STORE.delete_schedule(chat.id, schedule_id)
    if ok:
        await msg.reply_text(f"일정이 삭제되었습니다. (ID: {schedule_id})")
    else:
        await msg.reply_text(f"해당 일정을 찾을 수 없습니다. (ID: {schedule_id})")


async def cmd_dday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

async def cmd_dday(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_anniversary_cmd: bool = False,
) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    prefix = "!기념일" if is_anniversary_cmd else "!디데이"
    args_text = raw[len(prefix):].strip()

    if not args_text or args_text == "목록":
        ddays = await STORE.list_ddays(chat.id)
        if not ddays:
            await msg.reply_text(
                "등록된 디데이/기념일이 없습니다.\n"
                "예: !디데이 수능 2026-11-19\n"
                "예: !기념일 철수생일 10/25\n"
                "예: !디데이 결혼 2020-05-10"
            )
            return

        lines = ["📅 디데이 & 기념일 목록:"]
        anniversaries = [d for d in ddays if d.get("repeat_yearly")]
        goals = [d for d in ddays if not d.get("repeat_yearly")]

        if anniversaries:
            lines.append("\n[매년 반복 기념일 🔔]")
            for d in anniversaries:
                try:
                    t_date = datetime.strptime(d["target_date"], "%Y-%m-%d").date()
                    badge, desc = calculate_dday_info(t_date, repeat_yearly=True)
                    lines.append(f"• {d['name']}: {badge} ({desc})")
                except Exception:
                    lines.append(f"• {d['name']}: {d['target_date']}")

        if goals:
            lines.append("\n[1회성 목표 🎯]")
            for d in goals:
                try:
                    t_date = datetime.strptime(d["target_date"], "%Y-%m-%d").date()
                    badge, desc = calculate_dday_info(t_date, repeat_yearly=False)
                    lines.append(f"• {d['name']}: {badge} ({desc})")
                except Exception:
                    lines.append(f"• {d['name']}: {d['target_date']}")

        lines.append("\n(삭제: !디데이삭제 <이름> 또는 !기념일삭제 <이름>)")
        await msg.reply_text("\n".join(lines))
        return

    # Check if single word inquiry (e.g. "!디데이 결혼" or "!기념일 생일")
    tokens = args_text.split()
    if len(tokens) == 1:
        name = tokens[0]
        dday_info = await STORE.get_dday(chat.id, name)
        if dday_info is not None:
            try:
                t_date = datetime.strptime(dday_info["target_date"], "%Y-%m-%d").date()
                repeat_yearly = bool(dday_info["repeat_yearly"])
                badge, desc = calculate_dday_info(t_date, repeat_yearly=repeat_yearly)
                tag = "[매년 반복 🔔]" if repeat_yearly else "[1회성 목표 🎯]"
                await msg.reply_text(f"📅 {name}: {badge} {tag}\n({desc})")
                return
            except Exception:
                pass

    # Otherwise, registration: !디데이 <name> <date...> or !기념일 <name> <date...>
    try:
        name, target_date = parse_dday_input(args_text)
        repeat_yearly = 1 if detect_repeat_yearly(name, target_date, is_anniversary_cmd=is_anniversary_cmd) else 0
        await STORE.put_dday(chat.id, name, target_date.strftime("%Y-%m-%d"), repeat_yearly=repeat_yearly)
        badge, desc = calculate_dday_info(target_date, repeat_yearly=bool(repeat_yearly))

        if repeat_yearly:
            await msg.reply_text(f"✅ 기념일이 저장되었습니다. (매년 반복 알림 🔔)\n• {name}: {badge} ({desc})")
        else:
            await msg.reply_text(f"✅ 디데이가 저장되었습니다. (1회성 목표 🎯)\n• {name}: {badge} ({desc})")
    except DateParseError as e:
        await msg.reply_text(f"⚠️ {e}")
    except Exception as e:
        logger.exception("Failed to add dday: %s", e)
        await msg.reply_text("디데이/기념일 저장 중 오류가 발생했습니다.")


async def cmd_dday_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        await msg.reply_text("사용법: !디데이삭제 <이름> (또는 !기념일삭제 <이름>)")
        return

    name = parts[1].strip()
    ok = await STORE.delete_dday(chat.id, name)
    if ok:
        await msg.reply_text(f"디데이/기념일이 삭제되었습니다: {name}")
    else:
        await msg.reply_text(f"등록된 디데이/기념일을 찾을 수 없습니다: {name}")


async def reminder_worker(application: Application) -> None:
    """Periodic background worker to send due reminders and annual anniversaries."""
    logger.info("Schedule reminder worker started")
    while True:
        try:
            now = get_now_kst()
            now_iso = now.strftime("%Y-%m-%d %H:%M:%S")

            # 1. Schedules due
            due_items = await STORE.pop_due_schedules(now_iso)
            for item in due_items:
                chat_id = item["chat_id"]
                content = item["content"]
                remind_display = item["remind_at"][:16]
                text = f"⏰ [일정 알림]\n{content}\n(예약 시각: {remind_display})"
                try:
                    await application.bot.send_message(chat_id=chat_id, text=text)
                    logger.info("Sent reminder %s to chat %s", item["id"], chat_id)
                except Exception as e:
                    logger.error("Failed to send reminder %s to chat %s: %s", item["id"], chat_id, e)

            # 2. D-Days & Anniversaries due (fire at or after 09:00 KST)
            if now.hour >= 9:
                today_str = now.strftime("%Y-%m-%d")
                due_ddays = await STORE.pop_due_ddays(today_str, now.year)
                for item in due_ddays:
                    chat_id = item["chat_id"]
                    try:
                        t_date = datetime.strptime(item["target_date"], "%Y-%m-%d").date()
                        text = format_dday_notification(
                            item["name"],
                            t_date,
                            repeat_yearly=bool(item["repeat_yearly"]),
                            today=now.date(),
                        )
                        await application.bot.send_message(chat_id=chat_id, text=text)
                        logger.info("Sent dday notification %s (%s) to chat %s", item["id"], item["name"], chat_id)
                    except Exception as e:
                        logger.error("Failed to send dday %s to chat %s: %s", item["id"], chat_id, e)

        except asyncio.CancelledError:
            logger.info("Schedule reminder worker cancelled")
            break
        except Exception as e:
            logger.error("Error in reminder_worker: %s", e)

        await asyncio.sleep(30)


async def on_bang_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    if not raw.startswith("!"):
        return

    if raw in ("!도움말", "!도움", "!help"):
        await cmd_start(update, context)
        return

    if raw == "!목록":
        keys = await STORE.list_keys(chat.id)
        if not keys:
            await msg.reply_text("No notices saved yet.")
            return
        body = "\n".join(f"• {k}" for k in keys)
        await msg.reply_text(f"Keys ({len(keys)}):\n{body}")
        return

    if raw.startswith("!삭제"):
        parts = raw.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            await msg.reply_text("Usage: !삭제 <key>")
            return
        key = parts[1].strip()
        ok = await STORE.delete(chat.id, key)
        if ok:
            await msg.reply_text(f"Deleted: {key}")
        else:
            await msg.reply_text(f"No notice for key: {key}")
        return

    if raw.startswith("!기억"):
        await cmd_save(update, context)
        return

    if raw == "!일정목록":
        await cmd_schedule_list(update, context)
        return

    if raw.startswith("!일정삭제"):
        await cmd_schedule_delete(update, context)
        return

    if raw.startswith("!일정"):
        await cmd_schedule(update, context)
        return

    if raw in ("!기념일목록",):
        await cmd_dday(update, context, is_anniversary_cmd=True)
        return

    if raw.startswith("!기념일삭제"):
        await cmd_dday_delete(update, context)
        return

    if raw.startswith("!기념일"):
        await cmd_dday(update, context, is_anniversary_cmd=True)
        return

    if raw in ("!디데이목록",):
        await cmd_dday(update, context, is_anniversary_cmd=False)
        return

    if raw.startswith("!디데이삭제"):
        await cmd_dday_delete(update, context)
        return

    if raw.startswith("!디데이"):
        await cmd_dday(update, context, is_anniversary_cmd=False)
        return

    key = raw[1:].strip()
    if not key:
        return

    # 1. Look up notice
    text = await STORE.get(chat.id, key)
    if text is not None:
        await _reply_long(msg, text)
        return

    # 2. Look up dday / anniversary fallback
    dday_info = await STORE.get_dday(chat.id, key)
    if dday_info is not None:
        try:
            t_date = datetime.strptime(dday_info["target_date"], "%Y-%m-%d").date()
            repeat_yearly = bool(dday_info["repeat_yearly"])
            badge, desc = calculate_dday_info(t_date, repeat_yearly=repeat_yearly)
            tag = "[매년 반복 🔔]" if repeat_yearly else "[1회성 목표 🎯]"
            await msg.reply_text(f"📅 {key}: {badge} {tag}\n({desc})")
            return
        except Exception:
            pass


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("Set TELEGRAM_BOT_TOKEN in the environment or .env file.")
        sys.exit(1)

    async def post_init(app: Application) -> None:
        asyncio.create_task(reminder_worker(app))

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_bang_message))

    logger.info("Polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

