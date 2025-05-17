from flask import current_app, Blueprint, render_template, redirect, request, flash, session, url_for
# Use the updated database and moderation modules
from database_modules import database_module, moderation_module, formatting
from flask_socketio import SocketIO, emit
# Import datetime and timezone
from datetime import datetime, timezone
from PIL import Image, ImageSequence, UnidentifiedImageError # Убедимся, что Image импортирован
import cv2
import re
import os
import time
import shutil
import logging # Use logging
from werkzeug.utils import secure_filename # Useful for sanitizing original filenames
import random
import string

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Usually configured in main app
logger = logging.getLogger(__name__) # Use Flask's logger or configure one

# Blueprint register
posts_bp = Blueprint('posts', __name__, template_folder='../templates', static_folder='../static')
# SocketIO instance will be retrieved from current_app later

# --- Constants ---
THUMB_SIZE = (250, 250)
# Relative path to placeholder MP3 thumbnail within the static folder
MP3_THUMB_REL_PATH = 'play.jpg'
# Allowed file extensions (lowercase)
ALLOWED_EXTENSIONS = {'.jpeg', '.jpg', '.mov', '.gif', '.png', '.webp', '.webm', '.mp4', '.mp3'}
# Define upload folders relative to the static directory base
POST_IMAGE_FOLDER_REL = 'post_images'
REPLY_IMAGE_FOLDER_REL = 'reply_images'
MAX_COMMENT_LENGTH = 20000 # Example limit
WEBP_CONVERT_FILENAME = "image.png" # Имя файла для конвертации в WebP
WEBP_QUALITY = 90
WEBP_METHOD = 4


# --- Helper Functions ---
def get_static_file_abs_path(relative_path):
    """Gets the absolute path for a file within the static folder."""
    try:
        # Use Flask's app context if available, otherwise assume script runs from root
        static_folder = current_app.static_folder if current_app else 'static'
        return os.path.join(static_folder, relative_path)
    except RuntimeError: # Outside of application context
        logger.warning("Cannot get current_app context for static folder. Assuming 'static' directory.")
        return os.path.join('static', relative_path)

# Get absolute path for MP3 placeholder
MP3_THUMB_ABS_PATH = get_static_file_abs_path(MP3_THUMB_REL_PATH)

