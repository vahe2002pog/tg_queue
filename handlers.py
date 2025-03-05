# handlers.py
import logging
import json
from telegram import Update,  Message, BotCommand, ReplyKeyboardRemove
from telegram.ext import  ContextTypes,  CallbackContext,  ConversationHandler, JobQueue
from datetime import datetime
from geopy.distance import geodesic

from config import *
from db import (
     update_user_state, get_user_data, set_user_name, update_user_name,
    get_all_queues, get_user_created_queues, get_queue_by_id, get_queue_name_by_id, get_queue_id_by_name,
    get_queue_users_names, get_queue_users_ids, get_user_name, is_user_in_queue, get_user_queues,
    delete_queue, swap_queue_users,  insert_queue, remove_user_from_queue,
    insert_broadcast, get_broadcasts, delete_broadcast
)
from utils import (
    build_main_menu, build_location_menu, validate_date,
    validate_time, check_distance_and_join, create_join_queue_button,
    send_queue_created_message, build_queues_menu, build_delete_queue_menu, build_leave_queue_menu,
    build_skip_turn_menu, build_queue_info_menu, generate_queue_info_message, build_web_app_location_button
)

logger = logging.getLogger(__name__)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка команды /start."""
    user = update.message.from_user
    user_id = user.id
    conn = context.bot_data['conn']

    result = get_user_data(conn, user_id)
    if result:
        reply_markup = build_main_menu()
        await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Привет! Пожалуйста, введите ваше *имя*:", parse_mode="Markdown")
        update_user_state(conn, user_id, "waiting_for_name")

async def set_name(update: Update, context: CallbackContext) -> None:
    """Обработчик ввода имени пользователя."""
    user = update.message.from_user
    user_id = user.id
    user_name = update.message.text
    conn = context.bot_data['conn']

    set_user_name(conn, user_id, user_name)
    await update.message.reply_text(f"✅ Ваше имя *{user_name}* сохранено.", parse_mode="Markdown")
    update_user_state(conn, user_id, "name_entered")

    reply_markup = build_main_menu()
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

async def change_name_start(update: Update, context: CallbackContext) -> None:
    """Обработчик начала смены имени."""
    await update.callback_query.message.reply_text("🔄 Пожалуйста, введите новое *имя*:", parse_mode="Markdown")
    return CHANGE_NAME

async def change_name(update: Update, context: CallbackContext) -> int:
    """Обработчик получения нового имени."""
    user = update.message.from_user
    user_id = user.id
    new_name = update.message.text
    conn = context.bot_data['conn']

    update_user_name(conn, user_id, new_name)
    await update.message.reply_text(f"✅ Ваше имя изменено на *{new_name}*.", parse_mode="Markdown")
    update_user_state(conn, user_id, "name_entered")

    reply_markup = build_main_menu()
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END

async def create_queue_start(update: Update, context: CallbackContext) -> int:
    """Обработчик начала создания очереди."""
    await update.message.reply_text(
        "📌 *Создание очереди*\n\n"
        "🔹 Введите *название очереди*.\n",
        parse_mode="Markdown"
    )
    return QUEUE_NAME

async def create_queue_name(update: Update, context: CallbackContext) -> int:
    """Обработчик получения названия очереди."""
    context.user_data['queue_name'] = update.message.text
    await update.message.reply_text(
        f"✅ *Название очереди:* `{update.message.text}`\n\n"
        "📅 Теперь введите *дату начала* в формате _ДД.ММ.ГГ_.\n"
        "📆 Чтобы выбрать *сегодняшнюю дату*, введите /today.\n",
        parse_mode="Markdown"
    )
    return QUEUE_DATE

async def create_queue_date(update: Update, context: CallbackContext) -> int:
    """Обработчик получения даты очереди."""
    user_input = update.message.text.strip()

    if user_input == "/today":
        today = datetime.now(GMT_PLUS_5).strftime("%d.%m.%y")
        context.user_data['queue_date'] = today
        await update.message.reply_text(
            f"✅ *Дата выбрана:* `{today}` 📆\n\n"
            "🕒 Теперь введите *время начала* в формате _ЧЧ:ММ_.\n"
            "⏰ Чтобы выбрать *текущее время*, введите /now.\n",
            parse_mode="Markdown"
        )
        return QUEUE_TIME

    if not validate_date(user_input):
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
        "⏰ Чтобы выбрать *текущее время*, введите /now.\n",
        parse_mode="Markdown"
    )
    return QUEUE_TIME

async def create_queue_time(update: Update, context: CallbackContext) -> int:
    """Обработчик получения времени очереди."""
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
        if not validate_time(update.message.text):
            await update.message.reply_text(
                "⚠️ *Ошибка:* Неверный формат времени.\n\n"
                "⏰ Пожалуйста, используйте _ЧЧ:ММ_ или введите /now для выбора текущего времени.",
                parse_mode="Markdown"
            )
            return QUEUE_TIME

        context.user_data['queue_time'] = update.message.text

    reply_markup = build_location_menu()
    await update.message.reply_text(
        "🌍 *Выберите местоположение очереди:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CHOOSE_LOCATION

async def create_queue_location(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора местоположения очереди."""
    query = update.callback_query
    await query.answer()

    if query.data == "location_mathfac":
        context.user_data['latitude'] = MF_COORDINATES[0]
        context.user_data['longitude'] = MF_COORDINATES[1]
        await create_queue_final(update, context)
        return ConversationHandler.END

    elif query.data == "location_custom":
        await query.message.edit_text(
            "📍 *Пожалуйста, отправьте вашу геолокацию* для создания очереди:",
            parse_mode="Markdown"
        )
        return CHOOSE_LOCATION

