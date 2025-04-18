import json
import pytz
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from datetime import datetime, timedelta
from config import MF_COORDINATES, ADMIN_ID
from varibles import *
from db import *
from utils import *
from main_menu import *
from crypto import decrypt_data
logger = logging.getLogger(__name__)

async def create_queue(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания очереди."""
    await update.effective_message.reply_text(
        "✍ *Создание очереди*\n\n"
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
    user_timezone_str = get_user_timezone(conn = context.bot_data['conn'], user_id = update.effective_user.id)

    if user_input == "/today":
        today = datetime.now(pytz.timezone(user_timezone_str)).strftime("%d.%m.%y")
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
    user_timezone_str = get_user_timezone(conn = context.bot_data['conn'], user_id = update.effective_user.id)

    if user_input == "/now":
        now_time = datetime.now(pytz.timezone(user_timezone_str)).strftime("%H:%M")
        context.user_data['queue_time'] = now_time
        await update.message.reply_text(
            f"✅ *Выбрано текущее время:* `{now_time}` ⏰\n\n")
    else:
        if not validate_time(update.message.text):
            await update.message.reply_text(
                "⚠️ *Ошибка:* Неверный формат времени.\n\n"
                "⏰ Пожалуйста, используйте _ЧЧ:ММ_ или введите /now для выбора текущего времени.",
            )
            return QUEUE_TIME

        context.user_data['queue_time'] = update.message.text

    # Добавляем вопрос о времени без локации
    await update.message.reply_text(
        "⏳ Укажите время (в формате ЧЧ:ММ), после которого можно записаться без подтверждения геолокации:\n"
        "➡ Если не требуется, введите /skip",
    )
    return TIME_WITHOUT_LOCATION

async def set_time_without_location(update: Update, context: CallbackContext) -> int:
    """Обработчик установки времени без проверки локации."""
    user_input = update.message.text.strip()
    
    if user_input == "/skip":
        context.user_data['time_without_location'] = None
        await update.message.reply_text(
            "✅ Проверка геолокации будет требоваться всегда.\n\n"
            "🌍 Теперь выберите местоположение очереди:",
            reply_markup=build_location_menu(),
        )
        return CHOOSE_LOCATION
    
    if not validate_time(user_input):
        await update.message.reply_text(
            "⚠️ *Ошибка:* Неверный формат времени.\n\n"
            "⏰ Пожалуйста, используйте _ЧЧ:ММ_ или введите /skip, чтобы пропустить.",
        )
        return TIME_WITHOUT_LOCATION
    
    context.user_data['time_without_location'] = user_input
    await update.message.reply_text(
        f"✅ После {user_input} проверка геолокации не потребуется.\n\n"
        "🌍 Теперь выберите местоположение очереди:",
        reply_markup=build_location_menu(),
    )
    return CHOOSE_LOCATION

async def create_queue_location(update: Update, context: CallbackContext) -> int:
    """Обработчик выбора местоположения очереди."""
    query = update.callback_query
    await query.answer()

    if query.data == "location_mathfac":
        context.user_data['latitude'] = MF_COORDINATES[0]
        context.user_data['longitude'] = MF_COORDINATES[1]
        conn = context.bot_data['conn']
        user_id = update.effective_user.id
        user_groups = get_user_groups(conn, user_id)
        reply_markup = build_select_group_menu(user_groups)
        await query.message.edit_text("📋 Выберите группу для очереди (или 'Без группы'):", reply_markup=reply_markup)
        return CHOOSE_GROUP

    elif query.data == "location_custom":
        await query.message.edit_text(
            "📍 *Пожалуйста, отправьте вашу геолокацию* для создания очереди:")
        return CHOOSE_LOCATION

async def create_queue_location_custom(update: Update, context: CallbackContext) -> int:
    """Обработчик получения кастомной геолокации."""
    location = update.message.location
    context.user_data['latitude'] = location.latitude
    context.user_data['longitude'] = location.longitude
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
    time_without_location = context.user_data.get('time_without_location')
    conn = context.bot_data['conn']
    user_timezone_str = get_user_timezone(conn = context.bot_data['conn'], user_id = update.effective_user.id)

    try:
        # Конвертируем время из часового пояса пользователя в UTC
        user_timezone = pytz.timezone(user_timezone_str)
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
        start_time_localized = user_timezone.localize(start_time)
        start_time_utc = start_time_localized.astimezone(pytz.UTC)
        
        # Конвертируем время без локации (если указано)
        if time_without_location:
            time_without_location_dt = datetime.strptime(time_without_location, "%H:%M")
            time_without_location_dt = time_without_location_dt.replace(
                year=start_time.year,
                month=start_time.month,
                day=start_time.day
            )
            time_without_location_localized = user_timezone.localize(time_without_location_dt)
            time_without_location_utc = time_without_location_localized.astimezone(pytz.UTC)
        else:
            time_without_location_utc = None
    except ValueError:
        await update.effective_message.reply_text(
            "❌ *Ошибка:* Неверный формат даты или времени. Пожалуйста, проверьте ввод.",
        )
        return ConversationHandler.END

    # Вставляем очередь в БД (с group_id или NULL)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO queues (queue_name, start_time, latitude, longitude, creator_id, group_id, time_without_location)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, start_time_utc.isoformat(), latitude, longitude, update.effective_user.id, group_id, 
          time_without_location_utc.isoformat() if time_without_location_utc else None))
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

async def send_group_notification(update: Update, context: CallbackContext) -> None:
    """Отправка уведомления участникам группы с локацией."""
    conn = context.bot_data['conn']
    group_id = context.user_data.get('group_id')
    queue_id = context.user_data.get('queue_id')
    queue_creator_id = update.effective_user.id
    queue_name = context.user_data.get('queue_name')
    latitude = context.user_data.get('latitude')
    longitude = context.user_data.get('longitude')

    if not group_id or not queue_id:
        logger.error("Не удалось отправить уведомление: нет group_id или queue_id")
        return

    users = get_group_users(conn, group_id)
    if not users:
        logger.info(f"Нет пользователей в группе {group_id} для уведомлений")
        return

    reply_markup = await create_join_queue_button(context, queue_id, queue_creator_id)

    # Получаем данные очереди из БД
    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        logger.error(f"Очередь с id {queue_id} не найдена при отправке уведомлений.")
        return

    start_time = queue['start_time']
    time_without_location = queue.get('time_without_location')

    for user_id in users:
        if user_id != queue_creator_id:
            try:
                # Получаем часовой пояс получателя
                user_timezone_str = get_user_timezone(conn, user_id)
                user_timezone = pytz.timezone(user_timezone_str)

                # Конвертируем времена в часовой пояс получателя
                start_time_user = start_time.astimezone(user_timezone)
                
                # Формируем текст сообщения
                message_text = (
                    f"✅ Создана новая очередь *{queue_name}*! 🕒\n"
                    f"📆 Дата: *{start_time_user.strftime('%d.%m.%y')}*\n"
                    f"⏰ Время: *{start_time_user.strftime('%H:%M')}*\n"
                )

                # Добавляем информацию о времени без локации, если оно указано
                if time_without_location:
                    time_without_location_user = time_without_location.astimezone(user_timezone)
                    message_text += (
                        f"🕓 Без локации после: *{time_without_location_user.strftime('%H:%M')}*\n\n"
                    )
                else:
                    message_text += "\n"

                message_text += (
                    f"📍 *Локация:* (смотрите выше)\n\n"
                    f"➡ *Нажмите кнопку, чтобы присоединиться!*"
                )

                # Отправляем локацию
                await context.bot.send_location(
                    chat_id=user_id,
                    latitude=latitude,
                    longitude=longitude
                )

                # Отправляем текстовое сообщение с кнопкой
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
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
    user_id = update.effective_user.id

    #Создаем кнопку
    reply_markup = await create_join_queue_button(context, queue_id, user_id)
    #Формируем сообщение
    queue_message = await send_queue_created_message(update, context, queue_name, start_time, reply_markup)
    context.user_data['queue_message_id'] = queue_message.message_id #Сохраняем ID сообщения

    #Удаляем через 5 часов
    user_timezone_str = get_user_timezone(conn, user_id)
    user_timezone = pytz.timezone(user_timezone_str)
    start_time_localized = user_timezone.localize(start_time)
    start_time_utc = start_time_localized.astimezone(pytz.UTC)
    time_until_deletion = (start_time_utc + timedelta(hours=5)) - datetime.now(pytz.UTC)
    seconds_until_deletion = max(time_until_deletion.total_seconds(), 0)
    context.job_queue.run_once(delete_queue_job, seconds_until_deletion, data=queue_id) # Используем функцию из utils

    #Чистим данные
    context.user_data.pop('queue_name', None)
    context.user_data.pop('group_id', None)


async def handle_deeplink(update: Update, context: CallbackContext) -> None:
    """Обрабатывает deeplink-приглашения в очередь."""
    if not update.message:
        return

    message_text = update.message.text
    logger.info(f"Получено deeplink: {message_text}")

    # Проверяем формат команды /start с payload
    if not message_text.startswith("/start") or len(message_text.split()) <= 1:
        await start(update, context)
        return

    payload = message_text.split()[1]
    if not payload.startswith(JOIN_QUEUE_PAYLOAD):
        return

    try:
        # Декодируем параметры очереди
        encrypted_id = payload[len(JOIN_QUEUE_PAYLOAD):]
        queue_id, creator_id = decrypt_data(encrypted_id)
        
        if not queue_id or not creator_id:
            raise ValueError("Invalid queue data")
            
    except ValueError:
        await update.message.reply_text("❌ Неверный формат приглашения.")
        return

    # Проверяем существование очереди и создателя
    conn = context.bot_data['conn']
    queue = await get_queue_by_id(conn, queue_id)
    if not queue or queue['creator_id'] != creator_id:
        await update.message.reply_text("❌ Очередь не найдена или приглашение недействительно.")
        return

    # Проверяем регистрацию пользователя
    user_id = update.effective_user.id
    if not get_user_data(conn, user_id):
        await update.message.reply_text("✍ Для начала введите ваше *имя* с помощью команды /start.")
        return

    # Создаем искусственный callback_query для обработки
    class FakeCallbackQuery:
        def __init__(self, message):
            self.data = f"join_queue_{queue_id}"
            self.message = message
            self.from_user = update.effective_user
            
        async def answer(self):
            """Заглушка для answer()"""
            pass
            
        async def edit_message_text(self, *args, **kwargs):
            """Перенаправляем в reply_text"""
            return await self.message.reply_text(*args, **kwargs)

    # Создаем fake update с нашим callback_query
    fake_query = FakeCallbackQuery(update.message)
    fake_update = Update(update.update_id, callback_query=fake_query)
    
    # Обрабатываем как обычный callback
    await handle_join_queue(fake_update, context)

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

async def delete_queue_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки удаления очереди."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[2])

    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_queue_{queue_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"cancel_delete_queue_{queue_id}")]
    ]
    print(queue_id)
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Подтвердите удаление очереди:", reply_markup=reply_markup)

async def confirm_delete_queue(update: Update, context: CallbackContext) -> None:
    """Подтверждает удаление очереди."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    delete_queue(conn, queue_id)
    await query.edit_message_text(f"✅ Очередь *{queue_name}* успешно удалена.")

    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_queues(update, context)

async def cancel_delete_queue(update: Update, context: CallbackContext) -> None:
    """Отменяет удаление очереди."""
    query = update.callback_query
    await query.answer()
    queue_id = None
    # Извлекаем queue_id из query.data
    try:
        queue_id = int(query.data.split("_")[3])  # Извлекаем queue_id из "cancel_delete_queue_{queue_id}"
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    conn = context.bot_data['conn']
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    # Возвращаем пользователя к информации об очереди
    await queue_info_button(update, context)

async def leave_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки выхода из очереди."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[2])

    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"confirm_leave_queue_{queue_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"cancel_leave_queue_{queue_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Подтвердите выход из очереди:", reply_markup=reply_markup)

async def confirm_leave_queue(update: Update, context: CallbackContext) -> None:
    """Подтверждает выход из очереди."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    remove_user_from_queue(conn, queue_id, user_id)
    await query.edit_message_text(f"✅ Вы вышли из очереди: *{queue_name}*.")

    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_queues(update, context)

async def cancel_leave_queue(update: Update, context: CallbackContext) -> None:
    """Отменяет выход из очереди."""
    query = update.callback_query
    await query.answer()

    try:
        queue_id = int(query.data.split("_")[3])  # Извлекаем queue_id из "cancel_leave_queue_{queue_id}"
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    conn = context.bot_data['conn']
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    await queue_info_button(update, context)

async def skip_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки пропуска хода."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[1])

    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"confirm_skip_{queue_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"cancel_skip_{queue_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Подтвердите пропуск хода:", reply_markup=reply_markup)

async def confirm_skip(update: Update, context: CallbackContext) -> None:
    """Подтверждает пропуск хода."""
    query = update.callback_query
    await query.answer()
    queue_id = int(query.data.split("_")[2])

    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    queue_users_ids = get_queue_users_ids(conn, queue_id)
    if not queue_users_ids:
        await query.edit_message_text("🔍 В очереди пока нет участников.")
        return

    current_index = queue_users_ids.index(user_id)

    if current_index + 1 < len(queue_users_ids):
        user1_id = queue_users_ids[current_index]
        user2_id = queue_users_ids[current_index + 1]
        swap_queue_users(conn, queue_id, user1_id, user2_id)
        user_name = get_user_name(conn, user1_id)
        user2_name = get_user_name(conn, user2_id)

        if user2_name:
            await query.edit_message_text(f"✅ Вы пропустили ход. Теперь после *{user2_name}*.")
            await context.bot.send_message(chat_id=user2_id, text=f"ℹ️ Теперь вы перед *{user_name}* в '{queue_name}'.")
        else:
            await query.edit_message_text("✅ Вы пропустили ход.")

        context.user_data['queue_id'] = queue_id
        context.user_data['chat_id'] = query.message.chat_id
        context.user_data['edit_message'] = False 
        await queue_info_button(update, context)

    else:
        await query.edit_message_text("❌ Вы в конце очереди, нельзя пропустить.")

async def cancel_skip(update: Update, context: CallbackContext) -> None:
    """Отменяет пропуск хода."""
    query = update.callback_query
    await query.answer()

    try:
        queue_id = int(query.data.split("_")[2])  # Извлекаем queue_id из "cancel_skip_{queue_id}"
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    conn = context.bot_data['conn']
    queue_name = get_queue_name_by_id(conn, queue_id)

    if not queue_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя очереди.")
        return

    await queue_info_button(update, context)

async def queue_info_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки просмотра информации об очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']

    queue_id = None
    if queue_id is None:
        if query and (query.data.startswith("queue_info_") or query.data.startswith("cancel_skip_") 
                      or query.data.startswith("cancel_delete_queue_") or query.data.startswith("cancel_leave_queue_")):
            if query.data.startswith("cancel_delete_queue_") or query.data.startswith("cancel_leave_queue_"):
                queue_id = int(query.data.split("_")[3])
                print(queue_id)
            else:
                queue_id = int(query.data.split("_")[2])
        else:
            if query:
                await query.edit_message_text("❌ Ошибка: ID очереди не найден.")
            return

    user_id = update.effective_user.id
    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        await query.edit_message_text("❌ Ошибка: Очередь не найдена.")
        return

    users_list = get_queue_users_names(conn, queue_id)
    users_text = "\n".join([f"{i+1}. {user}" for i, user in enumerate(users_list)]) if users_list else "🔍 В очереди пока нет участников."

    keyboard = []
    if is_user_in_queue(conn, queue_id, user_id):
        keyboard.append([
            InlineKeyboardButton("⏭ Пропустить ход", callback_data=f"skip_{queue_id}"),
            InlineKeyboardButton("🚪 Выйти из очереди", callback_data=f"leave_queue_{queue_id}")
        ])
    else:
        keyboard.append([InlineKeyboardButton("➕ Присоединиться", callback_data=f"{JOIN_QUEUE_PAYLOAD}{queue_id}")])

    if queue['creator_id'] == user_id or user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("❌ Удалить очередь", callback_data=f"delete_queue_{queue_id}"),
            InlineKeyboardButton("🔗 Пригласить", callback_data=f"invite_queue_{queue_id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="show_queues")])

    reply_markup = InlineKeyboardMarkup(keyboard) 

    await query.edit_message_text(
        f"📋 Информация об очереди {queue['queue_name']}:\n\n"
        f"👥 Участники:\n{users_text}",
        reply_markup=reply_markup
    )

async def show_queues(update: Update, context: CallbackContext) -> None:
    """Отображает список доступных очередей."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    query = update.callback_query  # Получаем query

    chat_id = context.user_data.get('chat_id')
    if not chat_id:
        if update.message:
            chat_id = update.message.chat_id
        elif update.callback_query:
            chat_id = update.callback_query.message.chat_id
        else:
            logger.error("Не удалось определить chat_id в show_queues")
            return

    # Получаем очереди
    queues_list = get_user_queues(conn, user_id)
    if user_id == ADMIN_ID:
        queues_list = get_all_queues(conn)

    buttons = [InlineKeyboardButton("➕ Создать очередь", callback_data="create_queue")]
    buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))

    if queues_list:
        for queue in reversed(queues_list):
            buttons.insert(0, InlineKeyboardButton(queue['queue_name'], callback_data=f"queue_info_{queue['queue_id']}"))
        menu = build_menu(buttons, n_cols=1)
        reply_markup = InlineKeyboardMarkup(menu)
    else:
        menu = build_menu(buttons, n_cols=1)
        reply_markup = InlineKeyboardMarkup(menu)

    # Редактируем сообщение, если установлен флаг, И если есть query
    if context.user_data.get('edit_message') and query:
        await query.edit_message_text("📋 Выберите очередь:", reply_markup=reply_markup)
    else:
        # Иначе отправляем новое сообщение
        await context.bot.send_message(chat_id, "📋 Выберите очередь:", reply_markup=reply_markup)

