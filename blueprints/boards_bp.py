# --- START OF FILE boards_bp.py ---

# imports
from flask import current_app, Blueprint, render_template, session, redirect, request, url_for, flash
from database_modules import database_module
from database_modules import language_module
from database_modules import moderation_module
from database_modules import formatting # <--- Прямой импорт formatting
import logging
import json
import re # Для Regex
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

# blueprint register.
boards_bp = Blueprint('boards', __name__, template_folder='../templates', static_folder='../static')

# load language.
@boards_bp.context_processor
def inject_lang():
    user_lang_code = session.get('user_language', 'default')
    lang_data = language_module.get_user_lang(user_lang_code)
    return dict(lang=lang_data if lang_data else {})

# load nav boards (with stats)
@boards_bp.context_processor
def globalboards():
    try:
        boards_list = database_module.get_all_boards(include_stats=True)
        return {"boards": boards_list or []}
    except Exception as e:
        logger.error(f"Error loading global boards: {e}", exc_info=True)
        return {"boards": []}

# load custom themes
@boards_bp.context_processor
def customthemes():
    try:
        custom_themes_list = database_module.get_custom_themes()
        return {"custom_themes": custom_themes_list or []}
    except Exception as e:
        logger.error(f"Error loading custom themes: {e}", exc_info=True)
        return {"custom_themes": []}

# Context processor for reply counts
@boards_bp.context_processor
def inject_reply_counts():
    reply_counts = {}
    try:
        sql = """
            SELECT p.board_uri, COUNT(r.id) as reply_count
            FROM replies r
            JOIN posts p ON r.post_id = p.post_id
            GROUP BY p.board_uri
        """
        results = database_module.execute_query(sql)
        if results:
            reply_counts = {row['board_uri']: row['reply_count'] for row in results}
        return {"reply_counts": reply_counts}
    except Exception as e:
        logger.error(f"Failed to calculate reply counts: {e}", exc_info=True)
        return {"reply_counts": {}}

# error handling.
@boards_bp.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 Not Found error handled for path: {request.path}. Error: {e}")
    try:
        return render_template('errors/404.html', error=e, message="Page not found."), 404
    except Exception as render_err:
        logger.error(f"Error rendering 404 template: {render_err}", exc_info=True)
        return "404 Not Found", 404

@boards_bp.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 Internal Server Error handled for path: {request.path}. Error: {e}", exc_info=True)
    try:
        error_message = "An internal server error occurred."
        return render_template('errors/500.html', error=e, error_message=error_message), 500
    except Exception as render_err:
         logger.error(f"Error rendering 500 template: {render_err}", exc_info=True)
         return "Internal Server Error", 500

# --- НОВАЯ функция форматирования, которая НЕ вызывает formatting.format_comment ---
# --- так как HTML уже приходит из БД. Она только добавляет списки файлов, даты и backlinks ---
def format_content_for_template_pass_through_html(content_list, backlinks_map=None):
    """
    Deserializes files, formats dates, and adds backlink info.
    Assumes content (post_content/content) from DB is already HTML formatted.
    """
    formatted_list = []
    if not content_list: return []

    # print(f"[DEBUG_BOARDS_BP format_content_pass_through] Processing {len(content_list)} items. Backlinks_map provided: {backlinks_map is not None}")
    for item_row in content_list:
        item_dict = dict(item_row)
        # item_id_for_debug = item_dict.get('post_id') or item_dict.get('reply_id') # Для отладки

        image_key = 'post_images' if 'post_images' in item_dict else 'images'
        thumb_key = 'imagesthb'
        date_key = 'post_date'

        item_dict[f'{image_key}_list'] = database_module._deserialize_files(item_dict.get(image_key))
        item_dict[f'{thumb_key}_list'] = database_module._deserialize_files(item_dict.get(thumb_key))

        dt_obj = database_module.parse_datetime(item_dict.get(date_key))
        item_dict['date_display'] = database_module.format_datetime_for_display(dt_obj)

        # HTML контент (post_content для OP, content для ответов) уже должен быть в item_dict из БД
        # и он уже отформатирован. Ничего дополнительно с ним делать не нужно.

        if backlinks_map:
            item_id_for_backlink_lookup = None
            is_op_post = 'original_content' in item_dict # Признак OP (или post_id есть, а reply_id нет)
            if is_op_post:
                 item_id_for_backlink_lookup = item_dict.get('post_id')
            else: # Это ответ
                 item_id_for_backlink_lookup = item_dict.get('reply_id')
            
            if item_id_for_backlink_lookup is not None:
                item_dict['answered_by'] = backlinks_map.get(item_id_for_backlink_lookup, [])
                # if item_dict['answered_by']: # Отладочный print
                #      print(f"[DEBUG_BOARDS_BP format_content_pass_through] Item ID {item_id_for_debug} (lookup ID {item_id_for_backlink_lookup}) has answered_by: {item_dict['answered_by']}")
            else:
                item_dict['answered_by'] = []
        else:
            item_dict['answered_by'] = []
        
        formatted_list.append(item_dict)
    return formatted_list
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ФОРМАТИРОВАНИЯ ---


