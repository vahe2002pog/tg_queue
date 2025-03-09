# handlers.py
import logging
import json
from telegram import Update,  Message, BotCommand, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from telegram.ext import  ContextTypes,  CallbackContext,  ConversationHandler, JobQueue
from datetime import datetime
from geopy.distance import geodesic

from config import *
from varibles import *
from db import *
from utils import *

logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> int:
    """Обработка команды /start."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']

    result = get_user_data(conn, user_id)
    if result:
        reply_markup = build_main_menu()
        await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
        return ConversationHandler.END 
    else:
        await update.message.reply_text("Привет! Пожалуйста, введите ваше *имя*:")
        context.user_data['state'] = WAITING_FOR_NAME 
        return WAITING_FOR_NAME 

async def set_name(update: Update, context: CallbackContext) -> int:
    """Обработчик ввода имени пользователя."""
    user_id = update.effective_user.id
    user_name = update.message.text
    conn = context.bot_data['conn']
    set_user_name(conn, user_id, user_name)
    await update.message.reply_text(f"✅ Ваше имя *{user_name}* сохранено.")
    reply_markup = build_main_menu()
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END

async def change_name_start(update: Update, context: CallbackContext) -> None:
    """Обработчик начала смены имени."""
    await update.callback_query.message.reply_text("🔄 Пожалуйста, введите новое *имя*:")
    return CHANGE_NAME

async def change_name(update: Update, context: CallbackContext) -> int:
    """Обработчик получения нового имени."""
    user = update.message.from_user
    user_id = user.id
    new_name = update.message.text
    conn = context.bot_data['conn']

    update_user_name(conn, user_id, new_name)
    await update.message.reply_text(f"✅ Ваше имя изменено на *{new_name}*.")
    update_user_state(conn, user_id, "name_entered")

    reply_markup = build_main_menu()
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END

async def create_queue_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания очереди (выбор группы)."""
    await update.message.reply_text(
        "📌 *Создание очереди*\n\n"
        "🔹 Введите *название очереди*.\n",
        
    )
    return QUEUE_NAME

async def create_queue_name(update: Update, context: CallbackContext) -> int:
    """Обработчик получения названия очереди."""
    context.user_data['queue_name'] = update.message.text
    await update.message.reply_text(
        f"✅ *Название очереди:* `{update.message.text}`\n\n"
        "📅 Теперь введите *дату начала* в формате _ДД.ММ.ГГ_.\n"
        "📆 Чтобы выбрать *сегодняшнюю дату*, введите /today.\n",
        
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
            
        )
        return QUEUE_TIME

    if not validate_date(user_input):
        await update.message.reply_text(
            "⚠️ *Ошибка:* Неверный формат даты.\n\n"
            "📅 Пожалуйста, используйте _ДД.ММ.ГГ_ или введите /today для выбора сегодняшней даты.",
            
        )
        return QUEUE_DATE

    context.user_data['queue_date'] = user_input
    await update.message.reply_text(
        "📅 *Дата сохранена!* ✅\n\n"
        "🕒 Теперь введите *время начала* в формате _ЧЧ:ММ_.\n"
        "⏰ Чтобы выбрать *текущее время*, введите /now.\n",
        
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
            
        )
    else:
        if not validate_time(update.message.text):
            await update.message.reply_text(
                "⚠️ *Ошибка:* Неверный формат времени.\n\n"
                "⏰ Пожалуйста, используйте _ЧЧ:ММ_ или введите /now для выбора текущего времени.",
                
            )
            return QUEUE_TIME

        context.user_data['queue_time'] = update.message.text

    reply_markup = build_location_menu()
    await update.message.reply_text(
        "🌍 *Выберите местоположение очереди:*",
        reply_markup=reply_markup,
        
    )
    return CHOOSE_LOCATION

