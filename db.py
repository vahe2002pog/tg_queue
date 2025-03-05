# db.py

import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from config import DATABASE_NAME, GMT_PLUS_5

logger = logging.getLogger(__name__)

def create_connection():
    """Создает подключение к базе данных SQLite."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        logger.info(f"Подключение к базе данных {DATABASE_NAME} выполнено успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
    return conn

def create_tables(conn):
    """Создает необходимые таблицы в базе данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                state TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_name TEXT NOT NULL,
                start_time TEXT,
                latitude REAL,
                longitude REAL,
                creator_id INTEGER
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT,
                message_photo TEXT,
                recipients TEXT,
                send_time TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_users (
                queue_id INTEGER,
                user_id INTEGER,
                join_time TEXT,
                FOREIGN KEY (queue_id) REFERENCES queues(queue_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                PRIMARY KEY (queue_id, user_id)
            );
        """)
        conn.commit()
        logger.info("Таблицы созданы успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц: {e}")


def update_user_state(conn, user_id: int, state: str):
    """Обновляет состояние пользователя в базе данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET state = ? WHERE user_id = ?", (state, user_id))
        conn.commit()
        logger.info(f"Состояние пользователя {user_id} обновлено на {state} в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении состояния пользователя в базе данных: {e}")

def get_user_data(conn, user_id: int) -> tuple | None:
    """Получает данные пользователя (имя, состояние) из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name, state FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных пользователя: {e}")
        return None
    
def set_user_name(conn, user_id: int, user_name: str):
    """Сохраняет имя пользователя в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, name, state) VALUES (?, ?, ?)", (user_id, user_name, "name_entered"))
        conn.commit()
        logger.info(f"Имя пользователя {user_name} сохранено в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении имени пользователя в базе данных: {e}")

def update_user_name(conn, user_id: int, new_name: str):
    """Обновляет имя пользователя в базе данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        conn.commit()
        logger.info(f"Имя пользователя {user_id} изменено на {new_name} в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при изменении имени пользователя в базе данных: {e}")

def get_all_queues(conn) -> list[dict]:
    """Получает список всех очередей из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, queue_id, start_time FROM queues")
        results = cursor.fetchall()

        converted_results = []
        for row in results:
            start_time_str = row[2]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            converted_results.append({"queue_name": row[0], "queue_id": row[1], "start_time": start_time})
        return converted_results
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка очередей из базы данных: {e}")
        return []

def get_user_created_queues(conn, user_id: int) -> list[dict]:
    """Получает список очередей, созданных пользователем."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, queue_id, start_time FROM queues WHERE creator_id = ?", (user_id,))
        results = cursor.fetchall()
        converted_results = []
        for row in results:
            start_time_str = row[2]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            converted_results.append({"queue_name": row[0], "queue_id": row[1], "start_time": start_time})
        return converted_results
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка очередей, созданных пользователем: {e}")
        return []

async def get_queue_by_id(conn, queue_id: int) -> dict | None:
    """Получает информацию об очереди по её ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name, start_time, latitude, longitude, creator_id FROM queues WHERE queue_id = ?", (queue_id,))
        result = cursor.fetchone()
        if result:
            start_time_str = result[1]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            return {"queue_name": result[0], "start_time": start_time, "latitude": result[2], "longitude": result[3], "creator_id": result[4]}
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очереди из базы данных: {e}")
        return None

