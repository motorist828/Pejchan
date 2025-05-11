"""
Модуль базы данных имиджборда с использованием SQLite
Этот модуль обрабатывает все операции с базой данных для системы имиджборда.
"""

import datetime
import hashlib
import random
import base64
import string
import pytz # Для работы с часовыми поясами
import json # Для сериализации/десериализации списков файлов
import os
import io
import re
import sqlite3 # Основной модуль для работы с SQLite
from captcha.image import ImageCaptcha
import logging # Для логирования

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Конфигурация базы данных ---
DATABASE_DIR = 'instance' # Папка для хранения БД (рекомендация Flask)
DATABASE_PATH = os.path.join(DATABASE_DIR, 'imageboard.db') # Полный путь к файлу БД

# --- Определение путей к папкам static ---
# Определяем базовый путь к static один раз
# Получаем путь к текущему файлу -> папка database_modules -> корень проекта -> папка static
try:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
    STATIC_FOLDER_PATH = os.path.join(PROJECT_ROOT, 'static')
    if not os.path.isdir(STATIC_FOLDER_PATH):
        # Если структура другая (например, запускаем из корня)
        STATIC_FOLDER_PATH = os.path.join(os.getcwd(), 'static') # Пробуем от текущей директории
        if not os.path.isdir(STATIC_FOLDER_PATH):
             logger.error("Критическая ошибка: не удалось определить путь к папке static!")
             STATIC_FOLDER_PATH = './static' # Последняя попытка с относительным путем
except NameError: # __file__ не определен (например, в интерактивной сессии)
    logger.warning("__file__ не определен, используем относительный путь './static'")
    STATIC_FOLDER_PATH = './static'


# Папки для изображений относительно static
POST_IMAGE_FOLDER_REL = 'post_images'
REPLY_IMAGE_FOLDER_REL = 'reply_images'

# Абсолютные пути к папкам с *оригинальными* изображениями
POST_IMAGE_ABS_PATH = os.path.join(STATIC_FOLDER_PATH, POST_IMAGE_FOLDER_REL)
REPLY_IMAGE_ABS_PATH = os.path.join(STATIC_FOLDER_PATH, REPLY_IMAGE_FOLDER_REL)
# Папка для миниатюр постов (абсолютный путь)
POST_THUMB_ABS_PATH = os.path.join(POST_IMAGE_ABS_PATH, 'thumbs')
# Папка для миниатюр ответов (абсолютный путь)
REPLY_THUMB_ABS_PATH = os.path.join(REPLY_IMAGE_ABS_PATH, 'thumbs')

# --- Функции ---

def get_db_conn():
    """Устанавливает соединение с базой данных SQLite."""
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True) # Убеждаемся, что папка instance существует
        conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Ошибка подключения к базе данных: {e}", exc_info=True)
        raise

def generate_captcha():
    """Генерирует CAPTCHA."""
    try:
        captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        image = ImageCaptcha()
        captcha_image_data = image.generate(captcha_text) # Возвращает BytesIO с PNG данными
        image_base64 = base64.b64encode(captcha_image_data.getvalue()).decode('utf-8')
        return captcha_text, f"data:image/png;base64,{image_base64}"
    except Exception as e:
        logger.error(f"Ошибка генерации CAPTCHA: {e}", exc_info=True)
        return "ERROR", "data:image/png;base64,"

def generate_tripcode(post_name):
    """Генерирует трипкод из имени поста."""
    if not post_name: return ""
    match = re.search(r'#(\S+)', post_name)
    if match:
        text_to_encrypt = match.group(1)
        salt = "some_fixed_salt_for_tripcodes" # Можно сделать настраиваемой
        hashed_text = hashlib.pbkdf2_hmac(
            'sha256', text_to_encrypt.encode('utf-8'), salt.encode('utf-8'), 10000, dklen=16
        ).hex()
        truncated_hash = hashed_text[:10]
        post_name_safe = post_name.replace(f'#{text_to_encrypt}', '').strip()
        return f'{post_name_safe} <span class="tripcode">!{truncated_hash}</span>'
    return post_name

def hash_password(password):
    """Хеширует пароль с использованием PBKDF2."""
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + hashed.hex()

def verify_password(stored_password, provided_password):
    """Проверяет введенный пароль на соответствие хешу."""
    if not stored_password or ':' not in stored_password: return False
    try:
        salt_hex, hashed_hex = stored_password.split(':')
        salt = bytes.fromhex(salt_hex)
        hashed_provided = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return hashed_provided.hex() == hashed_hex
    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка проверки пароля: {e}", exc_info=True)
        return False

def validate_captcha(captcha_input, captcha_text):
    """Проверяет ввод CAPTCHA."""
    return isinstance(captcha_input, str) and isinstance(captcha_text, str) and captcha_input.upper() == captcha_text.upper()

def get_current_datetime():
    """Возвращает текущую дату и время в формате ISO 8601 (UTC)."""
    return datetime.datetime.now(pytz.utc).isoformat()

def parse_datetime(dt_str):
    """Преобразует строку ISO 8601 обратно в объект datetime (UTC)."""
    if not dt_str: return None
    try:
        if dt_str.endswith('Z'): dt_str = dt_str[:-1] + '+00:00'
        elif '+' not in dt_str and '-' not in dt_str[10:]: dt_str += '+00:00'
        dt = datetime.datetime.fromisoformat(dt_str)
        if dt.tzinfo is None: return pytz.utc.localize(dt)
        else: return dt.astimezone(pytz.utc)
    except ValueError:
        try:
            dt_naive = datetime.datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
            local_tz = pytz.timezone('Europe/Moscow') # Или ваш исходный часовой пояс
            dt_aware = local_tz.localize(dt_naive)
            return dt_aware.astimezone(pytz.utc)
        except (ValueError, TypeError):
            logger.warning(f"Не удалось разобрать строку даты/времени: {dt_str}")
            return None

