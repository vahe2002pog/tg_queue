from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove, LinkPreviewOptions
from telegram.ext import CallbackContext
from datetime import datetime
import logging
from geopy.distance import geodesic
from db import get_queue_by_id, get_queue_name_by_id, add_user_to_queue, get_queue_users_names, get_queue_users_ids, get_user_name
from config import GET_LOCATION_URL
from varibles import GMT_PLUS_5, max_distance

logger = logging.getLogger(__name__)

async def send_notification(user_id: int, message: str, context: CallbackContext):
    """Отправляет уведомление пользователю."""
    try:
        await context.bot.send_message(user_id, message)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    """Собирает inline клавиатуру."""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return InlineKeyboardMarkup(menu)

def build_main_menu():
    """Создает клавиатуру главного меню."""
    buttons = [
        InlineKeyboardButton("📋 Показать очереди", callback_data="show_queues"),
        InlineKeyboardButton("🔄 Сменить имя", callback_data="change_name")
    ]
    return build_menu(buttons, n_cols=1)

def build_location_menu():
    """Создает клавиатуру выбора местоположения."""
    buttons = [
        InlineKeyboardButton("🏛 МатФак", callback_data="location_mathfac"),
        InlineKeyboardButton("📍 Указать геолокацию", callback_data="location_custom")
    ]
    return build_menu(buttons, n_cols=1)

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

    if distance <= max_distance:
        join_time = datetime.now(GMT_PLUS_5).isoformat()
        add_user_to_queue(context.bot_data['conn'], queue_id, user_id, join_time)  # Corrected
        await update.message.reply_text(f"✅ Вы записаны в очередь {queue['queue_name']}.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Слишком далеко для записи в очередь.", reply_markup=ReplyKeyboardRemove())

async def create_join_queue_button(context, queue_id):
    """Создает кнопку 'Присоединиться к очереди'."""
    deeplink = f"https://t.me/{context.bot.username}?start=join_{queue_id}"
    keyboard = [[InlineKeyboardButton("📌 Присоединиться к очереди", url=deeplink)]]
    return InlineKeyboardMarkup(keyboard)

async def send_queue_created_message(update, context, queue_name, start_time, reply_markup):
    """Отправляет сообщение об успешном создании очереди."""

    message = await update.effective_message.reply_text(
        f"✅ Очередь *{queue_name}* успешно создана! 🕒\n"
        f"📆 Дата: *{start_time.strftime('%d.%m.%y')}*\n"
        f"⏰ Время: *{start_time.strftime('%H:%M')}*\n\n"
        f"➡ *Нажмите кнопку, чтобы присоединиться!*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    return message

def build_queues_menu(queues_list):
    """Создает меню со списком очередей."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"join_queue_{queue['queue_id']}") for queue in queues_list]
    return build_menu(buttons, n_cols=1)

def build_delete_queue_menu(queues_list):
    """Создает меню для удаления очередей."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"delete_queue_{queue['queue_id']}") for queue in queues_list]
    return build_menu(buttons, n_cols=1)

def build_leave_queue_menu(user_queues):
    """Создает меню для выхода из очередей."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"leave_{queue['queue_id']}") for queue in user_queues]
    return build_menu(buttons, n_cols=1)

def build_skip_turn_menu(user_queues):
     """Создает меню для пропуска хода."""
     buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"skip_{queue['queue_id']}") for queue in user_queues]
     return build_menu(buttons, n_cols=1)

def build_queue_info_menu(user_queues):
    """Создает меню для просмотра информации об очередях."""
    buttons = [InlineKeyboardButton(queue['queue_name'], callback_data=f"info_{queue['queue_id']}") for queue in user_queues]
    return build_menu(buttons, n_cols=1)
    
async def generate_queue_info_message(conn, queue_id):
    """Генерирует сообщение со списком участников очереди."""
    queue_name = get_queue_name_by_id(conn, queue_id)
    if not queue_name:
        return "❌ Ошибка: Не удалось получить имя очереди."

    users_list = get_queue_users_names(conn, queue_id)
    if not users_list:
        return "🔍 В очереди пока нет участников."

    users_text = ""
    queue_users_ids = get_queue_users_ids(conn, queue_id)

    for i, user_id in enumerate(queue_users_ids):
        user_name = get_user_name(conn, user_id)
        users_text += f"{i+1}. {user_name if user_name else '(Пользователь не найден)'}\n"

    return f"📋 Список участников очереди {queue_name}:\n{users_text}"

def build_web_app_location_button():
    """Создает кнопку для отправки геолокации через Web App."""
    keyboard = [[KeyboardButton("📍 Отправить геолокацию", web_app=WebAppInfo(url=GET_LOCATION_URL))]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def build_group_menu(groups: list[dict]) -> InlineKeyboardMarkup:
    """Создает меню со списком групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"join_group_{group['group_id']}") for group in groups]
    return build_menu(buttons, n_cols=1)

def build_select_group_menu(groups: list[dict], with_no_group: bool = True) -> InlineKeyboardMarkup:
    """Создает меню выбора группы при создании очереди."""
    buttons = []
    if with_no_group:
        buttons.append(InlineKeyboardButton("Без группы", callback_data="select_group_none"))
    buttons.extend([InlineKeyboardButton(group['group_name'], callback_data=f"select_group_{group['group_id']}") for group in groups])
    return build_menu(buttons, n_cols=1)

def build_leave_group_menu(user_groups: list[dict])-> InlineKeyboardMarkup:
    """Создает меню для выхода из групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"leave_group_{group['group_id']}") for group in user_groups]
    return build_menu(buttons, n_cols=1)

def build_delete_group_menu(groups: list[dict]) -> InlineKeyboardMarkup:
    """Создает меню для удаления групп."""
    buttons = [InlineKeyboardButton(group['group_name'], callback_data=f"delete_group_{group['group_id']}") for group in groups]

    return build_menu(buttons, n_cols=1)