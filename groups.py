# groups.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler
from config import ADMIN_ID
from varibles import GROUP_NAME, JOIN_GROUP_PAYLOAD
from db import *
from utils import *
from crypto import decrypt_data
logger = logging.getLogger(__name__)

async def create_group(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания группы."""
    await update.effective_message.reply_text("✍ Введите название группы:")
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
        reply_markup = await create_join_group_button(context, group_id, user_id)

        await update.message.reply_text(
            f"✅ Группа *{group_name}* создана!\n"
            f"➡ Нажмите кнопку, чтобы присоединиться.",
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text("❌ Ошибка при создании группы.")
    return ConversationHandler.END

async def handle_group_deeplink(update: Update, context: CallbackContext) -> None:
    """Обрабатывает deeplink для присоединения к группе."""
    conn = context.bot_data['conn']
    if update.message:
        message_text = update.message.text
        logger.info(f"Получено сообщение: {message_text}")

        if not message_text.startswith("/start") or len(message_text.split()) <= 1:
            return

        payload = message_text.split()[1]
        if payload.startswith(JOIN_GROUP_PAYLOAD):
            try:
                encrypted_id = payload[11:]
                group_id, creator_id = decrypt_data(encrypted_id)
                if not group_id or not creator_id:
                    await update.message.reply_text("❌ Неверный формат ID группы.")
                    return
            except ValueError:
                await update.message.reply_text("❌ Неверный формат ID группы.")
                return

            user_id = update.effective_user.id

            # Получаем информацию о группе
            group = get_group_by_id(conn, group_id)
            if not group:
                await update.message.reply_text("❌ Ошибка: Группа не найдена.")
                return

            if group['creator_id'] != creator_id:
                await update.message.reply_text("❌ Ошибка: Неверный создатель группы.")
                return

            if not get_user_data(conn, user_id):
                await update.message.reply_text(
                    "✍ Для начала введите ваше *имя* с помощью команды /start.",
                )
                return

            # Добавляем пользователя в группу
            add_user_to_group(conn, group_id, user_id)
            await update.message.reply_text(f"✅ Вы присоединились к группе '{group['group_name']}'")
    elif update.callback_query:
        pass

async def show_groups(update: Update, context: CallbackContext) -> None:
    """Показывает список групп."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    query = update.callback_query

    # chat_id получаем ТОЛЬКО если edit_message = False
    chat_id = context.user_data.get('chat_id')
    if not chat_id:
        if update.message:
            chat_id = update.message.chat_id
        elif update.callback_query:
            chat_id = update.callback_query.message.chat_id
        else:
            logger.error("Не удалось определить chat_id в show_groups")
            return

    # Получаем группы пользователя
    user_groups = get_user_groups(conn, user_id)
    if user_id == ADMIN_ID:
        user_groups = get_all_groups(conn)

    # Создаем кнопки
    buttons=[InlineKeyboardButton("➕ Создать группу", callback_data="create_group")]
    buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))

    if user_groups:
        for group in reversed(user_groups):
            buttons.insert(0, InlineKeyboardButton(group['group_name'], callback_data=f"group_info_{group['group_id']}"))
        reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=1))
    else:
        reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=1))

    # Редактируем сообщение, если установлен флаг, И если есть query
    if context.user_data.get('edit_message') and query:
        await query.edit_message_text("📋 Выберите группу:", reply_markup=reply_markup)
    else:
        # Иначе отправляем новое сообщение
        await context.bot.send_message(chat_id, "📋 Выберите группу:", reply_markup=reply_markup)

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

async def leave_group_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выход пользователя из группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[2])

    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"confirm_leave_group_{group_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"cancel_leave_group_{group_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Подтвердите выход из группы:", reply_markup=reply_markup)

async def confirm_leave_group(update: Update, context: CallbackContext) -> None:
    """Подтверждает выход из группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    group_name = get_group_name_by_id(conn, group_id)

    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя группы.")
        return

    remove_user_from_group(conn, group_id, user_id)
    await query.edit_message_text(f"✅ Вы вышли из группы: *{group_name}*.")

    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_groups(update, context)

async def cancel_leave_group(update: Update, context: CallbackContext) -> None:
    """Отменяет выход из группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    group_name = get_group_name_by_id(conn, group_id)

    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя группы.")
        return

    await query.edit_message_text(f"❌ Выход из группы *{group_name}* отменен.")
    await group_info_button(update, context)


async def delete_group_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки удаления группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[2])

    # Создаем кнопки подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_group_{group_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"cancel_delete_group_{group_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Подтвердите удаление группы:", reply_markup=reply_markup)

async def confirm_delete_group(update: Update, context: CallbackContext) -> None:
    """Подтверждает удаление группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    user_id = update.effective_user.id
    group_name = get_group_name_by_id(conn, group_id)

    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя группы.")
        return

    delete_group_db(conn, group_id)
    await query.edit_message_text(f"✅ Группа *{group_name}* успешно удалена.")

    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_groups(update, context)

async def cancel_delete_group(update: Update, context: CallbackContext) -> None:
    """Отменяет удаление группы."""
    query = update.callback_query
    await query.answer()
    group_id = int(query.data.split("_")[3])

    conn = context.bot_data['conn']
    group_name = get_group_name_by_id(conn, group_id)

    if not group_name:
        await query.edit_message_text("❌ Ошибка: Не удалось получить имя группы.")
        return

    await query.edit_message_text(f"❌ Удаление группы *{group_name}* отменено.")
    await group_info_button(update, context)

async def group_info_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки просмотра информации о группе."""
    query = update.callback_query
    await query.answer()  # query.answer() нужен, если мы вызываем edit_message_text
    conn = context.bot_data['conn']

    group_id = None
    if group_id is None:
        if query and (query.data.startswith("group_info_") or query.data.startswith("cancel_delete_group_") 
                      or query.data.startswith("cancel_leave_group_")):
            if query.data.startswith("cancel_delete_group_") or query.data.startswith("cancel_leave_group_"):
                group_id = int(query.data.split("_")[3])
            else:
                group_id = int(query.data.split("_")[2])
        else:
            if query:
                await query.edit_message_text("❌ Ошибка: ID группы не найден.")
            return

    user_id = update.effective_user.id
    group = get_group_by_id(conn, group_id)
    if not group:
        await query.edit_message_text("❌ Ошибка: Группа не найдена.")
        return

    # Получаем список участников группы
    users_list = get_group_users(conn, group_id)
    users_text = "\n".join([f"{i+1}. {get_user_name(conn, user_id)}" for i, user_id in enumerate(users_list)]) if users_list else "🔍 В группе пока нет участников."

    # Формируем кнопки
    buttons = []
    if is_user_in_group(conn, group_id, user_id):
        buttons.append(InlineKeyboardButton("🚪 Покинуть группу", callback_data=f"leave_group_{group_id}"))
    else:
        buttons.append(InlineKeyboardButton("➕ Присоединиться", callback_data=f"{JOIN_GROUP_PAYLOAD}{group_id}"))

    if group['creator_id'] == user_id or user_id == ADMIN_ID:
        buttons.append(InlineKeyboardButton("❌ Удалить группу", callback_data=f"delete_group_{group_id}"))

    buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="show_groups"))
    
    reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

    await query.edit_message_text(
        f"📋 Информация о группе {group['group_name']}:\n\n"
        f"👥 Участники:\n{users_text}",
        reply_markup=reply_markup
    )