def format_datetime_for_display(dt_obj, user_tz_str='Europe/Moscow'):
    """Форматирует объект datetime (предположительно UTC) для отображения."""
    if not dt_obj or not isinstance(dt_obj, datetime.datetime): return "N/A"
    try:
        if dt_obj.tzinfo is None: utc_dt = pytz.utc.localize(dt_obj)
        else: utc_dt = dt_obj.astimezone(pytz.utc)
        target_tz = pytz.timezone(user_tz_str)
        local_dt = utc_dt.astimezone(target_tz)
        return local_dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception as e:
        logger.warning(f"Не удалось отформатировать datetime {dt_obj} для отображения: {e}")
        try:
            # Резервный вариант без часового пояса
            return dt_obj.strftime("%d/%m/%Y %H:%M:%S") + " (?)"
        except: # Если даже это не сработает
             return str(dt_obj) # Просто строка

def execute_query(query, params=(), fetchone=False, fetchall=True, commit=False):
    """Выполняет SQL-запрос и возвращает результат."""
    conn = None
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit(); return cursor.lastrowid
        if fetchone: return cursor.fetchone()
        elif fetchall: return cursor.fetchall()
        else: return None # Для запросов без fetch (например, UPDATE без интереса к rowcount)
    except sqlite3.Error as e:
        logger.error(f"Ошибка запроса к базе данных: {e}\nЗапрос: {query}\nПараметры: {params}", exc_info=True)
        if conn and commit:
            try: conn.rollback()
            except sqlite3.Error as rb_err: logger.error(f"Ошибка при откате транзакции: {rb_err}")
        return None
    except Exception as e:
         logger.error(f"Неожиданная ошибка при выполнении запроса: {e}", exc_info=True)
         if conn and commit:
             try: conn.rollback()
             except sqlite3.Error as rb_err: logger.error(f"Ошибка при откате транзакции: {rb_err}")
         return None
    finally:
        if conn: conn.close()

# --- Board Operations ---
def verify_board_captcha(board_uri):
    sql = "SELECT enable_captcha FROM boards WHERE board_uri = ?"
    result = execute_query(sql, (board_uri,), fetchone=True)
    return result['enable_captcha'] == 1 if result else False

def set_all_boards_captcha(option):
    enable_value = 1 if option == 'enable' else 0
    sql = "UPDATE boards SET enable_captcha = ?"
    result = execute_query(sql, (enable_value,), commit=True, fetchall=False) # fetchall=False
    return result is not None # Успех, если не было ошибки

def get_board_info(board_uri):
    sql = "SELECT * FROM boards WHERE board_uri = ?"
    return execute_query(sql, (board_uri,), fetchone=True)

def get_board_banner(board_uri):
    banner_folder_abs = os.path.join(STATIC_FOLDER_PATH, 'imgs', 'banners', board_uri)
    default_banner = '/static/imgs/banners/default.jpg'
    if not os.path.isdir(banner_folder_abs): return default_banner
    try:
        images = [f for f in os.listdir(banner_folder_abs) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and os.path.isfile(os.path.join(banner_folder_abs, f))]
        if not images: return default_banner
        selected_image = random.choice(images)
        # Возвращаем относительный URL
        return f'/static/imgs/banners/{board_uri}/{selected_image}'.replace('\\', '/')
    except OSError as e: logger.error(f"Ошибка чтения изображений в {banner_folder_abs}: {e}", exc_info=True); return default_banner
    except Exception as e: logger.error(f"Ошибка выбора случайного баннера: {e}", exc_info=True); return default_banner

def get_all_boards(include_stats=False):
    boards_sql = "SELECT * FROM boards ORDER BY board_name"
    boards_raw = execute_query(boards_sql, fetchall=True)
    if not boards_raw: return []
    boards_list = [dict(board) for board in boards_raw]
    if include_stats:
        for board in boards_list:
            board_uri = board['board_uri']
            thread_sql = """
                SELECT COUNT(p.id) as count
                FROM posts p
                LEFT JOIN pinned pn ON p.post_id = pn.post_id AND p.board_uri = pn.board_uri
                WHERE p.board_uri = ? AND pn.post_id IS NULL
            """
            thread_res = execute_query(thread_sql, (board_uri,), fetchone=True)
            board['thread_count'] = thread_res['count'] if thread_res else 0
            post_ids_sql = "SELECT post_id FROM posts WHERE board_uri = ?"
            post_ids_res = execute_query(post_ids_sql, (board_uri,), fetchall=True)
            post_ids = [row['post_id'] for row in post_ids_res] if post_ids_res else []
            reply_count = 0
            if post_ids:
                placeholders = ','.join('?' * len(post_ids))
                reply_sql = f"SELECT COUNT(*) as count FROM replies WHERE post_id IN ({placeholders})"
                reply_res = execute_query(reply_sql, tuple(post_ids), fetchone=True)
                reply_count = reply_res['count'] if reply_res else 0
            board['reply_count'] = reply_count
            board['total_posts'] = board['thread_count'] + reply_count
            # Используем last_bumped для последней активности
            last_activity_sql = "SELECT MAX(last_bumped) as last_date FROM posts WHERE board_uri = ?"
            last_activity_res = execute_query(last_activity_sql, (board_uri,), fetchone=True)
            board['last_activity'] = last_activity_res['last_date'] if last_activity_res else None
    return boards_list

