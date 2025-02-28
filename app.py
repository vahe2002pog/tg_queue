import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, BotCommand, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, ApplicationBuilder, Defaults, ConversationHandler, JobQueue
from datetime import datetime, timedelta
from config import TOKEN, ADMIN_ID
from geopy.distance import geodesic
import asyncio
import httpx

# Структура данных для хранения очередей
queues = {}  # Словарь для хранения очередей
user_names = {}  # Словарь для хранения имя пользователей
user_state = {}  # Словарь для хранения состояния (запрос имени или уже введено)

# Stages для ConversationHandler
QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHANGE_NAME = range(4) # Добавлен CHANGE_NAME

# Координаты выбранной точки для проверки расстояния (например, координаты места очереди)
mathfac_coordinates = (57.159312774716255, 65.52250817857353)

# Настроим логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Функция для отправки уведомлений пользователям
async def send_notification(user_id: int, message: str, context: CallbackContext):
    try:
        await context.bot.send_message(user_id, message)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Команда /start — запросить имя пользователя
async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],  # Existing button
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]  # New button
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if user.id not in user_state or user_state[user.id] != "name_entered":
        # Запрашиваем имя, если оно еще не введено
        await update.message.reply_text("Привет! Пожалуйста, введите ваше имя:")
        user_state[user.id] = "waiting_for_name"
    else:
        # Показываем клавиатуру выбора, если имя уже введено
        await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

# Обработчик нажатий на кнопки главного меню
async def main_menu_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_queues":
        await show_queues(update, context)
    elif query.data == "change_name":
        await change_name_start(update, context)

