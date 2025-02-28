# handlers/location.py
import logging
import json
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, CallbackContext, WebAppInfo
from geopy.distance import geodesic
from datetime import datetime
from utils import GMT_PLUS_5
from config import GET_LOCATION_URL
from helpers import get_queue, is_user_in_queue

logger = logging.getLogger(__name__)
max_distance = 250

async def handle_web_app_data(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    """Обрабатываем данные с Web App (геолокацию)."""
    try:
        data = json.loads(update.message.web_app_data.data)
        logger.info(f"Получены данные от Web App: {data}")
        lat = data.get("lat")
        lon = data.get("lon")

        logger.info(f"Получены данные от Web App: {data}")  # Логируем входные данные

        if not lat or not lon:
            await update.message.reply_text("Ошибка: не удалось получить координаты.")
            return

        queue_name = context.user_data.get("queue_name")
        user_id = context.user_data.get("user_id")

        if not queue_name:
            await update.message.reply_text("Ошибка: не найдена очередь.")
            return

        queue = await get_queue(queue_name)
        if not queue:
            await update.message.reply_text("Ошибка: очередь не найдена.")
            return

        if queue is None:
            await update.message.reply_text("Ошибка: очередь не найдена.")
            return

        target_coordinates = (queue["latitude"], queue["longitude"])
        user_coord = (lat, lon)
        distance = geodesic(user_coord, target_coordinates).meters

        if distance <= max_distance:
            try:
                join_time = datetime.now(GMT_PLUS_5).isoformat()
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO queue_users (queue_name, user_id, join_time) VALUES (?, ?, ?)", (queue_name, user_id, join_time))
                conn.commit()
                logger.info(f"Пользователь {user_id} добавлен в очередь '{queue_name}'")
            except Exception as e:
                logger.error(f"Ошибка при добавлении пользователя: {e}")
                await update.message.reply_text("Произошла ошибка при записи в очередь.")
                return

            await update.message.reply_text(f"Вы записаны в очередь '{queue_name}'.")
        else:
            await update.message.reply_text("Слишком далеко для записи в очередь.")

    except Exception as e:
        logger.error(f"Ошибка в обработке Web App данных: {e}")
        await update.message.reply_text("Произошла ошибка при обработке геолокации.")


async def ask_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    queue_name = query.data.split("_")[2]
    context.user_data['queue_name'] = queue_name
    user_id = update.effective_user.id  # store user_id
    context.user_data['user_id'] = user_id  # store user_id

    # 1. Проверить, что пользователь еще не записан
    is_in_queue_bool = await is_user_in_queue(queue_name, user_id)
    if is_in_queue_bool:
        await query.edit_message_text("Вы уже записаны в эту очередь.")
        return

    # 2. Получаем очередь и время из базы данных
    queue = await get_queue(queue_name)
    if not queue:
        await update.effective_message.reply_text("Ошибка: очередь не найдена.")
        return

    # 3. Проверяем наступило ли время для записи
    queue_start_time = queue["start_time"]
    now = datetime.now(GMT_PLUS_5)

    if queue_start_time > now:
        await query.edit_message_text(f"Запись на эту очередь начнется {queue_start_time.strftime('%d.%m.%Y %H:%M')}")
        return

    # Сохраняем имя очереди, чтобы было ясно, что локацию ждут только для ask_location
    context.user_data["expecting_location_for"] = queue_name

    # Генерируем location_request_id
    location_request_id = str(uuid.uuid4())
    context.user_data["location_request_id"] = location_request_id

    # Создаем кнопку **ReplyKeyboardMarkup**, а не Inline
    keyboard = [
        [KeyboardButton("Отправить геолокацию", web_app=WebAppInfo(url=GET_LOCATION_URL))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    # Отправляем сообщение с кнопкой
    sent_message = await query.message.reply_text(
        f"Для записи в очередь '{queue_name}', нажмите кнопку и отправьте вашу геолокацию:",
        reply_markup=reply_markup
    )

    # Сохраняем ID сообщения
    context.user_data["location_message_id"] = sent_message.message_id