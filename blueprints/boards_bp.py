# --- START OF FILE boards_bp.py ---

# imports
from flask import current_app, Blueprint, render_template, session, redirect, request, url_for, flash
# --- ВАЖНО: Убедитесь, что эти импорты есть ---
from database_modules import database_module # <--- ОСНОВНОЙ ИМПОРТ
from database_modules import language_module
from database_modules import moderation_module # <--- Добавлен для дашборда (BanManager)
# --- КОНЕЦ ВАЖНОЙ ЧАСТИ ---
import logging
import json
from datetime import datetime, timezone # Для format_content_for_template и др.

# Configure logging
logger = logging.getLogger(__name__)

# blueprint register.
boards_bp = Blueprint('boards', __name__, template_folder='../templates', static_folder='../static')

# load language.
@boards_bp.context_processor
def inject_lang():
    user_lang_code = session.get('user_language', 'default')
    # Assuming language_module works independently or is adapted for SQLite if needed
    lang_data = language_module.get_user_lang(user_lang_code)
    return dict(lang=lang_data)

# load nav boards (with stats)
@boards_bp.context_processor
def globalboards():
    try:
        # get_all_boards returns list of dicts directly now (or Row objects convertible to dicts)
        boards_list = database_module.get_all_boards(include_stats=True)

        # Format last_activity date for display right here if needed by the template directly
        # Otherwise, templates can use the raw date string or a Jinja filter
        # Example formatting:
        # for board in boards_list:
        #     if board.get('last_activity'):
        #         dt_obj = database_module.parse_datetime(board['last_activity'])
        #         board['last_activity_display'] = database_module.format_datetime_for_display(dt_obj)
        #     else:
        #         board['last_activity_display'] = "No activity"

        return {"boards": boards_list or []}
    except Exception as e:
        logger.error(f"Error loading global boards: {e}", exc_info=True)
        return {"boards": []}

# load custom themes (filesystem access, no change needed for DB)
@boards_bp.context_processor
def customthemes():
    try:
        custom_themes_list = database_module.get_custom_themes()
        return {"custom_themes": custom_themes_list or []}
    except Exception as e:
        logger.error(f"Error loading custom themes: {e}", exc_info=True)
        return {"custom_themes": []}

# Context processor for reply counts (using direct SQL query)
@boards_bp.context_processor
def inject_reply_counts():
    reply_counts = {}
    try:
        # More efficient way: Query counts directly grouped by board URI
        sql = """
            SELECT p.board_uri, COUNT(r.id) as reply_count
            FROM replies r
            JOIN posts p ON r.post_id = p.post_id
            GROUP BY p.board_uri
        """
        # Use the execute_query helper from database_module
        results = database_module.execute_query(sql)
        if results:
            # Results are list of Row objects, convert to dict
            reply_counts = {row['board_uri']: row['reply_count'] for row in results}
        return {"reply_counts": reply_counts}

    except Exception as e:
        logger.error(f"Failed to calculate reply counts: {e}", exc_info=True)
        return {"reply_counts": {}} # Return empty dict on error

# error handling.
@boards_bp.errorhandler(404)
def page_not_found(e):
    # Log the path that was not found
    logger.warning(f"404 Not Found error handled for path: {request.path}")
    try:
        # Pass a message to the template if desired
        return render_template('errors/404.html', error=e, message="Page not found."), 404
    except Exception as render_err:
        # Fallback if the template itself fails
        logger.error(f"Error rendering 404 template: {render_err}", exc_info=True)
        return "404 Not Found", 404

@boards_bp.errorhandler(500)
def internal_server_error(e):
    # Log the full error
    logger.error(f"500 Internal Server Error handled for path: {request.path}", exc_info=True)
    try:
        # Pass a generic message or specific error info (carefully)
        error_message = "An internal server error occurred."
        # Optionally, you could try to extract a safe message from 'e' if needed
        # error_message = getattr(e, 'description', "An internal server error occurred.")
        return render_template('errors/500.html', error=e, error_message=error_message), 500
    except Exception as render_err:
         logger.error(f"Error rendering 500 template: {render_err}", exc_info=True)
         return "Internal Server Error", 500