# --- Вспомогательная функция для подготовки контента с backlinks ---
def _prepare_page_content(posts_raw, pinneds_raw, replies_raw):
    # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Entered. Posts: {len(posts_raw)}, Pinneds: {len(pinneds_raw)}, Replies: {len(replies_raw)}")
    backlinks = {}
    
    all_items_for_backlinks_raw = []
    if posts_raw: all_items_for_backlinks_raw.extend(posts_raw)
    if pinneds_raw: all_items_for_backlinks_raw.extend(pinneds_raw)
    if replies_raw: all_items_for_backlinks_raw.extend(replies_raw)
    # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Total items for backlink scan: {len(all_items_for_backlinks_raw)}")

    for item_row in all_items_for_backlinks_raw:
        item = dict(item_row)
        
        is_op_post = 'original_content' in item
        current_item_id = item.get('post_id') if is_op_post else item.get('reply_id')
        
        # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Processing item: keys={list(item.keys())}, IsOPPost: {is_op_post}, CurrentItemID: {current_item_id}")

        if not current_item_id:
            # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Item skipped, no valid ID found")
            continue

        # --- ПОЛУЧАЕМ ТЕКСТ ДЛЯ ПАРСИНГА ---
        # Для OP-постов: если есть 'post_content' (HTML), используем его. Иначе 'original_content' (сырой).
        # Для Ответов: используем 'content' (который уже HTML).
        text_to_scan_for_refs = ""
        use_html_parser = False # Флаг, какой regex использовать

        if is_op_post:
            if item.get('post_content'): # Предполагаем, что это HTML
                text_to_scan_for_refs = item.get('post_content', '')
                use_html_parser = True
                # print(f"[DEBUG_BOARDS_BP _prepare_page_content] OP Post {current_item_id} using 'post_content' (HTML) for ref scan.")
            else: 
                text_to_scan_for_refs = item.get('original_content', '')
                # print(f"[DEBUG_BOARDS_BP _prepare_page_content] OP Post {current_item_id} using 'original_content' (RAW) for ref scan.")
        else: # Это ответ
            text_to_scan_for_refs = item.get('content', '') # Это уже HTML
            use_html_parser = True
            # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Reply {current_item_id} using 'content' (HTML) for ref scan.")
        
        # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Scanning item ID {current_item_id}. Text for refs: '{str(text_to_scan_for_refs)[:150]}...' UseHTMLParser: {use_html_parser}")

        if not text_to_scan_for_refs:
            # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Item ID {current_item_id} has no suitable text for refs.")
            continue
            
        quoted_ids_matches = []
        if use_html_parser:
            # Ищем data-id в HTML
            quoted_ids_matches = re.findall(r'data-id="(\d+)"', text_to_scan_for_refs)
        else:
            # Ищем >>ID в сыром тексте (для original_content у OP-постов, если post_content нет)
            quoted_ids_matches = re.findall(r'>>(\d+)', text_to_scan_for_refs)
        
        if quoted_ids_matches:
            # print(f"[DEBUG_BOARDS_BP _prepare_page_content] For item ID {current_item_id}, found quote ID strings: {quoted_ids_matches}")
            
            for quoted_id_str in quoted_ids_matches:
                try:
                    quoted_id = int(quoted_id_str)
                    if quoted_id not in backlinks:
                        backlinks[quoted_id] = []
                    if current_item_id not in backlinks[quoted_id]:
                        backlinks[quoted_id].append(current_item_id)
                        # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Added backlink: item {current_item_id} replies to item {quoted_id}")
                except ValueError:
                    # print(f"[DEBUG_BOARDS_BP _prepare_page_content] ValueError: Could not convert quote ID '{quoted_id_str}' to int for item {current_item_id}")
                    continue
        # else:
            # print(f"[DEBUG_BOARDS_BP _prepare_page_content] No quote matches found for item ID {current_item_id}.")
            
    # print(f"[DEBUG_BOARDS_BP _prepare_page_content] Final backlinks map: {backlinks}")
    
    # Используем новую функцию форматирования, которая НЕ вызывает formatting.format_comment
    formatted_posts = format_content_for_template_pass_through_html(posts_raw, backlinks)
    formatted_pinneds = format_content_for_template_pass_through_html(pinneds_raw, backlinks)
    formatted_replies = format_content_for_template_pass_through_html(replies_raw, backlinks)
            
    return formatted_posts, formatted_pinneds, formatted_replies