def get_board_thread_count(board_uri, include_pinned=False):
    """Получает количество тредов (OP) на доске, опционально исключая закрепленные."""
    if include_pinned:
        # Считаем ВСЕ посты на доске
        sql = "SELECT COUNT(*) as count FROM posts WHERE board_uri = ?"
        params = (board_uri,)
    else:
        # Считаем только те, которых НЕТ в таблице pinned для этой доски
        sql = """
            SELECT COUNT(p.id) as count
            FROM posts p
            LEFT JOIN pinned pn ON p.post_id = pn.post_id AND p.board_uri = pn.board_uri
            WHERE p.board_uri = ? AND pn.post_id IS NULL
        """
        params = (board_uri,)

    # Выполняем запрос и возвращаем результат
    result = execute_query(sql, params, fetchone=True)
    # Возвращаем 0, если запрос ничего не вернул или count равен NULL
    return result['count'] if result and result['count'] is not None else 0


def get_max_post_id():
    post_sql = "SELECT MAX(post_id) as max_id FROM posts"
    reply_sql = "SELECT MAX(reply_id) as max_id FROM replies"
    max_post_res = execute_query(post_sql, fetchone=True)
    max_reply_res = execute_query(reply_sql, fetchone=True)
    max_post_id = max_post_res['max_id'] if max_post_res and max_post_res['max_id'] is not None else 0
    max_reply_id = max_reply_res['max_id'] if max_reply_res and max_reply_res['max_id'] is not None else 0
    return max(max_post_id, max_reply_id)

def create_banner_folder(board_uri):
    try:
        # Используем абсолютный путь
        board_folder_abs = os.path.join(STATIC_FOLDER_PATH, 'imgs', 'banners', board_uri)
        os.makedirs(board_folder_abs, exist_ok=True)
        logger.info(f"Папка для баннеров создана или уже существует: {board_folder_abs}")
    except OSError as e: logger.error(f"Не удалось создать папку для баннеров {board_uri}: {e}", exc_info=True)

def add_new_board(board_uri, board_name, board_description, username, captcha_input, captcha_text):
    # Валидация капчи теперь происходит в роуте, здесь не нужна captcha_input/text
    # Но сама функция validate_captcha может остаться для других целей
    if not board_uri or not board_name or len(board_description or '') < 3: logger.warning("Создание доски не удалось: Неверный URI, имя или описание."); return False
    if get_board_info(board_uri): logger.warning(f"Создание доски не удалось: URI '{board_uri}' уже существует."); return False
    if not get_user_by_username(username): logger.warning(f"Создание доски не удалось: Пользователь '{username}' не найден."); return False
    sql = "INSERT INTO boards (board_uri, board_name, board_desc, board_owner, enable_captcha) VALUES (?, ?, ?, ?, ?)"
    params = (board_uri, board_name, board_description, username, 0)
    try:
        result_id = execute_query(sql, params, commit=True, fetchall=False) # fetchall=False
        if result_id is not None: create_banner_folder(board_uri); logger.info(f"Доска '{board_uri}' успешно создана пользователем '{username}'."); return True
        else: return False
    except sqlite3.IntegrityError as e: logger.error(f"Создание доски не удалось из-за IntegrityError: {e}", exc_info=True); return False
    except Exception as e: logger.error(f"Неожиданная ошибка при создании доски '{board_uri}': {e}", exc_info=True); return False

def remove_board(board_uri, username, role):
    board_info = get_board_info(board_uri)
    if not board_info: logger.warning(f"Удаление доски не удалось: Доска '{board_uri}' не найдена."); return False
    is_owner = board_info['board_owner'] == username
    is_admin = role and ('mod' in role.lower() or 'owner' in role.lower())
    if not is_owner and not is_admin: logger.warning(f"Удаление доски не удалось: Пользователь '{username}' не имеет прав для доски '{board_uri}'."); return False
    conn = None
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT post_id, post_images, imagesthb FROM posts WHERE board_uri = ?", (board_uri,))
        posts_to_delete = cursor.fetchall()
        cursor.execute("SELECT r.images, r.imagesthb FROM replies r JOIN posts p ON r.post_id = p.post_id WHERE p.board_uri = ?", (board_uri,))
        replies_to_delete = cursor.fetchall()
        logger.info(f"Попытка удаления доски '{board_uri}'...")
        cursor.execute("DELETE FROM boards WHERE board_uri = ?", (board_uri,))
        rows_affected = cursor.rowcount
        conn.commit()
        if rows_affected > 0:
            logger.info(f"Доска '{board_uri}' удалена из базы данных.")
            for post_row in posts_to_delete:
                delete_media_files(post_row['post_images'], POST_IMAGE_ABS_PATH)
                delete_media_files(post_row['imagesthb'], STATIC_FOLDER_PATH) # База - static
            for reply_row in replies_to_delete:
                delete_media_files(reply_row['images'], REPLY_IMAGE_ABS_PATH)
                delete_media_files(reply_row['imagesthb'], STATIC_FOLDER_PATH) # База - static
            banner_folder_abs = os.path.join(STATIC_FOLDER_PATH, 'imgs', 'banners', board_uri)
            if os.path.isdir(banner_folder_abs):
                try: import shutil; shutil.rmtree(banner_folder_abs); logger.info(f"Удалена папка с баннерами: {banner_folder_abs}")
                except OSError as e: logger.error(f"Не удалось удалить папку с баннерами {banner_folder_abs}: {e}")
            return True
        else: logger.warning(f"Доска '{board_uri}' не найдена в БД при попытке удаления."); return False
    except sqlite3.Error as e: logger.error(f"Ошибка базы данных при удалении доски '{board_uri}': {e}", exc_info=True); conn.rollback(); return False
    except Exception as e: logger.error(f"Неожиданная ошибка при удалении доски '{board_uri}': {e}", exc_info=True); conn.rollback(); return False
    finally:
        if conn: conn.close()

