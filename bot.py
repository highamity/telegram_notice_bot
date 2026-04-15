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
from telegram.constants import ChatMemberStatus, ChatType, MessageLimit
from telegram.ext import Application, CommandHandler, ContextTypes

from storage import NoticeStore

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("notice_bot")

_default_db = Path(__file__).resolve().parent / "notices.db"
STORE = NoticeStore(Path(os.environ.get("NOTICE_DB_PATH", str(_default_db))))


def _strip_command_mention(first_token: str) -> str:
    return first_token.split("@", 1)[0]


async def _is_privileged(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Private chats: any user. Groups/supergroups: creator or admin only."""
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return False
    if chat.type == ChatType.PRIVATE:
        return True
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


def _parse_save_message(text: str) -> tuple[str | None, str | None]:
    """Parse '/save <key> <value...>'; value may span multiple lines."""
    raw = (text or "").strip()
    if not raw:
        return None, None
    parts = raw.split()
    if len(parts) < 2:
        return None, None
    cmd = _strip_command_mention(parts[0])
    if cmd != "/save":
        return None, None
    key = parts[1]
    m = re.match(r"^\s*\S+\s+\S+\s*(.*)$", raw, flags=re.DOTALL)
    value = (m.group(1) or "").strip() if m else ""
    return key, value if value else None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Notice bot for this chat only.\n\n"
        "Commands:\n"
        "• /save <key> <text...> — save (groups: admins only)\n"
        "• Reply to a message, then /save <key> — store that message body\n"
        "• /get <key> — show saved text\n"
        "• /list — list keys\n"
        "• /delete <key> — remove (groups: admins only)\n\n"
        "For reply-to-save, disable Privacy mode in BotFather (/setprivacy → Disable).\n\n"
        "Use one-word keys without spaces, e.g. meeting, parking, rules2024."
    )
    await update.effective_message.reply_text(text)


async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    if not await _is_privileged(update, context):
        await msg.reply_text("Only admins can save notices in this group.")
        return

    key, inline_value = _parse_save_message(msg.text or "")
    if not key:
        await msg.reply_text("Usage: /save <key> <text...> or reply then /save <key>")
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
                "When using reply, send only: /save <key> (no extra text)."
            )
            return
        value = quoted

    if value is None:
        await msg.reply_text("No content. Use /save <key> <text...> or reply then /save <key>.")
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
    if not await _is_privileged(update, context):
        await msg.reply_text("Only admins can delete notices in this group.")
        return
    args = context.args or []
    if len(args) != 1:
        await msg.reply_text("Usage: /delete <key>")
        return
    key = args[0]
    ok = await STORE.delete(chat.id, key)
    if ok:
        await msg.reply_text(f"Deleted: {key}")
    else:
        await msg.reply_text(f"No notice for key: {key}")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("Set TELEGRAM_BOT_TOKEN in the environment or .env file.")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("delete", cmd_delete))

    logger.info("Polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