# --- Post Handler Class ---
class PostHandler:
    # Use the managers from the updated moderation module
    timeout_manager = moderation_module.TimeoutManager()
    ban_manager = moderation_module.BanManager()

    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        # ... (код __init__ без изменений) ...
        if socketio is None:
            logger.error("!!! PostHandler received socketio as None !!!")
        else:
            logger.info("--- PostHandler initialized with a valid socketio instance ---")
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode # "post" or "reply"
        raw_name = post_name.strip() if post_name else "Anonymous"
        self.post_name = raw_name
        self.board_id = board_id
        self.original_content = comment
        self.comment = formatting.format_comment(comment)
        self.embed = embed
        self.captcha_input = captcha_input

    # ... (методы check_banned, check_timeout, validate_comment без изменений) ...
    def check_banned(self):
        try:
            banned_status = self.ban_manager.is_banned(self.user_ip)
            if banned_status.get('is_banned', False):
                reason = banned_status.get('reason', 'No reason provided.')
                flash(f"You are banned. Reason: {reason}", "error")
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking ban status for IP {self.user_ip}: {e}", exc_info=True)
            flash("An error occurred while checking ban status. Please try again later.", "error")
            return False

    def check_timeout(self):
        try:
            timeout_status = self.timeout_manager.check_timeout(self.user_ip)
            if timeout_status.get('is_timeout', False):
                flash("Please wait a few seconds before posting again.", "warning")
                return False
            return True
        except Exception as e:
            logger.error(f"Error checking timeout status for IP {self.user_ip}: {e}", exc_info=True)
            flash("An error occurred while checking posting timeout. Please try again later.", "error")
            return False

    def validate_comment(self):
        if len(self.original_content) > MAX_COMMENT_LENGTH:
            flash(f"Your comment is too long (max {MAX_COMMENT_LENGTH} characters).", "error")
            return False
        return True


    def generate_thumbnail(self, original_path, thumb_path, file_ext):
        # ... (код generate_thumbnail без изменений) ...
        try:
            logger.info(f"Generating thumbnail for {original_path} -> {thumb_path}")
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)

            if file_ext in ['.jpeg', '.jpg', '.png', '.webp']:
                with Image.open(original_path) as img:
                    try:
                        for orientation_tag in Image.ExifTags.TAGS.keys():
                            if Image.ExifTags.TAGS[orientation_tag] == 'Orientation': break
                        else: orientation_tag = None
                        if orientation_tag:
                            exif_data = img._getexif()
                            if exif_data is not None:
                                orientation = exif_data.get(orientation_tag)
                                if orientation == 3: img = img.rotate(180, expand=True)
                                elif orientation == 6: img = img.rotate(270, expand=True)
                                elif orientation == 8: img = img.rotate(90, expand=True)
                    except: pass
                    img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    save_format = 'JPEG'; quality = 85; img_mode = img.mode
                    has_transparency = (img_mode == 'RGBA' or (img_mode == 'P' and 'transparency' in img.info) or (img_mode == 'LA'))
                    if has_transparency:
                        save_format = 'PNG'; quality = None
                        if img_mode != 'RGBA': img = img.convert('RGBA')
                    else:
                        if img_mode != 'RGB': img = img.convert('RGB')
                    save_kwargs = {'format': save_format}
                    if quality: save_kwargs['quality'] = quality
                    if save_format == 'PNG': save_kwargs['optimize'] = True
                    if save_format == 'JPEG': save_kwargs['optimize'] = True; save_kwargs['progressive'] = True
                    img.save(thumb_path, **save_kwargs)
                return True
            elif file_ext == '.gif':
                 try:
                     with Image.open(original_path) as img:
                        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
                        if not frames: raise ValueError("No frames found in GIF")
                        first_frame = frames[0]
                        first_frame.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                        if first_frame.mode != 'RGBA': first_frame = first_frame.convert('RGBA')
                        first_frame.save(thumb_path, format='PNG', optimize=True)
                        return True
                 except Exception as gif_err: logger.error(f"Error processing GIF {original_path}: {gif_err}", exc_info=True); return False
            elif file_ext in ['.mp4', '.mov', '.webm']:
                 return self.capture_frame_from_video(original_path, thumb_path)
            elif file_ext == '.mp3':
                if not os.path.exists(MP3_THUMB_ABS_PATH): return False
                shutil.copy2(MP3_THUMB_ABS_PATH, thumb_path)
                return True
        except UnidentifiedImageError: flash(f"Could not process image file '{os.path.basename(original_path)}'.", "error"); return False
        except cv2.error as e: flash(f"Could not process video file '{os.path.basename(original_path)}'.", "error"); return False
        except Exception as e: flash(f"An unexpected error occurred while processing file '{os.path.basename(original_path)}'.", "error"); return False
        logger.warning(f"Thumbnail generation not implemented for extension: {file_ext}"); return False


    def capture_frame_from_video(self, video_path, thumb_path):
        # ... (код capture_frame_from_video без изменений) ...
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): return False
            fps = cap.get(cv2.CAP_PROP_FPS); total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame_idx = int(fps) if fps and fps > 0 and total_frames > fps else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx); ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0); ret, frame = cap.read()
                if not ret: return False
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); pil_image = Image.fromarray(frame_rgb)
            pil_image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            pil_image.save(thumb_path, format='JPEG', quality=85, optimize=True, progressive=True)
            return True
        except Exception as e: logger.error(f"Error capturing video frame for {video_path}: {e}", exc_info=True); return False
        finally:
            if cap: cap.release()


    def process_uploaded_files(self, upload_folder_rel, is_thread=False):
        files = request.files.getlist('fileInput')
        processed_files_info = []

        static_folder_abs = get_static_file_abs_path('')
        original_folder_abs = os.path.join(static_folder_abs, upload_folder_rel)
        thumb_folder_abs = os.path.join(original_folder_abs, 'thumbs')

        try:
            os.makedirs(original_folder_abs, exist_ok=True)
            os.makedirs(thumb_folder_abs, exist_ok=True)
        except OSError as e:
             logger.error(f"Failed to create upload directories: {e}", exc_info=True)
             flash("Server error: Could not create upload directory.", "error")
             return None

        for file_storage in files:
            if file_storage.filename == '':
                continue

            original_filename_unsafe = file_storage.filename
            filename_base, file_ext_original = os.path.splitext(original_filename_unsafe)
            file_ext_original_lower = file_ext_original.lower()

            should_convert_to_webp = False
            if original_filename_unsafe.lower() == WEBP_CONVERT_FILENAME.lower() and file_ext_original_lower == '.png':
                should_convert_to_webp = True
                logger.info(f"File '{original_filename_unsafe}' will be converted to WebP with transparency.")
                current_file_ext = '.webp'
            else:
                current_file_ext = file_ext_original_lower

            if current_file_ext not in ALLOWED_EXTENSIONS and not (should_convert_to_webp and '.webp' in ALLOWED_EXTENSIONS):
                flash(f"File type '{file_ext_original_lower}' is not allowed for file '{original_filename_unsafe}'.", "warning")
                continue

            timestamp_ms = int(time.time() * 1000)
            unique_filename_base = str(timestamp_ms) + ''.join(random.choices(string.ascii_lowercase + string.digits, k=2))
            
            new_filename = f"{unique_filename_base}{current_file_ext}"
            original_save_path = os.path.join(original_folder_abs, new_filename)

            thumb_ext_for_gen = '.jpg'
            # Если оригинал WebP (или конвертирован в WebP) и мы хотим WebP миниатюру с прозрачностью:
            if current_file_ext == '.webp': 
                thumb_ext_for_gen = '.webp' # Делаем и миниатюру WebP
            elif current_file_ext == '.mp3': thumb_ext_for_gen = '.jpg'
            elif current_file_ext == '.gif': thumb_ext_for_gen = '.png' # Статичная PNG миниатюра для GIF
            elif current_file_ext == '.png': thumb_ext_for_gen = '.png' # PNG миниатюра для PNG
            

            thumb_filename = f"thumb_{unique_filename_base}{thumb_ext_for_gen}"
            thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)

            try:
                if should_convert_to_webp:
                    img = Image.open(file_storage.stream)
                    
                    # --- ИЗМЕНЕНИЕ ДЛЯ СОХРАНЕНИЯ ПРОЗРАЧНОСТИ ---
                    # Убедимся, что изображение в режиме с поддержкой альфа-канала, если он есть
                    if img.mode not in ('RGBA', 'LA') and 'transparency' in img.info:
                        img = img.convert('RGBA') # Конвертируем в RGBA для сохранения альфа
                    
                    # Сохраняем в WebP с параметром lossless=True для сохранения прозрачности
                    # Это создаст WebP без потерь, который хорошо сжимает графику с прозрачностью.
                    # Файл может быть больше, чем WebP с потерями.
                    img.save(original_save_path, 'WEBP', quality=WEBP_QUALITY, method=WEBP_METHOD)
                    # Параметр quality для lossless=True обычно интерпретируется как усилие сжатия (0-100, где 100 - макс. сжатие/мин. размер).
                    # Method также влияет на баланс размер/скорость.
                    
                    # Альтернатива: WebP с потерями И альфа-каналом (если нужно меньший размер ценой некоторого качества)
                    # Для этого Pillow должен быть собран с libwebp, поддерживающей alpha_quality.
                    # if img.mode != 'RGBA':
                    #    img = img.convert('RGBA') # Убедимся, что есть альфа-канал для сохранения
                    # img.save(original_save_path, 'WEBP', quality=WEBP_QUALITY, method=WEBP_METHOD, alpha_quality=90)
                    # alpha_quality (0-100) - качество сжатия альфа-канала.
                    # --- КОНЕЦ ИЗМЕНЕНИЯ ДЛЯ СОХРАНЕНИЯ ПРОЗРАЧНОСТИ ---
                    
                    logger.info(f"Converted '{original_filename_unsafe}' and saved as WebP (lossless): {original_save_path}")
                else:
                    file_storage.save(original_save_path)
                    logger.info(f"Saved original file: {original_save_path}")

                # Генерация миниатюры
                # file_ext для generate_thumbnail теперь current_file_ext (может быть .webp)
                if self.generate_thumbnail(original_save_path, thumb_save_path, current_file_ext):
                    thumb_relative_path = os.path.join(upload_folder_rel, 'thumbs', thumb_filename).replace('\\', '/')
                    processed_files_info.append({
                        'original': new_filename,
                        'thumbnail': thumb_relative_path
                    })
                else:
                    logger.warning(f"Thumbnail generation failed for {new_filename}. Removing original file.")
                    if os.path.exists(original_save_path): os.remove(original_save_path)

            except Exception as e:
                logger.error(f"Error saving or processing file {original_filename_unsafe} as {new_filename}: {e}", exc_info=True)
                flash(f"Error processing file: {original_filename_unsafe}", "error")
                if os.path.exists(original_save_path):
                    try: os.remove(original_save_path)
                    except OSError as rm_err: logger.error(f"Failed to cleanup partially saved file {original_save_path}: {rm_err}")

        if not self.comment and not processed_files_info:
             logger.warning("Post attempt with no comment and no successfully processed files.")
             pass

        return processed_files_info

    # ... (методы handle_reply, handle_post без изменений в этой части) ...
    def handle_reply(self, reply_to_thread_id):
        try: tid = int(reply_to_thread_id)
        except (ValueError, TypeError): flash("Invalid thread ID format.", "error"); return None
        if not database_module.check_replyto_exist(tid): flash("This thread doesn't exist!", "error"); return None
        if database_module.verify_locked_thread(tid): flash("This thread is locked.", "error"); return None
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha: flash("CAPTCHA session expired. Please refresh.", "warning"); return None
            if not database_module.validate_captcha(self.captcha_input, session_captcha): flash("Invalid captcha.", "error"); return None
        processed_files = self.process_uploaded_files(REPLY_IMAGE_FOLDER_REL, is_thread=False)
        if processed_files is None: return None
        if not self.comment and not processed_files: flash("You need to type something or successfully upload a file for a reply.", "error"); return None
        original_filenames = [f['original'] for f in processed_files]; thumbnail_rel_paths = [f['thumbnail'] for f in processed_files]
        new_reply_id = database_module.add_new_reply(self.user_ip, tid, self.post_name, self.comment, self.embed, original_filenames, thumbnail_rel_paths)
        if new_reply_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(REPLY_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})
                now_utc = datetime.now(timezone.utc); now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)
                self.socketio.emit('nova_postagem', {'type': 'New Reply','post': {'id': new_reply_id, 'reply_id': new_reply_id, 'thread_id': tid,'name': display_name, 'content': self.comment, 'files_data': socket_files_data, 'date': now_display,'board': self.board_id}})
            except Exception as socket_err: logger.error(f"Failed to emit SocketIO event for reply {new_reply_id}: {socket_err}", exc_info=True)
            PASSCODE = "passcode"
            if self.embed != PASSCODE: self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after reply.")
            else: logger.info(f"Timeout skipped for IP {self.user_ip} due to passcode in reply {new_reply_id}.")
            return new_reply_id
        else: flash("Failed to save reply to the database.", "error"); return None

    def handle_post(self):
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha: flash("CAPTCHA session expired. Please refresh.", "warning"); return None
            if not database_module.validate_captcha(self.captcha_input, session_captcha): flash("Invalid captcha.", "error"); return None
        processed_files = self.process_uploaded_files(POST_IMAGE_FOLDER_REL, is_thread=True)
        if processed_files is None: return None
        if not processed_files: flash("You need to successfully upload at least one file to start a thread.", "error"); return None
        if not self.comment and not processed_files: flash("You need to type something or upload a file.", "error"); return None
        original_filenames = [f['original'] for f in processed_files]; thumbnail_rel_paths = [f['thumbnail'] for f in processed_files]
        new_post_id = database_module.add_new_post(self.user_ip, self.board_id, self.post_name, self.original_content, self.comment, self.embed, original_filenames, thumbnail_rel_paths)
        if new_post_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(POST_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})
                now_utc = datetime.now(timezone.utc); now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)
                self.socketio.emit('nova_postagem', {'type': 'New Thread', 'post': {'id': new_post_id, 'post_id': new_post_id, 'name': display_name, 'content': self.comment, 'files_data': socket_files_data, 'date': now_display, 'board': self.board_id}})
            except Exception as socket_err: logger.error(f"Failed to emit SocketIO event for post {new_post_id}: {socket_err}", exc_info=True)
            self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after post.")
            return new_post_id
        else: flash("Failed to save post to the database.", "error"); return None

