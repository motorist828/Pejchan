# --- START OF FILE posts_bp.py ---

from flask import current_app, Blueprint, render_template, redirect, request, flash, session, url_for
from database_modules import database_module, moderation_module, formatting
from flask_socketio import SocketIO, emit
from datetime import datetime, timezone
from PIL import Image, ImageSequence, UnidentifiedImageError
import cv2
import re
import os
import time
import shutil
import logging
from werkzeug.utils import secure_filename # Не используется активно, но может пригодиться
import random
import string
import io

logger = logging.getLogger(__name__)
posts_bp = Blueprint('posts', __name__, template_folder='../templates', static_folder='../static')

# --- Константы ---
THUMB_SIZE = (250, 250)
MP3_THUMB_REL_PATH = 'play.jpg'
ALLOWED_EXTENSIONS = {'.jpeg', '.jpg', '.png', '.webp', '.gif', '.mov', '.webm', '.mp4', '.mp3'} # Добавил .webp и .gif обратно в общие разрешенные
POST_IMAGE_FOLDER_REL = 'post_images'
REPLY_IMAGE_FOLDER_REL = 'reply_images'
MAX_COMMENT_LENGTH = 20000

# Параметры WebP для конвертации "image.png"
WEBP_IMAGE_PNG_QUALITY = 85
WEBP_IMAGE_PNG_METHOD = 4

# Параметры WebP для МИНИАТЮР (если они создаются как WebP)
WEBP_THUMB_QUALITY = 80
WEBP_THUMB_METHOD = 3


def get_static_file_abs_path(relative_path):
    # ... (без изменений) ...
    try:
        static_folder = current_app.static_folder if current_app else 'static'
        return os.path.join(static_folder, relative_path)
    except RuntimeError:
        logger.warning("Cannot get current_app context for static folder. Assuming 'static' directory.")
        return os.path.join('static', relative_path)

MP3_THUMB_ABS_PATH = get_static_file_abs_path(MP3_THUMB_REL_PATH)

