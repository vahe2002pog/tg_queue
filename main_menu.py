import logging
from telegram import Update, BotCommand, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler

from config import ADMIN_USER_ID
from varibles import *
from db import get_user_data, set_user_name, update_user_name, update_user_state
from utils import *
from groups import *
from broadcasts import *
from queues import *

logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> int:
    """Обработка команды /start."""
    user_id = update.effective_user.id
    conn = context.bot_data['conn']
    query = update.callback_query

    result = get_user_data(conn, user_id)
    if result:
        reply_markup = build_main_menu()
        # Проверяем, нужно ли редактировать сообщение
        if context.user_data.get('edit_message') and query:
            await query.edit_message_text("Главное меню", reply_markup=reply_markup)
            context.user_data['edit_message'] = False
        else:
            # Если не редактируем, отправляем новое сообщение
            if update.message:
                await update.message.reply_text("Главное меню", reply_markup=reply_markup)
            elif query:
                await query.message.reply_text("Главное меню", reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        if update.message:
            await update.message.reply_text("Привет! Пожалуйста, введите ваше *имя*:")
        elif update.callback_query:
            await update.callback_query.message.reply_text("Привет! Пожалуйста, введите ваше *имя*:")
        else:
            logger.error("Не удалось определить источник запроса в функции start.")
            return ConversationHandler.END

        context.user_data['state'] = WAITING_FOR_NAME
        context.user_data['time_zone'] = GMT_PLUS_5 #Временное решение
        return WAITING_FOR_NAME

async def set_name(update: Update, context: CallbackContext) -> int:
    """Обработчик ввода имени пользователя."""
    user_id = update.effective_user.id
    user_name = update.message.text
    conn = context.bot_data['conn']
    time_zone = GMT_PLUS_5

    set_user_name(conn, user_id, user_name, time_zone)
    await update.message.reply_text(f"✅ Ваше имя *{user_name}* сохранено.")
    reply_markup = build_main_menu()
    await update.message.reply_text("Главное меню", reply_markup=reply_markup)
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
    await update.message.reply_text("Главное меню", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую команду и очищает данные."""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def help_command(update: Update, context: CallbackContext) -> None:
    """Выводит список доступных команд."""
    help_text = (
        "/start - Начать\n"
        "/cancel - Отменить\n"
        f"По всем вопросам — {ADMIN_USER_ID}\n"
    )
    await update.effective_message.reply_text(help_text, parse_mode=None)

async def set_commands(app):
    """Устанавливает меню команд."""
    commands = [
        BotCommand("start", "Начать"),
        BotCommand("cancel", "Отмена"),
        BotCommand("help", "Помощь"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Команды установлены.")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")

async def unknown(update: Update, context: CallbackContext) -> None:
    """Обработчик неизвестных CallbackQuery."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("❌ Я не понимаю этот запрос!")
    else:
         await update.message.reply_text("❌ Я не понимаю этот запрос!")

async def back_to_main_menu(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки возврата в главное меню."""
    query = update.callback_query
    await query.answer()

    # Редактируем текущее сообщение, чтобы вернуться в главное меню
    reply_markup = build_main_menu()
    await query.edit_message_text("Главное меню", reply_markup=reply_markup)

async def main_menu_buttons(update: Update, context: CallbackContext) -> None:
    """Обработчик кнопок главного меню."""
    query = update.callback_query
    await query.answer()

    if query.data == "show_queues":
        context.user_data['edit_message'] = True
        await show_queues(update, context)
    elif query.data == "show_groups":
        context.user_data['edit_message'] = True
        await show_groups(update, context)
    elif query.data == "show_broadcasts":
        context.user_data['edit_message'] = True
        await show_broadcasts(update, context)
    elif query.data == "change_name":
        await change_name_start(update, context)
    elif query.data == "help":
        await help_command(update, context)
    elif query.data == "main_menu":
        context.user_data['edit_message'] = True
        await start(update, context)
