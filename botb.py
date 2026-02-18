import os
import sqlite3
import logging
from datetime import datetime, timezone, time, timedelta
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from openai import OpenAI  # DeepSeek совместимо через OpenAI API

# ---------------- CONFIG ----------------

BOT_TOKEN = "8525827747:AAGm2wVSTaru9hRu4rNMEG31CWS1dHlGeeY"
MODERATOR_ID = 7827962328
DEEPSEEK_API_KEY = "sk-ccb31d5d70184b478422d0f9eadd98c1"

DB = "messages.db"
DIGEST_HOUR = 3
DIGEST_MINUTE = 0

client = OpenAI(api_key=DEEPSEEK_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user TEXT,
        text TEXT,
        date TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS digests (
        chat_id INTEGER,
        date TEXT,
        PRIMARY KEY(chat_id, date)
    )
    """)
    conn.commit()
    conn.close()

def save_message(chat_id, user, text, date):
    conn = sqlite3.connect(DB)
    conn.execute("""
    INSERT INTO messages (chat_id, user, text, date)
    VALUES (?, ?, ?, ?)
    """, (chat_id, user, text, date.isoformat()))
    conn.commit()
    conn.close()

def get_today_messages(chat_id):
    today = datetime.now(timezone.utc).date()
    conn = sqlite3.connect(DB)
    cursor = conn.execute("""
    SELECT user, text, date FROM messages
    WHERE chat_id = ?
    """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for user, text, date_str in rows:
        dt = datetime.fromisoformat(date_str)
        if dt.date() == today:
            result.append((user, text))
    return result

def digest_exists(chat_id):
    today = datetime.now(timezone.utc).date()
    conn = sqlite3.connect(DB)
    cursor = conn.execute("""
    SELECT 1 FROM digests
    WHERE chat_id = ? AND date = ?
    """, (chat_id, today.isoformat()))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def mark_digest(chat_id):
    today = datetime.now(timezone.utc).date()
    conn = sqlite3.connect(DB)
    conn.execute("""
    INSERT OR IGNORE INTO digests (chat_id, date) VALUES (?, ?)
    """, (chat_id, today.isoformat()))
    conn.commit()
    conn.close()

# ---------------- AI ----------------

def summarize(messages):
    if not messages:
        return "Сегодня в чате пусто. Даже странно. Все живы вообще?"

    text = "\n".join(f"{user}: {msg}" for user, msg in messages)

    prompt = f"""
Сделай ДАЙДЖЕСТ чата за день.

Стиль:
— саркастичный
— дерзкий
— с подколками
— можно слегка пошлый юмор
— как будто ты токсичный, но умный админ

Формат:
Заголовок дня и список событий

Сообщения:
{text}
"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "Ты саркастичный ублюдок-админ, который пишет смешные дайджесты."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.9
    )
    return response.choices[0].message.content

# ---------------- HANDLERS ----------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.text and update.effective_chat.type in ("group", "supergroup"):
        save_message(msg.chat_id, msg.from_user.full_name, msg.text, msg.date)

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MODERATOR_ID:
        return
    await update.message.reply_text("Ща посмотрю, что вы там опять написали…")
    messages = get_today_messages(update.effective_chat.id)
    summary = summarize(messages)
    await update.message.reply_text(summary)

# ---------------- AUTO DIGEST ----------------

async def auto_digest(app: Application):
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=DIGEST_HOUR, minute=DIGEST_MINUTE, second=0)
        if now > target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        chats = getattr(app.bot_data, "chats", set())
        for chat_id in chats:
            if digest_exists(chat_id):
                continue
            messages = get_today_messages(chat_id)
            summary = summarize(messages)
            await app.bot.send_message(chat_id, summary)
            mark_digest(chat_id)

# ---------------- TRACK CHATS ----------------

async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if "chats" not in context.bot_data:
        context.bot_data["chats"] = set()
    context.bot_data["chats"].add(chat_id)

# ---------------- MAIN ----------------

async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.ALL, track_chat))
    app.add_handler(CommandHandler("summary", cmd_summary))
    asyncio.create_task(auto_digest(app))
    print("Bot started")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