# --- Helper function for formatting posts/replies (optional, can be inline) ---
def format_content_for_template(content_list):
    """Deserializes files and formats dates for a list of posts or replies."""
    formatted_list = []
    if not content_list:
        return []
    for item in content_list:
        item_dict = dict(item) # Convert Row object to dict
        # Determine keys based on whether it's a post or reply
        image_key = 'post_images' if 'post_images' in item_dict else 'images'
        thumb_key = 'imagesthb' if 'imagesthb' in item_dict else 'imagesthb' # Same key in both? Double-check schema/usage
        date_key = 'post_date' # Same key name in both posts and replies

        # Use the helpers from database_module
        item_dict[f'{image_key}_list'] = database_module._deserialize_files(item_dict.get(image_key))
        item_dict[f'{thumb_key}_list'] = database_module._deserialize_files(item_dict.get(thumb_key))

        dt_obj = database_module.parse_datetime(item_dict.get(date_key))
        item_dict['date_display'] = database_module.format_datetime_for_display(dt_obj)

        formatted_list.append(item_dict)
    return formatted_list

# --- Routes ---

# landing page route.
@boards_bp.route('/')
def main_page():
    try:
        # Fetch recent posts (OPs only)
        recent_posts_count = 6
        # Use the simple function, sorted by bump date (which includes replies) or post_date
        # Sorting by last_bumped DESC is generally preferred for main page
        all_ops = database_module.get_all_posts_simple(sort_by_date=True)

        # Slice the most recent OPs
        recent_ops_raw = all_ops[:recent_posts_count] if all_ops else []

        # Format for template (deserialize files, format date)
        recent_posts = format_content_for_template(recent_ops_raw)

        # Get all posts maybe for other sections? If not needed, remove this call.
        all_posts_for_template = format_content_for_template(all_ops) if all_ops else []


        return render_template('index.html',
                               all_posts=all_posts_for_template, # Pass all if needed
                               posts=recent_posts) # Pass formatted recent posts

    except Exception as e:
        logger.error(f"Error on main page: {e}", exc_info=True)
        # Use the 500 error handler by re-raising or rendering the 500 template
        return render_template('errors/500.html', error_message="Could not load main page content."), 500

# boards list page route.
@boards_bp.route('/tabuas')
def tabuas():
    try:
        # This page likely just needs the list of boards from the context processor.
        # If it needs posts too, fetch and format them.
        # Example: Fetching all OPs again if needed by tabuas.html
        # all_ops_raw = database_module.get_all_posts_simple(sort_by_date=False) # Maybe different sort?
        # all_posts_formatted = format_content_for_template(all_ops_raw)
        # return render_template('tabuas.html', all_posts=all_posts_formatted)

        # If tabuas.html only uses the {{ boards }} from context, this is simpler:
        return render_template('tabuas.html') # Assumes context processors provide necessary data

    except Exception as e:
        logger.error(f"Error on tabuas page: {e}", exc_info=True)
        return render_template('errors/500.html', error_message="Could not load boards list."), 500