async def create_queue_location(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора местоположения очереди."""
    query = update.callback_query
    await query.answer()

    if query.data == "location_mathfac":
        context.user_data['latitude'] = MF_COORDINATES[0]
        context.user_data['longitude'] = MF_COORDINATES[1]
        # await create_queue_final(update, context)
        conn = context.bot_data['conn']
        user_id = update.effective_user.id
        user_groups = get_user_groups(conn, user_id)
        reply_markup = build_select_group_menu(user_groups)
        await query.message.edit_text("📋 Выберите группу для очереди (или 'Без группы'):", reply_markup=reply_markup)
        return CHOOSE_GROUP

    elif query.data == "location_custom":
        await query.message.edit_text(
            "📍 *Пожалуйста, отправьте вашу геолокацию* для создания очереди:",
            
        )
        return CHOOSE_LOCATION

async def create_queue_location_custom(update: Update, context: CallbackContext) -> int:
    """Обработчик получения кастомной геолокации."""
    location = update.message.location
    context.user_data['latitude'] = location.latitude
    context.user_data['longitude'] = location.longitude
    # await create_queue_final(update, context)
    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    user_groups = get_user_groups(conn, user_id)
    reply_markup = build_select_group_menu(user_groups)
    await update.message.reply_text("📋 Выберите группу для очереди (или 'Без группы'):", reply_markup=reply_markup)
    return CHOOSE_GROUP

async def create_queue_choose_group(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор группы для очереди."""
    query = update.callback_query
    await query.answer()
    group_id_str = query.data

    if group_id_str == "select_group_none":
        context.user_data['group_id'] = None
        await query.edit_message_text("✅ Очередь будет без группы")

    elif group_id_str.startswith("select_group_"):
        try:
            group_id = int(group_id_str.split("_")[2])
            conn = context.bot_data['conn']
            group_name = get_group_by_id(conn, group_id)["group_name"]
            context.user_data['group_id'] = group_id
            await query.edit_message_text(f"✅ Выбрана группа *{group_name}*")
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Ошибка: Неверный формат выбора группы.")
            return CHOOSE_GROUP
    else:
        await query.edit_message_text("❌ Ошибка: Неподдерживаемый выбор.")
        return CHOOSE_GROUP
    return await create_queue_final(update, context)

async def create_queue_final(update: Update, context: CallbackContext) -> int:
    """Завершает создание очереди (с группой или без)."""
    name = context.user_data['queue_name']
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    latitude = context.user_data['latitude']
    longitude = context.user_data['longitude']
    group_id = context.user_data.get('group_id')
    conn = context.bot_data['conn']

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    except ValueError:
        await update.effective_message.reply_text(
            "❌ *Ошибка:* Неверный формат даты или времени. Пожалуйста, проверьте ввод.",
            
        )
        return ConversationHandler.END

    start_time_gmt5 = start_time.replace(tzinfo=GMT_PLUS_5)

    # Вставляем очередь в БД (с group_id или NULL)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO queues (queue_name, start_time, latitude, longitude, creator_id, group_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, start_time_gmt5.isoformat(), latitude, longitude, update.effective_user.id, group_id))
    conn.commit()
    queue_id = cursor.lastrowid


    location_message = await update.effective_message.reply_location(
        latitude=latitude,
        longitude=longitude
    )
    context.user_data['queue_message_id'] = None #Пока что None
    context.user_data['location_message_id'] = location_message.message_id
    context.user_data['queue_id'] = queue_id

    if group_id:
        keyboard = [
            [InlineKeyboardButton("✅ Да", callback_data="send_notification_yes")],
            [InlineKeyboardButton("❌ Нет", callback_data="send_notification_no")]
        ]
        logger.debug(update)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text(
            "🔔 Отправить уведомление участникам группы?",
            reply_markup=reply_markup
        )
        return SEND_NOTIFICATION
    else:
        #Если группы нет - сразу завершаем
        await finish_queue_creation(update, context)
        return ConversationHandler.END

async def send_notification_choice(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор отправки уведомления."""
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "send_notification_yes":
        await query.edit_message_text("🔔 Участники группы получат уведомление.")
        await send_group_notification(update, context) 
    else:
        await query.edit_message_text("🔕 Участники группы не получат уведомление.")

    await finish_queue_creation(update, context)
    return ConversationHandler.END

async def send_group_notification(update:Update, context:CallbackContext):
    """Отправка уведомления участникам"""
    conn = context.bot_data['conn']
    group_id = context.user_data.get('group_id')
    queue_id = context.user_data.get('queue_id')
    queue_creator_id = update.effective_user.id
    queue_name = context.user_data.get('queue_name')

    #Получаем дату и время для сообщения
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")


    if not group_id or not queue_id:
        logger.error("Не удалось отправить уведомление: нет group_id или queue_id")
        return

    users = get_group_users(conn, group_id)
    if not users:
        logger.info(f"Нет пользователей в группе {group_id} для уведомлений")
        return

    reply_markup = await create_join_queue_button(context, queue_id)  # кнопка
    message_text = (
        f"✅ Создана новая очередь *{queue_name}*! 🕒\n"
        f"📆 Дата: *{start_time.strftime('%d.%m.%y')}*\n"
        f"⏰ Время: *{start_time.strftime('%H:%M')}*\n\n"
        f"📍 *Локация:* (смотрите выше)\n\n"
        f"➡ *Нажмите кнопку, чтобы присоединиться!*")

    for user_id in users:
        if user_id != queue_creator_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text = message_text,
                    reply_markup=reply_markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
                logger.info(f"Уведомление о создании {queue_id} отправлено {user_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление {user_id} об {queue_id}: {e}")

async def finish_queue_creation(update:Update, context:CallbackContext):
    """Завершающая часть создания очереди"""

    #Получаем нужные данные
    conn = context.bot_data['conn']
    queue_id = context.user_data.get('queue_id')
    queue_name = context.user_data.get('queue_name')
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']
    start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    start_time_gmt5 = start_time.replace(tzinfo=GMT_PLUS_5)

    #Создаем кнопку
    reply_markup = await create_join_queue_button(context, queue_id)
    #Формируем сообщение
    queue_message = await send_queue_created_message(update, context, queue_name, start_time, reply_markup)
    context.user_data['queue_message_id'] = queue_message.message_id #Сохраняем ID сообщения

    #Удаляем через 5 часов
    time_until_deletion = (start_time_gmt5 + timedelta(hours=5)) - datetime.now(GMT_PLUS_5)
    seconds_until_deletion = max(time_until_deletion.total_seconds(), 0)
    context.job_queue.run_once(delete_queue_job, seconds_until_deletion, data=queue_id)

    #Чистим данные
    context.user_data.pop('queue_name', None)
    context.user_data.pop('group_id', None)


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
    await context.bot.send_message(ADMIN_ID, f"✅ Очередь {queue_name} (ID {queue_id}) была автоматически удалена.")
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
    await update.message.reply_text("📋 Выберите очередь для *удаления*:", reply_markup=reply_markup)

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
    await query.edit_message_text(f"✅ Очередь *{queue_name}* успешно удалена.")

async def leave_queue(update: Update, context: CallbackContext) -> None:
    """Показывает очереди, в которых состоит пользователь, для выхода."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.")
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
    await query.edit_message_text(f"✅ Вы вышли из очереди: *{queue_name}*.")

async def skip_turn(update: Update, context: CallbackContext) -> None:
    """Показывает очереди пользователя для пропуска хода."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.")
        return

    user_queues = get_user_queues(conn, user_id)
    if not user_queues:
        await update.message.reply_text("❌ Вы не состоите в очередях.")
        return

    reply_markup = build_skip_turn_menu(user_queues)
    await update.message.reply_text("Выберите очередь, чтобы *пропустить* ход:", reply_markup=reply_markup)

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
            await query.edit_message_text(f"✅ Вы пропустили ход. Теперь после *{user2_name}*.")
            await context.bot.send_message(chat_id=user2_id, text=f"ℹ️ Теперь вы перед *{user_name}* в '{queue_name}'.")
    else:
        await query.edit_message_text("❌ Вы в конце очереди, нельзя пропустить.")

async def queue_info(update: Update, context: CallbackContext) -> None:
    """Показывает очереди пользователя для просмотра информации."""
    user_id = update.message.from_user.id
    conn = context.bot_data['conn']

    if not get_user_data(conn, user_id):
        await update.message.reply_text("📌 Сначала введите ваше *имя* /start.")
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
    """Отображает список доступных очередей (с учетом групп)."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id

    # Получаем группы пользователя
    user_groups = get_user_groups(conn, user_id)
    group_ids = [group['group_id'] for group in user_groups]

    # Получаем очереди для каждой группы пользователя + очереди без группы
    queues_list = []
    for group_id in group_ids:
        queues_list.extend(get_queues_by_group(conn, group_id))
    queues_list.extend(get_queues_by_group(conn, None))  # Очереди без группы


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
        await message.reply_text(f"⚠️ Запись начнется *{queue['start_time'].strftime('%d.%m.%Y %H:%M')}* ⏰")
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
        "/delete_queue - Удалить очередь\n"
        "/leave - Покинуть очередь\n"
        "/skip - Пропустить ход в очереди\n"
        "/queue_info - Список людей в очереди\n"
        "/show_queues - Показать доступные очереди\n"
        "/create_group - Создать группу\n"
        "/delete_group - Удалить группу\n"
        "/show_groups - Показать список групп\n"
        "/broadcast - Создать рассылку\n"
        "/delete_broadcast - Удалить рассылку\n"
        "/leave_group - Покинуть группу\n"
        "/help - Помощь (список команд)\n"
    )
    await update.message.reply_text(help_text)

