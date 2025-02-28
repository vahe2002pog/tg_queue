import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackContext
from telegram.ext import ConversationHandler
from datetime import datetime
from utils import GMT_PLUS_5, delete_queue_job
from config import MF_COORDINATES

logger = logging.getLogger(__name__)

QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHOOSE_LOCATION = range(4)

async def create_queue_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Пожалуйста, введите название очереди:")
    return QUEUE_NAME

async def create_queue_name(update: Update, context: CallbackContext) -> int:
    context.user_data['queue_name'] = update.message.text
    await update.message.reply_text("Теперь введите дату начала очереди в формате ДД.ММ.ГГ:")
    return QUEUE_DATE

async def create_queue_date(update: Update, context: CallbackContext) -> int:
    try:
        datetime.strptime(update.message.text, "%d.%m.%y")
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Пожалуйста, используйте ДД.ММ.ГГ.")
        return QUEUE_DATE

    context.user_data['queue_date'] = update.message.text
    await update.message.reply_text("И, наконец, введите время начала очереди в формате ЧЧ:ММ:")
    return QUEUE_TIME

async def create_queue_time(update: Update, context: CallbackContext) -> int:
    try:
        datetime.strptime(update.message.text, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, используйте ЧЧ:ММ.")
        return QUEUE_TIME

    context.user_data['queue_time'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("МатФак", callback_data="location_mathfac")],
        [InlineKeyboardButton("Указать геолокацию", callback_data="location_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите местоположение очереди:", reply_markup=reply_markup)
    return CHOOSE_LOCATION

async def create_queue_location(update: Update, context: CallbackContext) -> int:
    from main import conn #Избавились от циклических зависимостей
    query = update.callback_query
    await query.answer()

    if query.data == "location_mathfac":
        context.user_data['latitude'] = MF_COORDINATES[0] #Mathfac-> target coordinates
        context.user_data['longitude'] = MF_COORDINATES[1] #Mathfac-> target coordinates
        await create_queue_final(update, context)
        return ConversationHandler.END

    elif query.data == "location_custom":
        await update.message.reply_text("Пожалуйста, отправьте геолокацию для очереди:")
        return CHOOSE_LOCATION

async def create_queue_location_custom(update: Update, context: CallbackContext) -> int:
    location = update.message.location
    context.user_data['latitude'] = location.latitude
    context.user_data['longitude'] = location.longitude
    await create_queue_final(update, context)
    return ConversationHandler.END

async def create_queue_final(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    name = context.user_data['queue_name']
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    latitude = context.user_data['latitude']
    longitude = context.user_data['longitude']

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    except ValueError:
        await update.effective_message.reply_text("Произошла ошибка при создании очереди. Проверьте формат даты и времени.")
        return ConversationHandler.END

    # Преобразуем время в GMT+5
    start_time_gmt5 = start_time.replace(tzinfo=GMT_PLUS_5)

    # Сохраняем очередь в базу данных
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO queues (queue_name, start_time, latitude, longitude) VALUES (?, ?, ?, ?)",
                       (name, start_time_gmt5.isoformat(), latitude, longitude))
        conn.commit()
        logger.info(f"Очередь '{name}' сохранена в базе данных с координатами")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении очереди в базе данных: {e}")

    await update.effective_message.reply_text(f"Очередь '{name}' создана и будет доступна с {start_time.strftime('%d.%m.%y %H:%M')}.")
    
    # Автоматическое удаление очереди через 5 часов
    context.job_queue.run_once(delete_queue_job, 5 * 3600, name)  # 5 hours in seconds

async def create_queue_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Создание очереди отменено.")
    return ConversationHandler.END