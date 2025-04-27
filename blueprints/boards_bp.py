# imports
from flask import current_app, Blueprint, render_template, session, redirect, request, url_for
from database_modules import database_module
from database_modules import language_module
import logging # Добавим импорт для логирования

# Настроим логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# blueprint register.
boards_bp = Blueprint('boards', __name__)

# load language.
@boards_bp.context_processor
def inject_lang():
    user_lang_code = session.get('user_language', 'default')
    lang = language_module.get_user_lang(user_lang_code)
    return dict(lang=lang)

# load nav boards
@boards_bp.context_processor
def globalboards():
    try:
        # Получаем все доски со статой из database_module
        boards = database_module.get_all_boards(include_stats=True)
        return {"boards": boards}
    except Exception as e:
        logger.error(f"Error loading global boards: {e}", exc_info=True)
        return {"boards": []}

# load custom themes
@boards_bp.context_processor
def customthemes():
    try:
        custom_themes_list = database_module.get_custom_themes()
        return {"custom_themes": custom_themes_list}
    except Exception as e:
        logger.error(f"Error loading custom themes: {e}", exc_info=True)
        return {"custom_themes": []}

# Контекстный процессор для подсчета ответов
@boards_bp.context_processor
def inject_reply_counts():
    try:
        all_posts = database_module.get_all_posts()
        all_replies = database_module.DB.find_all('replies')

        post_to_board_map = {}
        if all_posts:
             post_to_board_map = {
                post['post_id']: post.get('board')
                for post in all_posts if isinstance(post, dict) and 'post_id' in post and 'board' in post
            }

        reply_counts = {}
        if all_replies:
            for reply in all_replies:
                 if isinstance(reply, dict):
                    post_id = reply.get('post_id')
                    if post_id:
                        board_uri = post_to_board_map.get(post_id)
                        if board_uri:
                            reply_counts[board_uri] = reply_counts.get(board_uri, 0) + 1

        return {"reply_counts": reply_counts}
    except Exception as e:
        logger.error(f"Failed to calculate reply counts: {e}", exc_info=True)
        return {"reply_counts": {}}

# error handling.
@boards_bp.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 Not Found: {request.path}")
    try:
        return render_template('errors/404.html'), 404
    except Exception:
        return "404 Not Found", 404


# landing page route.
@boards_bp.route('/')
def main_page():
    try:
        all_posts = database_module.get_all_posts()
        recent_posts_count = 6
        recent_posts = []
        if all_posts and isinstance(all_posts, list):
             # Предполагая, что get_all_posts возвращает список, отсортированный по дате (старые -> новые)
             recent_posts = list(reversed(all_posts[-recent_posts_count:]))

        return render_template('index.html', all_posts=all_posts or [], posts=recent_posts)
    except Exception as e:
        logger.error(f"Error on main page: {e}", exc_info=True)
        try:
            return render_template('errors/500.html', error_message="Could not load main page content."), 500
        except Exception:
             return "Internal Server Error", 500

# boards page route.
@boards_bp.route('/tabuas')
def tabuas():
    try:
        all_posts = database_module.get_all_posts()
        return render_template('tabuas.html', all_posts=all_posts or [])
    except Exception as e:
        logger.error(f"Error on tabuas page: {e}", exc_info=True)
        try:
            return render_template('errors/500.html', error_message="Could not load boards list."), 500
        except Exception:
             return "Internal Server Error", 500