async def get_web_app_loc(update: Update, context: CallbackContext) -> None:
    """Обрабатывает данные Web App (геолокацию)."""
    conn = context.bot_data['conn']
    user_id = context.user_data.get("user_id")
    user_timezone_str = get_user_timezone(conn, user_id)
    user_timezone = pytz.timezone(user_timezone_str)

    queue_id = context.user_data.get("queue_id")
    queue = await get_queue_by_id(conn, queue_id)
    queue_start_time = queue["start_time"].astimezone(user_timezone)

    if queue_start_time > datetime.now(user_timezone):
        await update.message.reply_text(f"⚠️ Запись начнется *{queue_start_time.strftime('%d.%m.%Y %H:%M')}* ⏰")
        return
    try:
        data = json.loads(update.message.web_app_data.data)
        lat = data.get("lat")
        lon = data.get("lon")

        if not lat or not lon:
            await update.message.reply_text("❌ Ошибка: не удалось получить координаты.", reply_markup=ReplyKeyboardRemove())
            return

        if not queue_id:
            await update.message.reply_text("❌ Ошибка: не найдена очередь.", reply_markup=ReplyKeyboardRemove())
            return

        await check_distance_and_join(update, context, queue_id, user_id, lat, lon) # Используем функцию из utils

    except Exception as e:
        logger.error(f"Ошибка в обработке Web App данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка.", reply_markup=ReplyKeyboardRemove())

