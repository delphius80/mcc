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
import os

BOT_TOKEN = "1111111"
MODERATOR_ID = 1

# user_id -> chat_id
pending = {}


# 1️⃣ Заявка на вступление
async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    user = req.from_user

    pending[user.id] = req.chat.id

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            "Это закрытое сообщество.\n\n"
            "Пришлите *кружок (видеосообщение)* до 30 секунд, где:\n"
            "— вы смотрите в камеру\n"
            "— называете свое имя, возраст и город\n"
            "— говорите фразу:\n"
            "«Хочу вступить в группу»"
        ),
        parse_mode="Markdown",
    )


# 2️⃣ Приём сообщений от пользователя
async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user

    if user.id not in pending:
        return

    # Принимаем ТОЛЬКО кружок
    if not msg.video_note:
        await msg.reply_text("Нужен именно кружок (видеосообщение).")
        return

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{user.id}"),
        ]]
    )

    await context.bot.forward_message(
        chat_id=MODERATOR_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id,
    )

    await context.bot.send_message(
        chat_id=MODERATOR_ID,
        text=f"Запрос на вступление\n@{user.username or 'без_ника'}\nID: {user.id}",
        reply_markup=keyboard,
    )

    await msg.reply_text("Видео получено. Ожидайте решения модератора.")


# 3️⃣ Кнопки модератора
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, user_id = query.data.split(":")
    user_id = int(user_id)

    if user_id not in pending:
        await query.edit_message_text("Заявка уже обработана.")
        return

    chat_id = pending[user_id]

    if action == "approve":
        await context.bot.approve_chat_join_request(chat_id, user_id)
        await context.bot.send_message(user_id, "Добро пожаловать 👋")
        await query.edit_message_text("✅ Заявка одобрена")

    else:
        await context.bot.decline_chat_join_request(chat_id, user_id)
        await context.bot.send_message(user_id, "Заявка отклонена.")
        await query.edit_message_text("❌ Заявка отклонена")

    del pending[user_id]


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_private_message))
    app.add_handler(CallbackQueryHandler(on_callback))

    print("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()