# --- User Operations ---
def get_user_by_username(username):
     sql = "SELECT * FROM accounts WHERE username = ?"
     return execute_query(sql, (username,), fetchone=True)

def login_user(username, password):
    user = get_user_by_username(username)
    if user and verify_password(user['password'], password): logger.info(f"Пользователь '{username}' успешно вошел в систему."); return True
    logger.warning(f"Неудачная попытка входа для пользователя '{username}'."); return False

def register_user(username, password, captcha_input, captcha_text):
    # Проверка капчи должна быть в роуте ДО вызова этой функции
    if not username or len(username) < 3 or len(password) < 4: logger.warning("Регистрация не удалась: Неверная длина имени пользователя или пароля."); return False
    if get_user_by_username(username): logger.warning(f"Регистрация не удалась: Имя пользователя '{username}' уже занято."); return False
    hashed_password = hash_password(password)
    count_sql = "SELECT COUNT(*) as count FROM accounts"
    user_count_res = execute_query(count_sql, fetchone=True)
    user_count = user_count_res['count'] if user_count_res else 0
    role = 'owner' if user_count == 0 else 'user'
    insert_sql = "INSERT INTO accounts (username, password, role) VALUES (?, ?, ?)"
    try:
        result_id = execute_query(insert_sql, (username, hashed_password, role), commit=True, fetchall=False)
        if result_id is not None: logger.info(f"Пользователь '{username}' успешно зарегистрирован с ролью '{role}'."); return True
        else: return False
    except sqlite3.IntegrityError: logger.warning(f"Регистрация не удалась: Имя пользователя '{username}' уже занято (IntegrityError)."); return False
    except Exception as e: logger.error(f"Неожиданная ошибка при регистрации '{username}': {e}", exc_info=True); return False

def get_user_role(username):
    user = get_user_by_username(username)
    return user['role'] if user else None


def get_all_users_with_roles(exclude_username=None):
    """
    Получает список всех пользователей и их роли.
    Опционально исключает указанного пользователя из списка.
    """
    params = []
    sql = "SELECT id, username, role FROM accounts"
    if exclude_username:
        sql += " WHERE username != ?"
        params.append(exclude_username)
    sql += " ORDER BY username"

    users_raw = execute_query(sql, tuple(params), fetchall=True)
    if not users_raw:
        return []
    # Конвертируем в список словарей
    return [dict(user) for user in users_raw]


def set_user_role(target_username, new_role):
    """
    Устанавливает новую роль для указанного пользователя.
    Роль 'owner' может быть только одна, и владелец не может быть разжалован этой функцией.
    """
    # Проверка, что new_role допустима (например, 'mod', 'user', или пустая строка для снятия модераторства)
    allowed_roles_to_set = ['mod', 'user', ''] # Пустая строка будет означать стандартную роль 'user'
    if new_role not in allowed_roles_to_set and new_role is not None : # None может быть если роль снимается
        logger.error(f"Попытка установить недопустимую роль '{new_role}' для пользователя '{target_username}'.")
        return False

    target_user = get_user_by_username(target_username)
    if not target_user:
        logger.warning(f"Не удалось изменить роль: пользователь '{target_username}' не найден.")
        return False

    # Владелец не может быть изменен этой функцией или понижен до не-владельца
    if target_user['role'] == 'owner':
        logger.warning(f"Попытка изменить роль владельца '{target_username}' через set_user_role. Отклонено.")
        return False # Защита от случайного разжалования владельца

    # Если new_role пустая строка или None, устанавливаем роль 'user' (или какая у вас базовая)
    actual_new_role = new_role if new_role and new_role.strip() else 'user'

    sql = "UPDATE accounts SET role = ? WHERE username = ?"
    try:
        # fetchall=False для UPDATE
        result = execute_query(sql, (actual_new_role, target_username), commit=True, fetchall=False)
        if result is not None: # Указывает, что запрос выполнился без ошибки SQLite
            logger.info(f"Роль для пользователя '{target_username}' изменена на '{actual_new_role}'.")
            return True
        else:
            # Ошибка уже залогирована в execute_query
            return False
    except Exception as e:
        logger.error(f"Ошибка при изменении роли для '{target_username}': {e}", exc_info=True)
        return False



def get_post_ip(post_or_reply_id):
    try: pid = int(post_or_reply_id)
    except (ValueError, TypeError): logger.warning(f"Неверный ID для получения IP: {post_or_reply_id}"); return None
    post_sql = "SELECT user_ip FROM posts WHERE post_id = ?"
    post_res = execute_query(post_sql, (pid,), fetchone=True)
    if post_res: return post_res['user_ip']
    reply_sql = "SELECT user_ip FROM replies WHERE reply_id = ?"
    reply_res = execute_query(reply_sql, (pid,), fetchone=True)
    if reply_res: return reply_res['user_ip']
    logger.warning(f"Не удалось найти IP для ID {pid} в постах или ответах."); return None

def check_post_exist(post_or_reply_id):
    try: pid = int(post_or_reply_id)
    except (ValueError, TypeError): return False
    post_sql = "SELECT 1 FROM posts WHERE post_id = ?"
    reply_sql = "SELECT 1 FROM replies WHERE reply_id = ?"
    return bool(execute_query(post_sql, (pid,), fetchone=True) or execute_query(reply_sql, (pid,), fetchone=True))

def check_replyto_exist(thread_id):
    try: tid = int(thread_id)
    except (ValueError, TypeError): return False
    sql = "SELECT 1 FROM posts WHERE post_id = ?"
    return bool(execute_query(sql, (tid,), fetchone=True))