async def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую команду и очищает данные."""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.", reply_markup=ReplyKeyboardRemove())
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
        BotCommand("create_group", "Создать группу"),
        BotCommand("delete_group", "Удалить группу"),
        BotCommand("broadcast", "Создать рассылку"),
        BotCommand("delete_broadcast", "Удалить рассылку"),
        BotCommand("show_groups", "Показать группы"),
        BotCommand("leave_group", "Покинуть группу"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Команды установлены.")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")

async def start_broadcast(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания рассылки."""
    await update.message.reply_text(
        "📝 Введите сообщение для рассылки (текст, фото или файл).\n"
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: CallbackContext) -> int:
    """Обрабатывает сообщения для рассылки."""
    if not context.user_data.get('broadcast_messages'):
        context.user_data['broadcast_messages'] = []

    if update.message.text == "/end":
        if not context.user_data['broadcast_messages']:
            await update.message.reply_text("❌ Вы не добавили ни одного сообщения.")
            return ConversationHandler.END
        else:
            # Переходим к выбору получателей
            user_id = update.effective_user.id
            conn = context.bot_data['conn']

            if user_id == ADMIN_ID:
                # Админ видит все группы и кнопку "без группы"
                all_groups = get_all_groups(conn)
                reply_markup = build_select_group_menu(all_groups, with_no_group=True)
                await update.message.reply_text("📋 Выберите группу для рассылки или нажмите 'Без группы':", reply_markup=reply_markup)
            else:
                # Обычный пользователь видит только группы, в которых он состоит
                user_groups = get_user_groups(conn, user_id)
                if not user_groups:
                    await update.message.reply_text("❌ Вы не состоите ни в одной группе.")
                    return ConversationHandler.END

                # Показываем меню выбора группы (без опции "без группы")
                reply_markup = build_select_group_menu(user_groups, with_no_group=False)
                await update.message.reply_text("📋 Выберите группу для рассылки:", reply_markup=reply_markup)

            return BROADCAST_RECIPIENTS

    # Сохраняем текст, фото или файл в порядке получения
    if update.message.text:
        context.user_data['broadcast_messages'].append({"type": "text", "content": update.message.text})
    elif update.message.photo:
        context.user_data['broadcast_messages'].append({"type": "photo", "content": update.message.photo[-1].file_id})
    elif update.message.document:
        context.user_data['broadcast_messages'].append({"type": "document", "content": update.message.document.file_id})

    await update.message.reply_text("✅ Сообщение добавлено. Продолжайте ввод или введите /end для завершения.")
    return BROADCAST_MESSAGE