async def ask_location(update: Update, context: CallbackContext) -> None:
    """Обрабатывает данные геолокации из WebApp."""
    conn = context.bot_data['conn']
    user_id = context.user_data.get("user_id")
    queue_id = context.user_data.get("queue_id")
    
    if not user_id or not queue_id:
        await update.message.reply_text("❌ Ошибка: Не найден ID очереди или пользователя.")
        return

    try:
        data = json.loads(update.message.web_app_data.data)
        lat = data.get("lat")
        lon = data.get("lon")

        if not lat or not lon:
            await update.message.reply_text("❌ Ошибка: не удалось получить координаты.", reply_markup=ReplyKeyboardRemove())
            return

        await check_distance_and_join(update, context, queue_id, user_id, lat, lon)
    except Exception as e:
        logger.error(f"Ошибка в обработке Web App данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка.", reply_markup=ReplyKeyboardRemove())

async def generate_queue_invite_button(update: Update, context: CallbackContext) -> None:
    """Генерирует пригласительную кнопку для очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    print(query.data.split("_")[2])
    try:
        queue_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        await query.edit_message_text("❌ Ошибка: Очередь не найдена.")
        return

    user_id = update.effective_user.id
    if queue['creator_id'] != user_id and user_id != ADMIN_ID:
        await query.edit_message_text("❌ Только создатель очереди может генерировать приглашения.")
        return

    # Получаем информацию о времени начала в часовом поясе пользователя
    user_timezone_str = get_user_timezone(conn, user_id)
    start_time = convert_time_to_user_timezone(queue['start_time'], user_timezone_str)
    time_info = f"📅 Дата: *{start_time.strftime('%d.%m.%y')}*\n⏰ Время: *{start_time.strftime('%H:%M')}*"

    message_text, reply_markup = await generate_invite_button_message(
        context, "queue", queue_id, queue['creator_id'], queue['queue_name'], time_info
    )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message_text,
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

async def generate_group_invite_button(update: Update, context: CallbackContext) -> None:
    """Генерирует пригласительную кнопку для группы."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    try:
        group_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    group = get_group_by_id(conn, group_id)
    if not group:
        await query.edit_message_text("❌ Ошибка: Группа не найдена.")
        return

    user_id = update.effective_user.id
    if group['creator_id'] != user_id and user_id != ADMIN_ID:
        await query.edit_message_text("❌ Только создатель группы может генерировать приглашения.")
        return

    # Получаем список участников для дополнительной информации
    users_list = get_group_users(conn, group_id)
    members_count = len(users_list) if users_list else 0
    members_info = f"👥 Участников: *{members_count}*"

    message_text, reply_markup = await generate_invite_button_message(
        context, "group", group_id, group['creator_id'], group['group_name'], members_info
    )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message_text,
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