def get_queue_name_by_id(conn, queue_id: int) -> str | None:
    """Получает название очереди по ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_name FROM queues WHERE queue_id = ?", (queue_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени очереди по ID: {e}")
        return None

def get_queue_id_by_name(conn, queue_name: str) -> int | None:
    """Получает ID очереди по названию."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT queue_id FROM queues WHERE queue_name = ?", (queue_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении ID очереди: {e}")
        return None

def get_queue_users_names(conn, queue_id: int) -> list[str]:
    """Получает список имен пользователей в очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.name FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_id = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении участников очереди: {e}")
        return []

def get_queue_users_ids(conn, queue_id: int) -> list[int]:
    """Получает список ID пользователей в очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT users.user_id FROM users
            JOIN queue_users ON users.user_id = queue_users.user_id
            WHERE queue_users.queue_id = ?
            ORDER BY queue_users.join_time ASC
        """, (queue_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении ID участников очереди: {e}")
        return []

def get_user_name(conn, user_id: int) -> str | None:
    """Получает имя пользователя по ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени пользователя: {e}")
        return None

def is_user_in_queue(conn, queue_id: int, user_id: int) -> bool:
    """Проверяет, состоит ли пользователь в очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user_id))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при проверке нахождения пользователя в очереди: {e}")
        return False

def get_user_queues(conn, user_id: int) -> list[dict]:
    """Получает список очередей, в которых состоит пользователь."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT queues.queue_name, queues.queue_id FROM queues
            JOIN queue_users ON queues.queue_id = queue_users.queue_id
            WHERE queue_users.user_id = ?
        """, (user_id,))
        results = cursor.fetchall()
        return [{"queue_name": row[0], "queue_id": row[1]} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очередей пользователя: {e}")
        return []

def delete_queue(conn, queue_id: int):
    """Удаляет очередь и связанные записи из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queues WHERE queue_id = ?", (queue_id,))
        cursor.execute("DELETE FROM queue_users WHERE queue_id = ?", (queue_id,))
        conn.commit()
        logger.info(f"Очередь с ID {queue_id} удалена из базы данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении очереди: {e}")

def swap_queue_users(conn, queue_id: int, user1_id: int, user2_id: int):
    """Меняет местами двух пользователей в очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT join_time FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user1_id))
        time1 = cursor.fetchone()[0]
        cursor.execute("SELECT join_time FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user2_id))
        time2 = cursor.fetchone()[0]
        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_id = ? AND user_id = ?", (time2, queue_id, user1_id))
        cursor.execute("UPDATE queue_users SET join_time = ? WHERE queue_id = ? AND user_id = ?", (time1, queue_id, user2_id))
        conn.commit()
        logger.info(f"Пользователи {user1_id} и {user2_id} в очереди {queue_id} поменялись местами")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при перестановке пользователей: {e}")

def add_user_to_queue(conn, queue_id: int, user_id: int, join_time: str):
    """Добавляет пользователя в очередь."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO queue_users (queue_id, user_id, join_time) VALUES (?, ?, ?)", (queue_id, user_id, join_time))
        conn.commit()
        logger.info(f"Пользователь {user_id} добавлен в очередь {queue_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении пользователя в очередь: {e}")

def remove_user_from_queue(conn, queue_id: int, user_id: int):
    """Удаляет пользователя из очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM queue_users WHERE queue_id = ? AND user_id = ?", (queue_id, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} удален из очереди {queue_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении пользователя из очереди: {e}")
        
def insert_broadcast(conn, message_text: str, message_photo: str, recipients: str, send_time: datetime):
    """Вставляет данные о рассылке в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO broadcasts (message_text, message_photo, recipients, send_time) VALUES (?, ?, ?, ?)",
            (message_text, message_photo, recipients, send_time.isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении рассылки: {e}")
        return None

def get_broadcasts(conn):
    """Получает список всех рассылок из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, message_text, message_photo, recipients, send_time FROM broadcasts")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении рассылок: {e}")
        return []

def delete_broadcast(conn, broadcast_id: int):
    """Удаляет рассылку из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM broadcasts WHERE id = ?", (broadcast_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении рассылки: {e}")

def insert_queue(conn, queue_name: str, start_time: datetime, latitude: float, longitude: float, creator_id: int):
    """Вставляет данные о новой очереди в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO queues (queue_name, start_time, latitude, longitude, creator_id) VALUES (?, ?, ?, ?, ?)",
                       (queue_name, start_time.isoformat(), latitude, longitude, creator_id))
        conn.commit()
        logger.info(f"Очередь {queue_name} успешно сохранена в базе данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании очереди в базе данных: {e}")