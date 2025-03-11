import logging
from telegram.ext import ApplicationBuilder, Defaults
from telegram import  LinkPreviewOptions, Update
import asyncio
from handlers import *
from telegram.ext import (
     CommandHandler,  CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, JobQueue
)

from config import *
from varibles import *
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
        parse_mode = "Markdown",
        link_preview_options = LinkPreviewOptions(is_disabled=True),
        allow_sending_without_reply=True,
    )
    builder.defaults(defaults)
    builder.job_queue(job_queue)


    application = builder.build()
    application.bot_data['conn'] = conn
    loop.run_until_complete(set_commands(application))

    loop.run_until_complete(load_scheduled_broadcasts(job_queue))

    create_queue_handler = ConversationHandler(
        entry_points=[CommandHandler("create_queue", create_queue)],
        states={
            QUEUE_NAME: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_queue_name)
            ],
            QUEUE_DATE: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT, create_queue_date)
            ],
            QUEUE_TIME: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT, create_queue_time)
            ],
            CHOOSE_LOCATION: [
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(create_queue_location, pattern="^location_(mathfac|custom)$"),
                MessageHandler(filters.LOCATION, create_queue_location_custom),
            ],
            CHOOSE_GROUP: [
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(create_queue_choose_group, pattern="^select_group_.*")
            ],
            SEND_NOTIFICATION: [
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(send_notification_choice, pattern="^send_notification_(yes|no)$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(create_queue_handler)

    change_name_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(change_name_start, pattern="^change_name$")],
        states={
            CHANGE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, change_name)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(change_name_handler)

    create_group_handler = ConversationHandler(
        entry_points=[CommandHandler("create_group", create_group)],
        states={
            GROUP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_group_name)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(create_group_handler)

    # ConversationHandler для рассылки
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", create_broadcast)],
        states={
            BROADCAST_MESSAGE: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, broadcast_message)
            ],
            BROADCAST_RECIPIENTS: [
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(broadcast_choose_group, pattern="^select_group_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_recipients_input),
            ],
            BROADCAST_SCHEDULE: [
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT, broadcast_schedule),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Добавляем обработчик в приложение
    application.add_handler(broadcast_handler)

    # ConversationHandler для удаления рассылок
    # delete_broadcast_handler = ConversationHandler(
    #     entry_points=[CommandHandler("delete_broadcast", delete_broadcast_start)],
    #     states={
    #         DELETE_BROADCAST: [
    #             CallbackQueryHandler(delete_broadcast_confirm, pattern="^delete_broadcast_")
    #         ]
    #     },
    #     fallbacks=[CommandHandler("cancel", cancel)],
    # )

    # # Добавляем обработчик в приложение
    # application.add_handler(delete_broadcast_handler)

    application.add_handler(CommandHandler("start", handle_deeplink, filters.Regex(JOIN_QUEUE_PAYLOAD)))

    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

	 # Добавляем ConversationHandler в приложение
    application.add_handler(start_conv_handler)


    # application.add_handler(CallbackQueryHandler(main_menu_buttons, pattern="^(show_queues|change_name)$"))

    # Обработчики команд
    # application.add_handler(CommandHandler("delete_queue", delete_queue_start))
    # application.add_handler(CommandHandler("leave", leave_queue))
    # application.add_handler(CommandHandler("skip", skip_turn))
    # application.add_handler(CommandHandler("queue_info", queue_info))
    # application.add_handler(CommandHandler("show_queues", show_queues))
    # application.add_handler(CommandHandler("create_group", create_group_start))
    # application.add_handler(CommandHandler("delete_group", delete_group_start))
    # application.add_handler(CommandHandler("show_groups", show_groups)) 
    # application.add_handler(CommandHandler("leave_group", leave_group_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    
    # Обработчики нажатий кнопок
    application.add_handler(CallbackQueryHandler(main_menu_buttons, pattern="^(show_queues|show_groups|show_broadcasts|change_name|help|main_menu)$"))
    application.add_handler(CallbackQueryHandler(queue_info_button, pattern="^queue_info_"))
    application.add_handler(CallbackQueryHandler(group_info_button, pattern="^group_info_"))
    application.add_handler(CallbackQueryHandler(broadcast_info_button, pattern="^broadcast_info_"))
    application.add_handler(CallbackQueryHandler(create_queue, pattern="^create_queue$"))
    application.add_handler(CallbackQueryHandler(create_group, pattern="^create_group$"))
    application.add_handler(CallbackQueryHandler(create_broadcast, pattern="^create_broadcast$"))
    application.add_handler(CallbackQueryHandler(skip_button, pattern="^skip_"))
    application.add_handler(CallbackQueryHandler(leave_button, pattern="^leave_"))
    application.add_handler(CallbackQueryHandler(delete_queue_button, pattern="^delete_queue_"))
    application.add_handler(CallbackQueryHandler(leave_group_button, pattern="^leave_group_"))
    application.add_handler(CallbackQueryHandler(delete_group_button, pattern="^delete_group_"))
    application.add_handler(CallbackQueryHandler(cancel_broadcast_button, pattern="^cancel_broadcast_"))
    application.add_handler(CallbackQueryHandler(ask_location, pattern="^join_queue_"))
    application.add_handler(CallbackQueryHandler(join_group, pattern="^join_group_"))
    application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$"))

    # application.add_handler(CallbackQueryHandler(delete_group_button, pattern="^delete_group_"))
    # application.add_handler(CallbackQueryHandler(queue_info_button, pattern="info_"))
    # application.add_handler(CallbackQueryHandler(leave_button, pattern="^leave_"))
    # application.add_handler(CallbackQueryHandler(skip_button, pattern="^skip_"))
    # application.add_handler(CallbackQueryHandler(delete_queue_button, pattern="^delete_queue_"))
    # application.add_handler(CallbackQueryHandler(join_group, pattern="^join_group_"))
    # application.add_handler(CallbackQueryHandler(leave_group_button, pattern="^leave_group_"))
    application.add_handler(CallbackQueryHandler(unknown)) #Важно!
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    if conn:
        conn.close()
        logger.info("Соединение с базой данных закрыто")

if __name__ == "__main__":
    main()