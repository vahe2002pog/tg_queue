import sqlite3
import logging
from datetime import datetime
from config import DATABASE_NAME, ADMIN_ID
import pytz

TABLES_SCHEMA = {
    'users': [
        ('user_id', 'INTEGER', True, False),
        ('name', 'TEXT', False, True),
        ('state', 'TEXT', False, True),
        ('time_zone', 'TEXT', False, True)
    ],
    'queues': [
        ('queue_id', 'INTEGER', True, False),
        ('queue_name', 'TEXT', False, False),
        ('start_time', 'TEXT', False, True),
        ('latitude', 'REAL', False, True),
        ('longitude', 'REAL', False, True),
        ('creator_id', 'INTEGER', False, True),
        ('group_id', 'INTEGER', False, True),
        ('time_without_location', 'TEXT', False, True)
    ],
    'queue_users': [
        ('queue_id', 'INTEGER', False, False),
        ('user_id', 'INTEGER', False, False),
        ('join_time', 'TEXT', False, False)
    ],
    'groups': [
        ('group_id', 'INTEGER', True, False),
        ('group_name', 'TEXT', False, False),
        ('creator_id', 'INTEGER', False, True)
    ],
    'group_users': [
        ('group_id', 'INTEGER', False, False),
        ('user_id', 'INTEGER', False, False)
    ],
    'broadcasts': [
        ('id', 'INTEGER', True, False),
        ('message_text', 'TEXT', False, True),
        ('message_photo', 'TEXT', False, True),
        ('message_document', 'TEXT', False, True),
        ('recipients', 'TEXT', False, True),
        ('send_time', 'TEXT', False, True),
        ('creator_id', 'INTEGER', False, True),
        ('is_deleted', 'BOOLEAN', False, False)
    ]
}

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
    """Создает таблицы в базе данных на основе схемы TABLES_SCHEMA."""
    try:
        cursor = conn.cursor()
        
        for table_name, columns in TABLES_SCHEMA.items():
            # Формируем SQL для создания таблицы
            columns_sql = []
            primary_keys = []
            
            for column in columns:
                name, type_, is_pk, is_nullable = column
                column_sql = f"{name} {type_}"
                if is_pk:
                    if type_ == 'INTEGER':
                        column_sql += " PRIMARY KEY AUTOINCREMENT"
                    else:
                        primary_keys.append(name)
                if not is_nullable:
                    column_sql += " NOT NULL"
                
                columns_sql.append(column_sql)
            
            if primary_keys:
                columns_sql.append(f"PRIMARY KEY ({', '.join(primary_keys)})")
            
            # Создаем таблицу
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    {', '.join(columns_sql)}
                )
            """
            cursor.execute(create_sql)
            
            # Создаем индексы для внешних ключей
            if table_name == 'queue_users':
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_users_queue ON queue_users(queue_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_queue_users_user ON queue_users(user_id)
                """)
            elif table_name == 'group_users':
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_group_users_group ON group_users(group_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_group_users_user ON group_users(user_id)
                """)
        
        conn.commit()
        logger.info("Таблицы созданы успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        raise

def insert_group(conn, group_name: str, creator_id: int) -> int | None:
    """Добавляет новую группу в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO groups (group_name, creator_id) VALUES (?, ?)", (group_name, creator_id))
        conn.commit()
        return cursor.lastrowid  # Возвращаем ID созданной группы
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении группы: {e}")
        return None

def get_group_by_id(conn, group_id: int) -> dict | None:
    """Получает информацию о группе по ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT group_name, creator_id FROM groups WHERE group_id = ?", (group_id,))
        result = cursor.fetchone()
        if result:
            return {"group_name": result[0], "creator_id": result[1]}
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении группы по ID: {e}")
        return None
    
def get_group_name_by_id(conn, group_id: int) -> str | None:
    """Возвращает имя группы по ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT group_name FROM groups WHERE group_id = ?", (group_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении имени группы по ID: {e}")
        return None