async def create_queue_location_custom(update: Update, context: CallbackContext) -> int:
    """Обработчик получения кастомной геолокации."""
    location = update.message.location
    context.user_data['latitude'] = location.latitude
    context.user_data['longitude'] = location.longitude
    await create_queue_final(update, context)
    return ConversationHandler.END

async def create_queue_final(update: Update, context: CallbackContext) -> None:
    """Завершает создание очереди."""
    name = context.user_data['queue_name']
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    latitude = context.user_data['latitude']
    longitude = context.user_data['longitude']
    conn = context.bot_data['conn']

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    except ValueError:
        await update.effective_message.reply_text(
            "❌ *Ошибка:* Неверный формат даты или времени. Пожалуйста, проверьте ввод.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    start_time_gmt5 = start_time.replace(tzinfo=GMT_PLUS_5)
    insert_queue(conn, name, start_time_gmt5, latitude, longitude, update.effective_user.id)

    location_message = await update.effective_message.reply_location(
        latitude=latitude,
        longitude=longitude,
        reply_markup=None
    )

    queue_id = get_queue_id_by_name(conn, name)
    if not queue_id:
        await update.effective_message.reply_text("❌ Ошибка: Не удалось получить ID очереди.")
        return

    reply_markup = await create_join_queue_button(context, queue_id)
    queue_message = await send_queue_created_message(update, context, name, start_time, reply_markup)

    context.user_data['queue_message_id'] = queue_message.message_id
    context.user_data['location_message_id'] = location_message.message_id

    time_until_deletion = (start_time_gmt5 + timedelta(hours=5)) - datetime.now(GMT_PLUS_5)
    seconds_until_deletion = max(time_until_deletion.total_seconds(), 0)
    context.job_queue.run_once(delete_queue_job, seconds_until_deletion, data=queue_id)
    context.user_data.pop('queue_name', None)

    return ConversationHandler.END

async def handle_deeplink(update: Update, context: CallbackContext) -> None:
    """Обрабатывает deeplink."""
    conn = context.bot_data['conn']
    if update.message:
        message_text = update.message.text
        logger.info(f"Получено сообщение: {message_text}")

        if not message_text.startswith("/start") or len(message_text.split()) <= 1:
            return

        payload = message_text.split()[1]
        if payload.startswith("join_"):
            try:
                queue_id = int(payload[5:])
            except ValueError:
                await update.message.reply_text("❌ Неверный формат ID очереди.")
                return

            user_id = update.effective_user.id
            queue = await get_queue_by_id(conn, queue_id)
            if not queue:
                await update.message.reply_text("❌ Очередь не найдена.")
                return

            if not get_user_data(conn, user_id):
                await update.message.reply_text(
                    "📌 Для начала введите ваше *имя* с помощью команды /start.",
                    parse_mode="Markdown"
                )
                return

            context.user_data['queue_id'] = queue_id
            context.user_data['user_id'] = user_id
            await ask_location(update, context)
    elif update.callback_query:
        pass  # Не должно вызываться

async def delete_queue_job(context: CallbackContext) -> None:
    """Автоматически удаляет очередь."""
    queue_id = context.job.data
    conn = context.bot_data['conn']
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        logger.error(f"Не удалось получить имя очереди с ID {queue_id}")
        return

    delete_queue(conn, queue_id)
    await context.bot.send_message(ADMIN_ID, f"✅ Очередь {queue_name} (ID {queue_id}) была автоматически удалена.", parse_mode="Markdown")
    logger.info(f"Очередь {queue_name} (ID {queue_id}) была автоматически удалена.")

async def delete_queue_start(update: Update, context: CallbackContext) -> None:
    """Начинает процесс удаления очереди (показывает список)."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']

    queues_list = get_all_queues(conn) if user_id == ADMIN_ID else get_user_created_queues(conn, user_id)
    if not queues_list:
        await update.message.reply_text("❌ Нет доступных очередей для удаления.")
        return

    reply_markup = build_delete_queue_menu(queues_list)
    await update.message.reply_text("📋 Выберите очередь для *удаления*:", reply_markup=reply_markup, parse_mode="Markdown")

async def delete_queue_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки удаления очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']

    user_id = update.effective_user.id
    queue_id = int(query.data.split("_")[2])
    queue = await get_queue_by_id(conn, queue_id)

    if not queue:
        await query.edit_message_text("❌ Ошибка: Очередь не найдена.")
        return

    if user_id != ADMIN_ID and queue['creator_id'] != user_id:
        await query.edit_message_text("⚠️ Вы не можете удалить эту очередь.")
        return

    queue_name = get_queue_name_by_id(conn, queue_id)
    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    delete_queue(conn, queue_id)
    await query.edit_message_text(f"✅ Очередь *{queue_name}* успешно удалена.", parse_mode="Markdown")

async def leave_queue(update: Update, context: CallbackContext) -> None:
    """Показывает очереди, в которых состоит пользователь, для выхода."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.", parse_mode="Markdown")
        return

    user_queues = get_user_queues(conn, user_id)
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в очередях.")
        return

    reply_markup = build_leave_queue_menu(user_queues)
    await update.message.reply_text("📋 Выберите очередь для выхода:", reply_markup=reply_markup)

