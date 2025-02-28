import sqlite3
import logging

logger = logging.getLogger(__name__)
DATABASE_NAME = 'queue_bot.db'

def create_connection():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        logger.info(f"Подключение к базе данных {DATABASE_NAME} выполнено успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
    return conn

def create_tables(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                queue_name TEXT PRIMARY KEY,
                start_time TEXT,
                latitude REAL,
                longitude REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue_users (
                queue_name TEXT,
                user_id INTEGER,
                join_time TEXT,  -- Добавлено время присоединения
                FOREIGN KEY (queue_name) REFERENCES queues(queue_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                PRIMARY KEY (queue_name, user_id)
            )
        """)
        conn.commit()
        logger.info("Таблицы созданы успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц: {e}")