# account dashboard and login route.
@boards_bp.route('/conta')
def login(): # Название маршрута login, но он же и дашборд
    if 'username' in session:
        try:
            username = session["username"]
            user_info = database_module.get_user_by_username(username)
            if not user_info:
                 session.pop('username', None)
                 session.pop('role', None)
                 flash("Your account could not be found. Please log in again.", "warning")
                 return redirect(url_for('boards.login'))

            roles = user_info['role']
            user_boards_raw = database_module.get_user_boards(username)
            user_boards = [dict(board) for board in user_boards_raw] if user_boards_raw else []

            all_posts_list_raw = database_module.get_all_posts_simple(sort_by_date=True)
            total_posts_count = len(all_posts_list_raw) if all_posts_list_raw else 0
            recent_dashboard_posts_raw = all_posts_list_raw[:10]

            recent_dashboard_posts = []
            board_owners_cache = {} # Кэш: {board_uri: owner_username}
            if recent_dashboard_posts_raw:
                # format_content_for_template возвращает список словарей
                formatted_recent = format_content_for_template(recent_dashboard_posts_raw)
                for post_dict in formatted_recent: # post_dict теперь словарь
                    board_uri_key = 'board_uri'
                    board_uri = post_dict.get(board_uri_key)

                    if board_uri:
                        if board_uri not in board_owners_cache:
                            # database_module.get_board_info возвращает sqlite3.Row или None
                            board_info_row = database_module.get_board_info(board_uri)
                            if board_info_row:
                                # Доступ к данным в sqlite3.Row по имени колонки (как к ключу словаря)
                                board_owners_cache[board_uri] = board_info_row['board_owner']
                            else:
                                # Если информация о доске не найдена
                                board_owners_cache[board_uri] = None
                        # Добавляем закэшированное значение в словарь поста
                        post_dict['board_owner_info'] = board_owners_cache.get(board_uri)
                    else:
                        post_dict['board_owner_info'] = None
                    recent_dashboard_posts.append(post_dict)

            # --- Получение списка активных банов для модераторов/владельцев ---
            active_bans = []
            # --- Получение списка пользователей для управления ролями (только для владельца) ---
            manageable_users = []

            if roles and ('owner' in roles.lower() or 'mod' in roles.lower()):
                ban_manager = moderation_module.BanManager()
                active_bans = ban_manager.get_active_bans()
                
                # Владелец может управлять ролями других пользователей
                if 'owner' in roles.lower():
                    # Исключаем самого владельца из списка, чтобы он не мог себя разжаловать
                    manageable_users = database_module.get_all_users_with_roles(exclude_username=username)

            return render_template('dashboard.html',
                                   username=username,
                                   roles=roles,
                                   user_boards=user_boards,
                                   total_posts_count=total_posts_count,
                                   recent_dashboard_posts=recent_dashboard_posts,
                                   active_bans=active_bans,
                                   manageable_users=manageable_users, # <--- ПЕРЕДАЕМ ПОЛЬЗОВАТЕЛЕЙ
                                   all_boards=globalboards().get("boards", [])
                                  )
        except Exception as e:
            logger.error(f"Error loading dashboard for {session.get('username')}: {e}", exc_info=True)
            return render_template('errors/500.html', error_message="Could not load dashboard."), 500
    else:
        return render_template('login.html')


# register page route.
@boards_bp.route('/registrar')
def register():
    if 'username' in session:
        return redirect(url_for('boards.login')) # Redirect logged-in users
    try:
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text # Store correct answer in session
        return render_template('register.html', captcha_image=captcha_image)
    except Exception as e:
        logger.error(f"Error generating CAPTCHA for registration: {e}", exc_info=True)
        return render_template('errors/500.html', error_message="Could not load registration page."), 500

# board creation page route.
@boards_bp.route('/create')
def create():
    if 'username' not in session:
        flash("You must be logged in to create a board.", "warning")
        return redirect(url_for('boards.login'))

    # --- ПРОВЕРКА РОЛИ ПОЛЬЗОВАТЕЛЯ ---
    user_role = database_module.get_user_role(session["username"])
    if not user_role or 'owner' not in user_role.lower():
        flash("Only the site owner can create new boards.", "error")
        logger.warning(f"User '{session['username']}' (role: {user_role}) "
                       f"attempted to access board creation page without owner permission.")
        # Редирект на дашборд или главную страницу
        return redirect(url_for('boards.login')) # Если залогинен, попадет на дашборд
    # --- КОНЕЦ ПРОВЕРКИ РОЛИ ---

    # Если пользователь - владелец, продолжаем как обычно
    try:
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text
        return render_template('board-create.html', captcha_image=captcha_image)
    except Exception as e:
        logger.error(f"Error generating CAPTCHA for board creation by owner '{session['username']}': {e}", exc_info=True)
        return render_template('errors/500.html', error_message="Could not load board creation page."), 500

