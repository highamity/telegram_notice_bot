# Telegram notice bot (QNAP TS-251, Docker)

Save short notices **per chat** (each group has its own keys). Data is stored in a single **SQLite** file.

## What you asked for

1. **Runtime**: QNAP TS-251 — use **Container Station** with the included `Dockerfile`, or any host with Python 3.
2. **Behavior**: Remember text under a **key**, then print it again with a command (`/get`).
3. **Group use**: Good for “pinned” announcements. **Save/delete** is **admin-only** in groups; anyone can **read** (`/get`, `/list`).

## Commands (bot replies are in English)

| Command | Description |
|--------|-------------|
| `/save key text...` | Save (groups: **admins only**) |
| Reply to a message, then `/save key` | Save that message body |
| `/get key` | Show saved text |
| `/list` | List keys in this chat |
| `/delete key` | Delete (groups: **admins only**) |

**Privacy mode:** For reply-to-save, turn **Privacy mode** off in BotFather (`/setprivacy` → Disable).

**Keys:** Use one token without spaces, e.g. `meeting`, `parking`, `rules2024`.

## Create the bot

1. Open [@BotFather](https://t.me/BotFather), create a bot, copy the **token**.
2. Add the bot to your group.

## Run on QNAP (Docker)

```bash
cd telegram_notice_bot
docker build -t telegram-notice-bot .
docker run -d --name telegram-notice-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="YOUR_TOKEN_HERE" \
  -v /share/Container/telegram_bot_data:/data \
  telegram-notice-bot
```

Inside the container the DB defaults to `/data/notices.db` (`NOTICE_DB_PATH` in `Dockerfile`).

## Local test (Windows)

```bash
cd telegram_notice_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
REM put TELEGRAM_BOT_TOKEN in .env
python bot.py
```

Default DB path: `notices.db` next to `bot.py`.

## Security

- Never commit `.env` or tokens.
- Saved text is posted as-is; admin-only `/save` limits who can publish.

## Files

- `bot.py` — bot logic
- `storage.py` — SQLite access
- `requirements.txt`
- `Dockerfile`
- `.env.example`
