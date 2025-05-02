# --- START OF FILE auth_bp.py ---

from flask import (
    current_app, Blueprint, render_template, session,
    request, redirect, send_from_directory, flash, url_for
)
# Используем обновленные модули
from database_modules import database_module, language_module, moderation_module
import os
import logging # Добавляем логирование

# Получаем логгер
logger = logging.getLogger(__name__)

# Регистрация Blueprint
# Указываем пути к шаблонам/статике относительно корня проекта, если auth_bp в папке blueprints
auth_bp = Blueprint('auth', __name__, template_folder='../templates', static_folder='../static')

# --- Вспомогательные функции ---
def allowed_file(filename):
    """Проверяет разрешенные расширения для загружаемых файлов (например, баннеров)."""
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Маршруты ---

@auth_bp.route('/favicon.ico')
def favicon():
    """Отдает favicon.ico из папки static."""
    # Путь формируется относительно папки static приложения
    static_dir = current_app.static_folder or os.path.join(current_app.root_path, 'static')
    favicon_path = os.path.join(static_dir, 'imgs', 'decoration')
    try:
        return send_from_directory(favicon_path, 'icon.png', mimetype='image/png') # Указываем правильный mimetype
    except FileNotFoundError:
        logger.warning("favicon.ico not found at expected location.")
        # Возвращаем 404, если файл не найден
        from werkzeug.exceptions import NotFound
        raise NotFound()


@auth_bp.route('/change_general_lang', methods=['POST'])
def change_general_lang():
    """Изменяет язык по умолчанию для всего сайта (только владелец)."""
    new_lang = request.form.get('lang')
    if 'username' in session:
        user_role = database_module.get_user_role(session["username"])
        # Проверяем, что роль не None и содержит 'owner'
        if user_role and 'owner' in user_role.lower():
            try:
                if language_module.change_general_language(new_lang):
                    flash('Default language changed successfully!', 'success')
                    logger.info(f"User '{session['username']}' changed default language to '{new_lang}'.")
                else:
                    flash(f"Could not change language to '{new_lang}'. Language might not exist.", 'warning')
            except Exception as e:
                logger.error(f"Error changing default language: {e}", exc_info=True)
                flash('An error occurred while changing the language.', 'error')
        else:
            flash('You do not have permission to change the default language.', 'error')
    else:
        flash('You must be logged in as the owner to change the language.', 'warning')
    # Редирект на предыдущую страницу
    return redirect(request.referrer or url_for('boards.main_page'))


@auth_bp.route('/auth_user', methods=['POST'])
def login():
    """Обрабатывает вход пользователя."""
    # Проверяем, что метод POST (хотя route уже ограничивает)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Проверяем, что поля не пустые
        if not username or not password:
            flash('Username and password are required.', 'warning')
            return redirect(url_for('boards.login')) # Редирект на страницу логина

        # Пытаемся залогинить пользователя
        if database_module.login_user(username, password):
            # Успешно: сохраняем в сессию
            session['username'] = username
            # Получаем и сохраняем роль (важно для проверок прав)
            role = database_module.get_user_role(username)
            session['role'] = role if role else 'user' # Назначаем 'user' если роль не задана
            logger.info(f"User '{username}' logged in successfully.")
            # Редирект на дашборд
            return redirect(url_for('boards.login')) # '/conta' рендерит дашборд, если залогинен
        else:
            # Неуспешно: сообщение об ошибке
            flash('Invalid username or password. Please try again.', 'danger')
            logger.warning(f"Failed login attempt for username '{username}'.")
    # Если GET-запрос или ошибка, редирект на страницу логина
    return redirect(url_for('boards.login'))