# --- КОНЕЦ ФУНКЦИИ _prepare_page_content ---

# --- Routes ---
@boards_bp.route('/')
def main_page():
    try:
        recent_posts_count = 6
        all_ops_raw = database_module.get_all_posts_simple(sort_by_date=True)
        recent_ops_raw = all_ops_raw[:recent_posts_count] if all_ops_raw else []
        # Для главной страницы backlinks не нужны, и HTML уже должен быть в post_content
        recent_posts = format_content_for_template_pass_through_html(recent_ops_raw, None)
        return render_template('index.html', posts=recent_posts)
    except Exception as e:
        logger.error(f"Error on main page: {e}", exc_info=True)
        return render_template('errors/500.html', error_message="Could not load main page content."), 500

@boards_bp.route('/tabuas')
def tabuas():
    try:
        return render_template('tabuas.html')
    except Exception as e:
        logger.error(f"Error on tabuas page: {e}", exc_info=True)
        return render_template('errors/500.html', error_message="Could not load boards list."), 500

@boards_bp.route('/conta')
def login():
    if 'username' in session:
        try:
            username = session["username"]
            user_info_row = database_module.get_user_by_username(username)
            if not user_info_row:
                 session.pop('username', None); session.pop('role', None)
                 flash("Your account could not be found. Please log in again.", "warning")
                 return redirect(url_for('boards.login'))
            user_info = dict(user_info_row)
            roles = user_info.get('role', '')

            user_boards_raw = database_module.get_user_boards(username)
            user_boards = [dict(board) for board in user_boards_raw] if user_boards_raw else []

            all_posts_list_raw = database_module.get_all_posts_simple(sort_by_date=True)
            total_posts_count = len(all_posts_list_raw) if all_posts_list_raw else 0
            recent_dashboard_posts_raw = all_posts_list_raw[:10]
            
            # Для дашборда backlinks не нужны, HTML уже должен быть в post_content
            recent_dashboard_posts_formatted = format_content_for_template_pass_through_html(recent_dashboard_posts_raw, None)
            
            recent_dashboard_posts_final = []
            board_owners_cache = {}
            for post_dict in recent_dashboard_posts_formatted:
                board_uri = post_dict.get('board_uri')
                if board_uri:
                    if board_uri not in board_owners_cache:
                        board_info_owner_row = database_module.get_board_info(board_uri)
                        board_owners_cache[board_uri] = board_info_owner_row['board_owner'] if board_info_owner_row else None
                    post_dict['board_owner_info'] = board_owners_cache.get(board_uri)
                else: post_dict['board_owner_info'] = None
                recent_dashboard_posts_final.append(post_dict)

            active_bans = []
            manageable_users = []
            if roles and ('owner' in roles.lower() or 'mod' in roles.lower()):
                ban_manager = moderation_module.BanManager()
                active_bans = ban_manager.get_active_bans()
                if 'owner' in roles.lower():
                    manageable_users = database_module.get_all_users_with_roles(exclude_username=username)

            return render_template('dashboard.html',
                                   username=username, roles=roles, user_boards=user_boards,
                                   total_posts_count=total_posts_count,
                                   recent_dashboard_posts=recent_dashboard_posts_final,
                                   active_bans=active_bans, manageable_users=manageable_users,
                                   all_boards=globalboards().get("boards", []))
        except Exception as e:
            logger.error(f"Error loading dashboard for {session.get('username')}: {e}", exc_info=True)
            return render_template('errors/500.html', error_message="Could not load dashboard."), 500
    else:
        return render_template('login.html')