class PostHandler:
    timeout_manager = moderation_module.TimeoutManager()
    ban_manager = moderation_module.BanManager()

    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        # ... (конструктор без изменений) ...
        if socketio is None: logger.error("!!! PostHandler received socketio as None !!!")
        else: logger.info("--- PostHandler initialized with a valid socketio instance ---")
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode
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
            flash("An error occurred while checking posting timeout.", "error")
            return False

    def validate_comment(self):
        if len(self.original_content) > MAX_COMMENT_LENGTH:
            flash(f"Your comment is too long (max {MAX_COMMENT_LENGTH} characters).", "error")
            return False
        return True


    def _correct_image_orientation(self, img):
        # ... (без изменений) ...
        try:
            for orientation_tag in Image.ExifTags.TAGS.keys():
                if Image.ExifTags.TAGS[orientation_tag] == 'Orientation': break
            else: return img
            exif_data = img._getexif()
            if exif_data is not None:
                orientation = exif_data.get(orientation_tag)
                if orientation == 3: img = img.rotate(180, expand=True)
                elif orientation == 6: img = img.rotate(270, expand=True)
                elif orientation == 8: img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exif_err:
            logger.warning(f"Could not process EXIF data for orientation: {exif_err}")
        return img

    def generate_thumbnail(self, original_path, thumb_path, file_ext_of_original_source):
        """
        Generates a thumbnail.
        original_path: path to the "original" file (может быть "image.webp", если image.png был конвертирован).
        thumb_path: path to save the thumbnail (имя будет содержать расширение .webp для обычных изображений, .png для GIF, .jpg для видео/mp3).
        file_ext_of_original_source: The extension of the *very first* uploaded file (e.g. .jpg, .png, .gif).
        """
        try:
            logger.info(f"Generating thumbnail for '{original_path}' -> '{thumb_path}' (original source ext: {file_ext_of_original_source})")
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)

            # --- Логика создания миниатюр ---
            # Если ИСТОЧНИК был обычным изображением (JPG, PNG, WEBP), делаем WebP миниатюру
            if file_ext_of_original_source in ['.jpeg', '.jpg', '.png', '.webp']:
                with Image.open(original_path) as img: # original_path может быть .webp, если image.png был конвертирован
                    img_copy = img.copy() # Работаем с копией
                    img_copy = self._correct_image_orientation(img_copy)
                    img_copy.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    if img_copy.mode not in ('RGB', 'RGBA'):
                        if 'A' in img_copy.mode or (img_copy.mode == 'P' and 'transparency' in img_copy.info):
                            img_copy = img_copy.convert('RGBA')
                        else:
                            img_copy = img_copy.convert('RGB')
                    # Сохраняем миниатюру как WebP
                    img_copy.save(thumb_path, format='WEBP', quality=WEBP_THUMB_QUALITY, method=WEBP_THUMB_METHOD, lossless=False)
                logger.debug(f"Image thumbnail created as WebP: {thumb_path}")
                return True

            elif file_ext_of_original_source == '.gif':
                 try:
                     with Image.open(original_path) as img: # original_path это .gif
                        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
                        if not frames: raise ValueError("No frames found in GIF")
                        first_frame = frames[0]
                        first_frame.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                        if first_frame.mode != 'RGBA':
                            first_frame = first_frame.convert('RGBA')
                        first_frame.save(thumb_path, format='PNG', optimize=True) # PNG для GIF-тумбы
                        logger.debug(f"GIF thumbnail created (static PNG): {thumb_path}")
                        return True
                 except Exception as gif_err:
                      logger.error(f"Error processing GIF for thumbnail {original_path}: {gif_err}", exc_info=True)
                      return False

            elif file_ext_of_original_source in ['.mp4', '.mov', '.webm']:
                 success = self.capture_frame_from_video(original_path, thumb_path) # thumb_path будет .jpg
                 if success: logger.debug(f"Video thumbnail created (JPG): {thumb_path}")
                 else: logger.warning(f"Failed to create video thumbnail for {original_path}")
                 return success

            elif file_ext_of_original_source == '.mp3':
                if not os.path.exists(MP3_THUMB_ABS_PATH):
                    logger.warning(f"MP3 thumbnail placeholder not found at {MP3_THUMB_ABS_PATH}")
                    return False
                shutil.copy2(MP3_THUMB_ABS_PATH, thumb_path) # thumb_path будет .jpg
                logger.debug(f"MP3 thumbnail placeholder copied (JPG): {thumb_path}")
                return True
            else:
                logger.warning(f"Thumbnail generation not handled for original source extension: {file_ext_of_original_source}")
                return False
        # ... (обработка ошибок без изменений) ...
        except UnidentifiedImageError:
            logger.error(f"Cannot identify image file for thumbnail (corrupted/unsupported): {original_path}", exc_info=False)
            flash(f"Could not process image file '{os.path.basename(original_path)}' for thumbnail.", "error")
            return False
        except cv2.error as e:
             logger.error(f"OpenCV error creating video thumbnail from {original_path}: {e}", exc_info=True)
             flash(f"Could not process video file '{os.path.basename(original_path)}' for thumbnail.", "error")
             return False
        except Exception as e:
            logger.error(f"Error generating thumbnail for {original_path}: {e}", exc_info=True)
            flash(f"An unexpected error occurred while generating thumbnail for '{os.path.basename(original_path)}'.", "error")
            return False

    def capture_frame_from_video(self, video_path, thumb_path): # Сохраняет в JPG
        # ... (без изменений) ...
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): logger.error(f"Error: Unable to open video file: {video_path}"); return False
            fps = cap.get(cv2.CAP_PROP_FPS); total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame_idx = int(fps) if fps and fps > 0 and total_frames > fps else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"Failed to read frame at index {target_frame_idx} for {video_path}, trying frame 0.")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret: logger.error(f"Error: Unable to read any frame from video: {video_path}"); return False
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            pil_image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            pil_image.save(thumb_path, format='JPEG', quality=85, optimize=True, progressive=True)
            return True
        except cv2.error as e: logger.error(f"OpenCV processing error for video {video_path}: {e}", exc_info=True); return False
        except Exception as e: logger.error(f"Unexpected error capturing video frame for {video_path}: {e}", exc_info=True); return False
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

        for uploaded_file_storage in files:
            if uploaded_file_storage.filename == '': continue

            original_filename_unsafe = uploaded_file_storage.filename
            _, original_file_ext = os.path.splitext(original_filename_unsafe)
            original_file_ext = original_file_ext.lower()

            if original_file_ext not in ALLOWED_EXTENSIONS:
                flash(f"File type '{original_file_ext}' is not allowed for file '{original_filename_unsafe}'.", "warning")
                continue

            timestamp_ms = int(time.time() * 1000)
            unique_filename_base = str(timestamp_ms) + ''.join(random.choices(string.ascii_lowercase + string.digits, k=2))

            file_to_save_on_disk_stream = uploaded_file_storage.stream # Поток данных для сохранения
            final_original_saved_ext = original_file_ext       # Расширение, с которым будет сохранен "оригинал"

            # --- КОНВЕРТАЦИЯ ОРИГИНАЛА "image.png" В WEBP ---
            if original_filename_unsafe == "image.png" and original_file_ext == ".png":
                logger.info(f"File is 'image.png', attempting to convert original to WebP.")
                final_original_saved_ext = '.webp' # Оригинал будет WebP
                try:
                    img = Image.open(uploaded_file_storage.stream) # Читаем из потока FileStorage
                    img_copy = img.copy() # Работаем с копией
                    img_copy = self._correct_image_orientation(img_copy)

                    if img_copy.mode not in ('RGB', 'RGBA'):
                        if 'A' in img_copy.mode or (img_copy.mode == 'P' and 'transparency' in img_copy.info):
                            img_copy = img_copy.convert('RGBA')
                        else:
                            img_copy = img_copy.convert('RGB')
                    
                    webp_image_io = io.BytesIO()
                    img_copy.save(webp_image_io, format='WEBP', quality=WEBP_IMAGE_PNG_QUALITY, method=WEBP_IMAGE_PNG_METHOD, lossless=False)
                    webp_image_io.seek(0)
                    file_to_save_on_disk_stream = webp_image_io # Источник данных для сохранения теперь этот поток
                    logger.info(f"Successfully converted 'image.png' to WebP in memory.")
                except Exception as conversion_err:
                    logger.error(f"Failed to convert 'image.png' to WebP: {conversion_err}", exc_info=True)
                    flash(f"Could not convert file 'image.png' to WebP format. Saving as original PNG.", "error")
                    # Если конвертация не удалась, сохраняем как исходный PNG
                    final_original_saved_ext = '.png'
                    uploaded_file_storage.stream.seek(0) # Перематываем исходный поток
                    file_to_save_on_disk_stream = uploaded_file_storage.stream
            else:
                # Для всех других файлов (не "image.png") или если "image.png" но не .png расширения
                # Убедимся, что поток перемотан, если он уже читался
                if hasattr(uploaded_file_storage.stream, 'seek'):
                    uploaded_file_storage.stream.seek(0)
            # --- КОНЕЦ КОНВЕРТАЦИИ ОРИГИНАЛА ---

            new_original_filename_on_disk = f"{unique_filename_base}{final_original_saved_ext}"
            original_save_path = os.path.join(original_folder_abs, new_original_filename_on_disk)

            # Определяем расширение миниатюры на основе ИСХОДНОГО типа файла
            thumb_ext_for_save = '.webp' # По умолчанию для изображений делаем WebP миниатюру
            if original_file_ext == '.gif': thumb_ext_for_save = '.png'
            elif original_file_ext in ['.mp4', '.mov', '.webm']: thumb_ext_for_save = '.jpg'
            elif original_file_ext == '.mp3': thumb_ext_for_save = '.jpg'
            
            thumb_filename = f"thumb_{unique_filename_base}{thumb_ext_for_save}"
            thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)

            try:
                # Сохраняем "оригинальный" файл (возможно, конвертированный 'image.webp' или исходный)
                with open(original_save_path, 'wb') as f_out:
                    shutil.copyfileobj(file_to_save_on_disk_stream, f_out) # Копируем содержимое потока
                logger.info(f"Saved final original file: {original_save_path}")

                # Генерируем миниатюру из сохраненного "оригинального" файла на диске.
                # Передаем original_file_ext (исходный тип), чтобы generate_thumbnail знала, как его обработать.
                if self.generate_thumbnail(original_save_path, thumb_save_path, original_file_ext):
                    thumb_relative_path = os.path.join(upload_folder_rel, 'thumbs', thumb_filename).replace('\\', '/')
                    processed_files_info.append({
                        'original': new_original_filename_on_disk, # Имя сохраненного файла (может быть .webp)
                        'thumbnail': thumb_relative_path
                    })
                else:
                    logger.warning(f"Thumbnail generation failed for {new_original_filename_on_disk} (source: {original_filename_unsafe}). Removing original.")
                    if os.path.exists(original_save_path): os.remove(original_save_path)

            except Exception as e:
                logger.error(f"Error saving file or generating thumb for {original_filename_unsafe} (final: {new_original_filename_on_disk}): {e}", exc_info=True)
                flash(f"Error processing file: {original_filename_unsafe}", "error")
                if os.path.exists(original_save_path):
                    try: os.remove(original_save_path)
                    except OSError as rm_err: logger.error(f"Failed to cleanup file {original_save_path}: {rm_err}")
            finally:
                # Закрываем байтовый поток, если он был создан для WebP конвертации
                if isinstance(file_to_save_on_disk_stream, io.BytesIO):
                    file_to_save_on_disk_stream.close()
                # Важно: не закрывать uploaded_file_storage.stream здесь, Flask сделает это.

        if not self.comment and not processed_files_info:
             logger.warning("Post attempt with no comment and no successfully processed files.")
        return processed_files_info

    def handle_reply(self, reply_to_thread_id):
        # ... (логика метода без изменений, он вызывает process_uploaded_files) ...
        try: tid = int(reply_to_thread_id)
        except (ValueError, TypeError): flash("Invalid thread ID format.", "error"); logger.error(f"Invalid thread ID received in handle_reply: {reply_to_thread_id}"); return None
        if not database_module.check_replyto_exist(tid): flash("This thread doesn't exist!", "error"); return None
        if database_module.verify_locked_thread(tid): flash("This thread is locked.", "error"); return None
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha: flash("CAPTCHA session expired. Please refresh.", "warning"); logger.warning("CAPTCHA check failed: session data missing."); return None
            if not database_module.validate_captcha(self.captcha_input, session_captcha): flash("Invalid captcha.", "error"); return None
        processed_files = self.process_uploaded_files(REPLY_IMAGE_FOLDER_REL, is_thread=False)
        if processed_files is None: return None
        if not self.comment and not processed_files: flash("You need to type something or successfully upload a file for a reply.", "error"); return None
        original_filenames = [f['original'] for f in processed_files]
        thumbnail_rel_paths = [f['thumbnail'] for f in processed_files]
        new_reply_id = database_module.add_new_reply(self.user_ip, tid, self.post_name, self.comment, self.embed, original_filenames, thumbnail_rel_paths)
        if new_reply_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(REPLY_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})
                now_utc = datetime.now(timezone.utc)
                now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)
                self.socketio.emit('nova_postagem', {'type': 'New Reply', 'post': {'id': new_reply_id, 'reply_id': new_reply_id, 'thread_id': tid, 'name': display_name, 'content': self.comment, 'files_data': socket_files_data, 'date': now_display, 'board': self.board_id}}, broadcast=True)
                logger.info(f"SocketIO 'nova_postagem' (New Reply) emitted for reply {new_reply_id}")
            except Exception as socket_err: logger.error(f"Failed to emit SocketIO event for reply {new_reply_id}: {socket_err}", exc_info=True)
            PASSCODE = "passcode"
            if self.embed != PASSCODE:
                self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after reply.")
                logger.info(f"Timeout applied for IP {self.user_ip} after reply {new_reply_id}.")
            else:
                logger.info(f"Timeout skipped for IP {self.user_ip} due to passcode in reply {new_reply_id}.")
            return new_reply_id
        else: flash("Failed to save reply to the database.", "error"); return None

    def handle_post(self):
        # ... (логика метода без изменений, он вызывает process_uploaded_files) ...
        if database_module.verify_board_captcha(self.board_id):
            session_captcha = session.get('captcha_text')
            if not session_captcha: flash("CAPTCHA session expired. Please refresh.", "warning"); logger.warning("CAPTCHA check failed: session data missing."); return None
            if not database_module.validate_captcha(self.captcha_input, session_captcha): flash("Invalid captcha.", "error"); return None
        processed_files = self.process_uploaded_files(POST_IMAGE_FOLDER_REL, is_thread=True)
        if processed_files is None: return None
        if not processed_files: flash("You need to successfully upload at least one file to start a thread.", "error"); return None
        if not self.comment and not processed_files: flash("You need to type something or upload a file.", "error"); return None
        original_filenames = [f['original'] for f in processed_files]
        thumbnail_rel_paths = [f['thumbnail'] for f in processed_files]
        new_post_id = database_module.add_new_post(self.user_ip, self.board_id, self.post_name, self.original_content, self.comment, self.embed, original_filenames, thumbnail_rel_paths)
        if new_post_id:
            try:
                socket_files_data = []
                for f_info in processed_files:
                    orig_url = url_for('static', filename=os.path.join(POST_IMAGE_FOLDER_REL, f_info['original'])).replace('\\', '/')
                    thumb_url = url_for('static', filename=f_info['thumbnail']).replace('\\', '/')
                    socket_files_data.append({'original': orig_url, 'thumbnail': thumb_url})
                now_utc = datetime.now(timezone.utc)
                now_display = database_module.format_datetime_for_display(now_utc)
                display_name = database_module.generate_tripcode(self.post_name)
                self.socketio.emit('nova_postagem', {'type': 'New Thread', 'post': {'id': new_post_id, 'post_id': new_post_id, 'name': display_name, 'content': self.comment, 'files_data': socket_files_data, 'date': now_display, 'board': self.board_id}}, broadcast=True)
                logger.info(f"SocketIO 'nova_postagem' (New Thread) emitted for post {new_post_id}")
            except Exception as socket_err: logger.error(f"Failed to emit SocketIO event for post {new_post_id}: {socket_err}", exc_info=True)
            self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout after post.")
            return new_post_id
        else: flash("Failed to save post to the database.", "error"); return None