# --- Post Operations ---
def get_thread_id_for_post(post_or_reply_id):
     try: pid = int(post_or_reply_id)
     except (ValueError, TypeError): logger.warning(f"Неверный ID для поиска ID треда: {post_or_reply_id}"); return None
     post_sql = "SELECT post_id FROM posts WHERE post_id = ?"
     post_res = execute_query(post_sql, (pid,), fetchone=True)
     if post_res: return post_res['post_id']
     reply_sql = "SELECT post_id FROM replies WHERE reply_id = ?"
     reply_res = execute_query(reply_sql, (pid,), fetchone=True)
     if reply_res: return reply_res['post_id']
     logger.warning(f"Не удалось найти ID треда для поста/ответа ID {pid}."); return None

def bump_thread(thread_id):
    try: tid = int(thread_id)
    except (ValueError, TypeError): logger.error(f"Не удалось поднять тред: неверный ID {thread_id}"); return False
    current_time_iso = get_current_datetime()
    sql = "UPDATE posts SET last_bumped = ? WHERE post_id = ?"
    result = execute_query(sql, (current_time_iso, tid), commit=True, fetchall=False)
    if result is not None: return True
    else: logger.error(f"Не удалось поднять тред {tid}."); return False

def _serialize_files(files_list):
    """Безопасно сериализует список файлов (имен) в строку JSON."""
    if not files_list or not isinstance(files_list, list): return None
    try:
        # Фильтруем None и конвертируем в строку на всякий случай
        cleaned_list = [str(item) for item in files_list if item is not None]
        return json.dumps(cleaned_list)
    except (TypeError, ValueError) as e: logger.error(f"Ошибка сериализации списка файлов {files_list}: {e}"); return None

def _deserialize_files(files_json):
    """Безопасно десериализует строку JSON обратно в список строк."""
    if not files_json: return []
    try:
        files = json.loads(files_json)
        # Убеждаемся, что результат - список и все его элементы - строки
        if isinstance(files, list) and all(isinstance(item, str) for item in files):
             return files
        elif isinstance(files, list): # Если не все строки - пытаемся конвертировать
             logger.warning(f"Не все элементы в десериализованном списке файлов являются строками: {files}. Попытка конвертации.")
             return [str(item) for item in files]
        else:
             logger.warning(f"Десериализованные данные файлов не являются списком: {files}")
             return []
    except (json.JSONDecodeError, TypeError) as e: logger.error(f"Ошибка десериализации JSON файлов '{files_json}': {e}"); return []

def add_new_post(user_ip, board_id, post_name, original_content, comment, embed, files, filesthb):
    """Создает новый пост (тред). files и filesthb - списки имен/путей."""
    if not get_board_info(board_id): logger.error(f"Создание поста не удалось: Доска '{board_id}' не существует."); raise ValueError(f"Board '{board_id}' does not exist")
    new_post_id = get_max_post_id() + 1
    current_time_iso = get_current_datetime()
    processed_name = generate_tripcode(post_name)
    sql = """INSERT INTO posts (user_ip, post_id, post_user, post_date, board_uri, original_content, post_content, post_images, imagesthb, locked, visible, last_bumped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    params = (user_ip, new_post_id, processed_name, current_time_iso, board_id, original_content, comment, _serialize_files(files), _serialize_files(filesthb), 0, 1, current_time_iso)
    try:
        result_id = execute_query(sql, params, commit=True, fetchall=False)
        if result_id is not None: logger.info(f"Новый пост создан с ID {new_post_id} на доске '{board_id}'."); return new_post_id
        else: return None
    except sqlite3.IntegrityError as e: logger.error(f"Создание поста не удалось из-за IntegrityError: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Неожиданная ошибка при создании поста: {e}", exc_info=True); return None

def add_new_reply(user_ip, reply_to_thread_id, post_name, comment, embed, files, filesthb):
    """Добавляет ответ к посту. files и filesthb - списки имен/путей."""
    try: tid = int(reply_to_thread_id)
    except (ValueError, TypeError): logger.error(f"Создание ответа не удалось: неверный ID треда {reply_to_thread_id}"); return None
    if not check_replyto_exist(tid): logger.error(f"Создание ответа не удалось: Тред ID '{tid}' не существует."); return None
    new_reply_id = get_max_post_id() + 1
    current_time_iso = get_current_datetime()
    processed_name = generate_tripcode(post_name)
    sql = """INSERT INTO replies (user_ip, reply_id, post_id, post_user, post_date, content, images, imagesthb) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
    params = (user_ip, new_reply_id, tid, processed_name, current_time_iso, comment, _serialize_files(files), _serialize_files(filesthb))
    try:
        result_id = execute_query(sql, params, commit=True, fetchall=False)
        if result_id is not None:
            if not bump_thread(tid): logger.warning(f"Ответ {new_reply_id} создан, но не удалось поднять тред {tid}.")
            logger.info(f"Новый ответ создан с ID {new_reply_id} для треда {tid}."); return new_reply_id
        else: return None
    except sqlite3.IntegrityError as e: logger.error(f"Создание ответа не удалось из-за IntegrityError: {e}", exc_info=True); return None
    except Exception as e: logger.error(f"Неожиданная ошибка при создании ответа: {e}", exc_info=True); return None
    
    