@boards_bp.route('/registrar')
def register():
    if 'username' in session: return redirect(url_for('boards.login'))
    try:
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text
        return render_template('register.html', captcha_image=captcha_image)
    except Exception as e: logger.error(f"Error generating CAPTCHA for registration: {e}", exc_info=True); return render_template('errors/500.html', error_message="Could not load registration page."), 500

@boards_bp.route('/create')
def create():
    if 'username' not in session: flash("You must be logged in to create a board.", "warning"); return redirect(url_for('boards.login'))
    user_role = database_module.get_user_role(session["username"])
    if not user_role or 'owner' not in user_role.lower(): flash("Only the site owner can create new boards.", "error"); return redirect(url_for('boards.login'))
    try:
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text
        return render_template('board-create.html', captcha_image=captcha_image)
    except Exception as e: logger.error(f"Error generating CAPTCHA for board creation: {e}", exc_info=True); return render_template('errors/500.html', error_message="Could not load board creation page."), 500

@boards_bp.route('/pages/globalrules.html')
def global_rules():
    try: return render_template('pages/globalrules.html')
    except Exception as e: logger.error(f"Error rendering global rules page: {e}", exc_info=True); return "Could not load rules page.", 500

@boards_bp.route('/<board_uri>/')
def board_page(board_uri):
    # print(f"[DEBUG_BOARDS_BP board_page] Loading board: /{board_uri}/, Page: {request.args.get('page', 1)}")
    try:
        board_info_row = database_module.get_board_info(board_uri)
        if not board_info_row: return render_template('errors/404.html', message=f"The board '/{board_uri}/' does not exist."), 404
        board_info = dict(board_info_row)

        page = request.args.get('page', 1, type=int)
        if page < 1: page = 1
        posts_per_page = 6
        offset = (page - 1) * posts_per_page

        total_non_pinned_posts = database_module.get_board_thread_count(board_uri, include_pinned=False)
        total_pages = max(1, (total_non_pinned_posts + posts_per_page - 1) // posts_per_page if posts_per_page > 0 else 1)
        if page > total_pages : page = total_pages; offset = (page - 1) * posts_per_page

        posts_raw = database_module.get_posts_for_board(board_uri, offset=offset, limit=posts_per_page)
        pinneds_raw = database_module.get_pinned_posts(board_uri)
        board_banner = database_module.get_board_banner(board_uri)

        all_visible_op_ids = [p['post_id'] for p in posts_raw] + [p['post_id'] for p in pinneds_raw]
        replies_for_ops_raw = database_module.get_replies_for_posts(all_visible_op_ids) if all_visible_op_ids else []
        
        formatted_posts, formatted_pinneds, formatted_replies_for_template = _prepare_page_content(
            posts_raw, pinneds_raw, replies_for_ops_raw
        )

        roles = session.get('role', 'none')
        if roles == 'none' and 'username' in session: roles = database_module.get_user_role(session["username"]) or 'none'
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        return render_template(
            'board.html', board_info=board_info, captcha_image=captcha_image, roles=roles, page=page,
            posts_per_page=posts_per_page, total_pages=total_pages,
            pinneds=formatted_pinneds, posts=formatted_posts, replies=formatted_replies_for_template,
            board_banner=board_banner, board_id=board_uri,
        )
    except Exception as e:
        logger.error(f"Error loading board page /{board_uri}/ (page {request.args.get('page', '1')}): {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load board /{board_uri}/."), 500

@boards_bp.route('/<board_uri>/catalog')
def board_catalog(board_uri):
    # print(f"[DEBUG_BOARDS_BP board_catalog] Loading catalog for board: /{board_uri}/")
    try:
        board_info_row = database_module.get_board_info(board_uri)
        if not board_info_row: return render_template('errors/404.html', message=f"Board '/{board_uri}/' not found."), 404
        board_info = dict(board_info_row)

        catalog_posts_limit = 200
        posts_raw = database_module.get_posts_for_board(board_uri, offset=0, limit=catalog_posts_limit)
        pinneds_raw = database_module.get_pinned_posts(board_uri)
        board_banner = database_module.get_board_banner(board_uri)
        
        all_catalog_op_ids = [p['post_id'] for p in posts_raw] + [p['post_id'] for p in pinneds_raw]
        replies_for_catalog_ops_raw = database_module.get_replies_for_posts(all_catalog_op_ids) if all_catalog_op_ids else []
        
        formatted_posts, formatted_pinneds, formatted_replies_for_catalog = _prepare_page_content(
            posts_raw, pinneds_raw, replies_for_catalog_ops_raw
        )
        
        roles = session.get('role', 'none')
        if roles == 'none' and 'username' in session: roles = database_module.get_user_role(session["username"]) or 'none'
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        return render_template(
            'catalog.html', board_info=board_info, captcha_image=captcha_image, roles=roles,
            pinneds=formatted_pinneds, posts=formatted_posts, replies=formatted_replies_for_catalog,
            board_banner=board_banner, board_id=board_uri
        )
    except Exception as e:
        logger.error(f"Error loading catalog for board /{board_uri}/: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load catalog for /{board_uri}/."), 500

@boards_bp.route('/<board_uri>/banners')
def board_banners(board_uri):
    try:
        board_info_row = database_module.get_board_info(board_uri)
        if not board_info_row: return redirect(url_for('boards.main_page'))
        board_info = dict(board_info_row)
        board_banner = database_module.get_board_banner(board_uri)
        banners = database_module.get_all_banners(board_uri)
        username = session.get('username', 'anon')
        return render_template('board_banners.html',
                               username=username, board_banner=board_banner,
                               banners=banners or [], board_id=board_uri,
                               board_info=board_info)
    except Exception as e:
        logger.error(f"Error loading banners page for /{board_uri}/: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load banners for board /{board_uri}/."), 500

@boards_bp.route('/<board_name>/thread/<thread_id>')
def replies(board_name, thread_id):
    # print(f"[DEBUG_BOARDS_BP thread_replies] Loading thread: /{board_name}/thread/{thread_id}")
    try:
        try: thread_id_int = int(thread_id)
        except ValueError: return render_template('errors/404.html', message=f"Invalid thread ID '{thread_id}'."), 404

        board_info_row = database_module.get_board_info(board_name)
        if not board_info_row: return render_template('errors/404.html', message=f"Board '/{board_name}/' does not exist."), 404
        board_info = dict(board_info_row)

        thread_op_raw, post_replies_raw = database_module.get_post_and_replies(thread_id_int)

        if not thread_op_raw: return render_template('errors/404.html', message=f"Thread {thread_id_int} not found."), 404
        if thread_op_raw['board_uri'] != board_name:
            return render_template('errors/404.html', message=f"Thread {thread_id_int} not found on board '/{board_name}/'."), 404
        
        formatted_op_list, _, formatted_thread_replies = _prepare_page_content(
            [thread_op_raw], [], post_replies_raw
        )
        
        formatted_op_dict = formatted_op_list[0] if formatted_op_list else None
        if not formatted_op_dict:
             logger.error(f"Failed to format OP for thread {thread_id_int}")
             return render_template('errors/500.html', error_message="Error processing thread data."), 500

        roles = session.get('role', 'none')
        if roles == 'none' and 'username' in session: roles = database_module.get_user_role(session["username"]) or 'none'
        captcha_text, captcha_image = database_module.generate_captcha()
        session['captcha_text'] = captcha_text

        return render_template(
            'thread_reply.html',
            captcha_image=captcha_image, board_info=board_info,
            posts=[formatted_op_dict],
            replies=formatted_thread_replies,
            board_id=board_name, thread_id=thread_id_int,
            post_mode="reply", roles=roles
        )
    except Exception as e:
        logger.error(f"Error loading thread page /{board_name}/thread/{thread_id}: {e}", exc_info=True)
        return render_template('errors/500.html', error_message=f"Could not load thread {thread_id} on board /{board_name}/."), 500

# --- END OF FILE boards_bp.py ---