# --- Main Route for Handling Posts and Replies ---
@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    # ... (код маршрута без изменений) ...
    socketio = current_app.extensions.get('socketio')
    if not socketio:
        logger.error("SocketIO instance not found in Flask app extensions!")
        flash("A server configuration error occurred (SocketIO).", "error")
        return redirect(request.referrer or url_for('boards.main_page'))
    logger.info("--- SocketIO instance obtained successfully in /new_post ---")
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip: user_ip = user_ip.split(',')[0].strip()
    post_mode_form = request.form.get("post_mode", "post")
    comment_raw = request.form.get('text', '').strip()
    post_name_raw = request.form.get("name", "Anonymous").strip()
    board_id = request.form.get('board_id')
    embed = request.form.get('embed', '').strip()
    captcha_input = request.form.get('captcha', '').strip()
    thread_id_form = request.form.get('thread_id')
    if not board_id:
        flash('Board ID is missing.', 'error')
        logger.warning(f"Post attempt failed: Board ID missing. IP: {user_ip}")
        return redirect(request.referrer or url_for('boards.main_page'))
    if not database_module.get_board_info(board_id):
         flash(f"Board '/{board_id}/' does not exist.", 'error')
         logger.warning(f"Post attempt failed: Board '{board_id}' not found. IP: {user_ip}")
         return redirect(url_for('boards.main_page'))
    captcha_required = database_module.verify_board_captcha(board_id)
    if captcha_required and not captcha_input:
        flash("Captcha is required for this board.", "error")
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if formatting.filter_xss(comment_raw) or formatting.filter_xss(post_name_raw):
        flash('HTML tags are not allowed in name or comment.', 'error')
        logger.warning(f"Post attempt blocked due to potential XSS. IP: {user_ip}, Board: {board_id}")
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, comment_raw, embed, captcha_input)
    if not handler.check_banned(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if not handler.check_timeout(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    if not handler.validate_comment(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    is_reply_mode = False
    reply_to_thread_id = None
    if post_mode_form == "reply" and thread_id_form:
        try:
            reply_to_thread_id = int(thread_id_form)
            is_reply_mode = True
            logger.debug(f"Explicit reply mode detected. Replying to thread {reply_to_thread_id}")
        except (ValueError, TypeError):
            flash("Invalid thread ID provided for reply.", "error")
            logger.warning(f"Invalid thread_id '{thread_id_form}' in reply mode. IP: {user_ip}, Board: {board_id}")
            return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
    reply_match = re.match(r'^(?:#|>>)(\d+)', comment_raw)
    if not is_reply_mode and reply_match:
        potential_reply_target_id = int(reply_match.group(1))
        target_thread_id = database_module.get_thread_id_for_post(potential_reply_target_id)
        if target_thread_id:
            is_reply_mode = True
            reply_to_thread_id = target_thread_id
            logger.debug(f"Implicit reply mode detected via comment '{reply_match.group(0)}'. Replying to thread {reply_to_thread_id}")
            cleaned_comment = comment_raw[len(reply_match.group(0)):].lstrip()
            handler = PostHandler(socketio, user_ip, post_mode_form, post_name_raw, board_id, cleaned_comment, embed, captcha_input)
            if not handler.validate_comment(): return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))
        else:
             flash(f"Cannot reply to post '{reply_match.group(0)}' as it doesn't exist.", "warning")
             logger.warning(f"Implicit reply failed: Target post '{reply_match.group(0)}' not found. IP: {user_ip}, Board: {board_id}")
    posted_id = None
    if is_reply_mode:
        if reply_to_thread_id: posted_id = handler.handle_reply(reply_to_thread_id)
        else: logger.error("Reply mode determined but reply_to_thread_id is missing."); flash("Internal error: Could not determine thread ID for reply.", "error")
    else: posted_id = handler.handle_post()
    if posted_id:
        flash(f"Post successful! ID: {posted_id}", "success")
        if is_reply_mode and reply_to_thread_id:
             referrer_url = request.referrer
             if referrer_url:
                 base_url = referrer_url.split('#')[0]
                 return redirect(url_for('boards.replies', board_name=board_id, thread_id=reply_to_thread_id, _anchor=f'p{posted_id}'))
             else:
                 logger.warning("Referrer missing for reply redirect, falling back to board page.")
                 return redirect(url_for('boards.board_page', board_uri=board_id))
        else: 
             try:
                thread_redirect_url = url_for('boards.replies', board_name=board_id, thread_id=posted_id, _anchor=f'p{posted_id}')
                return redirect(thread_redirect_url)
             except Exception as e:
                logger.warning(f"Could not build URL for thread view (board: {board_id}, thread: {posted_id}): {e}. Falling back to board page redirect.")
                return redirect(url_for('boards.board_page', board_uri=board_id))
    else:
        return redirect(request.referrer or url_for('boards.board_page', board_uri=board_id))

# --- END OF FILE posts_bp.py ---