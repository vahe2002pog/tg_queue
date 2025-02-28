import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackContext
from telegram.ext import ConversationHandler

logger = logging.getLogger(__name__)

CHANGE_NAME = 0

async def change_name_start(update: Update, context: CallbackContext) -> None:
    await update.callback_query.message.reply_text("Пожалуйста, введите новое имя:")
    return CHANGE_NAME

async def change_name(update: Update, context: CallbackContext) -> int:
    from main import conn, user_names, user_state  # Import here to avoid circular import
    user = update.message.from_user
    user_id = user.id
    new_name = update.message.text

    # Обновляем имя пользователя в словаре
    user_names[user.id] = new_name

     # Обновляем имя пользователя в базе данных
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        conn.commit()
        logger.info(f"Имя пользователя {user_id} изменено на {new_name} в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при изменении имени пользователя в базе данных: {e}")

    # Подтверждаем, что имя изменено
    await update.message.reply_text(f"Ваше имя изменено на '{new_name}'.")
    user_state[user.id] = "name_entered" # Update user state

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

    return ConversationHandler.END # End conversation

async def change_name_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Смена имени отменена.")
    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END