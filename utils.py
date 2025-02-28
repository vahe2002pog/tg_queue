import logging
import sqlite3
from telegram import Update, CallbackContext
from datetime import datetime, timedelta, timezone
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Часовой пояс GMT+5
GMT_PLUS_5 = timezone(timedelta(hours=5))

# Функция для отправки уведомлений пользователям
async def send_notification(user_id: int, message: str, context: CallbackContext):
    try:
        await context.bot.send_message(user_id, message)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Функция для автоматического удаления очереди
async def delete_queue_job(context: CallbackContext) -> None:
    queue_name = context.job.data
    from main import conn  # Import here to avoid circular import

    # Удаляем очередь из базы данных
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queues WHERE queue_name = ?", (queue_name,))
        conn.commit()
        logger.info(f"Очередь '{queue_name}' удалена из базы данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении очереди из базы данных: {e}")

    # Также нужно удалить записи из queue_users
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_name = ?", (queue_name,))
        conn.commit()
        logger.info(f"Записи queue_users для очереди '{queue_name}' удалены")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении записей queue_users для очереди '{queue_name}': {e}")

    # Отправляем уведомление администратору об удалении очереди
    await context.bot.send_message(ADMIN_ID, f"Очередь '{queue_name}' была автоматически удалена.")
    logger.info(f"Очередь '{queue_name}' была автоматически удалена.")