# account dashboard and login route.
# ---- ИЗМЕНЕННАЯ ФУНКЦИЯ (включает все исправления для dashboard.html) ----
@boards_bp.route('/conta')
def login():
    if 'username' in session:
        try:
            username = session["username"]
            user_boards = database_module.get_user_boards(username)
            roles = database_module.get_user_role(username)

            # --- Получаем все посты ОДИН раз (предполагая сортировку по дате) ---
            all_posts_list = database_module.get_all_posts(sort_by_date=True) # Важно: sort_by_date=True

            # --- Расчет общего количества постов ---
            total_posts_count = len(all_posts_list) if isinstance(all_posts_list, list) else 0

            # --- Получаем последние 10 постов для дашборда ---
            recent_dashboard_posts = []
            if all_posts_list:
                 recent_dashboard_posts = all_posts_list[:10] # Берем первые 10 (новейшие)

            # --- Добавляем информацию о владельце доски к недавним постам (с кэшированием) ---
            board_owners_cache = {} # Кэш: {board_uri: owner_username}
            if recent_dashboard_posts:
                for post in recent_dashboard_posts:
                    if isinstance(post, dict):
                        board_uri = post.get('board')
                        if board_uri:
                            if board_uri not in board_owners_cache:
                                board_info = database_module.get_board_info(board_uri)
                                board_owners_cache[board_uri] = board_info.get('board_owner') if board_info and isinstance(board_info, dict) else None
                            post['board_owner_info'] = board_owners_cache.get(board_uri) # Добавляем в словарь поста
                        else:
                            post['board_owner_info'] = None
                    # else: обработка не-словарей, если нужно

            # --- Передаем данные в шаблон ---
            # Контекстные процессоры предоставят 'boards' (все доски) и 'reply_counts'
            return render_template('dashboard.html',
                                   username=username,
                                   roles=roles,
                                   user_boards=user_boards or [],
                                   total_posts_count=total_posts_count,
                                   recent_dashboard_posts=recent_dashboard_posts # Посты теперь с 'board_owner_info'
                                  )

        except Exception as e:
            logger.error(f"Error loading dashboard for {session.get('username')}: {e}", exc_info=True)
            try:
                 return render_template('errors/500.html', error_message="Could not load dashboard."), 500
            except Exception:
                 return "Internal Server Error", 500
    else:
        return render_template('login.html')
# ---- КОНЕЦ ИЗМЕНЕННОЙ ФУНКЦИИ ----

# register page route.
@boards_bp.route('/registrar')
def register():
    if 'username' in session:
        return redirect(url_for('boards.login'))
    try:
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text
        return render_template('register.html', captcha_image=captcha_image)
    except Exception as e:
        logger.error(f"Error generating CAPTCHA for registration: {e}", exc_info=True)
        try:
            return render_template('errors/500.html', error_message="Could not load registration page."), 500
        except Exception:
             return "Internal Server Error", 500

# board creation page route.
@boards_bp.route('/create')
def create():
    if 'username' in session:
        try:
            captcha_text, captcha_image = database_module.generate_captcha()
            session['captcha_text'] = captcha_text
            return render_template('board-create.html', captcha_image=captcha_image)
        except Exception as e:
            logger.error(f"Error generating CAPTCHA for board creation: {e}", exc_info=True)
            try:
                 return render_template('errors/500.html', error_message="Could not load board creation page."), 500
            except Exception:
                 return "Internal Server Error", 500
    else:
        return redirect(url_for('boards.login'))

# rules route page
@boards_bp.route('/pages/globalrules.html')
def global_rules():
    return render_template('pages/globalrules.html')

# board page endpoint
@boards_bp.route('/<board_uri>/')
def board_page(board_uri):
    try:
        board_info = database_module.get_board_info(board_uri)
        if not board_info:
            logger.warning(f"Board not found: /{board_uri}/")
            return redirect(url_for('boards.main_page'))

        try:
            page = int(request.args.get('page', '1'))
            if page < 1: page = 1
        except ValueError:
            page = 1

        posts_per_page = 6
        offset = (page - 1) * posts_per_page

        posts = database_module.load_db_page(board_uri, offset=offset, limit=posts_per_page)
        pinneds = database_module.get_pinned_posts(board_uri)
        board_banner = database_module.get_board_banner(board_uri)

        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        visible_post_ids = []
        if posts:
             visible_post_ids = [post['post_id'] for post in posts if isinstance(post, dict) and 'post_id' in post]

        replies = []
        if visible_post_ids:
            try:
                all_replies = database_module.DB.find_all('replies')
                if all_replies:
                     replies = [reply for reply in all_replies if isinstance(reply, dict) and reply.get('post_id') in visible_post_ids]
            except Exception as db_err:
                 logger.error(f"Error fetching replies for board /{board_uri}/: {db_err}", exc_info=True)

        roles = 'none'
        if 'username' in session:
            roles = database_module.get_user_role(session["username"])

        return render_template(
            'board.html',
            board_info=board_info,
            captcha_image=captcha_image,
            roles=roles,
            page=page,
            posts_per_page=posts_per_page,
            pinneds=pinneds or [],
            posts=posts or [],
            replies=replies,
            board_banner=board_banner,
            board_id=board_uri,
        )
    except Exception as e:
        logger.error(f"Error loading board page /{board_uri}/: {e}", exc_info=True)
        try:
             return render_template('errors/500.html', error_message=f"Could not load board /{board_uri}/."), 500
        except Exception:
             return "Internal Server Error", 500

