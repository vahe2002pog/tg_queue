# groups.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler
from config import ADMIN_ID
from varibles import GROUP_NAME
from db import *
from utils import *
logger = logging.getLogger(__name__)

async def create_group(update: Update, context: CallbackContext) -> int:
    """Начинает процесс создания группы."""
    await update.effective_message.reply_text("📌 Введите название группы:")
    return GROUP_NAME

# groups.py (измененный create_group_name)
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
        deeplink = f"https://t.me/{context.bot.username}?start=join_group_{group_id}"
        keyboard = [[InlineKeyboardButton("📌 Присоединиться к группе", url=deeplink)]]
        reply_markup = InlineKeyboardMarkup(keyboard)


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
      if not message_text.startswith("/start") or len(message_text.split()) <= 1:
          return  # Если это не deeplink, игнорируем

      payload = message_text.split()[1]
      if payload.startswith("join_group_"):
          try:
              group_id = int(payload[11:])  # Извлекаем group_id
          except ValueError:
              await update.message.reply_text("❌ Неверный формат ID группы.")
              return

          user_id = update.effective_user.id

          group_name = get_group_name_by_id(conn, group_id)
          if not group_name:
              await update.message.reply_text("❌ Ошибка: Группа не найдена.")
              return

          if not get_user_data(conn, user_id):
                await update.message.reply_text(
                    "📌 Для начала введите ваше *имя* с помощью команды /start.",

                )
                return
          add_user_to_group(conn, group_id, user_id)
          await update.message.reply_text(f"✅ Вы присоединились к группе '{group_name}'")
    elif update.callback_query:
      pass

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

async def leave_group_command(update:Update, context:CallbackContext) -> None:
    """Показывает список групп пользователя для выхода."""
    conn = context.bot_data['conn']
    user_id = update.effective_user.id

    user_groups = get_user_groups(conn,user_id)

    if not user_groups:
        await update.message.reply_text("❌ Вы не состоите ни в одной группе")
        return

    reply_markup = build_leave_group_menu(user_groups) # Используем функцию из utils
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

    # Устанавливаем флаг edit_message в False и сохраняем chat_id
    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_groups(update, context)  # Передаем update и context


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

    reply_markup = build_delete_group_menu(groups_list)  # Используем функцию из utils
    await update.message.reply_text("📋 Выберите группу для *удаления*:", reply_markup=reply_markup)

async def delete_group_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки удаления группы."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']

    user_id = update.effective_user.id
    try:
        group_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Ошибка: некорректный формат")
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

    # Устанавливаем флаг edit_message в False и сохраняем chat_id
    context.user_data['chat_id'] = query.message.chat_id
    context.user_data['edit_message'] = False
    await show_groups(update, context) # Передаем update и context

async def group_info_button(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки просмотра информации о группе."""
    query = update.callback_query
    await query.answer()
    conn = context.bot_data['conn']
    group_id = int(query.data.split("_")[2])

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
        buttons.append(InlineKeyboardButton("➕ Присоединиться", callback_data=f"join_group_{group_id}"))

    if group['creator_id'] == user_id or user_id == ADMIN_ID:
        buttons.append(InlineKeyboardButton("❌ Удалить группу", callback_data=f"delete_group_{group_id}"))

    buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="show_groups"))
    
    reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

    await query.edit_message_text(
        f"📋 Информация о группе {group['group_name']}:\n\n"
        f"👥 Участники:\n{users_text}",
        reply_markup=reply_markup
    )