# rules route page
@boards_bp.route('/pages/globalrules.html')
def global_rules():
    # This typically just renders a static template
    try:
        return render_template('pages/globalrules.html')
    except Exception as e:
         logger.error(f"Error rendering global rules page: {e}", exc_info=True)
         # Fallback or render error page
         return "Could not load rules page.", 500


# board page endpoint
@boards_bp.route('/<board_uri>/')
def board_page(board_uri):
    """Отображает страницу конкретной доски с постами и пагинацией."""
    try:
        # 1. Получаем информацию о доске
        board_info_raw = database_module.get_board_info(board_uri)
        if not board_info_raw:
            logger.warning(f"Board not found request: /{board_uri}/")
            return render_template('errors/404.html', message=f"The board '/{board_uri}/' does not exist."), 404
        board_info = dict(board_info_raw) # Преобразуем в словарь для шаблона

        # 2. Обработка пагинации
        try:
            page = int(request.args.get('page', '1'))
            if page < 1: page = 1
        except ValueError:
            page = 1
        posts_per_page = 6 # Количество постов на странице (можно вынести в конфиг)
        offset = (page - 1) * posts_per_page

        # 3. Вычисление общего количества страниц для пагинации
        # Используем функцию, считающую НЕзакрепленные посты
        total_non_pinned_posts = database_module.get_board_thread_count(board_uri, include_pinned=False)
        if total_non_pinned_posts > 0 and posts_per_page > 0:
            total_pages = (total_non_pinned_posts + posts_per_page - 1) // posts_per_page
        else:
            total_pages = 1 # Как минимум одна страница

        # 4. Получение данных из БД
        # Получаем порцию НЕзакрепленных постов для текущей страницы
        posts_raw = database_module.get_posts_for_board(board_uri, offset=offset, limit=posts_per_page)
        # Получаем ВСЕ закрепленные посты для этой доски
        pinneds_raw = database_module.get_pinned_posts(board_uri)
        # Получаем случайный баннер
        board_banner = database_module.get_board_banner(board_uri)

        # 5. Получение ответов для видимых постов
        visible_post_ids = [p['post_id'] for p in posts_raw] + [p['post_id'] for p in pinneds_raw]
        replies_raw = []
        if visible_post_ids:
            try:
                replies_raw = database_module.get_replies_for_posts(visible_post_ids)
            except Exception as db_err:
                 logger.error(f"Error fetching replies for board /{board_uri}/ posts {visible_post_ids}: {db_err}", exc_info=True)
                 # Решаем, как обрабатывать: можно показать страницу без ответов или с ошибкой
                 flash("Could not load replies for some posts.", "warning")

        # 6. Форматирование данных для шаблона
        posts = format_content_for_template(posts_raw)
        pinneds = format_content_for_template(pinneds_raw)
        replies = format_content_for_template(replies_raw)

        # 7. Получение информации о пользователе и генерация CAPTCHA
        roles = 'none'
        if 'username' in session:
            roles = database_module.get_user_role(session["username"]) or 'none'

        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        # 8. Рендеринг шаблона со всеми данными
        return render_template(
            'board.html',
            board_info=board_info,         # Информация о доске (словарь)
            captcha_image=captcha_image,   # Изображение CAPTCHA (base64)
            roles=roles,                   # Роль пользователя
            page=page,                     # Номер текущей страницы
            posts_per_page=posts_per_page, # Количество постов на странице
            total_pages=total_pages,       # Общее количество страниц для пагинации
            pinneds=pinneds,               # Список закрепленных постов (форматированный)
            posts=posts,                   # Список постов для текущей страницы (форматированный)
            replies=replies,               # Список ответов для видимых постов (форматированный)
            board_banner=board_banner,     # URL баннера
            board_id=board_uri,            # URI доски (передаем как board_id для совместимости)
        )
    except Exception as e:
        # Логирование общей ошибки при загрузке страницы
        logger.error(f"Error loading board page /{board_uri}/ (page {request.args.get('page', '1')}): {e}", exc_info=True)
        # Отображение страницы с ошибкой 500
        return render_template('errors/500.html', error_message=f"Could not load board /{board_uri}/."), 500


