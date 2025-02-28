import logging
import sqlite3
from telegram import Update, CallbackContext
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def delete_queue(update: Update, context: CallbackContext) -> None:
    from main import conn  # Import here to avoid circular import
    user = update.message.from_user
    if user.id == ADMIN_ID:
        # Проверяем, что введено название очереди для удаления
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /delete_queue <название_очереди>")
            return

        # Получаем название очереди
        queue_name = context.args[0]

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

        await update.message.reply_text(f"Очередь '{queue_name}' успешно удалена.")
    else:
        await update.message.reply_text("Только администратор может удалить очередь.")