# Обработчик ввода имя пользователя
async def set_name(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = update.message.text  # Получаем введенное имя

    # Сохраняем имя пользователя в словарь
    user_names[user.id] = user_name

    # Подтверждаем, что имя сохранено
    await update.message.reply_text(f"Ваше имя '{user_name}' сохранено.")
    
    # Меняем состояние, чтобы больше не запрашивать имя
    user_state[user.id] = "name_entered"

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

# Обработчик начала смены имени
async def change_name_start(update: Update, context: CallbackContext) -> None:
    await update.callback_query.message.reply_text("Пожалуйста, введите новое имя:")
    return CHANGE_NAME

# Обработчик получения нового имени
async def change_name(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    new_name = update.message.text

    # Обновляем имя пользователя в словаре
    user_names[user.id] = new_name

    # Подтверждаем, что имя изменено
    await update.message.reply_text(f"Ваше имя изменено на '{new_name}'.")
    user_state[user.id] = "name_entered" # Update user state

    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)

    return ConversationHandler.END # End conversation

# Обработчик отмены смены имени
async def change_name_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Смена имени отменена.")
    # Показываем кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("Показать очереди", callback_data="show_queues")],
        [InlineKeyboardButton("Сменить имя", callback_data="change_name")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=reply_markup)
    return ConversationHandler.END

# Обработчик начала создания очереди
async def create_queue_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Пожалуйста, введите название очереди:")
    return QUEUE_NAME

# Обработчик получения названия очереди
async def create_queue_name(update: Update, context: CallbackContext) -> int:
    context.user_data['queue_name'] = update.message.text
    await update.message.reply_text("Теперь введите дату начала очереди в формате ДД.ММ.ГГ:")
    return QUEUE_DATE

# Обработчик получения даты очереди
async def create_queue_date(update: Update, context: CallbackContext) -> int:
    try:
        datetime.strptime(update.message.text, "%d.%m.%y")
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Пожалуйста, используйте ДД.ММ.ГГ.")
        return QUEUE_DATE

    context.user_data['queue_date'] = update.message.text
    await update.message.reply_text("И, наконец, введите время начала очереди в формате ЧЧ:ММ:")
    return QUEUE_TIME

# Обработчик получения времени очереди и создания очереди
async def create_queue_time(update: Update, context: CallbackContext) -> int:
    try:
        datetime.strptime(update.message.text, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, используйте ЧЧ:ММ.")
        return QUEUE_TIME

    context.user_data['queue_time'] = update.message.text

    # Создаем очередь
    name = context.user_data['queue_name']
    date_str = context.user_data['queue_date']
    time_str = context.user_data['queue_time']

    try:
        start_time = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    except ValueError:
        await update.message.reply_text("Произошла ошибка при создании очереди. Проверьте формат даты и времени.")
        return ConversationHandler.END

    queues[name] = {
        'name': name,
        'start_time': start_time,
        'users': [],
        'current_index': 0
    }

    await update.message.reply_text(f"Очередь '{name}' создана и будет доступна с {start_time.strftime('%d.%m.%y %H:%M')}.")
    
    # Автоматическое удаление очереди через 5 часов
    context.job_queue.run_once(delete_queue_job, 5 * 3600, name)  # 5 hours in seconds

    # Завершаем ConversationHandler
    return ConversationHandler.END

# Функция для автоматического удаления очереди
async def delete_queue_job(context: CallbackContext) -> None:
    queue_name = context.job.data
    if queue_name in queues:
        del queues[queue_name]
        # Отправляем уведомление администратору об удалении очереди
        await context.bot.send_message(ADMIN_ID, f"Очередь '{queue_name}' была автоматически удалена.")
        logger.info(f"Очередь '{queue_name}' была автоматически удалена.")
    else:
        logger.warning(f"Попытка удалить несуществующую очередь: {queue_name}")

# Обработчик отмены создания очереди
async def create_queue_cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Создание очереди отменено.")
    return ConversationHandler.END

# Команда /delete_queue — удаление очереди администратором
async def delete_queue(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    if user.id == ADMIN_ID:
        # Проверяем, что введено название очереди для удаления
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /delete_queue <название_очереди>")
            return

        # Получаем название очереди
        queue_name = context.args[0]

        # Проверяем, существует ли очередь с таким названием
        if queue_name not in queues:
            await update.message.reply_text(f"Очередь '{queue_name}' не существует.")
            return

        # Удаляем очередь
        del queues[queue_name]
        await update.message.reply_text(f"Очередь '{queue_name}' успешно удалена.")
    else:
        await update.message.reply_text("Только администратор может удалить очередь.")

# Команда /leave — показать очереди, в которых состоит пользователь, и выйти из выбранной
async def leave_queue(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = [queue_name for queue_name, queue in queues.items() if user_name in queue['users']]
    
    if not user_queues:
        await update.message.reply_text("Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для выхода из очереди
    keyboard = [
        [InlineKeyboardButton(queue_name, callback_data=f"leave_{queue_name}")]
        for queue_name in user_queues
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите очередь, из которой хотите выйти:", reply_markup=reply_markup)

# Обработчик нажатий на кнопки выхода из очереди
async def leave_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_name = user_names.get(user.id)
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data

    if not user_name:
        await query.edit_message_text("Для начала введите ваше имя с помощью команды /start.")
        return

    if queue_name not in queues:
        await query.edit_message_text("Такой очереди нет.")
        return

    queue = queues[queue_name]
    
    if user_name in queue['users']:
        queue['users'].remove(user_name)
        await query.edit_message_text(f"Вы вышли из очереди: {queue_name}.")
    else:
        await query.edit_message_text(f"Вы не состоите в очереди: {queue_name}.")

# Команда /skip — пропуск хода
async def skip_turn(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = [queue_name for queue_name, queue in queues.items() if user_name in queue['users']]
    
    if not user_queues:
        await update.message.reply_text("Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для пропуска хода
    keyboard = [
        [InlineKeyboardButton(queue_name, callback_data=f"skip_{queue_name}")]
        for queue_name in user_queues
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите очередь, чтобы пропустить свой ход:", reply_markup=reply_markup)

# Обработчик нажатий на кнопки пропуска хода
async def skip_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_name = user_names.get(user.id)
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data

    if not user_name:
        await query.edit_message_text("Для начала введите ваше имя с помощью команды /start.")
        return

    if queue_name not in queues:
        await query.edit_message_text("Такой очереди нет.")
        return

    queue = queues[queue_name]

    # Проверяем, если это действительно ход пользователя
    if user_name != queue['users'][queue['current_index']]:
        await query.edit_message_text("Это не ваш ход!")
        return

    # Проверяем, что следующий пользователь существует
    if queue['current_index'] + 1 < len(queue['users']):
        # Меняем местами текущего пользователя и следующего
        queue['users'][queue['current_index']], queue['users'][queue['current_index'] + 1] = \
            queue['users'][queue['current_index'] + 1], queue['users'][queue['current_index']]
        
        # Перемещаем указатель на следующий элемент
        queue['current_index'] += 1
        await query.edit_message_text(f"Вы пропустили свой ход. Ваш ход теперь после {queue['users'][queue['current_index']]}.")

    else:
        await query.edit_message_text("Вы находитесь в последней позиции и не можете пропустить ход.")


# Команда /queue_info — просмотр списка людей в очереди
async def queue_info(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = [queue_name for queue_name, queue in queues.items() if user_name in queue['users']]
    
    if not user_queues:
        await update.message.reply_text("Вы не состоите в ни одной очереди.")
        return

    # Формируем клавиатуру с кнопками для просмотра информации о очереди
    keyboard = [
        [InlineKeyboardButton(queue_name, callback_data=f"info_{queue_name}")]
        for queue_name in user_queues
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите очередь для просмотра списка участников:", reply_markup=reply_markup)

# Обработчик нажатий на кнопки просмотра информации о очереди
async def queue_info_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_name = user_names.get(user.id)
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data

    if not user_name:
        await query.edit_message_text("Для начала введите ваше имя с помощью команды /start.")
        return

    if queue_name not in queues:
        await query.edit_message_text("Такой очереди нет.")
        return

    queue = queues[queue_name]
    users_list = "\n".join(f"{i+1}. {user}" for i, user in enumerate(queue['users']))
    await query.edit_message_text(f"Список участников очереди {queue_name}:\n{users_list}")
    
# Функция для отображения списка очередей
async def show_queues(update: Update, context: CallbackContext) -> None:
    if queues:
        keyboard = [
            [InlineKeyboardButton(queue['name'], callback_data=f"ask_location_{queue['name']}")] 
            for queue in queues.values()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите очередь для записи:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Нет доступных очередей.")

async def ask_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    queue_name = query.data.split("_")[2]
    context.user_data['queue_name'] = queue_name

    keyboard = [[KeyboardButton(text="Поделиться геолокацией", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"Для записи в очередь '{queue_name}', поделитесь геолокацией:",
        reply_markup=reply_markup
    )

async def handle_location(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    location = update.message.location
    queue_name = context.user_data.get('queue_name')

    # Удаляем клавиатуру
    reply_markup = ReplyKeyboardMarkup([[]], resize_keyboard=True)
    await update.message.reply_text("Геолокация получена...", reply_markup=reply_markup)

    if not queue_name:
        await update.message.reply_text("Ошибка: название очереди не найдено.")
        return

    queue_coord = mathfac_coordinates
    user_coord = (location.latitude, location.longitude)
    distance = geodesic(user_coord, queue_coord).meters

    if distance <= 100:
        queue = queues[queue_name]
        user_name = user_names.get(user.id)
        if user_name and user_name not in queue['users']:
            queue['users'].append(user_name)
            await update.message.reply_text(f"Вы записаны в очередь '{queue_name}'.")
        else:
            await update.message.reply_text(f"Вы уже в очереди '{queue_name}'.")
    else:
        await update.message.reply_text("Слишком далеко для записи в очередь.")

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
    except httpx.ConnectError as e:
        logger.error(f"Не удалось подключиться к серверам Telegram для установки команд: {e}")
    except Exception as e:
        logger.error(f"Не удалось установить команды: {e}")

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
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))

    # Обработчики нажатий кнопок
    application.add_handler(CallbackQueryHandler(ask_location, pattern="^ask_location_"))
    application.add_handler(CallbackQueryHandler(leave_button, pattern="leave_"))
    application.add_handler(CommandHandler("skip", skip_turn))
    application.add_handler(CallbackQueryHandler(queue_info_button, pattern="info_"))

    # Обработчик неизвестных callback query (это важно!)
    application.add_handler(CallbackQueryHandler(unknown))

    # Запускаем приложение
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()