async def leave_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки выхода из очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']

    user_id = query.from_user.id
    queue_id = int(query.data.split("_")[1])
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    remove_user_from_queue(conn, queue_id, user_id)
    await query.edit_message_text(f"✅ Вы вышли из очереди: *{queue_name}*.", parse_mode="Markdown")

async def skip_turn(update: Update, context: CallbackContext) -> None:
    """Показывает очереди пользователя для пропуска хода."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.", parse_mode="Markdown")
        return

    user_queues = get_user_queues(conn, user_id)
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в очередях.")
        return

    reply_markup = build_skip_turn_menu(user_queues)
    await update.message.reply_text("Выберите очередь, чтобы *пропустить* ход:", reply_markup=reply_markup, parse_mode="Markdown")

async def skip_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки пропуска хода."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    queue_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    user_name = get_user_name(conn, user_id)
    if not user_name:
            await query.edit_message_text("❌ Не удалось найти ваше имя.")
            return

    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        await query.edit_message_text("❌ Такой очереди нет.")
        return

    queue_users_ids = get_queue_users_ids(conn, queue_id)
    if not queue_users_ids:
        await query.edit_message_text("🔍 В очереди пока нет участников.")
        return

    if user_id not in queue_users_ids:
        await query.edit_message_text("❌ Вы не состоите в этой очереди.")
        return

    current_index = queue_users_ids.index(user_id)

    if current_index + 1 < len(queue_users_ids):
        user1_id = queue_users_ids[current_index]
        user2_id = queue_users_ids[current_index + 1]
        swap_queue_users(conn, queue_id, user1_id, user2_id)
        user2_name = get_user_name(conn, user2_id)

        if user2_name:
            await query.edit_message_text(f"✅ Вы пропустили ход. Теперь после *{user2_name}*.", parse_mode="Markdown")
            await context.bot.send_message(chat_id=user2_id, text=f"ℹ️ Теперь вы перед *{user_name}* в '{queue_name}'.", parse_mode="Markdown")
    else:
        await query.edit_message_text("❌ Вы в конце очереди, нельзя пропустить.")

async def queue_info(update: Update, context: CallbackContext) -> None:
    """Показывает очереди пользователя для просмотра информации."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.", parse_mode="Markdown")
        return

    user_queues = get_user_queues(conn, user_id)
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в очередях.")
        return

    reply_markup = build_queue_info_menu(user_queues)
    await update.message.reply_text("Выберите очередь:", reply_markup=reply_markup)

