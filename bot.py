"""
Telegram bot: save and recall short notices per chat (group or private).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import MessageLimit
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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
        "Notice bot for this chat only.\n\n"
        "Commands:\n"
        "• !기억 <key> <text...> — save\n"
        "• Reply to a message, then !기억 <key> — store that message body\n"
        "• !<key> — show saved text\n"
        "• !목록 — list keys\n"
        "• !삭제 <key> — remove\n\n"
        "For reply-to-save, disable Privacy mode in BotFather (/setprivacy → Disable).\n\n"
        "Use one-word keys without spaces, e.g. meeting, parking, rules2024."
    )
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


async def on_bang_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    raw = (msg.text or "").strip()
    if not raw.startswith("!"):
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

    key = raw[1:].strip()
    if not key:
        return
    text = await STORE.get(chat.id, key)
    if text is None:
        return
    await _reply_long(msg, text)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("Set TELEGRAM_BOT_TOKEN in the environment or .env file.")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_bang_message))

    logger.info("Polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
