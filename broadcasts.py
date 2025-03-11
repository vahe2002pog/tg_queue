import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler, JobQueue
from datetime import datetime
import pytz
from config import ADMIN_ID
from varibles import BROADCAST_MESSAGE, BROADCAST_RECIPIENTS, BROADCAST_SCHEDULE
from db import *
from utils import build_menu, build_select_group_menu

logger = logging.getLogger(__name__)

async def show_broadcasts(update: Update, context: CallbackContext) -> None:
    """Показывает список рассылок."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    query = update.callback_query

    # Пытаемся получить chat_id из context.user_data
    chat_id = context.user_data.get('chat_id')

    # Если chat_id нет, получаем его из update
    if not chat_id:
        if update.message:
            chat_id = update.message.chat_id
        elif update.callback_query:
            chat_id = update.callback_query.message.chat_id
        else:
            logger.error("Не удалось определить chat_id в show_broadcasts")
            return

    # Получаем рассылки пользователя
    broadcasts = get_broadcasts(conn, user_id)
    if user_id == ADMIN_ID:
        broadcasts = get_broadcasts(conn)  # Админ видит все рассылки

    # Добавляем кнопки "Создать рассылку" и "Назад"
    buttons = [InlineKeyboardButton("➕ Создать рассылку", callback_data="create_broadcast")]
    buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))

    if broadcasts:
        # Создаем кнопки для каждой рассылки
        for broadcast in reversed(broadcasts):
            broadcast_id, message_text, message_photo, message_document, recipients, send_time = broadcast
            # Формируем название рассылки
            if message_text:
                name = " ".join(message_text.split()[:2])
                if len(name) > 16:
                    name = name[:16] + "..."
            elif message_photo:
                name = "Фото"
            elif message_document:
                name = "Файл"
            else:
                name = "Рассылка"
            buttons.insert(0, InlineKeyboardButton(name, callback_data=f"broadcast_info_{broadcast_id}"))

        menu = build_menu(buttons, n_cols=1)
        reply_markup = InlineKeyboardMarkup(menu)
    else:
        menu = build_menu(buttons, n_cols=1)
        reply_markup = InlineKeyboardMarkup(menu)

    # Редактируем или отправляем новое сообщение в зависимости от флага
    if context.user_data.get('edit_message') and query:
        await query.edit_message_text("📋 Выберите рассылку:", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id, "📋 Выберите рассылку:", reply_markup=reply_markup)

async def broadcast_info_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки просмотра информации о рассылке."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    broadcast_id = int(query.data.split("_")[2])

    # Получаем информацию о рассылке
    broadcast = get_broadcast_by_id(conn, broadcast_id)
    if not broadcast:
        await query.edit_message_text("❌ Ошибка: Рассылка не найдена.")
        return

    # Получаем запланированное время
    cursor = conn.cursor()
    cursor.execute("SELECT send_time FROM broadcasts WHERE id = ?", (broadcast_id,))
    send_time_result = cursor.fetchone()
    send_time = datetime.fromisoformat(send_time_result[0]).strftime("%d.%m.%Y %H:%M") if send_time_result else "Не указано"

    # Формируем текст сообщения
    message_text = broadcast.get("message_text", "")
    message_photo = broadcast.get("message_photo", "")
    message_document = broadcast.get("message_document", "")

    # Формируем информацию о рассылке
    info_text = f"📋 *Информация о рассылке:*\n\n"
    if message_text:
        info_text += f"📝 *Сообщение:*\n{message_text}\n\n"
    if message_photo:
        info_text += "🖼 *Фото:* Прикреплено\n\n"
    if message_document:
        info_text += "📄 *Документ:* Прикреплен\n\n"
    info_text += f"⏰ *Запланированное время:* {send_time}"

    # Формируем кнопки
    buttons = [
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_broadcast_{broadcast_id}"),
        InlineKeyboardButton("🔙 Назад", callback_data="show_broadcasts")
    ]
    reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=1))

    # Отправляем сообщение с информацией о рассылке
    await query.edit_message_text(info_text, reply_markup=reply_markup, parse_mode="Markdown")

async def create_broadcast(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания рассылки."""
    await update.effective_message.reply_text(
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
        send_time = datetime.now(pytz.UTC)
        send_time_utc = send_time  # Инициализируем send_time_utc
    else:
        try:
            user_timezone_str = get_user_timezone(conn, user_id)
            user_timezone = pytz.timezone(user_timezone_str)
            send_time = datetime.strptime(update.message.text.strip(), "%d.%m.%y %H:%M")
            send_time_localized = user_timezone.localize(send_time)
            send_time_utc = send_time_localized.astimezone(pytz.UTC)
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

    if send_time == datetime.now(pytz.UTC):
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
        delay = (send_time_utc - datetime.now(pytz.UTC)).total_seconds()
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

        send_time = datetime.fromisoformat(send_time_str).replace(tzinfo=pytz.UTC)

        # Если время рассылки уже прошло, удаляем её из базы данных
        if send_time < datetime.now(pytz.UTC):
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
        delay = (send_time - datetime.now(pytz.UTC)).total_seconds()

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

async def cancel_broadcast_button(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор рассылки для удаления."""
    query = update.callback_query
    await query.answer()
    broadcast_id = int(query.data.split("_")[2])
    conn = context.bot_data['conn']

    # Помечаем рассылку как удаленную
    mark_broadcast_as_deleted(conn, broadcast_id)
    await query.edit_message_text("✅ Рассылка успешно удалена.")

    # Сохраняем chat_id в context.user_data и устанавливаем флаг
    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_broadcasts(update, context)

    return ConversationHandler.END