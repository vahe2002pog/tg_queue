import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackContext

logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> None:
    from main import conn, user_names, user_state  # Import here to avoid circular import
    user = update.message.from_user
    user_id = user.id

    # Получаем имя пользователя из базы данных
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result:
        user_name = result[0]
        user_names[user_id] = user_name  # Load into memory
        user_state[user_id] = "name_entered"
        keyboard = [
            [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
            [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Показываем клавиатуру выбора, если имя уже введено
        await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

    else:
        # Запрашиваем имя, если оно еще не введено
        await update.message.reply_text("Привет! Пожалуйста, введите ваше имя:")
        user_state[user_id] = "waiting_for_name"

async def set_name(update: Update, context: CallbackContext) -> None:
    from main import conn, user_names, user_state  # Import here to avoid circular import
    user = update.message.from_user
    user_id = user.id
    user_name = update.message.text  # Получаем введенное имя

    # Сохраняем имя пользователя в базу данных
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, name) VALUES (?, ?)", (user_id, user_name))
        conn.commit()
        logger.info(f"Имя пользователя {user_name} сохранено в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении имени пользователя в базе данных: {e}")

    # Сохраняем имя пользователя в словарь
    user_names[user.id] = user_name

    # Подтверждаем, что имя сохранено
    await update.message.reply_text(f"Ваше имя '{user_name}' сохранено.")
    
    # Меняем состояние, чтобы больше не запрашивать имя
    user_state[user.id] = "name_entered"

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)