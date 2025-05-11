# --- START OF FILE database_setup.py ---
import sqlite3
import os
import sys

# --- Импортируем ТОЛЬКО необходимое из database_module ---
# Добавим корень проекта в путь для импорта
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:
    from database_modules.database_module import hash_password
    HASH_PASSWORD_AVAILABLE = True
    print("Функция hash_password успешно импортирована.")
except ImportError as e:
    print(f"ПРЕДУПРЕЖДЕНИЕ: Не удалось импортировать hash_password из database_module: {e}")
    print("Администратор по умолчанию не может быть создан автоматически.")
    HASH_PASSWORD_AVAILABLE = False
    # Определим заглушку, чтобы код ниже не падал при попытке вызова
    def hash_password(p):
        print("Заглушка hash_password вызвана.")
        return None

# --- Конфигурация БД ---
DATABASE_DIR = 'instance' # Папка для БД
DATABASE_PATH = os.path.join(DATABASE_DIR, 'imageboard.db') # Путь к файлу БД

def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    # Убеждаемся, что папка instance существует
    os.makedirs(DATABASE_DIR, exist_ok=True)

    print(f"Инициализация базы данных по пути: {DATABASE_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # Включаем поддержку внешних ключей
        conn.execute("PRAGMA foreign_keys = ON;")

        # --- Создание таблицы accounts ---
        print("Создание таблицы: accounts")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT
            )
        ''')

        # --- Создание таблицы boards ---
        print("Создание таблицы: boards")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_uri TEXT UNIQUE NOT NULL,
                board_name TEXT NOT NULL,
                board_desc TEXT,
                board_owner TEXT NOT NULL,
                enable_captcha INTEGER DEFAULT 0,
                FOREIGN KEY (board_owner) REFERENCES accounts (username) ON DELETE CASCADE
            )
        ''')
        # Индекс для быстрого поиска досок по URI
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_board_uri ON boards (board_uri)')

        # --- Создание таблицы posts ---
        print("Создание таблицы: posts")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ip TEXT,
                post_id INTEGER UNIQUE NOT NULL,
                post_user TEXT,
                post_date TEXT NOT NULL, -- Храним как строку ISO 8601 UTC
                board_uri TEXT NOT NULL,
                original_content TEXT,
                post_content TEXT,
                post_images TEXT, -- Храним как JSON строку списка имен файлов
                imagesthb TEXT, -- Храним как JSON строку списка имен миниатюр
                locked INTEGER DEFAULT 0,
                visible INTEGER DEFAULT 1, -- Возможно, не используется, если pinned отдельно
                last_bumped TEXT NOT NULL, -- Храним как строку ISO 8601 UTC для сортировки
                FOREIGN KEY (board_uri) REFERENCES boards (board_uri) ON DELETE CASCADE
            )
        ''')
        # Индексы для ускорения запросов к постам
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_board_uri ON posts (board_uri)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_id ON posts (post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_last_bumped ON posts (last_bumped)')

        # --- Создание таблицы pinned ---
        print("Создание таблицы: pinned")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pinned (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_uri TEXT NOT NULL,
                post_id INTEGER UNIQUE NOT NULL,
                FOREIGN KEY (board_uri) REFERENCES boards (board_uri) ON DELETE CASCADE,
                FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE
            )
        ''')
        # Индекс для быстрого получения закрепленных постов доски
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pinned_board_uri ON pinned (board_uri)')

        # --- Создание таблицы replies ---
        print("Создание таблицы: replies")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ip TEXT,
                reply_id INTEGER UNIQUE NOT NULL,
                post_id INTEGER NOT NULL, -- ID треда, к которому относится ответ
                post_user TEXT,
                post_date TEXT NOT NULL, -- Храним как строку ISO 8601 UTC
                content TEXT,
                images TEXT, -- Храним как JSON строку списка имен файлов
                imagesthb TEXT, -- Храним как JSON строку списка имен миниатюр
                FOREIGN KEY (post_id) REFERENCES posts (post_id) ON DELETE CASCADE
            )
        ''')
        # Индексы для ускорения запросов к ответам
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reply_post_id ON replies (post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reply_id ON replies (reply_id)')

        # --- Создание таблицы timeouts ---
        print("Создание таблицы: timeouts")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timeouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ip TEXT UNIQUE NOT NULL, -- Один активный таймаут на IP
                end_time TEXT NOT NULL, -- ISO формат UTC
                reason TEXT,
                moderator TEXT,
                applied_at TEXT NOT NULL -- ISO формат UTC
            )
        ''')
        # Индекс для быстрой проверки таймаута по IP
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeout_user_ip ON timeouts (user_ip)')

        # --- Создание таблицы bans ---
        print("Создание таблицы: bans")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ip TEXT UNIQUE NOT NULL, -- Один активный бан на IP
                end_time TEXT, -- ISO формат UTC, NULL для постоянного
                reason TEXT,
                moderator TEXT,
                applied_at TEXT NOT NULL, -- ISO формат UTC
                is_permanent INTEGER NOT NULL DEFAULT 0 -- 0 (false) или 1 (true)
            )
        ''')
        # Индекс для быстрой проверки бана по IP
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ban_user_ip ON bans (user_ip)')

        # --- Создание администратора по умолчанию (Опционально) ---
        if HASH_PASSWORD_AVAILABLE:
            cursor.execute("SELECT COUNT(*) FROM accounts WHERE role = 'owner'")
            # fetchone() возвращает кортеж, берем первый элемент
            if cursor.fetchone()[0] == 0:
                print("Создание учетной записи владельца по умолчанию (admin/password)")
                default_pass = hash_password('password')
                if default_pass: # Убедимся, что хеширование сработало
                    try:
                        cursor.execute("INSERT INTO accounts (username, password, role) VALUES (?, ?, ?)",
                                       ('admin', default_pass, 'owner'))
                        print("Владелец по умолчанию 'admin' создан.")
                    except sqlite3.IntegrityError:
                        # Эта ошибка может возникнуть, если пользователь 'admin' уже есть
                        print("Владелец по умолчанию 'admin' уже существует.")
                else:
                    print("Не удалось хешировать пароль для админа.")
        else:
            print("Пропуск создания админа: функция hash_password недоступна.")

        # Фиксируем изменения в БД
        conn.commit()
        print("База данных успешно инициализирована.")

    except sqlite3.Error as e:
        print(f"ОШИБКА базы данных при инициализации: {e}")
        print("!!! Таблицы могли быть не созданы или созданы частично !!!")
        if conn:
            conn.rollback() # Откатываем изменения при ошибке
    except Exception as e:
         print(f"Неожиданная ОШИБКА при инициализации: {e}")
         if conn:
             conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Соединение с базой данных закрыто.")

# --- Запуск инициализации при выполнении скрипта ---
if __name__ == '__main__':
    print("--- Запуск database_setup.py ---")
    init_db()
    print("--- Завершение database_setup.py ---")

# --- END OF FILE database_setup.py ---