@auth_bp.route('/register_user', methods=['POST'])
def register():
    """Обрабатывает регистрацию нового пользователя."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').strip()
        session_captcha = session.get('captcha_text') # Получаем правильный ответ из сессии

        # Валидация капчи ДО запроса к БД
        if not database_module.validate_captcha(captcha_input, session_captcha):
            flash('Invalid captcha code.', 'error')
            # Генерируем новую капчу для следующей попытки
            captcha_text_new, captcha_image_new = database_module.generate_captcha()
            session['captcha_text'] = captcha_text_new
            # Передаем НОВУЮ капчу в шаблон регистрационной страницы при редиректе?
            # Или просто редирект и пусть GET-маршрут /registrar генерирует новую?
            # Проще просто редирект назад:
            return redirect(request.referrer or url_for('boards.register'))

        # Пытаемся зарегистрировать пользователя
        # Передаем session_captcha для проверки внутри register_user
        if database_module.register_user(username, password, captcha_input, session_captcha):
            flash('Registration successful! Please log in.', 'success')
            logger.info(f"New user '{username}' registered.")
            # Редирект на страницу логина после успешной регистрации
            return redirect(url_for('boards.login'))
        else:
            # register_user вернул False (ошибка валидации, занятое имя и т.д.)
            # Сообщение flash должно быть установлено внутри register_user или здесь
            flash('Registration failed. Username might be taken or invalid input.', 'error')
            # Редирект обратно на страницу регистрации
            return redirect(request.referrer or url_for('boards.register'))

    # Если GET-запрос, редирект на страницу регистрации
    return redirect(url_for('boards.register'))


@auth_bp.route('/create_board', methods=['POST'])
def create_board():
    """Обрабатывает создание новой доски."""
    if 'username' not in session:
        flash('You must be logged in to create a board.', 'warning')
        return redirect(url_for('boards.login'))

    if request.method == 'POST':
        uri = request.form.get('uri', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        captcha_input = request.form.get('captcha', '').strip()
        session_captcha = session.get('captcha_text')
        current_user = session['username']

        # Валидация капчи
        if not database_module.validate_captcha(captcha_input, session_captcha):
            flash('Invalid captcha code.', 'error')
            return redirect(request.referrer or url_for('boards.create')) # Назад на форму создания

        # Пытаемся создать доску
        if database_module.add_new_board(uri, name, description, current_user, captcha_input, session_captcha):
            flash(f"Board '/{uri}/' created successfully!", 'success')
            logger.info(f"User '{current_user}' created board '/{uri}/'.")
            # Редирект на страницу новой доски
            return redirect(url_for('boards.board_page', board_uri=uri))
        else:
            # add_new_board вернул False (ошибка валидации, занятый URI и т.д.)
            flash('Failed to create board. URI might be taken or invalid input.', 'error')
            # Редирект обратно на форму создания
            return redirect(request.referrer or url_for('boards.create'))

    # Если GET-запрос
    return redirect(url_for('boards.create'))


@auth_bp.route('/apply_general_captcha', methods=['POST'])
def apply_general_captcha():
    """Включает/выключает капчу для всех досок (владелец/модератор)."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    if request.method == 'POST':
        option = request.form.get('generalcaptcha_option') # 'enable' или 'disable'
        user_role = database_module.get_user_role(session["username"])

        # Проверка прав
        if user_role and ('owner' in user_role.lower() or 'mod' in user_role.lower()):
            if option in ['enable', 'disable']:
                if database_module.set_all_boards_captcha(option):
                    status = "enabled" if option == "enable" else "disabled"
                    flash(f'CAPTCHA requirement {status} for all boards.', 'success')
                    logger.info(f"User '{session['username']}' {status} CAPTCHA globally.")
                else:
                    flash('Failed to update CAPTCHA settings.', 'error')
            else:
                flash('Invalid option selected.', 'warning')
        else:
            flash('You do not have permission to change global CAPTCHA settings.', 'error')

    return redirect(request.referrer or url_for('boards.main_page'))