def delete_media_files(files_json_or_list, base_abs_path):
    """
    Вспомогательная функция для безопасного удаления медиафайлов.

    Args:
        files_json_or_list: Строка JSON со списком имен/путей или сам список.
                            Для оригиналов это список имен файлов.
                            Для миниатюр это список относительных путей от папки static
                            (например, ['post_images/thumbs/thumb1.jpg', 'post_images/thumbs/thumb2.png']).
        base_abs_path: Абсолютный путь к базовой папке, откуда нужно считать пути файлов.
                       Для оригиналов это POST_IMAGE_ABS_PATH или REPLY_IMAGE_ABS_PATH.
                       Для миниатюр это STATIC_FOLDER_PATH.
    """
    if not files_json_or_list:
        # logger.debug(f"Нет файлов для удаления в {base_abs_path}.")
        return

    file_paths_to_delete = []
    # Определяем, что пришло: строка JSON или уже список
    if isinstance(files_json_or_list, str):
        file_paths_to_delete = _deserialize_files(files_json_or_list)
    elif isinstance(files_json_or_list, list):
        file_paths_to_delete = files_json_or_list # Уже список
    else:
        logger.warning(f"Неверный тип данных для удаления файлов: {type(files_json_or_list)} в {base_abs_path}. Пропуск.")
        return

    # Дополнительная проверка после десериализации
    if not isinstance(file_paths_to_delete, list):
         logger.warning(f"Данные файлов после десериализации не являются списком: {file_paths_to_delete}. Пропуск удаления.")
         return

    logger.debug(f"Попытка удаления файлов: {file_paths_to_delete} из базового пути: {base_abs_path}")
    deleted_count = 0
    failed_count = 0

    # Убедимся, что базовый путь существует и является директорией
    if not os.path.isdir(base_abs_path):
         logger.error(f"Базовый путь для удаления '{base_abs_path}' не существует или не является директорией. Удаление файлов отменено.")
         return # Не можем продолжать без базового пути

    for file_path_part in file_paths_to_delete:
        if not file_path_part or not isinstance(file_path_part, str): # Пропускаем пустые или нестроковые элементы
            logger.debug(f"Пропуск невалидной записи в списке файлов: {file_path_part}")
            continue

        # --- Сборка и проверка полного пути ---
        # Нормализуем разделители для безопасности
        clean_file_path_part = file_path_part.replace('\\', '/')

        # Проверка безопасности: предотвращение обхода каталога
        if '..' in clean_file_path_part or clean_file_path_part.startswith('/'):
             logger.warning(f"Пропуск потенциально опасного пути к файлу: '{file_path_part}' в {base_abs_path}")
             failed_count += 1
             continue

        # Собираем абсолютный путь
        # os.path.join корректно обработает разделители
        try:
            full_abs_path_to_delete = os.path.abspath(os.path.join(base_abs_path, clean_file_path_part))
        except Exception as path_err:
             logger.error(f"Ошибка сборки пути для '{file_path_part}' в '{base_abs_path}': {path_err}")
             failed_count += 1
             continue

        # Дополнительная проверка безопасности: убедимся, что файл находится ВНУТРИ ожидаемой базовой папки
        # (на случай изощренных атак, которые обошли проверку '..')
        common_prefix = os.path.commonpath([base_abs_path, full_abs_path_to_delete])
        if os.path.abspath(common_prefix) != os.path.abspath(base_abs_path):
            logger.error(f"Попытка удаления файла вне базовой директории! Путь: '{full_abs_path_to_delete}', База: '{base_abs_path}'. Отменено.")
            failed_count += 1
            continue

        # --- Удаление файла ---
        try:
            # Проверяем существование файла перед удалением
            if os.path.isfile(full_abs_path_to_delete):
                os.remove(full_abs_path_to_delete)
                logger.info(f"Удален файл: {full_abs_path_to_delete}") # Используем INFO для удаленных
                deleted_count += 1
            # else:
                # Логировать ненайденные файлы может быть слишком шумно
                # logger.debug(f"Файл не найден для удаления: {full_abs_path_to_delete}")
                # failed_count += 1 # Считать ли ненайденный файл ошибкой? Зависит от логики.
                pass
        except OSError as e:
            # Логируем ошибку ОС (например, нет прав)
            logger.error(f"Ошибка удаления файла {clean_file_path_part} по пути {full_abs_path_to_delete}: {e}", exc_info=True)
            failed_count += 1
        except Exception as e:
            # Логируем другие неожиданные ошибки
            logger.error(f"Неожиданная ошибка при удалении файла {clean_file_path_part}: {e}", exc_info=True)
            failed_count += 1

    # Логируем итог операции
    if failed_count > 0:
         logger.warning(f"Завершено удаление медиа из '{base_abs_path}'. Удалено: {deleted_count}, Ошибки/Пропущено/Не найдено: {failed_count}")
    elif deleted_count > 0:
         logger.info(f"Завершено удаление медиа из '{base_abs_path}'. Удалено: {deleted_count}.")
    else:
         logger.debug(f"Нет файлов для удаления в '{base_abs_path}' или список был пуст.")