# board banners page route.
@boards_bp.route('/<board_uri>/banners')
def board_banners(board_uri):
    try:
        board_info = database_module.get_board_info(board_uri)
        if not board_info:
            logger.warning(f"Board not found for banners: /{board_uri}/")
            return redirect(url_for('boards.main_page'))

        username = session.get('username', 'anon')
        board_banner = database_module.get_board_banner(board_uri)
        banners = database_module.get_all_banners(board_uri)
        return render_template('board_banners.html',
                               username=username,
                               board_banner=board_banner,
                               banners=banners or [],
                               board_id=board_uri,
                               board_info=board_info)
    except Exception as e:
        logger.error(f"Error loading banners page for /{board_uri}/: {e}", exc_info=True)
        try:
             return render_template('errors/500.html', error_message=f"Could not load banners for board /{board_uri}/."), 500
        except Exception:
             return "Internal Server Error", 500

# thread page route.
@boards_bp.route('/<board_name>/thread/<thread_id>')
def replies(board_name, thread_id):
    try:
        board_info = database_module.get_board_info(board_name)
        if not board_info:
            logger.warning(f"Board not found for thread: /{board_name}/")
            return redirect(url_for('boards.main_page'))

        try:
            thread_id_int = int(thread_id)
        except ValueError:
            logger.warning(f"Invalid thread ID format: {thread_id} on board /{board_name}/")
            return redirect(url_for('boards.board_page', board_uri=board_name))

        threads_list = database_module.DB.query('posts', {
            'post_id': {'==': thread_id_int},
            'board': {'==': board_name}
        })

        if not threads_list:
            logger.warning(f"Thread not found: ID {thread_id_int} on board /{board_name}/")
            return redirect(url_for('boards.board_page', board_uri=board_name))

        post_replies = []
        try:
            all_replies = database_module.DB.query('replies', {'post_id': {'==': thread_id_int}})
            if all_replies:
                 post_replies = [reply for reply in all_replies if isinstance(reply, dict)]

        except Exception as db_err:
             logger.error(f"DB query failed for replies by post_id {thread_id_int}. Error: {db_err}", exc_info=True)
             try:
                 all_replies_fallback = database_module.DB.find_all('replies')
                 if all_replies_fallback:
                     post_replies = [reply for reply in all_replies_fallback if isinstance(reply, dict) and reply.get('post_id') == thread_id_int]
             except Exception as fallback_err:
                 logger.error(f"Fallback find_all for replies also failed: {fallback_err}", exc_info=True)
                 post_replies = []

        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        roles = 'none'
        if 'username' in session:
            roles = database_module.get_user_role(session["username"])

        return render_template(
            'thread_reply.html',
            captcha_image=captcha_image,
            board_info=board_info,
            posts=threads_list,
            replies=post_replies,
            board_id=board_name,
            thread_id=thread_id_int,
            post_mode="reply",
            roles=roles
        )
    except Exception as e:
        logger.error(f"Error loading thread page /{board_name}/thread/{thread_id}: {e}", exc_info=True)
        try:
            return render_template('errors/500.html', error_message=f"Could not load thread {thread_id} on board /{board_name}/."), 500
        except Exception:
            return "Internal Server Error", 500