def is_user_in_group(conn, group_id: int, user_id: int) -> bool:
    """Проверяет, состоит ли пользователь в группе."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM group_users WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при проверке нахождения пользователя в группе: {e}")
        return False

def get_group_id_by_name(conn, group_name: str) -> int | None:
    """Получает ID группы по её названию."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT group_id FROM groups WHERE group_name = ?", (group_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении ID группы: {e}")
        return None

def delete_group_db(conn, group_id: int):
    """Удаляет группу и связанные записи из базы данных."""
    try:
        cursor = conn.cursor()
        # Удаляем записи из group_users
        cursor.execute("DELETE FROM group_users WHERE group_id = ?", (group_id,))
        # Удаляем записи из queues, связанные с этой группой (если нужно)
        cursor.execute("UPDATE queues SET group_id = NULL WHERE group_id = ?", (group_id,))
        # Удаляем саму группу
        cursor.execute("DELETE FROM groups WHERE group_id = ?", (group_id,))

        conn.commit()
        logger.info(f"Группа {group_id} и связанные данные удалены")

    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении группы {group_id}: {e}")

def get_user_groups(conn, user_id: int) -> list[dict]:
    """Получает список групп, в которых состоит пользователь."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT groups.group_id, groups.group_name FROM groups
            JOIN group_users ON groups.group_id = group_users.group_id
            WHERE group_users.user_id = ?
        """, (user_id,))
        results = cursor.fetchall()
        return [{"group_id": row[0], "group_name": row[1]} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении групп пользователя: {e}")
        return []

def add_user_to_group(conn, group_id: int, user_id: int):
    """Добавляет пользователя в группу."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO group_users (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} добавлен в группу {group_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении пользователя в группу: {e}")

def remove_user_from_group(conn, group_id: int, user_id: int):
    """Удаляет пользователя из группы."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM group_users WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        conn.commit()
        logger.info(f"Пользователь {user_id} удален из группы {group_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении пользователя из группы: {e}")

def get_group_users(conn, group_id: int) -> list[int]:
    """Получает список ID пользователей в группе."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM group_users WHERE group_id = ?", (group_id,))
        results = cursor.fetchall()
        return [row[0] for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении пользователей группы: {e}")
        return []
def get_all_groups(conn) -> list[dict]:
    """Возвращает список всех групп"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT group_id, group_name FROM groups")
        result = cursor.fetchall()
        return [{"group_id":row[0], "group_name":row[1]} for row in result]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при возврате всех групп: {e}")
        return []

def get_queues_by_group(conn, group_id: int | None) -> list[dict]:
    """Возвращает список очередей для заданной группы (или все, если группа None)."""
    try:
        cursor = conn.cursor()
        if group_id is None:
            cursor.execute("SELECT queue_id, queue_name, start_time FROM queues WHERE group_id IS NULL")
        else:
            cursor.execute("SELECT queue_id, queue_name, start_time FROM queues WHERE group_id = ?", (group_id,))

        results = cursor.fetchall()
        converted_results = []
        for row in results:
            start_time_str = row[2]
            start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
            converted_results.append({"queue_id": row[0], "queue_name": row[1], "start_time": start_time})
        return converted_results

    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении очередей для группы: {e}")
        return []

def update_queue_group_id(conn, queue_id: int, group_id: int | None):
    """Обновляет group_id для указанной очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE queues SET group_id = ? WHERE queue_id = ?", (group_id, queue_id))
        conn.commit()
        logger.info(f"Очередь {queue_id} привязана к группе {group_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении group_id для очереди: {e}")

def get_queue_group_id(conn, queue_id:int) -> int | None:
    """Получает ID группы"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT group_id FROM queues WHERE queue_id = ?", (queue_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении ID группы в очереди: {e}")
        return None

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
    
def set_user_name(conn, user_id: int, user_name: str, time_zone: str):
    """Сохраняет имя пользователя и часовой пояс в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, name, state, time_zone) VALUES (?, ?, ?, ?)", 
                       (user_id, user_name, "name_entered", str(time_zone)))
        conn.commit()
        logger.info(f"Имя пользователя {user_name} и часовой пояс {time_zone} сохранены в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении имени пользователя и часового пояса в базе данных: {e}")

def get_user_timezone(conn, user_id: int) -> str | None:
    """Получает часовой пояс пользователя из базы данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT time_zone FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении часового пояса пользователя: {e}")
        return None

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
        cursor.execute("""
            SELECT queue_name, start_time, latitude, longitude, creator_id, time_without_location 
            FROM queues WHERE queue_id = ?
        """, (queue_id,))
        result = cursor.fetchone()
        if result:
            start_time_str = result[1]
            start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=pytz.UTC) if start_time_str else None
            time_without_location_str = result[5]
            time_without_location = datetime.fromisoformat(time_without_location_str).replace(tzinfo=pytz.UTC) if time_without_location_str else None
            return {
                "queue_name": result[0],
                "start_time": start_time,
                "latitude": result[2],
                "longitude": result[3],
                "creator_id": result[4],
                "time_without_location": time_without_location
            }
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
    """Получает список очередей, доступных пользователю."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT queues.queue_name, queues.queue_id 
            FROM queues
            LEFT JOIN groups ON queues.group_id = groups.group_id
            LEFT JOIN group_users ON groups.group_id = group_users.group_id
            WHERE queues.group_id IS NULL 
               OR group_users.user_id = ?
               OR groups.creator_id = ?
        """, (user_id, user_id))
        results = cursor.fetchall()
        return [{"queue_name": row[0], "queue_id": row[1]} for row in results]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении доступных очередей пользователя: {e}")
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
        
