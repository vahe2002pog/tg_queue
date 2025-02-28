import logging
import sqlite3
from telegram import Update, CallbackContext
from datetime import datetime
from utils import GMT_PLUS_5

logger = logging.getLogger(__name__)

async def get_queue(queue_name: str) -> dict | None:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, start_time, latitude, longitude FROM queues WHERE queue_name = ?", (queue_name,))
        result = cursor.fetchone()
        if result:
            start_time_str = result[1]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            return {"queue_name": result[0], "start_time":start_time, "latitude": result[2], "longitude": result[3]}
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очереди из базы данных: {e}")
        return None

async def is_user_in_queue(queue_name: str, user_id: int) -> bool:
    from main import conn  # Import here to avoid circular import
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM queue_users WHERE queue_name = ? AND user_id = ?", (queue_name, user_id))
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при проверке пользователя в очереди: {e}")
        return False

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