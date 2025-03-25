import pytz
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove, LinkPreviewOptions, Update
from telegram.ext import CallbackContext
from datetime import datetime
from geopy.distance import geodesic
from db import get_queue_by_id, get_queue_name_by_id, add_user_to_queue, get_queue_users_names, get_queue_users_ids, get_user_name, get_user_timezone
from config import GET_LOCATION_URL
from varibles import MAX_DISTANCE, JOIN_GROUP_PAYLOAD, JOIN_QUEUE_PAYLOAD, RUSSIAN_TIMEZONES
from crypto import encrypt_data
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

async def send_notification(user_id: int, message: str, context: CallbackContext):
    """Отправляет уведомление пользователю."""
    try:
        await context.bot.send_message(user_id, message)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

def build_menu(buttons, n_cols=1, header_buttons=None, footer_buttons=None):
    """Создает меню из кнопок."""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu

def build_location_menu():
    """Создает клавиатуру выбора местоположения."""
    buttons = [
        InlineKeyboardButton("🏛 МатФак", callback_data="location_mathfac"),
        InlineKeyboardButton("📍 Указать геолокацию", callback_data="location_custom")
    ]
    return InlineKeyboardMarkup(build_menu(buttons)) 

def validate_date(date_str: str) -> bool:
    """Проверяет корректность формата даты."""
    try:
        datetime.strptime(date_str, "%d.%m.%y")
        return True
    except ValueError:
        return False

def validate_time(time_str: str) -> bool:
    """Проверяет корректность формата времени."""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False

async def check_distance_and_join(update, context, queue_id, user_id, lat, lon):
    """Проверяет расстояние и записывает пользователя в очередь."""
    conn = context.bot_data['conn']
    queue = await get_queue_by_id(context.bot_data['conn'], queue_id)
    if not queue:
        await update.message.reply_text("❌ Ошибка: очередь не найдена.", reply_markup=ReplyKeyboardRemove())
        return

    target_coordinates = (queue["latitude"], queue["longitude"])
    user_coord = (lat, lon)
    distance = geodesic(user_coord, target_coordinates).meters
    location_message = await update.effective_message.reply_location(
        latitude=lat,
        longitude=lon,
        reply_markup=None
        )
    context.user_data['location_message_id'] = location_message.message_id

    if distance <= MAX_DISTANCE:
        user_timezone_str = get_user_timezone(conn, user_id)
        user_timezone = pytz.timezone(user_timezone_str)
        join_time = datetime.now(user_timezone).isoformat()
        add_user_to_queue(context.bot_data['conn'], queue_id, user_id, join_time)  # Corrected
        await update.message.reply_text(f"✅ Вы записаны в очередь {queue['queue_name']}.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Слишком далеко для записи в очередь.", reply_markup=ReplyKeyboardRemove())

async def create_join_queue_button(context, queue_id, creator_id):
    """Создает кнопку 'Присоединиться к очереди' с зашифрованным ID."""
    encrypted_id = encrypt_data(queue_id, creator_id)
    deeplink = f"https://t.me/{context.bot.username}?start={JOIN_QUEUE_PAYLOAD}{encrypted_id}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ Присоединиться к очереди", url=deeplink)]])

async def create_join_group_button(context, group_id, creator_id):
    encrypted_id = encrypt_data(group_id, creator_id)
    deeplink = f"https://t.me/{context.bot.username}?start={JOIN_GROUP_PAYLOAD}{encrypted_id}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ Присоединиться к группе", url=deeplink)]])

async def send_queue_created_message(update, context, queue_name, start_time, reply_markup):
    """Отправляет сообщение об успешном создании очереди."""
    # Получаем часовой пояс пользователя
    user_timezone_str = get_user_timezone(conn = context.bot_data['conn'], user_id = update.effective_user.id)

    # Формируем сообщение с локальным временем пользователя
    message = await update.effective_message.reply_text(
        f"✅ Очередь *{queue_name}* успешно создана! 🕒\n"
        f"📆 Дата: *{start_time.strftime('%d.%m.%y')}*\n"
        f"⏰ Время: *{start_time.strftime('%H:%M')}*\n\n"
        f"➡ *Нажмите кнопку, чтобы присоединиться!*",
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    return message

def build_queues_menu(queues_list):
    """Создает меню со списком очередей."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"{JOIN_QUEUE_PAYLOAD}{queue['queue_id']}") for queue in queues_list]
    return InlineKeyboardMarkup(build_menu(buttons))

def build_skip_turn_menu(user_queues):
    """Создает меню для пропуска хода."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"skip_{queue['queue_id']}") for queue in user_queues]
    return InlineKeyboardMarkup(build_menu(buttons))

def build_queue_info_menu(user_queues):
    """Создает меню для просмотра информации об очередях."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"info_{queue['queue_id']}") for queue in user_queues]
    return InlineKeyboardMarkup(build_menu(buttons))

async def generate_queue_info_message(conn, queue_id: int, user_timezone_str: str) -> str:
    """Генерирует сообщение со списком участников очереди с учетом часового пояса пользователя."""
    queue_name = get_queue_name_by_id(conn, queue_id)
    if not queue_name:
        return "❌ Ошибка: Не удалось получить имя очереди."

    queue = await get_queue_by_id(conn, queue_id)
    if not queue:
        return "❌ Ошибка: очередь не найдена."

    start_time = queue['start_time']
    if start_time:
        start_time = convert_time_to_user_timezone(start_time, user_timezone_str)
        start_time_str = start_time.strftime("%d.%m.%y %H:%M")
    else:
        start_time_str = "Не указано"

    users_list = get_queue_users_names(conn, queue_id)
    if not users_list:
        return f"🔍 В очереди {queue_name} пока нет участников. Время начала: {start_time_str}"

    users_text = ""
    queue_users_ids = get_queue_users_ids(conn, queue_id)

    for i, user_id in enumerate(queue_users_ids):
        user_name = get_user_name(conn, user_id)
        users_text += f"{i+1}. {user_name if user_name else '(Пользователь не найден)'}\n"

    return f"📋 Список участников очереди {queue_name} (время начала: {start_time_str}):\n{users_text}"

def build_web_app_location_button(rec_source):
    """Создает кнопку для отправки геолокации через Web App."""
    url = f"{GET_LOCATION_URL}?rec_source={rec_source}"
    keyboard = [[KeyboardButton("📍 Отправить геолокацию", web_app=WebAppInfo(url=url))]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def build_group_menu(groups: list[dict]) -> InlineKeyboardMarkup:
    """Создает меню со списком групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"{JOIN_GROUP_PAYLOAD}{group['group_id']}") for group in groups]
    return InlineKeyboardMarkup(build_menu(buttons))