def remove_post(post_id):
    """Удаляет пост, его ответы, статус закрепления и связанные медиафайлы."""
    try:
        pid = int(post_id)
    except (ValueError, TypeError):
        logger.error(f"Не удалось удалить пост: неверный ID {post_id}")
        return False

    conn = None
    try:
        conn = get_db_conn()
        cursor = conn.cursor()

        # Получаем списки файлов ДО удаления из БД
        cursor.execute("SELECT post_images, imagesthb FROM posts WHERE post_id = ?", (pid,))
        post_files_row = cursor.fetchone()
        cursor.execute("SELECT images, imagesthb FROM replies WHERE post_id = ?", (pid,))
        reply_files_list_rows = cursor.fetchall()

        # Удаляем пост (каскадно удалит ответы и пины)
        cursor.execute("DELETE FROM posts WHERE post_id = ?", (pid,))
        rows_affected = cursor.rowcount
        conn.commit()

        if rows_affected > 0:
            logger.info(f"Пост {pid} и связанные ответы/пины удалены из базы данных.")

            # --- Удаляем файлы ПОСЛЕ успешного удаления из БД ---
            if post_files_row:
                # Удаляем ОРИГИНАЛЬНЫЕ изображения поста
                # Передаем АБСОЛЮТНЫЙ путь к папке с оригиналами
                delete_media_files(post_files_row['post_images'], POST_IMAGE_ABS_PATH)
                # Удаляем МИНИАТЮРЫ поста
                # Передаем АБСОЛЮТНЫЙ путь к папке static, т.к. пути в imagesthb уже содержат 'post_images/thumbs/...'
                delete_media_files(post_files_row['imagesthb'], STATIC_FOLDER_PATH)

            # Удаляем файлы ответов
            for reply_files_row in reply_files_list_rows:
                # Удаляем ОРИГИНАЛЬНЫЕ изображения ответа
                delete_media_files(reply_files_row['images'], REPLY_IMAGE_ABS_PATH)
                # Удаляем МИНИАТЮРЫ ответа
                delete_media_files(reply_files_row['imagesthb'], STATIC_FOLDER_PATH)
            return True
        else:
            logger.warning(f"Попытка удаления поста {pid}, но он не найден в базе данных.")
            return False

    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при удалении поста {pid}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при удалении поста {pid}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def remove_reply(reply_id):
    """Удаляет один ответ и связанные с ним медиафайлы."""
    try:
        rid = int(reply_id)
    except (ValueError, TypeError):
        logger.error(f"Не удалось удалить ответ: неверный ID {reply_id}")
        return False

    conn = None
    try:
        conn = get_db_conn()
        cursor = conn.cursor()

        # Получаем списки файлов ДО удаления из БД
        cursor.execute("SELECT images, imagesthb FROM replies WHERE reply_id = ?", (rid,))
        reply_files_row = cursor.fetchone()

        # Удаляем ответ
        cursor.execute("DELETE FROM replies WHERE reply_id = ?", (rid,))
        rows_affected = cursor.rowcount
        conn.commit()

        if rows_affected > 0:
            logger.info(f"Ответ {rid} удален из базы данных.")

            # --- Удаляем файлы ПОСЛЕ успешного удаления из БД ---
            if reply_files_row:
                # Удаляем ОРИГИНАЛЬНЫЕ изображения ответа
                delete_media_files(reply_files_row['images'], REPLY_IMAGE_ABS_PATH)
                # Удаляем МИНИАТЮРЫ ответа
                delete_media_files(reply_files_row['imagesthb'], STATIC_FOLDER_PATH)
            return True
        else:
            logger.warning(f"Попытка удаления ответа {rid}, но он не найден.")
            return False

    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных при удалении ответа {rid}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при удалении ответа {rid}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


def verify_locked_thread(thread_id):
    """Проверяет, заблокирован ли тред."""
    try: tid = int(thread_id)
    except (ValueError, TypeError): return False
    sql = "SELECT locked FROM posts WHERE post_id = ?"
    result = execute_query(sql, (tid,), fetchone=True)
    return result['locked'] == 1 if result else False

def lock_thread(thread_id):
    """Блокирует или разблокирует тред."""
    try: tid = int(thread_id)
    except (ValueError, TypeError): logger.error(f"Не удалось заблокировать/разблокировать тред: неверный ID {thread_id}"); return False
    current_state_sql = "SELECT locked FROM posts WHERE post_id = ?"
    current_state = execute_query(current_state_sql, (tid,), fetchone=True)
    if not current_state: logger.warning(f"Невозможно заблокировать/разблокировать тред {tid}: Тред не найден."); return False
    new_state = 1 if current_state['locked'] == 0 else 0
    update_sql = "UPDATE posts SET locked = ? WHERE post_id = ?"
    try:
        # fetchall=False здесь не обязательно, т.к. commit=True уже есть
        result = execute_query(update_sql, (new_state, tid), commit=True)
        if result is not None: action = "заблокирован" if new_state == 1 else "разблокирован"; logger.info(f"Тред {tid} был успешно {action}."); return True
        else: return False # Ошибка была залогирована в execute_query
    except Exception as e: action = "блокировки" if new_state == 1 else "разблокировки"; logger.error(f"Не удалось выполнить операцию {action} треда {tid}: {e}", exc_info=True); return False


def is_post_pinned(post_id, board_uri):
     """Проверяет, закреплен ли конкретный пост на доске."""
     try: pid = int(post_id)
     except (ValueError, TypeError): return False
     sql = "SELECT 1 FROM pinned WHERE post_id = ? AND board_uri = ?"
     return bool(execute_query(sql, (pid, board_uri), fetchone=True))

def pin_post(post_id):
    """Закрепляет или открепляет пост."""
    try: pid = int(post_id)
    except (ValueError, TypeError): logger.error(f"Не удалось закрепить/открепить пост: неверный ID {post_id}"); return False
    post_info_sql = "SELECT board_uri FROM posts WHERE post_id = ?"
    post_info = execute_query(post_info_sql, (pid,), fetchone=True)
    if not post_info: logger.warning(f"Невозможно закрепить/открепить пост {pid}: Пост не найден."); return False
    board_uri = post_info['board_uri']
    currently_pinned = is_post_pinned(pid, board_uri)
    if currently_pinned:
        # Открепляем
        sql = "DELETE FROM pinned WHERE post_id = ? AND board_uri = ?"
        try:
            result = execute_query(sql, (pid, board_uri), commit=True, fetchall=False)
            if result is not None: logger.info(f"Пост {pid} откреплен от доски '{board_uri}'."); return True
            else: return False
        except Exception as e: logger.error(f"Не удалось открепить пост {pid}: {e}", exc_info=True); return False
    else:
        # Закрепляем
        sql = "INSERT OR IGNORE INTO pinned (post_id, board_uri) VALUES (?, ?)"
        try:
            result = execute_query(sql, (pid, board_uri), commit=True, fetchall=False)
            if result is not None: logger.info(f"Пост {pid} закреплен на доске '{board_uri}'."); return True
            else: return False
        except Exception as e: logger.error(f"Не удалось закрепить пост {pid}: {e}", exc_info=True); return False


