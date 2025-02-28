import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackContext
from datetime import datetime
from utils import GMT_PLUS_5

logger = logging.getLogger(__name__)

async def leave_queue(update: Update, context: CallbackContext) -> None:
    from main import conn, user_names  # Import here to avoid circular import
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update, context)
    
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

async def get_user_queues(update: Update, context: CallbackContext) -> list[str]:
    from main import conn  # Import here to avoid circular import
    user_id = update.message.from_user.id  # Получаем ID пользователя
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT queues.queue_name FROM queues
            JOIN queue_users ON queues.queue_name = queue_users.queue_name
            WHERE queue_users.user_id = ?
        """, (user_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очередей пользователя из базы данных: {e}")
        return []

async def leave_button(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_id = user.id
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data

    # Удаляем пользователя из очереди в базе данных
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_name = ? AND user_id = ?", (queue_name, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} удален из очереди '{queue_name}' в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении пользователя из очереди в базе данных: {e}")
    
    await query.edit_message_text(f"Вы вышли из очереди: {queue_name}.")

async def skip_turn(update: Update, context: CallbackContext) -> None:
    from main import conn, user_names  # Import here to avoid circular import
    user = update.message.from_user
    user_id = update.message.from_user.id
    user_name = user_names.get(user_id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update, context)
    
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

async def skip_button(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие кнопки
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data
    user_id = update.effective_user.id
    
    try:
        # 1. Получаем имя из БД
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            user_name = result[0]
        else:
            await query.edit_message_text("Не удалось найти ваше имя.")
            return

        # 2. Получаем очередь из базы данных
        queue = await get_queue(queue_name)
        if not queue:
            await query.edit_message_text("Такой очереди нет.")
            return

        queue_users = await get_queue_users_name(queue_name) #извлекаем имена

        if user_name not in queue_users:
             await query.edit_message_text("Вы не состоите в этой очереди.")
             return

        #3. Извлекаем queue_users в числовом виде, чтобы можно было работать с очередью
        queue_users_ids = await get_queue_users_ids(queue_name) 
        if not queue_users_ids:
            await query.edit_message_text("В очереди пока нет участников.")
            return

        current_index = queue_users_ids.index(user_id)
        
        if current_index+1 < len(queue_users_ids):
            #Меняем местами текущего пользователя и следующего
            
            user1_id=queue_users_ids[current_index]
            user2_id=queue_users_ids[current_index+1]

            await swap_queue_users(queue_name,user1_id,user2_id)

            #Добавлена проверка на наличие второго пользователя, а также извлечение ника
            #Нужно извлекать не из user_names, a из БД, чтобы было актуальное инфо
            user2_name= await get_user_name(user2_id)
            if user2_name:
               await query.edit_message_text(f"Вы пропустили свой ход. Ваш ход теперь после  {user2_name}.")
            else: 
               await query.edit_message_text(f"Вы пропустили свой ход. Cледующий участник проинформирован")

        else:
            await query.edit_message_text("Вы находитесь в конце очереди и не можете пропустить ход.")
            return


    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")

async def get_queue_users_ids(queue_name: str) -> list[int]:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.user_id FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_name = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_name,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении участников очереди из базы данных: {e}")
        return []

async def swap_queue_users(queue_name:str, user1_id:int, user2_id:int):
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        #cursor.execute("""SELECT user_id FROM queue_users WHERE queue_name = ?""",(queue_name,))

        #1. Получаем время для 1 пользователя
        cursor.execute("""SELECT join_time FROM queue_users WHERE queue_name = ? AND user_id=?""",(queue_name,user1_id))
        result1 = cursor.fetchone()
        time1=result1[0]

         #2. Получаем время для 2 пользователя
        cursor.execute("""SELECT join_time FROM queue_users WHERE queue_name = ? AND user_id=?""",(queue_name,user2_id))
        result2 = cursor.fetchone()
        time2=result2[0]


        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_name = ? AND user_id = ?", (time2, queue_name, user1_id))
        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_name = ? AND user_id = ?", (time1, queue_name, user2_id))
        
        
        conn.commit()
        logger.info(f"Пользователи с id {user1_id} и {user2_id}  в очереди '{queue_name}' успешно поменялись местами ")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обмене пользователями: {e}")

async def queue_info(update: Update, context: CallbackContext) -> None:
    from main import conn, user_names  # Import here to avoid circular import
    user = update.message.from_user
    user_name = user_names.get(user.id, None)

    if not user_name:
        await update.message.reply_text("Для начала введите ваше имя с помощью команды /start.")
        return

    # Находим очереди, в которых состоит пользователь
    user_queues = await get_user_queues(update,context)
    
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

async def queue_info_button(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    query = update.callback_query
    query.answer()  # Подтверждаем нажатие кнопки

    user = query.from_user  # Используем from_user из callback_query, а не из message
    user_id = update.effective_user.id
    queue_name = query.data.split("_")[1]  # Извлекаем название очереди из callback_data

     # Получаем список участников очереди из базы данных
    users_list = await get_queue_users_name(queue_name)
    if not users_list:
        await query.edit_message_text("В очереди пока нет участников.")
        return

    # Формируем сообщение со списком участников
    users_text = ""
    queue_users_ids = await get_queue_users_ids(queue_name)

    for i, user_id in enumerate(queue_users_ids):
        user_name = await get_user_name(user_id) #Исправлено
        if user_name:
           users_text += f"{i+1}. {user_name}\n"
        else:
           users_text += f"{i+1}. (Пользователь не найден)\n" #Для дебага
           

    await query.edit_message_text(f"Список участников очереди {queue_name}:\n{users_text}")

async def get_queue_users_name(queue_name: str) -> list[str]:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.name FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_name = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_name,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении участников очереди из базы данных: {e}")
        return []

async def get_user_name(user_id: int)->str | None:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("""SELECT name FROM users WHERE user_id = ?""",(user_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени из базы данных: {e}")
        return None

async def show_queues(update: Update, context: CallbackContext) -> None:
   # Получаем список очередей из базы данных
    queues_list = await get_all_queues()

    if queues_list:
        keyboard = []
        for queue in queues_list:  # Iterate over the queues
            keyboard.append([InlineKeyboardButton(queue['queue_name'], callback_data=f"join_queue_{queue['queue_name']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text("Выберите очередь для записи:", reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text("Нет доступных очередей.")

async def get_all_queues() -> list[dict]:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, start_time, latitude, longitude FROM queues")
        results = cursor.fetchall()
        
        #Конвертируем в объекты datetime
        converted_results = []
        for row in results:
            start_time_str = row[1]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None #Если время не найдено - ставим None

            converted_results.append({"queue_name": row[0], "start_time":start_time, "latitude": row[2], "longitude":row[3]})
        
        return converted_results
    
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка очередей из базы данных: {e}")
        return []