# board page endpoint for catalog view
@boards_bp.route('/<board_uri>/catalog')
def board_catalog(board_uri):
    try:
        # 1. Проверка существования доски и получение информации о ней
        board_info_raw = database_module.get_board_info(board_uri)
        if not board_info_raw:
            logger.warning(f"Board not found for catalog request: /{board_uri}/")
            flash(f"Board '/{board_uri}/' does not exist.", "error")
            return redirect(url_for('boards.main_page'))
        
        board_info = dict(board_info_raw) # Преобразуем Row в dict

        # 2. Загрузка постов (не закрепленных) для каталога
        # Для каталога обычно нужен большой лимит или все посты
        # Установим очень большой лимит, чтобы имитировать "все посты" для каталога
        # В реальном приложении здесь могла бы быть отдельная функция "get_all_posts_for_catalog"
        catalog_posts_limit = 200 # Пример: показать до 200 постов в каталоге
        posts_raw = database_module.get_posts_for_board(board_uri, offset=0, limit=catalog_posts_limit)
        
        # 3. Закрепленные посты
        pinneds_raw = database_module.get_pinned_posts(board_uri)
        
        # 4. Получение баннера (работает с файловой системой)
        board_banner = database_module.get_board_banner(board_uri)
        
        # 5. Генерация CAPTCHA
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text
        
        # 6. Получение ответов для видимых постов (и закрепленных, и обычных)
        # В каталоге обычно показывают только ОП или ОП с небольшим количеством последних ответов.
        # Текущая логика загружает ВСЕ ответы для ВСЕХ постов на странице, что может быть избыточно для каталога.
        # Для каталога, возможно, ответы не нужны или нужны только для предпросмотра.
        # Если ответы нужны:
        visible_post_ids = [p['post_id'] for p in posts_raw] + [p['post_id'] for p in pinneds_raw]
        replies_raw = []
        if visible_post_ids:
            try:
                replies_raw = database_module.get_replies_for_posts(visible_post_ids)
                # Для каталога можно ограничить количество ответов на пост, если нужно
                # Например, взять только 3 последних ответа для каждого поста
                # Это потребует дополнительной логики или изменения get_replies_for_posts
            except Exception as db_err:
                 logger.error(f"Error fetching replies for board catalog /{board_uri}/: {db_err}", exc_info=True)
        
        # 7. Роли пользователя
        roles = 'none'
        if 'username' in session:
            roles = database_module.get_user_role(session["username"]) or 'none'

        # 8. Форматирование данных для шаблона
        # Используем ту же вспомогательную функцию format_content_for_template
        posts_formatted = format_content_for_template(posts_raw)
        pinneds_formatted = format_content_for_template(pinneds_raw)
        replies_formatted = format_content_for_template(replies_raw) # Форматируем ответы, если они загружены

        return render_template(
            'catalog.html', # Убедитесь, что шаблон называется catalog.html
            board_info=board_info,
            captcha_image=captcha_image, # Для формы постинга из каталога?
            roles=roles,
            pinneds=pinneds_formatted,
            posts=posts_formatted,
            replies=replies_formatted, # Передаем отформатированные ответы
            board_banner=board_banner,
            board_id=board_uri # Используем board_uri, но передаем как board_id для совместимости с шаблоном
        )

    except Exception as e:
        logger.error(f"Error loading board catalog for /{board_uri}/: {e}", exc_info=True)
        # Можно отрендерить страницу с ошибкой или перенаправить
        flash("An error occurred while loading the board catalog.", "error")
        return render_template('errors/500.html', error_message=f"Could not load catalog for board /{board_uri}/."), 500




