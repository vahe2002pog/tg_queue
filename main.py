import logging
from telegram import Update, LinkPreviewOptions
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, ApplicationBuilder, Defaults, ConversationHandler, JobQueue
import asyncio
from config import TOKEN, ADMIN_ID, MF_COORDINATES
from database import create_connection, create_tables
from handlers.start import start, set_name
from handlers.queue_management import create_queue_start, create_queue_name, create_queue_date, create_queue_time, create_queue_location, create_queue_location_custom, create_queue_cancel
from handlers.admin import delete_queue
from handlers.queue_actions import leave_queue, skip_turn, queue_info, leave_button, skip_button, queue_info_button, show_queues
from handlers.general import unknown, help_command, set_commands
from handlers.location import handle_web_app_data, ask_location
from handlers.change_name import change_name_start, change_name, change_name_cancel
from utils import delete_queue_job

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация соединения с базой данных и создание таблиц
conn = create_connection()
if conn:
    create_tables(conn)

# Словари для хранения данных в памяти
user_names = {}  # Словарь для хранения имен пользователей
user_state = {}  # Словарь для хранения состояния (запрос имени или уже введено)

# Stages для ConversationHandler
QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHANGE_NAME, CHOOSE_LOCATION = range(5) # Добавлен CHOOSE_LOCATION

# Обработчик нажатий на кнопки главного меню
async def main_menu_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_queues":
        await show_queues(update, context)
    elif query.data == "change_name":
        await change_name_start(update, context)

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
            QUEUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_queue_date)],
            QUEUE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_queue_time)],
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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete_queue", delete_queue))
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