# main.py

import logging
from telegram.ext import ApplicationBuilder, Defaults
from telegram import  LinkPreviewOptions, Update
import asyncio
from handlers import (
    start, set_name, change_name_start, change_name, create_queue_start,
    create_queue_name, create_queue_date, create_queue_time,
    create_queue_location, create_queue_location_custom, create_queue_final,
    handle_deeplink, delete_queue_job, delete_queue_start, delete_queue_button,
    leave_queue, leave_button, skip_turn, skip_button, queue_info,
    queue_info_button, show_queues, handle_web_app_data, ask_location,
    main_menu_buttons, unknown, help_command,
    cancel, set_commands, load_scheduled_broadcasts, start_broadcast, broadcast_message,
    broadcast_targets, broadcast_schedule, send_broadcast
)

from telegram.ext import (
     CommandHandler,  CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, JobQueue
)

from config import TOKEN, QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHOOSE_LOCATION, CHANGE_NAME, BROADCAST_MESSAGE, BROADCAST_TARGETS, BROADCAST_SCHEDULE, JOIN_QUEUE_PAYLOAD
from db import create_connection, create_tables

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    conn = create_connection()
    if conn:
        create_tables(conn)

    job_queue = JobQueue()
    builder = ApplicationBuilder().token(TOKEN)
    defaults = Defaults(
        parse_mode=None,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        allow_sending_without_reply=True,
    )
    builder.defaults(defaults)
    builder.job_queue(job_queue)

    application = builder.build()
    application.bot_data['conn'] = conn #Передаем подключение
    loop.run_until_complete(set_commands(application))

    conv_handler = ConversationHandler( #Создание очереди
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
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    change_name_handler = ConversationHandler( #Смена имени
        entry_points=[CallbackQueryHandler(change_name_start, pattern="^change_name$")],
        states={
            CHANGE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    broadcast_handler = ConversationHandler( #Рассылка
        entry_points=[CommandHandler("broadcast", start_broadcast)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT | filters.PHOTO, broadcast_message)],
            BROADCAST_TARGETS: [MessageHandler(filters.TEXT, broadcast_targets)],
            BROADCAST_SCHEDULE: [MessageHandler(filters.TEXT, broadcast_schedule)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(change_name_handler)
    application.add_handler(broadcast_handler)
    application.add_handler(CallbackQueryHandler(main_menu_buttons, pattern="^(show_queues|change_name)$"))

    # Обработчики команд
    application.add_handler(CommandHandler("start", handle_deeplink, filters.Regex(JOIN_QUEUE_PAYLOAD)))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete_queue", delete_queue_start))
    application.add_handler(CommandHandler("leave", leave_queue))
    application.add_handler(CommandHandler("skip", skip_turn))
    application.add_handler(CommandHandler("queue_info", queue_info))
    application.add_handler(CommandHandler("show_queues", show_queues))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, set_name))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    # Обработчики нажатий кнопок
    application.add_handler(CallbackQueryHandler(ask_location, pattern="^join_queue_"))
    application.add_handler(CallbackQueryHandler(leave_button, pattern="^leave_"))
    application.add_handler(CallbackQueryHandler(skip_button, pattern="^skip_"))
    application.add_handler(CallbackQueryHandler(queue_info_button, pattern="info_"))
    application.add_handler(CallbackQueryHandler(delete_queue_button, pattern="^delete_queue_"))
    application.add_handler(CallbackQueryHandler(unknown)) #Важно!
    application.job_queue.run_once(load_scheduled_broadcasts, 1)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    if conn:
        conn.close()
        logger.info("Соединение с базой данных закрыто")

if __name__ == "__main__":
    main()