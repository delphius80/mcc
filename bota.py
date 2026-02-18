import os
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    ChatJoinRequestHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ================= CONFIG =================

BOT_TOKEN = "8525827747:AAGm2wVSTaru9hRu4rNMEG31CWS1dHlGeeY"

MODERATORS = {7827962328}

REQUEST_TTL = 24

DB_FILE = "requests.db"

# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# ================= DATABASE =================

conn = sqlite3.connect(
    DB_FILE,
    check_same_thread=False,
)

conn.execute("""

CREATE TABLE IF NOT EXISTS requests (

    user_id INTEGER PRIMARY KEY,

    chat_id INTEGER NOT NULL,

    status TEXT NOT NULL,

    created_at TEXT NOT NULL

)

""")

conn.commit()


def db_add(user_id, chat_id):

    conn.execute(
        """
        INSERT OR REPLACE INTO requests
        (user_id, chat_id, status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            chat_id,
            "pending",
            datetime.utcnow().isoformat(),
        ),
    )

    conn.commit()


def db_get(user_id):

    cur = conn.execute(
        """
        SELECT chat_id, status, created_at
        FROM requests
        WHERE user_id = ?
        """,
        (user_id,),
    )

    return cur.fetchone()


def db_update(user_id, status):

    conn.execute(
        """
        UPDATE requests
        SET status = ?
        WHERE user_id = ?
        """,
        (status, user_id),
    )

    conn.commit()


def db_is_expired(created_at):

    created = datetime.fromisoformat(created_at)

    return datetime.utcnow() - created > timedelta(
        hours=REQUEST_TTL
    )


# ================= JOIN REQUEST =================

async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):

    req = update.chat_join_request

    user = req.from_user

    logger.info(f"Join request {user.id}")

    db_add(user.id, req.chat.id)

    try:

        await context.bot.send_message(

            chat_id=user.id,

            text=(
                "Отправьте видеосообщение (кружок):\n\n"
                "Назовите имя, возраст и город\n"
                "и скажите:\n"
                "Хочу вступить в группу"
            ),
        )

    except Exception as e:

        logger.error(e)


# ================= VIDEO HANDLER =================

async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = update.message

    user = msg.from_user

    data = db_get(user.id)

    if not data:
        return

    chat_id, status, created_at = data

    if status != "pending":
        return

    if db_is_expired(created_at):

        await msg.reply_text(
            "Заявка устарела"
        )

        db_update(user.id, "expired")

        return

    if not msg.video_note:

        await msg.reply_text(
            "Нужно видеосообщение"
        )

        return

    keyboard = InlineKeyboardMarkup([

        [

            InlineKeyboardButton(
                "Одобрить",
                callback_data=f"approve:{user.id}",
            ),

            InlineKeyboardButton(
                "Отклонить",
                callback_data=f"decline:{user.id}",
            ),

        ]

    ])

    for mod in MODERATORS:

        try:

            await context.bot.forward_message(

                mod,
                msg.chat_id,
                msg.message_id,

            )

            await context.bot.send_message(

                mod,

                f"User @{user.username}\nID {user.id}",

                reply_markup=keyboard,

            )

        except Exception as e:

            logger.error(e)

    await msg.reply_text("Отправлено модератору")

    db_update(user.id, "review")


# ================= MODERATOR =================

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    if query.from_user.id not in MODERATORS:

        await query.edit_message_text(
            "Нет доступа"
        )

        return

    action, user_id = query.data.split(":")

    user_id = int(user_id)

    data = db_get(user_id)

    if not data:

        await query.edit_message_text(
            "Нет заявки"
        )

        return

    chat_id, status, created_at = data

    if status not in ("pending", "review"):

        await query.edit_message_text(
            "Уже обработано"
        )

        return

    try:

        if action == "approve":

            await context.bot.approve_chat_join_request(

                chat_id,
                user_id,

            )

            await context.bot.send_message(

                user_id,

                "Добро пожаловать",

            )

            db_update(user_id, "approved")

            await query.edit_message_text(
                "Одобрено"
            )

        else:

            await context.bot.decline_chat_join_request(

                chat_id,
                user_id,

            )

            await context.bot.send_message(

                user_id,

                "Отклонено",

            )

            db_update(user_id, "declined")

            await query.edit_message_text(
                "Отклонено"
            )

    except Exception as e:

        logger.error(e)


# ================= MAIN =================

def main():

    logger.info("Bot started")

    app = ApplicationBuilder().token(
        BOT_TOKEN
    ).build()

    app.add_handler(
        ChatJoinRequestHandler(on_join_request)
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE &
            ~filters.COMMAND,
            on_private_message,
        )
    )

    app.add_handler(
        CallbackQueryHandler(on_callback)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
