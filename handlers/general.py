import logging
from telegram import Update, CallbackContext
from telegram import BotCommand

logger = logging.getLogger(__name__)

# Обработчик для неизвестных запросов CallbackQuery
async def unknown(update: Update, context: CallbackContext) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Я не понимаю этот запрос!")

# Функция для вывода списка доступных команд
async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "/start - Начать взаимодействие с ботом (ввод имени)\n"
        "/create_queue - Создать очередь\n"
        "/leave - Покинуть очередь\n"
        "/skip - Пропустить свой ход в очереди\n"
        "/queue_info - Просмотреть список людей в очереди\n"
        "/show_queues - Показать доступные очереди и записаться в них\n"
        "/help - Получить помощь (список команд)\n"
    )
    await update.message.reply_text(help_text)

# Функция для установки меню команд
async def set_commands(app):
    from main import conn  # Import here to avoid circular import
    commands = [
        BotCommand("start", "Начать"),
        BotCommand("create_queue", "Создать очередь"),
        BotCommand("leave", "Покинуть очередь"),
        BotCommand("skip", "Пропустить ход"),
        BotCommand("queue_info", "Список в очереди"),
        BotCommand("show_queues", "Показать очереди"),
        BotCommand("help", "Помощь"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logger.info("Команды успешно установлены.")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")