async def queue_info_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки просмотра информации об очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    callback_data = query.data
    data_parts = callback_data.split("_")

    if len(data_parts) >= 2 and data_parts[1].isdigit():
        queue_id = int(data_parts[1])
    elif len(data_parts) >= 3 and data_parts[2].isdigit():
        queue_id = int(data_parts[2])
    else:
        await query.message.reply_text("❌ Ошибка: Неверный формат данных.")
        return

    message = await generate_queue_info_message(conn, queue_id)
    await query.edit_message_text(message)

async def show_queues(update: Update, context: CallbackContext) -> None:
    """Отображает список доступных очередей."""
    conn = context.bot_data['conn']
    queues_list = get_all_queues(conn)

    if queues_list:
        reply_markup = build_queues_menu(queues_list)
        await update.effective_message.reply_text("Выберите очередь:", reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text("❌ Нет доступных очередей.")

async def handle_web_app_data(update: Update, context: CallbackContext) -> None:
    """Обрабатывает данные Web App (геолокацию)."""
    conn = context.bot_data['conn']
    try:
        data = json.loads(update.message.web_app_data.data)
        lat = data.get("lat")
        lon = data.get("lon")

        if not lat or not lon:
            await update.message.reply_text("❌ Ошибка: не удалось получить координаты.", reply_markup=ReplyKeyboardRemove())
            return

        queue_id = context.user_data.get("queue_id")
        user_id = context.user_data.get("user_id")

        if not queue_id:
            await update.message.reply_text("❌ Ошибка: не найдена очередь.", reply_markup=ReplyKeyboardRemove())
            return

        await check_distance_and_join(update, context, queue_id, user_id, lat, lon)

    except Exception as e:
        logger.error(f"Ошибка в обработке Web App данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка.", reply_markup=ReplyKeyboardRemove())

async def ask_location(update: Update, context: CallbackContext) -> None:
    """Запрашивает геолокацию пользователя."""
    conn = context.bot_data['conn']

    # Определение источника запроса (CallbackQuery или Message)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        data_parts = query.data.split("_")
        if len(data_parts) < 3 or not data_parts[2].isdigit():
            await message.reply_text("❌ Ошибка: Неверный формат данных.")
            return
        queue_id = int(data_parts[2])
        user_id = update.effective_user.id

    elif update.message:
        message = update.message
        queue_id = context.user_data.get("queue_id")
        user_id = message.from_user.id
        if not queue_id:
            await message.reply_text("❌ Ошибка: Не найден ID очереди.")
            return
    else:
        return

    context.user_data['queue_id'] = queue_id
    context.user_data['user_id'] = user_id

    # Предварительный показ списка участников (для обоих случаев)
    info_message = await generate_queue_info_message(conn, queue_id)
    await message.reply_text(info_message)


    if is_user_in_queue(conn, queue_id, user_id):
        await message.reply_text("✅ Вы уже записаны в эту очередь.")
        return

    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        await message.reply_text("❌ Ошибка: очередь не найдена.")
        return

    if queue["start_time"] > datetime.now(GMT_PLUS_5):
        await message.reply_text(f"⚠️ Запись начнется *{queue['start_time'].strftime('%d.%m.%Y %H:%M')}* ⏰", parse_mode="Markdown")
        return

    context.user_data["expecting_location_for"] = queue_id
    reply_markup = build_web_app_location_button()

    queue_name = queue['queue_name'] if update.callback_query else get_queue_name_by_id(conn, queue_id)
    if not queue_name:
        await message.reply_text("❌ Ошибка: Не удалось получить имя")
        return

    sent_message = await message.reply_text(
        f"📌 Для записи в '{queue_name}', нажмите *кнопку* и отправьте геолокацию 📍:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data["location_message_id"] = sent_message.message_id

async def main_menu_buttons(update: Update, context: CallbackContext) -> None:
    """Обработчик кнопок главного меню."""
    query = update.callback_query
    await query.answer()

    if query.data == "show_queues":
        await show_queues(update, context)
    elif query.data == "change_name":
        await change_name_start(update, context)

async def unknown(update: Update, context: CallbackContext) -> None:
    """Обработчик неизвестных CallbackQuery."""
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("❌ Я не понимаю этот запрос!")

async def help_command(update: Update, context: CallbackContext) -> None:
    """Выводит список доступных команд."""
    help_text = (
        "/start - Начать (ввод имени)\n"
        "/cancel - Отменить\n"
        "/create_queue - Создать очередь\n"
        "/delete_queue - Удалить\n"
        "/leave - Покинуть\n"
        "/skip - Пропустить ход\n"
        "/queue_info - Список в очереди\n"
        "/show_queues - Показать очереди\n"
        "/help - Помощь (список команд)\n"
    )
    await update.message.reply_text(help_text)

async def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую команду и очищает данные."""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.",  parse_mode="Markdown") #reply_markup=ReplyKeyboardRemove(),
    return ConversationHandler.END

async def set_commands(app):
    """Устанавливает меню команд."""
    commands = [
        BotCommand("start", "Начать"),
        BotCommand("cancel", "Отмена"),
        BotCommand("queue_info", "Список в очереди"),
        BotCommand("show_queues", "Показать очереди"),
        BotCommand("leave", "Покинуть очередь"),
        BotCommand("skip", "Пропустить ход"),
        BotCommand("create_queue", "Создать очередь"),
        BotCommand("delete_queue", "Удалить очередь"),
        BotCommand("help", "Помощь"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Команды установлены.")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")

async def load_scheduled_broadcasts(job_queue: JobQueue):
    """Загружает запланированные рассылки при запуске."""
    conn = job_queue.application.bot_data['conn']
    for row in get_broadcasts(conn):
        broadcast_id, text, photo, recipients, send_time_str = row
        send_time = datetime.fromisoformat(send_time_str).replace(tzinfo=GMT_PLUS_5)
        delay = (send_time - datetime.now(GMT_PLUS_5)).total_seconds()

        if delay > 0:
            job_queue.run_once(send_broadcast, delay, data={
                'broadcast_id': broadcast_id,
                'broadcast_text': text if text else '',
                'broadcast_photo': photo if photo else '',
                'broadcast_targets': recipients
            })

async def start_broadcast(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания рассылки."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав.")
        return ConversationHandler.END

    await update.message.reply_text("📝 Введите текст сообщения/отправьте изображение:")
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: CallbackContext) -> int:
    """Обрабатывает текст/изображение для рассылки."""
    text = update.message.caption if update.message.caption else update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None
    context.user_data['broadcast_text'] = text if text else ''
    context.user_data['broadcast_photo'] = photo if photo else ''

    await update.message.reply_text("👥 Введите ID пользователей /all:")
    return BROADCAST_TARGETS

async def broadcast_targets(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор получателей."""
    if update.message.text.lower() == '/all':
        context.user_data['broadcast_targets'] = 'all'
    else:
        context.user_data['broadcast_targets'] = list(map(int, update.message.text.split()))
    await update.message.reply_text("⏰ Введите дату и время (ДД.ММ.ГГ ЧЧ:ММ):")
    return BROADCAST_SCHEDULE

async def broadcast_schedule(update: Update, context: CallbackContext) -> int:
    """Обрабатывает время отправки рассылки."""
    conn = context.bot_data['conn']
    user_input = update.message.text.strip()

    try:
        send_time = datetime.strptime(user_input, "%d.%m.%y %H:%M").replace(tzinfo=GMT_PLUS_5)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введите ДД.ММ.ГГ ЧЧ:ММ:")
        return BROADCAST_SCHEDULE

    context.user_data['broadcast_time'] = send_time
    broadcast_id = insert_broadcast(
        conn,
        context.user_data['broadcast_text'],
        context.user_data['broadcast_photo'],
        ','.join(map(str, context.user_data['broadcast_targets'])) if context.user_data['broadcast_targets'] != 'all' else 'all',
        send_time
    )

    context.job_queue.run_once(send_broadcast, (send_time - datetime.now(GMT_PLUS_5)).total_seconds(), data={
        'broadcast_id': broadcast_id,
        'broadcast_text': context.user_data['broadcast_text'],
        'broadcast_photo': context.user_data['broadcast_photo'],
        'broadcast_targets': context.user_data['broadcast_targets']
    })
    await update.message.reply_text("✅ Рассылка запланирована.")
    return ConversationHandler.END

async def send_broadcast(context: CallbackContext) -> None:
    """Отправляет рассылку."""
    conn = context.bot_data['conn']
    data = context.job.data
    text = data.get('broadcast_text', '').strip()
    photo = data.get('broadcast_photo', '').strip()
    targets = data.get('broadcast_targets')

    if targets == 'all':
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
    else:
        users = list(map(int, targets.split(',')))

    for user_id in users:
        try:
            if photo and text:
                await context.bot.send_photo(chat_id=user_id, photo=photo, caption=text, parse_mode="Markdown")
            elif photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo)
            else:
                await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка при отправке {user_id}: {e}")
    delete_broadcast(conn, data['broadcast_id'])