def get_broadcasts(conn, user_id: int = None):
    """Получает список активных рассылок из базы данных."""
    try:
        cursor = conn.cursor()
        if user_id:
            # Для обычного пользователя — только его рассылки
            cursor.execute("""
                SELECT id, message_text, message_photo, message_document, recipients, send_time 
                FROM broadcasts 
                WHERE creator_id = ? AND is_deleted = FALSE
            """, (user_id,))
        else:
            # Для админа — все активные рассылки
            cursor.execute("""
                SELECT id, message_text, message_photo, message_document, recipients, send_time 
                FROM broadcasts 
                WHERE is_deleted = FALSE
            """)
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении рассылок: {e}")
        return []
    
def insert_broadcast(conn, message_text: str, message_photo: str, message_document: str, recipients: str, send_time: datetime, creator_id: int):
    """Вставляет данные о рассылке в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO broadcasts (message_text, message_photo, message_document, recipients, send_time, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
            (message_text, message_photo, message_document, recipients, send_time.isoformat(), creator_id)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении рассылки: {e}")
        return None

def mark_broadcast_as_deleted(conn, broadcast_id: int):
    """Помечает рассылку как удаленную."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE broadcasts SET is_deleted = TRUE WHERE id = ?", (broadcast_id,))
        conn.commit()
        logger.info(f"Рассылка #{broadcast_id} помечена как удаленная.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при пометке рассылки как удаленной: {e}")

def insert_queue(conn, queue_name: str, start_time: datetime, latitude: float, longitude: float, creator_id: int, time_without_location: datetime = None):
    """Вставляет данные о новой очереди в базу данных."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO queues 
            (queue_name, start_time, latitude, longitude, creator_id, time_without_location) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            queue_name, 
            start_time.astimezone(pytz.UTC).isoformat(), 
            latitude, 
            longitude, 
            creator_id,
            time_without_location.astimezone(pytz.UTC).isoformat() if time_without_location else None
        ))
        conn.commit()
        logger.info(f"Очередь {queue_name} успешно сохранена в базе данных.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании очереди в базе данных: {e}")

def get_broadcast_by_id(conn, broadcast_id: int) -> dict | None:
    """Получает информацию о рассылке по её ID."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT message_text, message_photo, message_document FROM broadcasts WHERE id = ?", (broadcast_id,))
        result = cursor.fetchone()
        if result:
            return {"message_text": result[0], "message_photo": result[1], "message_document": result[2]}
        return None
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении рассылки из базы данных: {e}")
        return None

def update_user_timezone(conn, user_id: int, timezone: str):
    """Обновляет часовой пояс пользователя."""
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET time_zone = ? WHERE user_id = ?", (timezone, user_id))
    conn.commit()

def update_queue_time_without_location(conn, queue_id: int, time_without_location: datetime):
    """Обновляет время без проверки геолокации для очереди."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE queues 
            SET time_without_location = ? 
            WHERE queue_id = ?
        """, (
            time_without_location.astimezone(pytz.UTC).isoformat() if time_without_location else None,
            queue_id
        ))
        conn.commit()
        logger.info(f"Время без проверки геолокации обновлено для очереди {queue_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении времени без проверки геолокации: {e}")

def migrate_database(conn):
    """Проверяет и добавляет недостающие столбцы на основе схемы TABLES_SCHEMA."""
    try:
        cursor = conn.cursor()
        
        for table_name, columns in TABLES_SCHEMA.items():
            # Проверяем существование таблицы
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                logger.warning(f"Таблица {table_name} не существует, будет создана при следующем запуске")
                continue
                
            # Получаем текущие столбцы таблицы
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {column[1] for column in cursor.fetchall()}
            
            # Проверяем каждый ожидаемый столбец
            for column in columns:
                name, type_, is_pk, is_nullable = column
                if name not in existing_columns:
                    try:
                        column_def = f"{name} {type_}"
                        if not is_nullable:
                            column_def += " NOT NULL"
                        
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")
                        logger.info(f"Добавлен столбец {name} в таблицу {table_name}")
                    except sqlite3.Error as e:
                        logger.error(f"Ошибка при добавлении столбца {name} в {table_name}: {e}")
        
        conn.commit()
        logger.info("Миграция базы данных завершена успешно")
        
    except sqlite3.Error as e:
        logger.error(f"Критическая ошибка при миграции базы данных: {e}")
        raise