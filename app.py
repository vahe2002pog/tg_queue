import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, BotCommand, LinkPreviewOptions, WebAppInfo, Message
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, ApplicationBuilder, Defaults, ConversationHandler, JobQueue
from datetime import datetime, timedelta, timezone
from config import TOKEN, ADMIN_ID, MF_COORDINATES, GET_LOCATION_URL
from geopy.distance import geodesic
import asyncio
import httpx
import sqlite3
import uuid

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

max_distance = 250

# Подключение к базе данных SQLite
DATABASE_NAME = 'queue_bot.db'

JOIN_QUEUE_PAYLOAD = "join_"

def create_connection():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        logger.info(f"Подключение к базе данных {DATABASE_NAME} выполнено успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
    return conn

def create_tables(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_name TEXT NOT NULL,
                start_time TEXT,
                latitude REAL,
                longitude REAL,
                creator_id INTEGER
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_users (
                queue_id INTEGER,
                user_id INTEGER,
                join_time TEXT,
                FOREIGN KEY (queue_id) REFERENCES queues(queue_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                PRIMARY KEY (queue_id, user_id)
            );
        """)
        conn.commit()
        logger.info("Таблицы созданы успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц: {e}")

# Инициализация соединения с базой данных и создание таблиц
conn = create_connection()
if conn:
    create_tables(conn)

# Структура данных для хранения очередей (теперь не нужна в памяти, берем из БД)
# queues = {}  # Словарь для хранения очередей
user_names = {}  # Словарь для хранения имя пользователей
user_state = {}  # Словарь для хранения состояния (запрос имени или уже введено)

# Stages для ConversationHandler
QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHANGE_NAME, CHOOSE_LOCATION = range(5) # Добавлен CHOOSE_LOCATION

target_coordinates = MF_COORDINATES

# Часовой пояс GMT+5
GMT_PLUS_5 = timezone(timedelta(hours=5))

# Функция для отправки уведомлений пользователям
async def send_notification(user_id: int, message: str, context: CallbackContext):
    try:
        await context.bot.send_message(user_id, message)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Команда /start — запросить имя пользователя
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start с deep-linking."""
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
            [InlineKeyboardButton("📋 Показать очереди", callback_data="show_queues")],
            [InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Показываем клавиатуру выбора, если имя уже введено
        await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

    else:
        # Запрашиваем имя, если оно еще не введено
        await update.message.reply_text("Привет! Пожалуйста, введите ваше *имя*:", parse_mode="Markdown")
        user_state[user_id] = "waiting_for_name"

# Обработчик нажатий на кнопки главного меню
async def main_menu_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_queues":
        await show_queues(update, context)
    elif query.data == "change_name":
        await change_name_start(update, context)

# Обработчик ввода имя пользователя
async def set_name(update: Update, context: CallbackContext) -> None:
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
    await update.message.reply_text(f"✅ Ваше имя *{user_name}* сохранено.", parse_mode="Markdown")
    
    # Меняем состояние, чтобы больше не запрашивать имя
    user_state[user.id] = "name_entered"

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("📋 Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

# Обработчик начала смены имени
async def change_name_start(update: Update, context: CallbackContext) -> None:
    await update.callback_query.message.reply_text("🔄 Пожалуйста, введите новое *имя*:", parse_mode="Markdown")
    return CHANGE_NAME

# Обработчик получения нового имени
async def change_name(update: Update, context: CallbackContext) -> int:
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
    await update.message.reply_text(f"✅ Ваше имя изменено на *{new_name}*.", parse_mode="Markdown")
    user_state[user_id] = "name_entered" # Update user state

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("📋 Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

    return ConversationHandler.END # End conversation

# Обработчик отмены смены имени
async def change_name_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Смена имени отменена.")
    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("📋 Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END

# Обработчик начала создания очереди
async def create_queue_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "📌 *Создание очереди*\n\n"
        "🔹 Введите *название очереди*.\n"
        "❌ Для отмены введите /cancel",
        parse_mode="Markdown"
    )
    return QUEUE_NAME

# Обработчик получения названия очереди
async def create_queue_name(update: Update, context: CallbackContext) -> int:
    context.user_data['queue_name'] = update.message.text
    await update.message.reply_text(
        f"✅ *Название очереди:* `{update.message.text}`\n\n"
        "📅 Теперь введите *дату начала* в формате _ДД.ММ.ГГ_.\n"
        "📆 Чтобы выбрать *сегодняшнюю дату*, введите /today.\n"
        "❌ Для отмены введите /cancel.",
        parse_mode="Markdown"
    )
    return QUEUE_DATE

# Обработчик получения даты очереди
async def create_queue_date(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip()

    if user_input == "/today":
        today = datetime.now(GMT_PLUS_5).strftime("%d.%m.%y")
        context.user_data['queue_date'] = today
        await update.message.reply_text(
            f"✅ *Дата выбрана:* `{today}` 📆\n\n"
            "🕒 Теперь введите *время начала* в формате _ЧЧ:ММ_.\n"
            "⏰ Чтобы выбрать *текущее время*, введите /now.\n"
            "❌ Для отмены введите /cancel.",
            parse_mode="Markdown"
        )
        return QUEUE_TIME

    try:
        datetime.strptime(user_input, "%d.%m.%y")
    except ValueError:
        await update.message.reply_text(
            "⚠️ *Ошибка:* Неверный формат даты.\n\n"
            "📅 Пожалуйста, используйте _ДД.ММ.ГГ_ или введите /today для выбора сегодняшней даты.",
            parse_mode="Markdown"
        )
        return QUEUE_DATE

    context.user_data['queue_date'] = user_input
    await update.message.reply_text(
        "📅 *Дата сохранена!* ✅\n\n"
        "🕒 Теперь введите *время начала* в формате _ЧЧ:ММ_.\n"
        "❌ Для отмены введите /cancel.",
        parse_mode="Markdown"
    )
    return QUEUE_TIME

# Обработчик получения времени очереди
async def create_queue_time(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip()

    if user_input == "/now":
        now_time = datetime.now(GMT_PLUS_5).strftime("%H:%M")
        context.user_data['queue_time'] = now_time
        await update.message.reply_text(
            f"✅ *Выбрано текущее время:* `{now_time}` ⏰\n\n"
            "📍 Теперь выберите *местоположение очереди*:",
            parse_mode="Markdown"
        )
    else:
        try:
            datetime.strptime(update.message.text, "%H:%M")
        except ValueError:
            await update.message.reply_text(
                "⚠️ *Ошибка:* Неверный формат времени.\n\n"
                "⏰ Пожалуйста, используйте _ЧЧ:ММ_ или введите /now для выбора текущего времени.",
                parse_mode="Markdown"
            )
            return QUEUE_TIME

        context.user_data['queue_time'] = update.message.text

    # Кнопки выбора местоположения
    keyboard = [
        [InlineKeyboardButton("🏛 МатФак", callback_data="location_mathfac")],
        [InlineKeyboardButton("📍 Указать геолокацию", callback_data="location_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🌍 *Выберите местоположение очереди:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CHOOSE_LOCATION

# Обработчик выбора местоположения очереди
async def create_queue_location(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "location_mathfac":
        context.user_data['latitude'] = target_coordinates[0]  # Координаты МатФака
        context.user_data['longitude'] = target_coordinates[1]  
        await create_queue_final(update, context)
        return ConversationHandler.END

    elif query.data == "location_custom":
        await query.message.edit_text(
            "📍 *Пожалуйста, отправьте вашу геолокацию* для создания очереди:",
            parse_mode="Markdown"
        )
        return CHOOSE_LOCATION

async def create_queue_location_custom(update: Update, context: CallbackContext) -> int:
    location = update.message.location
    context.user_data['latitude'] = location.latitude
    context.user_data['longitude'] = location.longitude
    await create_queue_final(update, context)
    return ConversationHandler.END

# Функция для завершения создания очереди
async def create_queue_final(update: Update, context: CallbackContext) -> None:
    name = context.user_data['queue_name']
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    latitude = context.user_data['latitude']
    longitude = context.user_data['longitude']

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    except ValueError:
        await update.effective_message.reply_text(
            "❌ *Ошибка:* Неверный формат даты или времени. Пожалуйста, проверьте ввод.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Преобразуем время в GMT+5
    start_time_gmt5 = start_time.replace(tzinfo=GMT_PLUS_5)

    # Сохраняем очередь в базу данных
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO queues (queue_name, start_time, latitude, longitude, creator_id) VALUES (?, ?, ?, ?, ?)",
                       (name, start_time_gmt5.isoformat(), latitude, longitude, update.effective_user.id)) #Сохраняем ID создателя
        conn.commit()
        logger.info(f"Очередь {name} успешно сохранена в базе данных с координатами.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении очереди в базе данных: {e}")

    # Отправляем локацию (карты)
    location_message = await update.effective_message.reply_location(
        latitude=latitude,
        longitude=longitude,
        reply_markup=None
    )

    #Создаем deeplink
    #deeplink = f"https://t.me/{context.bot.username}?start=join_{name}"
    # Вместо имени очереди используем queue_id
    queue_id = await get_queue_id_by_name(name)
    if not queue_id:
        await update.effective_message.reply_text("❌ Ошибка: Не удалось получить ID очереди.")
        return

    deeplink = f"https://t.me/{context.bot.username}?start=join_{queue_id}"
    # Создаем кнопку для присоединения (теперь это URL-кнопка)
    keyboard = [
        [InlineKeyboardButton("📌 Присоединиться к очереди", url=deeplink)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с информацией и кнопкой
    queue_message = await update.effective_message.reply_text(
        f"✅ Очередь *{name}* успешно создана! 🕒\n"
        f"📆 Дата: *{start_time.strftime('%d.%m.%y')}*\n"
        f"⏰ Время: *{start_time.strftime('%H:%M')}*\n\n"
        f"📍 *Локация:* (смотрите выше)\n\n"
        f"➡ *Нажмите кнопку, чтобы присоединиться!*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True) #Отключаем предпросмотр ссылки
    )

    # Сохраняем ID сообщений (если нужно для удаления)
    context.user_data['queue_message_id'] = queue_message.message_id
    context.user_data['location_message_id'] = location_message.message_id

    # Автоматическое удаление очереди через 5 часов
    #context.job_queue.run_once(delete_queue_job, 5 * 3600, name)  # 5 hours in секундах
    time_until_deletion = (start_time_gmt5 + timedelta(hours=5)) - datetime.now(GMT_PLUS_5)
    seconds_until_deletion = max(time_until_deletion.total_seconds(), 0)  # Не даем отрицательные значения

    # Планируем удаление
    context.job_queue.run_once(delete_queue_job, seconds_until_deletion, queue_id)
    context.user_data.pop('queue_name', None)

    return ConversationHandler.END

async def handle_deeplink(update: Update, context: CallbackContext) -> None:
    """Handles deeplink when user starts the bot."""
    if update.message:
        message_text = update.message.text
        logger.info(f"Получено сообщение: {update.message.text}")

        if not message_text.startswith("/start"):
            return

        if len(message_text.split()) > 1:
            payload = message_text.split()[1]
            if payload.startswith("join_"):
                try:
                    queue_id = int(payload[5:])
                except ValueError:
                    await update.message.reply_text("❌ Неверный формат ID очереди.")
                    return

                user_id = update.effective_user.id
                queue = await get_queue_by_id(queue_id)
                if not queue:
                    await update.message.reply_text("❌ Очередь не найдена.")
                    return

                cursor = conn.cursor()
                cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()

                if not result:
                    await update.message.reply_text(
                        "📌 Для начала введите ваше *имя* с помощью команды /start.",
                        parse_mode="Markdown"
                    )
                    return

                context.user_data['queue_id'] = queue_id
                context.user_data['user_id'] = user_id

                # Вызываем ask_location с использованием update.message
                await ask_location_from_message(update.message, context) #Изменено
    elif update.callback_query:
        #Если это CallbackQuery
        pass #Этот код не должен вызываться никогда
    else:
         await update.message.reply_text("❌ Неизвестный тип запроса.")

# Функция для автоматического удаления очереди
async def delete_queue_job(context: CallbackContext) -> None:
    queue_id = context.job.data

    # Получаем название очереди перед удалением
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        logger.error(f"Не удалось получить имя очереди с ID {queue_id}")
        return

    # Удаляем очередь из базы данных
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queues WHERE queue_id = ?", (queue_id,))
        conn.commit()
        logger.info(f"Очередь {queue_name} (ID {queue_id}) удалена из базы данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении очереди с ID {queue_id} из базы данных: {e}")

    # Также нужно удалить записи из queue_users
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_id = ?", (queue_id,))
        conn.commit()
        logger.info(f"Записи queue_users для очереди {queue_name} (ID {queue_id}) удалены")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении записей queue_users для очереди {queue_name} (ID {queue_id}): {e}")

    # Отправляем уведомление администратору об удалении очереди
    await context.bot.send_message(ADMIN_ID, f"✅ Очередь {queue_name} (ID {queue_id}) была автоматически удалена.", parse_mode="Markdown")
    logger.info(f"Очередь {queue_name} (ID {queue_id}) была автоматически удалена.")

# Обработчик отмены создания очереди
async def create_queue_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("❌ Создание очереди *отменено*.", parse_mode="Markdown")
    return ConversationHandler.END

# Команда /delete_queue — удаление очереди администратором
async def delete_queue_start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user  # Используем from_user из message
    user_id = update.effective_user.id

    # Получаем список очередей, созданных пользователем, или все очереди, если пользователь - администратор
    if user_id == ADMIN_ID:
        queues_list = await get_all_queues()
    else:
        queues_list = await get_user_created_queues(user_id)

    if not queues_list:
        await update.message.reply_text("❌ Нет доступных очередей для удаления.")
        return

    # Формируем клавиатуру с inline кнопками для каждой очереди
    keyboard = [
        [InlineKeyboardButton(queue['queue_name'], callback_data=f"delete_queue_{queue['queue_id']}")]
        for queue in queues_list
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Выберите очередь для *удаления*:", reply_markup=reply_markup, parse_mode="Markdown")


async def get_user_created_queues(user_id: int) -> list[dict]:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, queue_id, start_time FROM queues WHERE creator_id = ?", (user_id,))
        results = cursor.fetchall()

        converted_results = []
        for row in results:
            start_time_str = row[2]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None

            converted_results.append({"queue_name": row[0], "queue_id": row[1], "start_time": start_time})

        return converted_results
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка очередей, созданных пользователем, из базы данных: {e}")
        return []

# Обработчик нажатий на кнопки удаления очереди
async def delete_queue_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    queue_id = int(query.data.split("_")[2])

    # Проверяем, является ли пользователь администратором или создателем очереди
    queue = await get_queue_by_id(queue_id)
    if not queue:
        await query.edit_message_text("❌ Ошибка: Очередь не найдена.")
        return

    if user_id != ADMIN_ID and queue['creator_id'] != user_id:
        await query.edit_message_text("⚠️ Вы не можете удалить эту очередь, так как вы не являетесь ее создателем или администратором.")
        return

    queue_name = await get_queue_name_by_id(queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

     # Удаляем очередь из базы данных
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queues WHERE queue_id = ?", (queue_id,))
        conn.commit()
        logger.info(f"Очередь {queue_name} (ID {queue_id}) удалена из базы данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении очереди с ID {queue_id} из базы данных: {e}")

    # Также нужно удалить записи из queue_users
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_id = ?", (queue_id,))
        conn.commit()
        logger.info(f"Записи queue_users для очереди {queue_name} (ID {queue_id}) удалены")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении записей queue_users для очереди {queue_name} (ID {queue_id}): {e}")

    await query.edit_message_text(f"✅ Очередь *{queue_name}* успешно удалена.", parse_mode="Markdown")

# Команда /leave — показать очереди, в которых состоит пользователь, и выйти из выбранной
async def leave_queue(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("📌 Для начала введите ваше *имя* с помощью команды /start.", parse_mode="Markdown")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update, context)
    
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для выхода из очереди
    keyboard = []
    for queue in user_queues:
        keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"leave_{queue['queue_id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Выберите очередь, из которой хотите выйти:", reply_markup=reply_markup)

async def get_user_queues(update: Update, context: CallbackContext) -> list[dict]:
    user_id = update.message.from_user.id  # Получаем ID пользователя
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT queues.queue_name, queues.queue_id FROM queues
            JOIN queue_users ON queues.queue_id = queue_users.queue_id
            WHERE queue_users.user_id = ?
        """, (user_id,))
        results = cursor.fetchall()
        return [{"queue_name": row[0], "queue_id": row[1]} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очередей пользователя из базы данных: {e}")
        return []

# Обработчик нажатий на кнопки выхода из очереди
async def leave_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_id = user.id
    queue_id = int(query.data.split("_")[1])  # Извлекаем queue_id из callback_data

    # Получаем название очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    # Удаляем пользователя из очереди в базе данных
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} удален из очереди {queue_name} (ID {queue_id}) в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении пользователя из очереди в базе данных: {e}")
    
    await query.edit_message_text(f"✅ Вы вышли из очереди: *{queue_name}*.", parse_mode="Markdown")

# Команда /skip — пропуск хода
async def skip_turn(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_id = update.message.from_user.id
    user_name = user_names.get(user_id, None)

    if not user_name:
        await update.message.reply_text("📌 Для начала введите ваше *имя* с помощью команды /start.", parse_mode="Markdown")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update, context)
    
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для пропуска хода
    keyboard = []
    for queue in user_queues:
        keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"skip_{queue['queue_id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Выберите очередь, чтобы *пропустить* свой ход:", reply_markup=reply_markup, parse_mode="Markdown")

# Обработчик нажатий на кнопки пропуска хода
async def skip_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    queue_id = int(query.data.split("_")[1])  # Извлекаем queue_id из callback_data
    user_id = update.effective_user.id

    # Получаем название очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return
    
    try:
        # 1. Получаем имя из БД
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            user_name = result[0]
        else:
            await query.edit_message_text("❌ Не удалось найти ваше имя.")
            return

        # 2. Получаем очередь из базы данных
        #queue = await get_queue(queue_name)
        queue = await get_queue_by_id(queue_id)

        if not queue:
            await query.edit_message_text("❌ Такой очереди нет.")
            return

        queue_users = await get_queue_users_name(queue_id) #извлекаем имена

        if user_name not in queue_users:
             await query.edit_message_text("❌ Вы не состоите в этой очереди.")
             return

        #3. Извлекаем queue_users в числовом виде, чтобы можно было работать с очередью
        queue_users_ids = await get_queue_users_ids(queue_id) 
        if not queue_users_ids:
            await query.edit_message_text("🔍 В очереди пока нет участников.")
            return

        current_index = queue_users_ids.index(user_id)
        
        if current_index+1 < len(queue_users_ids):
            #Меняем местами текущего пользователя и следующего
            
            user1_id=queue_users_ids[current_index]
            user2_id=queue_users_ids[current_index+1]

            await swap_queue_users(queue_id,user1_id,user2_id)

            #Добавлена проверка на наличие второго пользователя, а также извлечение ника
            #Нужно извлекать не из user_names, a из БД, чтобы было актуальное инфо
            user2_name= await get_user_name(user2_id)
            if user2_name:
               await query.edit_message_text(f"✅ Вы пропустили свой ход. Ваш ход теперь после *{user2_name}*.", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Вы находитесь в конце очереди и не можете пропустить ход.")
            return


    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")

async def get_queue_users_ids(queue_id: int) -> list[int]:
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.user_id FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_id = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении участников очереди из базы данных: {e}")
        return []

async def swap_queue_users(queue_id:int, user1_id:int, user2_id:int):
    try:
        cursor = conn.cursor()
        #cursor.execute("""SELECT user_id FROM queue_users WHERE queue_name = ?""",(queue_name,))

        #1. Получаем время для 1 пользователя
        cursor.execute("""SELECT join_time FROM queue_users WHERE queue_id = ? AND user_id=?""",(queue_id,user1_id))
        result1 = cursor.fetchone()
        time1=result1[0]

         #2. Получаем время для 2 пользователя
        cursor.execute("""SELECT join_time FROM queue_users WHERE queue_id = ? AND user_id=?""",(queue_id,user2_id))
        result2 = cursor.fetchone()
        time2=result2[0]


        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_id = ? AND user_id = ?", (time2, queue_id, user1_id))
        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_id = ? AND user_id = ?", (time1, queue_id, user2_id))

        conn.commit()
        logger.info(f"Пользователи с id {user1_id} и {user2_id}  в очереди с ID {queue_id} успешно поменялись местами ")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обмене пользователями: {e}")

# Команда /queue_info — просмотр списка людей в очереди
async def queue_info(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("📌 Для начала введите ваше *имя* с помощью команды /start.", parse_mode="Markdown")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update,context)
    
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для просмотра информации о очереди
    keyboard = []
    for queue in user_queues:
        keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"info_{queue['queue_id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Выберите очередь для просмотра списка участников:", reply_markup=reply_markup)

# Обработчик нажатий на кнопки просмотра информации о очереди
async def queue_info_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_id = update.effective_user.id
    queue_id = int(query.data.split("_")[1])  # Извлекаем queue_id из callback_data

    # Получаем название очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

     # Получаем список участников очереди из базы данных
    users_list = await get_queue_users_name(queue_id)
    if not users_list:
        await query.edit_message_text("🔍 В очереди пока нет участников.")
        return

    # Формируем сообщение со списком участников
    users_text = ""
    queue_users_ids = await get_queue_users_ids(queue_id)

    for i, user_id in enumerate(queue_users_ids):
        user_name = await get_user_name(user_id)
        if user_name:
           users_text += f"{i+1}. {user_name}\n"
        else:
           users_text += f"{i+1}. (Пользователь не найден)\n"
           

    await query.edit_message_text(f"📋 Список участников очереди {queue_name}:\n{users_text}")

#Функция для получения имен пользователей
async def get_queue_users_name(queue_id: int) -> list[str]:
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.name FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_id = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении участников очереди из базы данных: {e}")
        return []

#Добавлена функция для извлечения имени по id
async def get_user_name(user_id: int)->str | None:
    try:
        cursor = conn.cursor()
        cursor.execute("""SELECT name FROM users WHERE user_id = ?""",(user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени из базы данных: {e}")
        return None

# Функция для отображения списка очередей
async def show_queues(update: Update, context: CallbackContext) -> None:
   # Получаем список очередей из базы данных
    queues_list = await get_all_queues()

    if queues_list:
        keyboard = []
        for queue in queues_list:  # Iterate over the queues
            #keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"join_queue_{queue['queue_name']}")])
            keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"join_queue_{queue['queue_id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text("📋 Выберите очередь для записи:", reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text("❌ Нет доступных очередей.")

async def get_all_queues() -> list[dict]:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, queue_id, start_time FROM queues")
        results = cursor.fetchall()
        
        #Конвертируем в объекты datetime
        converted_results = []
        for row in results:
            start_time_str = row[2]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None #Если время не найдено - ставим None

            converted_results.append({"queue_name": row[0], "queue_id":row[1],"start_time":start_time})
        
        return converted_results
    
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка очередей из базы данных: {e}")
        return []
async def skip_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    queue_id = int(query.data.split("_")[1])  # Извлекаем queue_id из callback_data
    user_id = update.effective_user.id

    # Получаем название очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return
    
    try:
        # 1. Получаем имя из БД
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            user_name = result[0]
        else:
            await query.edit_message_text("❌ Не удалось найти ваше имя.")
            return

        # 2. Получаем очередь из базы данных
        queue = await get_queue_by_id(queue_id)
        if not queue:
            await query.edit_message_text("❌ Такой очереди нет.")
            return

        queue_users = await get_queue_users_name(queue_id)  # Извлекаем имена

        if user_name not in queue_users:
            await query.edit_message_text("❌ Вы не состоите в этой очереди.")
            return

        # 3. Извлекаем queue_users в числовом виде, чтобы можно было работать с очередью
        queue_users_ids = await get_queue_users_ids(queue_id)
        if not queue_users_ids:
            await query.edit_message_text("🔍 В очереди пока нет участников.")
            return

        current_index = queue_users_ids.index(user_id)
        
        if current_index + 1 < len(queue_users_ids):
            # Меняем местами текущего пользователя и следующего
            user1_id = queue_users_ids[current_index]
            user2_id = queue_users_ids[current_index + 1]

            await swap_queue_users(queue_id, user1_id, user2_id)

            # Добавлена проверка на наличие второго пользователя, а также извлечение ника
            user2_name = await get_user_name(user2_id)
            if user2_name:
                await query.edit_message_text(
                    f"✅ Вы пропустили свой ход. Ваш ход теперь после *{user2_name}*.", 
                    parse_mode="Markdown"
                )

                # Отправляем уведомление второму участнику
                await context.bot.send_message(
                    chat_id=user2_id,
                    text=f"ℹ️ В очереди '{queue_name}' пользователь *{user_name}* пропустил свой ход. Теперь вы перед ним.",
                    parse_mode="Markdown"
                )
        else:
            await query.edit_message_text("❌ Вы находитесь в конце очереди и не можете пропустить ход.")
            return

    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка: {str(e)}")
        
async def ask_location_from_message(message: Message, context: CallbackContext) -> None:
    """Запрашивает геолокацию пользователя, если deeplink был вызван командой /start."""

    queue_id = context.user_data.get("queue_id")

    if not queue_id:
        await message.reply_text("❌ Ошибка: Не найден ID очереди.")
        return

    # Получаем имя очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await message.reply_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    user_id = message.from_user.id  # store user_id
    context.user_data['user_id'] = user_id  # store user_id

    # Проверяем, что пользователь еще не записан
    is_in_queue = await is_user_in_queue(queue_id, user_id)
    if is_in_queue:
        await message.reply_text("✅ Вы уже записаны в эту очередь.")
        return

    # Получаем очередь и время из базы данных
    queue = await get_queue_by_id(queue_id)
    if not queue:
        await message.reply_text("❌ Ошибка: очередь не найдена.")
        return

    # Проверяем наступило ли время для записи
    queue_start_time = queue["start_time"]
    now = datetime.now(GMT_PLUS_5)

    if queue_start_time > now:
        await message.reply_text(f"⚠️ Запись на эту очередь начнется *{queue_start_time.strftime('%d.%m.%Y %H:%M')}*⏰", parse_mode="Markdown")
        return

    # Сохраняем имя очереди, чтобы было ясно, что локацию ждут только для ask_location
    context.user_data["expecting_location_for"] = queue_id

    # Создаем кнопку **ReplyKeyboardMarkup**
    keyboard = [
        [KeyboardButton("Отправить геолокацию", web_app=WebAppInfo(url=GET_LOCATION_URL))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    # Отправляем сообщение с кнопкой
    sent_message = await message.reply_text(  # Используем message.reply_text вместо query.message.edit_text
        f"📌 Для записи в очередь *{queue_name}*, нажмите *кнопку* и отправьте вашу геолокацию📍:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    # Сохраняем ID сообщения
    context.user_data["location_message_id"] = sent_message.message_id

async def ask_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    #queue_name = query.data.split("_")[2]
    queue_id = int(query.data.split("_")[2]) #Извлекаем queue_id
    #context.user_data['queue_name'] = queue_name
    context.user_data['queue_id'] = queue_id
    user_id = update.effective_user.id  # store user_id
    context.user_data['user_id'] = user_id  # store user_id
    
    # 1. Получить название очереди по ID
    queue_name = await get_queue_name_by_id(queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    # 2. Проверить, что пользователь еще не записан
    #is_in_queue = await is_user_in_queue(queue_name, user_id)
    is_in_queue = await is_user_in_queue(queue_id, user_id)
    if is_in_queue:
        await query.edit_message_text("✅ Вы уже записаны в эту очередь.")
        return

    # 3. Получаем очередь и время из базы данных
    #queue = await get_queue(queue_name)
    queue = await get_queue_by_id(queue_id)
    if not queue:
        await update.effective_message.reply_text("❌ Ошибка: очередь не найдена.")
        return

    # 4. Проверяем наступило ли время для записи
    queue_start_time = queue["start_time"]
    now = datetime.now(GMT_PLUS_5)

    if queue_start_time > now:
        await query.edit_message_text(f"⚠️ Запись на эту очередь начнется *{queue_start_time.strftime('%d.%m.%Y %H:%M')}*⏰", parse_mode="Markdown")
        return

    # Сохраняем имя очереди, чтобы было ясно, что локацию ждут только для ask_location
    #context.user_data["expecting_location_for"] = queue_name
    context.user_data["expecting_location_for"] = queue_id

    # Создаем кнопку **ReplyKeyboardMarkup**
    keyboard = [
        [KeyboardButton("Отправить геолокацию", web_app=WebAppInfo(url=GET_LOCATION_URL))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    # Отправляем сообщение с кнопкой
    sent_message = await query.message.reply_text(
        f"📌 Для записи в очередь *{queue_name}*, нажмите *кнопку* и отправьте вашу геолокацию📍:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    # Сохраняем ID сообщения
    context.user_data["location_message_id"] = sent_message.message_id

async def get_queue(queue_name: str) -> dict | None:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, start_time, latitude, longitude FROM queues WHERE queue_name = ?", (queue_name,))
        result = cursor.fetchone()
        if result:
            start_time_str = result[1]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            return {"queue_name": result[0], "start_time":start_time, "latitude": result[2], "longitude": result[3]}
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очереди из базы данных: {e}")
        return None

async def get_queue_by_id(queue_id: int) -> dict | None:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, start_time, latitude, longitude, creator_id FROM queues WHERE queue_id = ?", (queue_id,))
        result = cursor.fetchone()
        if result:
            start_time_str = result[1]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            return {"queue_name": result[0], "start_time":start_time, "latitude": result[2], "longitude": result[3], "creator_id": result[4]}
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очереди из базы данных: {e}")
        return None

async def is_user_in_queue(queue_id: int, user_id: int) -> bool:
    try:
        cursor = conn.cursor()
        #cursor.execute("SELECT 1 FROM queue_users WHERE queue_name = ? AND user_id = ?", (queue_name, user_id))
        cursor.execute("SELECT 1 FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user_id))
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при проверке пользователя в очереди: {e}")
        return False

# Обработчик для неизвестных запросов CallbackQuery
async def unknown(update: Update, context: CallbackContext) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("❌ Я не понимаю этот запрос!")

# Функция для вывода списка доступных команд
async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "/start - Начать взаимодействие с ботом (ввод имени)\n"
        "/create_queue - Создать очередь\n"
        "/delete_queue - Удалить очередь\n"
        "/leave - Покинуть очередь\n"
        "/skip - Пропустить свой ход в очереди\n"
        "/queue_info - Просмотреть список людей в очереди\n"
        "/show_queues - Показать доступные очереди и записаться в них\n"
        "/help - Получить помощь (список команд)\n"
    )
    await update.message.reply_text(help_text)

# Функция для установки меню команд
async def set_commands(app):
    commands = [
        BotCommand("start", "Начать"),
        BotCommand("create_queue", "Создать очередь"),
        BotCommand("delete_queue", "Удалить очередь"),
        BotCommand("leave", "Покинуть очередь"),
        BotCommand("skip", "Пропустить ход"),
        BotCommand("queue_info", "Список в очереди"),
        BotCommand("show_queues", "Показать очереди"),
        BotCommand("help", "Помощь"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Команды успешно установлены.")
    except httpx.ConnectError as e:
        logger.error(f"Не удалось подключиться к серверам Telegram для установки команд: {e}")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")

async def get_user_name(user_id: int)->str | None:
    try:
        cursor = conn.cursor()
        cursor.execute("""SELECT name FROM users WHERE user_id = ?""",(user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени из базы данных: {e}")
        return None

async def get_queue_id_by_name(queue_name: str) -> int | None:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_id FROM queues WHERE queue_name = ?", (queue_name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении ID очереди по имени: {e}")
        return None

async def get_queue_name_by_id(queue_id: int) -> str | None:
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name FROM queues WHERE queue_id = ?", (queue_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени очереди по ID: {e}")
        return None

def main():
    # Создаем новый цикл событий
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Создаем JobQueue
    job_queue = JobQueue()

    # Создаем Application
    builder = ApplicationBuilder().token(TOKEN)

    # Устанавливаем defaults
    defaults = Defaults(
        parse_mode=None,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        allow_sending_without_reply=True,
    )
    builder.defaults(defaults)

    # Передаем job queue в builder
    builder.job_queue(job_queue)

    application = builder.build()

    # Устанавливаем команды
    loop.run_until_complete(set_commands(application))

    # ConversationHandler для create_queue
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create_queue", create_queue_start)],
        states={
            QUEUE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_queue_name)],
            QUEUE_DATE: [MessageHandler(filters.TEXT, create_queue_date)],
            QUEUE_TIME: [MessageHandler(filters.TEXT, create_queue_time)],
            CHOOSE_LOCATION: [
                 CallbackQueryHandler(create_queue_location, pattern="^location_(mathfac|custom)$"),
                 MessageHandler(filters.LOCATION, create_queue_location_custom),
            ]
        },
        fallbacks=[CommandHandler("cancel", create_queue_cancel)],
    )

    # ConversationHandler для смены имени
    change_name_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(change_name_start, pattern="^change_name$")],
        states={
            CHANGE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_name)]
        },
        fallbacks=[CommandHandler("cancel", change_name_cancel)]
    )

    # Добавляем ConversationHandler
    application.add_handler(conv_handler)
    application.add_handler(change_name_handler)

    # Добавляем обработчик для кнопок главного меню
    application.add_handler(CallbackQueryHandler(main_menu_buttons, pattern="^(show_queues|change_name)$"))

    # Обработчики команд
    application.add_handler(CommandHandler("start", handle_deeplink, filters.Regex(JOIN_QUEUE_PAYLOAD)))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete_queue", delete_queue_start))
    application.add_handler(CommandHandler("leave", leave_queue))
    application.add_handler(CommandHandler("skip", skip_turn))
    application.add_handler(CommandHandler("queue_info", queue_info))
    application.add_handler(CommandHandler("show_queues", show_queues))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_name))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    # Обработчики нажатий кнопок
    application.add_handler(CallbackQueryHandler(ask_location, pattern="^join_queue_")) #Обновлен
    application.add_handler(CallbackQueryHandler(leave_button, pattern="^leave_"))
    application.add_handler(CallbackQueryHandler(skip_button, pattern="^skip_"))
    application.add_handler(CallbackQueryHandler(queue_info_button, pattern="info_"))
    application.add_handler(CallbackQueryHandler(delete_queue_button, pattern="^delete_queue_"))

    # Обработчик неизвестных callback query (это важно!)
    application.add_handler(CallbackQueryHandler(unknown))

    # Запускаем приложение
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    # Закрываем соединение с базой данных при завершении работы
    if conn:
        conn.close()
        logger.info("Соединение с базой данных закрыто")

if __name__ == "__main__":
    main()