async def handle_join_queue(update: Update, context: CallbackContext) -> None:
    """Централизованный обработчик присоединения к очереди."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    
    # Получаем queue_id из callback_data
    try:
        queue_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: Неверный формат данных.")
        return

    user_id = update.effective_user.id
    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        await query.edit_message_text("❌ Ошибка: Очередь не найдена.")
        return

    # Проверяем, не записан ли уже пользователь
    if is_user_in_queue(conn, queue_id, user_id):
        await query.edit_message_text("✅ Вы уже записаны в эту очередь.")
        return

    # Проверяем время начала очереди
    user_timezone_str = get_user_timezone(conn, user_id)
    user_timezone = pytz.timezone(user_timezone_str)
    queue_start_time = queue["start_time"].astimezone(user_timezone)
    
    if datetime.now(user_timezone) < queue_start_time:
        await query.edit_message_text(f"⚠️ Запись начнется *{queue_start_time.strftime('%d.%m.%Y %H:%M')}* ⏰")
        return

    # Проверяем время без локации
    time_without_location = queue.get('time_without_location')
    if time_without_location:
        time_without_location = time_without_location.astimezone(user_timezone)
        if datetime.now(user_timezone).time() >= time_without_location.time():
            # Записываем без проверки локации
            join_time = datetime.now(user_timezone).isoformat()
            add_user_to_queue(conn, queue_id, user_id, join_time)
            await query.edit_message_text(
                f"✅ Вы записаны в очередь {queue['queue_name']}"
            )
            return

    # Если требуется проверка локации
    context.user_data['queue_id'] = queue_id
    context.user_data['user_id'] = user_id
    
    # Запрашиваем локацию
    reply_markup = build_web_app_location_button(rec_source="get_location")
    sent_message = await query.message.reply_text(
        f"📌 Для записи в '{queue['queue_name']}', отправьте геолокацию 📍:",
        reply_markup=reply_markup,
    )
    context.user_data["location_message_id"] = sent_message.message_id