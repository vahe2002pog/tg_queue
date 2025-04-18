import logging
from telegram.ext import ApplicationBuilder, Defaults
from telegram import  LinkPreviewOptions, Update
import asyncio
from broadcasts import *
from main_menu import *
from queues import *
from groups import *
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
        migrate_database(conn)

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
        entry_points=[CallbackQueryHandler(create_queue, pattern="^create_queue$")],
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
            TIME_WITHOUT_LOCATION: [  # Новый шаг
                CommandHandler("cancel", cancel),
                CommandHandler("skip", set_time_without_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_time_without_location)
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
        entry_points=[CallbackQueryHandler(create_group, pattern="^create_group$")],
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
        entry_points=[CallbackQueryHandler(create_broadcast, pattern="^create_broadcast$")],
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
    application.add_handler(broadcast_handler)

    application.add_handler(CommandHandler("start", handle_deeplink, filters.Regex(JOIN_QUEUE_PAYLOAD)))
    application.add_handler(CommandHandler("start", handle_group_deeplink, filters.Regex(JOIN_GROUP_PAYLOAD)))

    # Основной ConversationHandler для старта
    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Добавляем ConversationHandler в приложение
    application.add_handler(start_conv_handler)

    # ConversationHandler для выбора часового пояса
    timezone_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(select_timezone_start, pattern="^select_timezone$")],
        states={
            SELECT_TIMEZONE: [CallbackQueryHandler(select_timezone)],
            # SELECT_TIMEZONE_BY_LOCATION: [CallbackQueryHandler(select_timezone_by_location, pattern="^select_location_tz$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Добавляем ConversationHandler в приложение
    application.add_handler(timezone_conv_handler)


    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("help", help_command))

    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    
    # Обработчики нажатий кнопок
    application.add_handler(CallbackQueryHandler(main_menu_buttons, pattern="^(show_queues|show_groups|show_broadcasts|change_name|select_timezone|help|main_menu)$"))
    application.add_handler(CallbackQueryHandler(queue_info_button, pattern="^queue_info_"))
    application.add_handler(CallbackQueryHandler(group_info_button, pattern="^group_info_"))
    application.add_handler(CallbackQueryHandler(broadcast_info_button, pattern="^broadcast_info_"))
    application.add_handler(CallbackQueryHandler(skip_button, pattern="^skip_"))
    application.add_handler(CallbackQueryHandler(leave_button, pattern="^leave_queue_"))
    application.add_handler(CallbackQueryHandler(delete_queue_button, pattern="^delete_queue_"))
    application.add_handler(CallbackQueryHandler(leave_group_button, pattern="^leave_group_"))
    application.add_handler(CallbackQueryHandler(delete_group_button, pattern="^delete_group_"))
    application.add_handler(CallbackQueryHandler(cancel_broadcast_button, pattern="^cancel_broadcast_"))
    application.add_handler(CallbackQueryHandler(handle_join_queue, pattern="^join_queue_"))
    application.add_handler(CallbackQueryHandler(join_group, pattern="^join_group_"))
    application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$"))

    # Обработчики для подтверждения действий
    application.add_handler(CallbackQueryHandler(generate_queue_invite_button, pattern="^invite_queue_"))
    application.add_handler(CallbackQueryHandler(generate_group_invite_button, pattern="^invite_group_"))
    application.add_handler(CallbackQueryHandler(confirm_leave_queue, pattern="^confirm_leave_queue_"))
    application.add_handler(CallbackQueryHandler(cancel_leave_queue, pattern="^cancel_leave_queue_"))
    application.add_handler(CallbackQueryHandler(confirm_skip, pattern="^confirm_skip_"))
    application.add_handler(CallbackQueryHandler(cancel_skip, pattern="^cancel_skip_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_queue, pattern="^confirm_delete_queue_"))
    application.add_handler(CallbackQueryHandler(cancel_delete_queue, pattern="^cancel_delete_queue_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_group, pattern="^confirm_delete_group_"))
    application.add_handler(CallbackQueryHandler(cancel_delete_group, pattern="^cancel_delete_group_"))
    application.add_handler(CallbackQueryHandler(confirm_leave_group, pattern="^confirm_leave_group_"))
    application.add_handler(CallbackQueryHandler(cancel_leave_group, pattern="^cancel_leave_group_"))
    application.add_handler(CallbackQueryHandler(confirm_cancel_broadcast, pattern="^confirm_cancel_broadcast_"))
    application.add_handler(CallbackQueryHandler(cancel_cancel_broadcast, pattern="^cancel_cancel_broadcast_"))

    application.add_handler(CallbackQueryHandler(unknown)) #Важно!
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    if conn:
        conn.close()
        logger.info("Соединение с базой данных закрыто")

if __name__ == "__main__":
    main()