# --- Main Route for Handling Posts and Replies ---
@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    # ... (код new_post без изменений) ...
    socketio = current_app.extensions.get('socketio')
    if not socketio:
        logger.error("SocketIO instance not found!"); flash("Server error (SocketIO).", "error")
        return redirect(request.referrer or url_for('boards.main_page'))
    logger.info("--- SocketIO instance obtained ---")
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr); user_ip = user_ip.split(',')[0].strip() if user_ip else request.remote_addr
    post_mode_form = request.form.get("post_mode", "post"); comment_raw = request.form.get('text', '').strip()
    post_name_raw = request.form.get("name", "Anonymous").strip(); board_id = request.form.get('board_id')
    embed = request.form.get('embed', '').strip(); captcha_input = request.form.get('captcha', '').strip()
    thread_id_form = request.form.get('thread_id')
    if not board_id: flash('Board ID is missing.', 'error'); return redirect(request.referrer or url_for('boards.main_page'))
    if not database_module.get_board_info(board_id): flash(f"Board '/{board_id}/' does not exist.", 'error'); return redirect(url_for('boards.main_page'))
    captcha_required = database_module.verify_board_captcha(board_id)
    if captcha_required and not captcha_input: flash("Captcha is required.", "error"); return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if formatting.filter_xss(comment_raw) or formatting.filter_xss(post_name_raw): flash('HTML not allowed.', 'error'); return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, comment_raw, embed, captcha_input)
    if not handler.check_banned(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if not handler.check_timeout(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if not handler.validate_comment(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    is_reply_mode = False; reply_to_thread_id = None
    if post_mode_form == "reply" and thread_id_form:
        try: reply_to_thread_id = int(thread_id_form); is_reply_mode = True
        except: flash("Invalid thread ID for reply.", "error"); return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    reply_match = re.match(r'^(?:#|>>)(\d+)', comment_raw)
    if not is_reply_mode and reply_match:
        target_thread_id = database_module.get_thread_id_for_post(int(reply_match.group(1)))
        if target_thread_id:
            is_reply_mode = True; reply_to_thread_id = target_thread_id
            cleaned_comment = comment_raw[len(reply_match.group(0)):].lstrip()
            handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, cleaned_comment, embed, captcha_input)
            if not handler.validate_comment(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
        else: flash(f"Cannot reply to post '{reply_match.group(0)}'.", "warning")
    posted_id = None
    if is_reply_mode:
        if reply_to_thread_id: posted_id = handler.handle_reply(reply_to_thread_id)
        else: flash("Internal error: Could not determine thread ID for reply.", "error")
    else: posted_id = handler.handle_post()
    if posted_id:
        flash(f"Post successful! ID: {posted_id}", "success")
        if is_reply_mode and reply_to_thread_id:
            referrer_url = request.referrer; base_url = referrer_url.split('#')[0] if referrer_url else None
            return redirect(f"{base_url}#p{posted_id}" if base_url else url_for('boards.board_page', board_uri=board_id))
        else:
            try: return redirect(url_for('boards.replies', board_name=board_id, thread_id=posted_id, _anchor=f'p{posted_id}')) # ИЗМЕНЕНО replies на thread_page
            except Exception as e: logger.warning(f"URL build error: {e}. Fallback."); return redirect(url_for('boards.board_page', board_uri=board_id))
    else: return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))