@auth_bp.route('/lock_thread/<post_id>', methods=['POST'])
def lock_thread(post_id):
    """Блокирует/разблокирует тред."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    try:
        pid = int(post_id)
    except ValueError:
        flash('Invalid post ID.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # --- Проверка прав ---
    # Получаем инфо о посте, чтобы узнать доску и проверить существование
    post_info = database_module.execute_query("SELECT board_uri FROM posts WHERE post_id = ?", (pid,), fetchone=True)
    if not post_info:
        flash('Thread not found.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    board_uri = post_info['board_uri']
    board_info = database_module.get_board_info(board_uri)
    actual_board_owner = board_info['board_owner'] if board_info else None

    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    can_lock = False
    if user_roles:
        if 'owner' in user_roles.lower() or 'mod' in user_roles.lower():
            can_lock = True
        elif actual_board_owner and current_user == actual_board_owner:
            can_lock = True

    if not can_lock:
        flash('You do not have permission to lock/unlock this thread.', 'error')
        return redirect(request.referrer or url_for('boards.replies', board_name=board_uri, thread_id=pid))

    # --- Выполнение действия ---
    # Получаем текущее состояние перед изменением для сообщения
    is_currently_locked = database_module.verify_locked_thread(pid)

    if database_module.lock_thread(pid):
        action = "unlocked" if is_currently_locked else "locked"
        flash(f'Thread {action} successfully.', 'success')
        logger.info(f"User '{current_user}' {action} thread {pid} on board '{board_uri}'.")
    else:
        # lock_thread мог вернуть False, если пост не найден (хотя мы проверили)
        flash('Failed to change thread lock state.', 'error')

    # Редирект на страницу треда
    return redirect(request.referrer or url_for('boards.replies', board_name=board_uri, thread_id=pid))


@auth_bp.route('/remove_board/<board_uri>', methods=['POST'])
def remove_board(board_uri):
    """Удаляет доску (владелец доски/владелец сайта/модератор)."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    # Вызываем функцию удаления, передавая текущего пользователя и его роль
    # Функция remove_board внутри себя проверит права
    if database_module.remove_board(board_uri, current_user, user_roles):
        flash(f'Board /{board_uri}/ and all its content have been deleted!', 'success')
        logger.info(f"User '{current_user}' deleted board '/{board_uri}/'.")
        # Редирект на главную страницу после удаления доски
        return redirect(url_for('boards.main_page'))
    else:
        # Сообщение flash должно быть установлено внутри remove_board или здесь
        flash(f'Failed to delete board /{board_uri}/. You might not have permission or the board does not exist.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))


@auth_bp.route('/upload_banner', methods=['POST'])
def upload_banner():
    """Загружает новый баннер для доски (только владелец доски)."""
    if 'username' not in session:
        flash('You must be logged in to upload banners.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    board_uri = request.form.get('board_uri')
    if not board_uri:
        flash('Board URI is missing.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # Получаем информацию о доске для проверки владельца
    board_info = database_module.get_board_info(board_uri)
    if not board_info:
        flash(f"Board '/{board_uri}/' not found.", 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # Проверка прав: только владелец доски
    if session['username'] != board_info['board_owner']:
        flash('Only the board owner can upload banners.', 'error')
        return redirect(request.referrer or url_for('boards.board_banners', board_uri=board_uri))

    # Проверка наличия файла в запросе
    if 'imageUpload' not in request.files:
        flash('No file selected for upload.', 'warning')
        return redirect(request.referrer or url_for('boards.board_banners', board_uri=board_uri))

    file = request.files['imageUpload']

    # Проверка имени файла и расширения
    if file.filename == '':
        flash('No file selected for upload.', 'warning')
        return redirect(request.referrer or url_for('boards.board_banners', board_uri=board_uri))

    if file and allowed_file(file.filename):
        # Формируем путь для сохранения
        # Используем относительный путь от корня проекта
        directory = os.path.join('.', 'static', 'imgs', 'banners', board_uri)
        try:
            os.makedirs(directory, exist_ok=True) # Создаем папку, если ее нет
            # Используем secure_filename для безопасности имени файла
            # filename = secure_filename(file.filename) # Раскомментируйте, если хотите очищать имя
            filename = file.filename # Или сохраняем оригинальное имя
            save_path = os.path.join(directory, filename)
            file.save(save_path)
            flash(f'Banner "{filename}" uploaded successfully!', 'success')
            logger.info(f"User '{session['username']}' uploaded banner '{filename}' for board '/{board_uri}/'.")
        except Exception as e:
            logger.error(f"Error saving uploaded banner for board '/{board_uri}/': {e}", exc_info=True)
            flash('An error occurred while saving the banner.', 'error')
    else:
        flash('Invalid file type. Allowed types: jpg, jpeg, png, gif, webp.', 'warning')

    # Редирект на страницу управления баннерами
    return redirect(url_for('boards.board_banners', board_uri=board_uri))


@auth_bp.route('/pin_post/<post_id>', methods=['POST'])
def pin_post(post_id):
    """Закрепляет/открепляет пост (владелец доски/владелец сайта/модератор)."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    try:
        pid = int(post_id)
    except ValueError:
        flash('Invalid post ID.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # --- Проверка прав (аналогично lock_thread) ---
    post_info = database_module.execute_query("SELECT board_uri FROM posts WHERE post_id = ?", (pid,), fetchone=True)
    if not post_info:
        flash('Post not found.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    board_uri = post_info['board_uri']
    board_info = database_module.get_board_info(board_uri)
    actual_board_owner = board_info['board_owner'] if board_info else None

    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    can_pin = False
    if user_roles:
        if 'owner' in user_roles.lower() or 'mod' in user_roles.lower():
            can_pin = True
        elif actual_board_owner and current_user == actual_board_owner:
            can_pin = True

    if not can_pin:
        flash('You do not have permission to pin/unpin this post.', 'error')
        # Редирект на тред или доску
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_uri))

    # --- Выполнение действия ---
    is_currently_pinned = database_module.is_post_pinned(pid, board_uri) # Проверяем текущее состояние

    if database_module.pin_post(pid): # pin_post сама переключает состояние
        action = "unpinned" if is_currently_pinned else "pinned"
        flash(f'Post {action} successfully!', 'success')
        logger.info(f"User '{current_user}' {action} post {pid} on board '{board_uri}'.")
    else:
        # pin_post вернул False (ошибка или пост не найден)
        flash('Failed to change post pin state.', 'error')

    # Редирект обратно (вероятно, на доску или тред)
    return redirect(request.referrer or url_for('boards.board_page', board_uri=board_uri))


@auth_bp.route('/delete_post/<post_id>', methods=['POST'])
def delete_post(post_id):
    """Удаляет пост (владелец доски/владелец сайта/модератор)."""
    # Проверка, залогинен ли пользователь
    if 'username' not in session:
        flash('You must be logged in to delete posts.', 'warning')
        return redirect(url_for('boards.login'))

    try:
        pid = int(post_id)
    except ValueError:
        flash('Invalid post ID.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # Получаем информацию о посте ДО удаления (включая board_uri)
    # Используем execute_query напрямую для простоты
    post_info = database_module.execute_query("SELECT board_uri FROM posts WHERE post_id = ?", (pid,), fetchone=True)

    if not post_info:
        flash('Post not found.', 'error')
        # Если пост уже удален, редирект на главную или referrer
        return redirect(request.referrer or url_for('boards.main_page'))

    board_uri_to_redirect = post_info['board_uri']

    # Получаем информацию о доске, чтобы узнать владельца
    board_info = database_module.get_board_info(board_uri_to_redirect)
    actual_board_owner = board_info['board_owner'] if board_info else None

    # Получаем роль текущего пользователя
    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    # --- Проверка прав на удаление ---
    can_delete = False
    if user_roles: # Убедимся, что роль получена
        if 'owner' in user_roles.lower() or 'mod' in user_roles.lower():
            can_delete = True
        elif actual_board_owner and current_user == actual_board_owner:
            can_delete = True

    if not can_delete:
        flash('You do not have permission to delete this post.', 'error')
        logger.warning(f"User '{current_user}' attempted to delete post {pid} on board '{board_uri_to_redirect}' without permission.")
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_uri_to_redirect))

    # --- Попытка удаления поста ---
    if database_module.remove_post(pid):
        flash('Post deleted successfully!', 'success')
        logger.info(f"User '{current_user}' deleted post {pid} from board '{board_uri_to_redirect}'.")
        # Редирект на главную страницу доски
        return redirect(url_for('boards.board_page', board_uri=board_uri_to_redirect))
    else:
        # remove_post вернул False
        flash('Failed to delete the post. It might have been already deleted.', 'warning')
        return redirect(url_for('boards.board_page', board_uri=board_uri_to_redirect))


@auth_bp.route('/delete_reply/<reply_id>', methods=['POST'])
def delete_reply(reply_id):
    """Удаляет ответ (владелец доски/владелец сайта/модератор)."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(url_for('boards.login'))

    try:
        rid = int(reply_id)
    except ValueError:
        flash('Invalid reply ID.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # Получаем информацию об ответе ДО удаления (включая post_id -> board_uri)
    reply_info = database_module.execute_query(
        "SELECT p.board_uri FROM replies r JOIN posts p ON r.post_id = p.post_id WHERE r.reply_id = ?",
        (rid,), fetchone=True)

    if not reply_info:
        flash('Reply not found.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    board_uri_to_redirect = reply_info['board_uri']

    # Проверка прав (аналогично delete_post)
    board_info = database_module.get_board_info(board_uri_to_redirect)
    actual_board_owner = board_info['board_owner'] if board_info else None
    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    can_delete = False
    if user_roles:
        if 'owner' in user_roles.lower() or 'mod' in user_roles.lower():
            can_delete = True
        elif actual_board_owner and current_user == actual_board_owner:
            can_delete = True

    if not can_delete:
        flash('You do not have permission to delete this reply.', 'error')
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_uri_to_redirect))

    # --- Попытка удаления ответа ---
    if database_module.remove_reply(rid):
        flash('Reply deleted successfully!', 'success')
        logger.info(f"User '{current_user}' deleted reply {rid} from board '{board_uri_to_redirect}'.")
    else:
        flash('Failed to delete the reply. It might have been already deleted.', 'warning')

    # Редирект обратно на страницу (вероятно, тред или доска)
    return redirect(request.referrer or url_for('boards.board_page', board_uri=board_uri_to_redirect))


@auth_bp.route('/ban_user/<post_id>', methods=['POST'])
def ban_user(post_id):
    """Банит пользователя по IP адресу поста/ответа (владелец сайта/модератор)."""
    if 'username' not in session:
        flash('You must be logged in.', 'warning')
        return redirect(request.referrer or url_for('boards.main_page'))

    try:
        content_id = int(post_id) # Это может быть ID поста или ответа
    except ValueError:
        flash('Invalid content ID for banning.', 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # --- Проверка прав на бан ---
    current_user = session["username"]
    user_roles = database_module.get_user_role(current_user)

    can_ban = False
    if user_roles and ('owner' in user_roles.lower() or 'mod' in user_roles.lower()):
        can_ban = True

    if not can_ban:
        flash("You don't have permission to ban users.", 'error')
        return redirect(request.referrer or url_for('boards.main_page'))

    # --- Получение IP и выполнение бана ---
    user_ip_to_ban = database_module.get_post_ip(content_id)

    if user_ip_to_ban:
        ban_manager = moderation_module.BanManager()
        reason = request.form.get('ban_reason', 'No reason provided.') # Можно добавить поле для причины в форму
        duration_str = request.form.get('ban_duration') # Поле для длительности (например, в секундах или 'permanent')

        duration_seconds = None # По умолчанию - перманентный
        if duration_str and duration_str.isdigit():
            duration_seconds = int(duration_str)
        elif duration_str == 'permanent':
             duration_seconds = None

        # Баним пользователя
        if ban_manager.ban_user(user_ip_to_ban, duration_seconds=duration_seconds, reason=reason, moderator=current_user):
            flash(f'The user with IP {user_ip_to_ban} has been banned. Reason: {reason}', 'success')
            logger.info(f"User '{current_user}' banned IP {user_ip_to_ban} (from content ID {content_id}). Reason: {reason}, Duration(s): {duration_seconds}")
        else:
             # Ошибка в ban_user (маловероятно, если IP есть)
             flash('An error occurred while trying to ban the user.', 'error')
    else:
        # IP не найден для данного ID (пост/ответ удален?)
        flash('Could not find the user IP associated with this content to ban.', 'error')

    return redirect(request.referrer or url_for('boards.main_page'))


@auth_bp.route('/logout')
def logout():
    """Выход пользователя из системы."""
    if 'username' in session:
        logged_out_user = session['username']
        session.pop('username', None)
        session.pop('role', None) # Удаляем и роль из сессии
        flash('You have been logged out successfully.', 'info')
        logger.info(f"User '{logged_out_user}' logged out.")
    # Редирект на главную страницу
    return redirect(url_for('boards.main_page'))

# --- END OF FILE auth_bp.py ---