# --- Query Operations ---
def get_posts_for_board(board_uri, offset=0, limit=10):
    """Загружает страницы с постами (тредами) для доски, исключая закрепленные."""
    sql = "SELECT p.* FROM posts p LEFT JOIN pinned pn ON p.post_id = pn.post_id AND p.board_uri = pn.board_uri WHERE p.board_uri = ? AND pn.post_id IS NULL ORDER BY p.last_bumped DESC LIMIT ? OFFSET ?"
    params = (board_uri, limit, offset)
    posts = execute_query(sql, params, fetchall=True)
    return posts if posts else []

def get_pinned_posts(board_uri):
    """Получает закрепленные посты для доски."""
    sql = "SELECT p.* FROM posts p JOIN pinned pn ON p.post_id = pn.post_id WHERE pn.board_uri = ? ORDER BY p.post_date DESC"
    params = (board_uri,)
    pinned_posts = execute_query(sql, params, fetchall=True)
    return pinned_posts if pinned_posts else []

def get_replies_for_posts(post_ids):
    """Получает все ответы для списка ID постов."""
    if not post_ids or not isinstance(post_ids, (list, tuple)): return []
    placeholders = ','.join('?' * len(post_ids))
    sql = f"SELECT * FROM replies WHERE post_id IN ({placeholders}) ORDER BY post_date ASC"
    replies = execute_query(sql, tuple(post_ids), fetchall=True)
    return replies if replies else []

def get_post_and_replies(thread_id):
     """Получает конкретный пост (OP треда) и все его ответы."""
     try: tid = int(thread_id)
     except (ValueError, TypeError): return None, []
     post_sql = "SELECT * FROM posts WHERE post_id = ?"
     thread_op = execute_query(post_sql, (tid,), fetchone=True)
     if not thread_op: return None, []
     replies_sql = "SELECT * FROM replies WHERE post_id = ? ORDER BY post_date ASC"
     replies = execute_query(replies_sql, (tid,), fetchall=True)
     return thread_op, (replies if replies else [])

def get_user_boards(username):
    """Получает все доски, принадлежащие пользователю."""
    sql = "SELECT * FROM boards WHERE board_owner = ? ORDER BY board_name"
    boards = execute_query(sql, (username,), fetchall=True)
    return boards if boards else []

def get_custom_themes():
    """Получает доступные пользовательские темы (работа с файловой системой)."""
    custom_css_path = os.path.join(STATIC_FOLDER_PATH, 'css', 'custom')
    temas = []
    if os.path.isdir(custom_css_path):
        try:
            for arquivo in os.listdir(custom_css_path):
                if arquivo.endswith('.css') and os.path.isfile(os.path.join(custom_css_path, arquivo)):
                    nome_sem_extensao = os.path.splitext(arquivo)[0]
                    tema = {"theme_name": nome_sem_extensao, "theme_file": arquivo}
                    temas.append(tema)
        except OSError as e: logger.error(f"Ошибка чтения тем в {custom_css_path}: {e}")
    else: logger.warning(f'Папка пользовательских тем {custom_css_path} не существует или не является директорией.')
    return temas

def get_all_banners(board_uri):
    """Получает все баннеры для доски (работа с файловой системой)."""
    banner_folder_abs = os.path.join(STATIC_FOLDER_PATH, 'imgs', 'banners', board_uri)
    banners_paths = []
    if os.path.isdir(banner_folder_abs):
        try:
            for banner_file in os.listdir(banner_folder_abs):
                 if banner_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and os.path.isfile(os.path.join(banner_folder_abs, banner_file)):
                    rel_path = f'/static/imgs/banners/{board_uri}/{banner_file}'.replace('\\', '/')
                    banners_paths.append(rel_path)
        except OSError as e: logger.error(f"Ошибка чтения баннеров в {banner_folder_abs}: {e}")
    else: logger.warning(f"Папка баннеров {banner_folder_abs} не найдена для доски {board_uri}.")
    return banners_paths


# --- Functions needed for context processors etc. ---
def get_all_posts_simple(sort_by_date=True):
    """Получает все посты (только OP), опционально отсортированные."""
    order = "ORDER BY last_bumped DESC" if sort_by_date else "ORDER BY post_date DESC"
    sql = f"SELECT * FROM posts {order}"
    posts = execute_query(sql, fetchall=True)
    return posts if posts else []

def get_all_replies_simple():
     """Получает все ответы (для подсчетов или других нужд)."""
     sql = "SELECT * FROM replies ORDER BY post_date DESC"
     replies = execute_query(sql, fetchall=True)
     return replies if replies else []

# --- Блок для тестирования модуля (при запуске напрямую) ---
if __name__ == '__main__':
    # Используем основной логгер, определенный в начале файла
    logger.info("Модуль базы данных ЗАПУЩЕН НАПРЯМУЮ. Запуск примеров проверок.")
    test_passed = False
    try:
        conn_test = get_db_conn()
        if conn_test:
            conn_test.close()
            logger.info("Тест соединения с базой данных (из __main__) успешен.")
            test_passed = True
        else:
            logger.error("Тест соединения с базой данных (из __main__) НЕ удался.")

    except Exception as e:
        logger.error(f"Ошибка во время тестов в __main__ database_module: {e}", exc_info=True)

    if test_passed:
        logger.info("Тесты в __main__ database_module завершены успешно.")
    else:
        logger.warning("Тесты в __main__ database_module завершены с ошибками или не выполнялись.")

    logger.info("--- Конец выполнения __main__ в database_module.py ---")

# --- END OF FILE database_module.py ---