def build_select_group_menu(groups: list[dict], with_no_group: bool = True) -> InlineKeyboardMarkup:
    """Создает меню выбора группы при создании очереди."""
    buttons = []
    if with_no_group:
        buttons.append(InlineKeyboardButton("Без группы", callback_data="select_group_none"))
    buttons.extend([InlineKeyboardButton(group['group_name'], callback_data=f"select_group_{group['group_id']}") for group in groups])
    return InlineKeyboardMarkup(build_menu(buttons))

def build_leave_group_menu(user_groups: list[dict])-> InlineKeyboardMarkup:
    """Создает меню для выхода из групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"leave_group_{group['group_id']}") for group in user_groups]
    return InlineKeyboardMarkup(build_menu(buttons))

def build_delete_group_menu(groups: list[dict]) -> InlineKeyboardMarkup:
    """Создает меню для удаления групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"delete_group_{group['group_id']}") for group in groups]
    return InlineKeyboardMarkup(build_menu(buttons))

def convert_time_to_user_timezone(server_time: datetime, user_timezone_str: str) -> datetime:
    """Конвертирует время из UTC в часовой пояс пользователя."""
    user_timezone = pytz.timezone(user_timezone_str)

    # Проверяем, есть ли уже таймзона у server_time
    if server_time.tzinfo is None:
        server_time = pytz.UTC.localize(server_time)  # Присваиваем UTC
    else:
        server_time = server_time.astimezone(pytz.UTC)  # Переводим в UTC, если уже есть таймзона
    
    return server_time.astimezone(user_timezone)

def build_main_menu():
    """Создает клавиатуру главного меню."""
    buttons = [
        InlineKeyboardButton("📋 Очереди", callback_data="show_queues"),
        InlineKeyboardButton("👥 Группы", callback_data="show_groups"),
        InlineKeyboardButton("📨 Рассылка", callback_data="show_broadcasts"),
        InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name"),
        InlineKeyboardButton("🕒 Часовой пояс", callback_data="select_timezone"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    ]
    return InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

def error_handler(update: object, context: CallbackContext) -> None:
    """Логирует ошибки, вызванные обновлениями."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def get_all_timezones():
    """Возвращает список всех доступных часовых поясов."""
    return pytz.all_timezones

def get_timezone_by_location(lat, lon):
    """Определяет часовой пояс по координатам."""
    tf = TimezoneFinder()
    return tf.timezone_at(lng=lon, lat=lat)

def build_russian_timezone_menu():
    """Создает меню выбора часового пояса для России."""
    buttons = [InlineKeyboardButton(tz_name, callback_data=f"select_tz_{tz_code}") for tz_name, tz_code in RUSSIAN_TIMEZONES.items()]
    buttons.append(InlineKeyboardButton("📍 Определить по геолокации", callback_data="select_location_tz"))
    return InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

async def generate_invite_button_message(context, entity_type: str, entity_id: int, creator_id: int, entity_name: str, additional_info: str = "") -> tuple:
    """Генерирует сообщение с информацией о сущности (очереди/группе) и кнопкой присоединиться.
    Возвращает кортеж: (текст сообщения, reply_markup)"""
    
    if entity_type == "queue":
        payload = JOIN_QUEUE_PAYLOAD
        entity_type_name = "очереди"
        reply_markup = await create_join_queue_button(context, entity_id, creator_id)
    elif entity_type == "group":
        payload = JOIN_GROUP_PAYLOAD
        entity_type_name = "группы"
        reply_markup = await create_join_group_button(context, entity_id, creator_id)
    else:
        raise ValueError("Неверный тип сущности")

    message_text = (
        f"🔗 *Приглашение в {entity_type_name}*:\n\n"
        f"📌 Название: *{entity_name}*\n"
        f"{additional_info}\n"
        f"➡ Нажмите кнопку ниже, чтобы присоединиться!"
    )
    
    return message_text, reply_markup