async def broadcast_choose_group(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор группы для рассылки."""
    query = update.callback_query
    await query.answer()
    group_id_str = query.data

    if group_id_str == "select_group_none":
        # Если выбрана "без группы", запрашиваем ID пользователей
        context.user_data['group_id'] = None
        await query.edit_message_text("👥 Введите ID пользователей через пробел:")
        return BROADCAST_RECIPIENTS
    elif group_id_str.startswith("select_group_"):
        try:
            group_id = int(group_id_str.split("_")[2])
            conn = context.bot_data['conn']
            group_name = get_group_by_id(conn, group_id)["group_name"]
            context.user_data['group_id'] = group_id
            await query.edit_message_text(f"✅ Выбрана группа *{group_name}*")
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Ошибка: Неверный формат выбора группы.")
            return BROADCAST_RECIPIENTS
    else:
        await query.edit_message_text("❌ Ошибка: Неподдерживаемый выбор.")
        return BROADCAST_RECIPIENTS

    # Переходим к выбору времени рассылки
    await query.message.reply_text("⏰ Введите дату и время рассылки в формате ДД.ММ.ГГ ЧЧ:ММ или /now для отправки сразу.")
    return BROADCAST_SCHEDULE

async def broadcast_recipients_input(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод ID пользователей для рассылки."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']

    if user_id == ADMIN_ID:
        # Админ вводит ID пользователей через пробел
        recipients = update.message.text.strip()
        context.user_data['recipients'] = recipients
        await update.message.reply_text("⏰ Введите дату и время рассылки в формате ДД.ММ.ГГ ЧЧ:ММ или /now для отправки сразу.")
        return BROADCAST_SCHEDULE
    else:
        # Обычный пользователь не должен сюда попадать
        await update.message.reply_text("❌ У вас нет прав для ввода ID пользователей.")
        return ConversationHandler.END
    

async def broadcast_schedule(update: Update, context: CallbackContext) -> int:
    """Обрабатывает время отправки рассылки."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id

    if update.message.text.lower() == "/now":
        send_time = datetime.now(GMT_PLUS_5)
    else:
        try:
            send_time = datetime.strptime(update.message.text.strip(), "%d.%m.%y %H:%M").replace(tzinfo=GMT_PLUS_5)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите ДД.ММ.ГГ ЧЧ:ММ или /now.")
            return BROADCAST_SCHEDULE

    # Получаем список получателей
    if context.user_data.get('group_id'):
        group_id = context.user_data['group_id']
        recipients = ",".join(map(str, get_group_users(conn, group_id)))
    else:
        recipients = context.user_data.get('recipients', '')

    # Сохраняем рассылку в базу данных
    broadcast_id = insert_broadcast(
        conn,
        message_text="\n".join([msg['content'] for msg in context.user_data['broadcast_messages'] if msg['type'] == "text"]),
        message_photo=next((msg['content'] for msg in context.user_data['broadcast_messages'] if msg['type'] == "photo"), None),
        message_document=next((msg['content'] for msg in context.user_data['broadcast_messages'] if msg['type'] == "document"), None),
        recipients=recipients,
        send_time=send_time,
        creator_id=user_id
    )

    if send_time == datetime.now(GMT_PLUS_5):
        # Отправляем рассылку сразу
        context.job_queue.run_once(
            send_broadcast,
            0,  # Задержка 0 секунд (отправка сразу)
            data={
                'broadcast_id': broadcast_id,
                'messages': context.user_data['broadcast_messages'],  # Передаем список сообщений
                'recipients': recipients
            }
        )
        await update.message.reply_text("✅ Рассылка отправлена.")
    else:
        # Планируем рассылку
        delay = (send_time - datetime.now(GMT_PLUS_5)).total_seconds()
        context.job_queue.run_once(
            send_broadcast,
            delay,
            data={
                'broadcast_id': broadcast_id,
                'messages': context.user_data['broadcast_messages'],  # Передаем список сообщений
                'recipients': recipients
            }
        )
        await update.message.reply_text(f"✅ Рассылка запланирована на {send_time.strftime('%d.%m.%Y %H:%M')}.")

    # Очищаем данные
    context.user_data.clear()
    return ConversationHandler.END

async def send_broadcast(context: CallbackContext) -> None:
    """Отправляет рассылку."""
    conn = context.bot_data['conn']
    data = context.job.data

    broadcast_id = data['broadcast_id']
    messages = data['messages']
    recipients = data.get('recipients', '')

    # Проверяем, не была ли рассылка удалена
    cursor = conn.cursor()
    cursor.execute("SELECT is_deleted FROM broadcasts WHERE id = ?", (broadcast_id,))
    result = cursor.fetchone()
    if result and result[0]:  # Если рассылка помечена как удаленная
        logger.info(f"Рассылка #{broadcast_id} была удалена и не будет отправлена.")
        return

    user_ids = list(map(int, recipients.split(",")))

    # Отправляем сообщения в том же порядке
    for user_id in user_ids:
        for message in messages:
            try:
                if message['type'] == "text":
                    await context.bot.send_message(chat_id=user_id, text=message['content'])
                elif message['type'] == "photo":
                    await context.bot.send_photo(chat_id=user_id, photo=message['content'])
                elif message['type'] == "document":
                    await context.bot.send_document(chat_id=user_id, document=message['content'])
            except Exception as e:
                logger.error(f"Ошибка при отправке рассылки пользователю {user_id}: {e}")

    # Помечаем рассылку как удаленную
    mark_broadcast_as_deleted(conn, broadcast_id)

async def load_scheduled_broadcasts(job_queue: JobQueue):
    """Загружает запланированные рассылки при запуске бота."""
    conn = job_queue.application.bot_data['conn']
    broadcasts = get_broadcasts(conn)

    for broadcast in broadcasts:
        broadcast_id, message_text, message_photo, message_document, recipients, send_time_str = broadcast

        # Проверяем, не была ли рассылка удалена
        cursor = conn.cursor()
        cursor.execute("SELECT is_deleted FROM broadcasts WHERE id = ?", (broadcast_id,))
        result = cursor.fetchone()
        if result and result[0]:  # Если рассылка помечена как удаленная
            logger.info(f"Рассылка #{broadcast_id} была удалена и не будет запланирована.")
            continue

        send_time = datetime.fromisoformat(send_time_str).replace(tzinfo=GMT_PLUS_5)

        # Если время рассылки уже прошло, удаляем её из базы данных
        if send_time < datetime.now(GMT_PLUS_5):
            mark_broadcast_as_deleted(conn, broadcast_id)
            continue

        # Создаем список сообщений в порядке их получения
        messages = []
        if message_text:
            messages.append({"type": "text", "content": message_text})
        if message_photo:
            messages.append({"type": "photo", "content": message_photo})
        if message_document:
            messages.append({"type": "document", "content": message_document})

        # Вычисляем задержку до времени отправки
        delay = (send_time - datetime.now(GMT_PLUS_5)).total_seconds()

        # Добавляем задачу в JobQueue
        job_queue.run_once(
            send_broadcast,
            delay,
            data={
                'broadcast_id': broadcast_id,
                'messages': messages,  # Передаем список сообщений
                'recipients': recipients
            }
        )
        logger.info(f"Рассылка #{broadcast_id} запланирована на {send_time}.")

async def delete_broadcast_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс удаления рассылки."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']

    # Получаем список рассылок
    if user_id == ADMIN_ID:
        broadcasts = get_broadcasts(conn)  # Для админа — все рассылки
    else:
        broadcasts = get_broadcasts(conn, user_id)  # Для обычного пользователя — только его рассылки

    if not broadcasts:
        await update.message.reply_text("❌ Нет доступных рассылок для удаления.")
        return ConversationHandler.END

    # Создаем меню с рассылками
    buttons = []
    for broadcast in broadcasts:
        broadcast_id, message_text, message_photo, message_document, recipients, send_time = broadcast
        # Формируем название рассылки
        if message_text:
            name = " ".join(message_text.split()[:2])  # Первые 2 слова текста
            if len(name) > 16:
                name = name[:16] + "..."
        elif message_photo:
            name = "Фото"
        elif message_document:
            name = "Файл"
        else:
            name = "Рассылка"
        buttons.append(InlineKeyboardButton(name, callback_data=f"delete_broadcast_{broadcast_id}"))

    reply_markup = InlineKeyboardMarkup([buttons])
    await update.message.reply_text("📋 Выберите рассылку для удаления:", reply_markup=reply_markup)
    return DELETE_BROADCAST

async def delete_broadcast_confirm(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор рассылки для удаления."""
    query = update.callback_query
    await query.answer()
    broadcast_id = int(query.data.split("_")[2])
    conn = context.bot_data['conn']

    # Помечаем рассылку как удаленную
    mark_broadcast_as_deleted(conn, broadcast_id)
    await query.edit_message_text("✅ Рассылка успешно удалена.")
    return ConversationHandler.END

async def create_group_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания группы."""
    await update.message.reply_text("📌 Введите название группы:")
    return GROUP_NAME

async def create_group_name(update: Update, context: CallbackContext) -> int:
    """Сохраняет название группы и завершает процесс."""
    group_name = update.message.text.strip()
    conn = context.bot_data['conn']
    user_id = update.effective_user.id

    if not group_name:
        await update.message.reply_text("⚠️ Название группы не может быть пустым. Попробуйте снова.")
        return GROUP_NAME

    group_id = insert_group(conn, group_name, user_id)  # Сохраняем группу
    if group_id:
        # Создаем кнопку "Присоединиться"
        keyboard = [[InlineKeyboardButton("📌 Присоединиться к группе", callback_data=f"{JOIN_GROUP_PAYLOAD}{group_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Группа *{group_name}* создана!\n"
            f"➡ Нажмите кнопку, чтобы присоединиться.",
            reply_markup=reply_markup,
            
        )
    else:
        await update.message.reply_text("❌ Ошибка при создании группы.")
    return ConversationHandler.END

async def join_group(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие на кнопку 'Присоединиться к группе'."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    data_parts = query.data.split("_")

    #Валидация данных
    if len(data_parts) < 3:
        await query.message.reply_text("❌ Ошибка: неверный формат данных")
        return
    try:
        group_id = int(data_parts[2])
    except ValueError:
         await query.message.reply_text("❌ Ошибка: неверный формат ID группы")
         return

    user_id = update.effective_user.id

    group_name = get_group_name_by_id(conn, group_id)
    if not group_name:
        await query.message.reply_text("❌ Ошибка: Группа не найдена.")
        return

    add_user_to_group(conn, group_id, user_id)
    await query.message.reply_text(f"✅ Вы присоединились к группе '{group_name}'")

async def show_groups(update: Update, context: CallbackContext) -> None:
    """Показывает список групп."""
    conn = context.bot_data['conn']
    groups = get_all_groups(conn)
    if groups:
        reply_markup = build_group_menu(groups)
        await update.message.reply_text("📋 Выберите группу:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Нет доступных групп.")

async def leave_group_command(update:Update, context:CallbackContext) -> None:
    """Показывает список групп пользователя для выхода."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id

    user_groups = get_user_groups(conn,user_id)

    if not user_groups:
        await update.message.reply_text("❌ Вы не состоите ни в одной группе")
        return

    reply_markup = build_leave_group_menu(user_groups)
    await update.message.reply_text("📋 Выберите группу для выхода", reply_markup=reply_markup)

async def leave_group_button(update:Update, context:CallbackContext) -> None:
    """Обрабатывает выход пользователя из группы."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    group_id = int(query.data.split("_")[2])

    group_name = get_group_name_by_id(conn, group_id)
    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    remove_user_from_group(conn, group_id, user_id)
    await query.edit_message_text(f"✅ Вы вышли из группы: *{group_name}*.")

async def delete_group_start(update: Update, context: CallbackContext) -> None:
    """Начинает процесс удаления группы (показывает список групп)."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']

    if user_id == ADMIN_ID:
        groups_list = get_all_groups(conn)  # Админ видит все группы
    else:
        # Показываем пользователю только те группы, которые он создал
        groups_list = [g for g in get_all_groups(conn) if get_group_by_id(conn, g['group_id'])['creator_id'] == user_id]

    if not groups_list:
        await update.message.reply_text("❌ Нет доступных групп для удаления.")
        return

    reply_markup = build_delete_group_menu(groups_list)
    await update.message.reply_text("📋 Выберите группу для *удаления*:", reply_markup=reply_markup)

async def delete_group_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки удаления группы."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']

    user_id = update.effective_user.id

    try:
        group_id = int(query.data.split("_")[2])  # Извлекаем group_id
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Некорректный формат данных callback-запроса.")
        return
    
    group = get_group_by_id(conn, group_id)

    if not group:
        await query.edit_message_text("❌ Ошибка: Группа не найдена.")
        return

    if user_id != ADMIN_ID and group['creator_id'] != user_id:
        await query.edit_message_text("⚠️ Вы не можете удалить эту группу.")
        return

    group_name = get_group_name_by_id(conn, group_id)
    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя группы.")
        return

    delete_group_db(conn, group_id)
    await query.edit_message_text(f"✅ Группа *{group_name}* успешно удалена.")
