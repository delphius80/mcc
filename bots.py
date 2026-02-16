import os
import logging
import aiosqlite
from datetime import datetime, timezone, time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from openai import AsyncOpenAI

# ---------------- CONFIG ----------------

BOT_TOKEN = os.environ["BOT_TOKEN"]
MODERATOR_ID = int(os.environ["MODERATOR_ID"])
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]

DB = "messages.db"

DIGEST_HOUR = 21
DIGEST_MINUTE = 0

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ---------------- DATABASE ----------------

async def init_db():

    async with aiosqlite.connect(DB) as db:

        await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            user TEXT,
            text TEXT,
            date TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            chat_id INTEGER,
            date TEXT,
            PRIMARY KEY(chat_id, date)
        )
        """)

        await db.commit()


async def save_message(update: Update):

    msg = update.effective_message

    if not msg.text:
        return

    async with aiosqlite.connect(DB) as db:

        await db.execute("""

        INSERT INTO messages
        (chat_id, user, text, date)

        VALUES (?, ?, ?, ?)

        """, (

            msg.chat_id,
            msg.from_user.full_name,
            msg.text,
            msg.date.isoformat()

        ))

        await db.commit()


async def get_today_messages(chat_id):

    today = datetime.now(timezone.utc).date()

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute("""

        SELECT user, text
        FROM messages

        WHERE chat_id = ?
        AND date >= ?

        """, (

            chat_id,
            today.isoformat()

        ))

        return await cursor.fetchall()


async def digest_exists(chat_id):

    today = datetime.now(timezone.utc).date()

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute("""

        SELECT 1 FROM digests
        WHERE chat_id = ?
        AND date = ?

        """, (

            chat_id,
            today.isoformat()

        ))

        return await cursor.fetchone() is not None


async def mark_digest(chat_id):

    today = datetime.now(timezone.utc).date()

    async with aiosqlite.connect(DB) as db:

        await db.execute("""

        INSERT OR IGNORE INTO digests
        VALUES (?, ?)

        """, (

            chat_id,
            today.isoformat()

        ))

        await db.commit()


# ---------------- AI ----------------

async def summarize(messages):

    if not messages:
        return "Сегодня в чате пусто. Даже странно. Все живы вообще?"

    text = "\n".join(
        f"{user}: {msg}"
        for user, msg in messages
    )

    prompt = f"""

Сделай ДАЙДЖЕСТ чата за день.

Стиль:

— саркастичный
— дерзкий
— с подколками
— можно пошлый юмор
— как будто ты токсичный, но умный админ

Но:

— без откровенной жести
— без ненависти

Формат:

Заголовок дня

и список событий

Сообщения:

{text}

"""

    response = await client.chat.completions.create(

        model="deepseek-chat",

        messages=[

            {
                "role": "system",
                "content":
                "Ты саркастичный ублюдок-админ, который пишет смешные дайджесты."
            },

            {
                "role": "user",
                "content": prompt
            }

        ],

        temperature=0.9

    )

    return response.choices[0].message.content


# ---------------- HANDLERS ----------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type in ("group", "supergroup"):

        await save_message(update)


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != MODERATOR_ID:
        return

    await update.message.reply_text("Ща посмотрю, что вы там опять написали…")

    messages = await get_today_messages(
        update.effective_chat.id
    )

    summary = await summarize(messages)

    await update.message.reply_text(summary)


# ---------------- AUTO DIGEST ----------------

async def auto_digest(context: ContextTypes.DEFAULT_TYPE):

    for chat_id in context.bot_data.get("chats", []):

        if await digest_exists(chat_id):
            continue

        messages = await get_today_messages(chat_id)

        summary = await summarize(messages)

        await context.bot.send_message(chat_id, summary)

        await mark_digest(chat_id)


# ---------------- CHAT TRACK ----------------

async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    if "chats" not in context.bot_data:

        context.bot_data["chats"] = set()

    context.bot_data["chats"].add(chat_id)


# ---------------- MAIN ----------------

async def main():

    await init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        on_message
    ))

    app.add_handler(MessageHandler(
        filters.ALL,
        track_chat
    ))

    app.add_handler(CommandHandler(
        "summary",
        cmd_summary
    ))

    app.job_queue.run_daily(

        auto_digest,

        time=time(
            hour=DIGEST_HOUR,
            minute=DIGEST_MINUTE,
            tzinfo=timezone.utc
        )

    )

    print("Bot started")

    await app.run_polling()


if __name__ == "__main__":

    import asyncio
    asyncio.run(main())