# board banners page route.
@boards_bp.route('/<board_uri>/banners')
def board_banners(board_uri):
    try:
        board_info_raw = database_module.get_board_info(board_uri)
        if not board_info_raw:
            logger.warning(f"Board not found for banners request: /{board_uri}/")
            flash(f"Board '/{board_uri}/' not found.", "error")
            return redirect(url_for('boards.main_page'))

        board_info = dict(board_info_raw) # Convert Row to dict

        # Filesystem access functions remain the same
        board_banner = database_module.get_board_banner(board_uri)
        banners = database_module.get_all_banners(board_uri) # Returns list of URL paths

        username = session.get('username', 'anon') # Get username if logged in

        return render_template('board_banners.html',
                               username=username,
                               board_banner=board_banner, # Current random banner
                               banners=banners or [],     # List of all banner paths
                               board_id=board_uri,        # Keep name board_id
                               board_info=board_info)     # Pass board details

    except Exception as e:
        logger.error(f"Error loading banners page for /{board_uri}/: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load banners for board /{board_uri}/."), 500


# thread page route.
@boards_bp.route('/<board_name>/thread/<thread_id>')
def replies(board_name, thread_id):
    try:
        # Validate thread_id is an integer
        try:
            thread_id_int = int(thread_id)
        except ValueError:
            logger.warning(f"Invalid thread ID format: {thread_id} on board /{board_name}/")
            return render_template('errors/404.html', message=f"Invalid thread ID '{thread_id}'."), 404

        # Get board info first
        board_info_raw = database_module.get_board_info(board_name)
        if not board_info_raw:
            logger.warning(f"Board /{board_name}/ not found when accessing thread {thread_id_int}.")
            return render_template('errors/404.html', message=f"Board '/{board_name}/' does not exist."), 404
        board_info = dict(board_info_raw)

        # Fetch thread OP and its replies using the dedicated function
        thread_op_raw, post_replies_raw = database_module.get_post_and_replies(thread_id_int)

        # Check if thread exists
        if not thread_op_raw:
            logger.warning(f"Thread ID {thread_id_int} not found when accessed via /{board_name}/.")
            return render_template('errors/404.html', message=f"Thread {thread_id_int} not found."), 404

        # IMPORTANT: Verify the found thread belongs to the requested board
        if thread_op_raw['board_uri'] != board_name:
            logger.warning(f"Thread ID {thread_id_int} found, but belongs to board '{thread_op_raw['board_uri']}', not requested board '{board_name}'.")
            # Treat as not found on *this* board
            return render_template('errors/404.html', message=f"Thread {thread_id_int} not found on board '/{board_name}/'."), 404

        # Generate CAPTCHA
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        # Get user roles
        roles = 'none'
        if 'username' in session:
            roles = database_module.get_user_role(session["username"]) or 'none'

        # Format OP and replies for template
        formatted_op = format_content_for_template([thread_op_raw])[0] # Format the single OP
        formatted_replies = format_content_for_template(post_replies_raw)

        return render_template(
            'thread_reply.html', # Verify template name
            captcha_image=captcha_image,
            board_info=board_info,
            posts=[formatted_op], # Pass OP in a list as template likely expects iteration
            replies=formatted_replies,
            board_id=board_name, # Pass board URI
            thread_id=thread_id_int,
            post_mode="reply", # Seems constant for this view
            roles=roles
        )
    except Exception as e:
        logger.error(f"Error loading thread page /{board_name}/thread/{thread_id}: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load thread {thread_id} on board /{board_name}/."), 500

# --- END OF FILE boards_bp.py ---