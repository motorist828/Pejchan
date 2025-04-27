from flask import current_app, Blueprint, render_template, redirect, request, flash, session, url_for
from database_modules import database_module, moderation_module, formatting
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
from PIL import Image, UnidentifiedImageError # Добавлен UnidentifiedImageError для обработки ошибок Pillow
import cv2
import re
import os
import time # Добавлен для Unix timestamp
import shutil # Добавлен для копирования MP3 плейсхолдера

# Blueprint register
posts_bp = Blueprint('posts', __name__)
socketio = SocketIO()

# --- Constants ---
THUMB_SIZE = (250, 250)
# Относительный путь к плейсхолдеру MP3 (относительно static)
MP3_THUMB_REL_PATH = 'play.jpg'
# Абсолютный путь к плейсхолдеру MP3
MP3_THUMB_ABS_PATH = os.path.join('static', MP3_THUMB_REL_PATH)
ALLOWED_EXTENSIONS = {'.jpeg', '.jpg', '.mov', '.gif', '.png', '.webp', '.webm', '.mp4', '.mp3'} # Добавлен .mp3

class PostHandler:
    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode
        self.post_name = post_name
        self.board_id = board_id
        self.original_content = comment
        self.comment = formatting.format_comment(comment)
        self.embed = embed
        self.captcha_input = captcha_input

    timeout_manager = moderation_module.TimeoutManager()
    ban_manager = moderation_module.BanManager()

    def check_banned(self):
        banned_status = self.ban_manager.is_banned(self.user_ip)
        if banned_status.get('is_banned', True):
            flash(f"You has been banned, reason: {banned_status.get('reason')}")
            return False
        return True

    def check_timeout(self):
        timeout_status = self.timeout_manager.check_timeout(self.user_ip)
        if timeout_status.get('is_timeout', False):
            flash('Wait a few seconds to post again.')
            return False
        return True

    def validate_comment(self):
        if len(self.comment) >= 20000:
            flash('You reached the limit.')
            return False
        # Пустой комментарий теперь разрешен, если есть файл
        # if self.comment == '':
        #     flash('You have to type something, you bastard.')
        #     return False
        return True

    def generate_thumbnail(self, original_path, thumb_path, file_ext):
        """Генерирует миниатюру для разных типов файлов."""
        try:
            if file_ext in ['.jpeg', '.jpg', '.png', '.webp']:
                with Image.open(original_path) as img:
                    img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    # Сохраняем в JPG для унификации (кроме PNG с прозрачностью)
                    save_format = 'JPEG'
                    if img.mode == 'RGBA' and file_ext == '.png':
                        save_format = 'PNG'
                        img.save(thumb_path, format=save_format)
                    elif img.mode == 'P' and 'transparency' in img.info: # Handle indexed transparency (like some GIFs/PNGs)
                         img = img.convert('RGBA')
                         img.save(thumb_path, format='PNG')
                    else:
                        img = img.convert('RGB')
                        img.save(thumb_path, format=save_format, quality=85)
                return True
            elif file_ext == '.gif':
                with Image.open(original_path) as img:
                    # Берем первый кадр
                    img.seek(0)
                    # Создаем копию кадра для изменения размера
                    frame = img.copy()
                    frame.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    # Сохраняем как GIF (первый кадр)
                    frame.save(thumb_path, format='GIF')
                return True
            elif file_ext in ['.mp4', '.mov', '.webm']:
                return self.capture_frame_from_video(original_path, thumb_path)
            elif file_ext == '.mp3':
                 # Проверяем наличие плейсхолдера
                if not os.path.exists(MP3_THUMB_ABS_PATH):
                    print(f"Warning: MP3 thumbnail placeholder not found at {MP3_THUMB_ABS_PATH}")
                    return False # Не можем создать миниатюру без плейсхолдера
                # Копируем плейсхолдер как миниатюру
                shutil.copy2(MP3_THUMB_ABS_PATH, thumb_path)
                return True
        except UnidentifiedImageError:
            print(f"Error: Cannot identify image file {original_path}. It might be corrupted or unsupported.")
            return False
        except cv2.error as e:
             print(f"Error processing video {original_path} with OpenCV: {e}")
             return False
        except Exception as e:
            print(f"Error generating thumbnail for {original_path}: {e}")
            return False
        return False

    def process_uploaded_files(self, upload_folder, is_thread=False):
        """Обрабатывает загруженные файлы, сохраняет их с Unix timestamp именем и создает миниатюры."""
        files = request.files.getlist('fileInput')
        processed_files_info = [] # Список словарей {'original': filename, 'thumbnail': thumb_filename}

        # Определяем папки для оригиналов и миниатюр
        base_upload_folder = './static/post_images/' if is_thread else './static/reply_images/'
        thumb_folder_abs = os.path.join(base_upload_folder, 'thumbs/')
        original_folder_abs = base_upload_folder

        os.makedirs(thumb_folder_abs, exist_ok=True)
        os.makedirs(original_folder_abs, exist_ok=True)

        for file in files:
            if file.filename == '':
                continue

            original_filename_unsafe = file.filename
            _, file_ext = os.path.splitext(original_filename_unsafe)
            file_ext = file_ext.lower() # Приводим расширение к нижнему регистру

            if file_ext not in ALLOWED_EXTENSIONS:
                flash(f"File type {file_ext} is not allowed.")
                continue # Пропускаем недопустимые файлы

            # Генерируем уникальное имя файла на основе Unix timestamp
            timestamp = int(time.time() * 1000) # мс для большей уникальности
            new_filename_base = str(timestamp)
            new_filename = f"{new_filename_base}{file_ext}"
            counter = 0
            # Обработка очень редких коллизий timestamp
            while os.path.exists(os.path.join(original_folder_abs, new_filename)):
                counter += 1
                new_filename_base = f"{timestamp}_{counter}"
                new_filename = f"{new_filename_base}{file_ext}"

            original_save_path = os.path.join(original_folder_abs, new_filename)

            try:
                # Сохраняем оригинальный файл
                file.save(original_save_path)

                # --- Создание миниатюры ---
                thumb_filename = "" # Имя файла миниатюры
                thumb_save_path = ""  # Полный путь для сохранения миниатюры

                if file_ext == '.mp3':
                     # Для MP3 миниатюра - это плейсхолдер, имя миниатюры соответствует оригиналу + .jpg
                     thumb_filename_base = new_filename_base
                     thumb_ext = '.jpg' # Миниатюра будет JPG
                     thumb_filename = f"thumb_{thumb_filename_base}{thumb_ext}"
                     thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)
                elif file_ext == '.gif':
                    # Для GIF миниатюра тоже GIF
                    thumb_filename_base = new_filename_base
                    thumb_ext = '.gif'
                    thumb_filename = f"thumb_{thumb_filename_base}{thumb_ext}"
                    thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)
                else:
                     # Для остальных - JPG миниатюра
                    thumb_filename_base = new_filename_base
                    thumb_ext = '.jpg'
                    thumb_filename = f"thumb_{thumb_filename_base}{thumb_ext}"
                    thumb_save_path = os.path.join(thumb_folder_abs, thumb_filename)


                if self.generate_thumbnail(original_save_path, thumb_save_path, file_ext):
                    # Получаем относительный путь к миниатюре для сохранения в БД/HTML
                    thumb_relative_path = os.path.join(os.path.basename(os.path.dirname(thumb_folder_abs)), thumb_filename).replace('\\', '/')

                    processed_files_info.append({
                        'original': new_filename, # Сохраняем новое имя оригинала
                        'thumbnail': thumb_relative_path # Сохраняем относительный путь к миниатюре
                    })
                else:
                    # Если миниатюра не создалась, удаляем оригинал (или можно оставить без миниатюры)
                    print(f"Failed to create thumbnail for {new_filename}. Removing original.")
                    os.remove(original_save_path)
                    flash(f"Could not process file {original_filename_unsafe}.")


            except Exception as e:
                print(f"Error saving or processing file {original_filename_unsafe}: {e}")
                flash(f"Error processing file {original_filename_unsafe}.")
                # Попытаться удалить частично сохраненный файл, если он есть
                if os.path.exists(original_save_path):
                    os.remove(original_save_path)

        # Проверка, если комментарий пуст, но файлы есть
        if not self.comment and not processed_files_info:
             flash('You have to type something or upload a file.')
             return None # Возвращаем None при ошибке валидации

        return processed_files_info # Возвращаем список информации о файлах

    def handle_reply(self, reply_to):
        if not database_module.check_replyto_exist(int(reply_to)):
            flash("This thread don't even exist, dumb!")
            return False

        if database_module.verify_locked_thread(int(reply_to)):
            flash("This thread is locked.")
            return False

        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session["captcha_text"]):
                flash("Invalid captcha.")
                return False

        upload_folder = './static/reply_images/' # Базовая папка для ответов
        processed_files = self.process_uploaded_files(upload_folder, is_thread=False)

        # Проверяем результат process_uploaded_files (может быть None при ошибке)
        if processed_files is None:
             # Сообщение об ошибке уже установлено в process_uploaded_files
             return False

        # Проверка: нужен либо текст, либо файл
        if not self.comment and not processed_files:
            flash("You need to type something or upload a file for a reply.")
            return False

        # --- Обновление для SocketIO и Базы Данных ---
        # Извлекаем только оригинальные имена для обратной совместимости или если фронтенд ожидает строки
        original_filenames = [f['original'] for f in processed_files]
        # Создаем данные для сокета с информацией о миниатюрах
        socket_files_data = [{'original': f['original'], 'thumbnail': url_for('static', filename=os.path.join(os.path.basename(upload_folder), 'thumbs', os.path.basename(f['thumbnail']))).replace('\\','/')} for f in processed_files]
        filethumb = [f"thumbs/{os.path.basename(f['thumbnail'])}" for f in processed_files]
        fileorig = [f"{os.path.basename(f['original'])}" for f in processed_files]
        
        self.socketio.emit('nova_postagem', {
            'type': 'New Reply',
            'post': {
                'id': database_module.get_max_post_id() + 1,
                'thread_id': reply_to,
                'name': self.post_name,
                'content': self.comment,
                # Отправляем данные с миниатюрами для реалтайм обновления
                
                # Можно оставить и старый формат для совместимости, если где-то используется
                'filesthb': filethumb,
                'files': fileorig,
                'date': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                'board': self.board_id
            }
        }, broadcast=True)

        # Передаем всю структуру processed_files в базу данных
        database_module.add_new_reply(self.user_ip, reply_to, self.post_name, self.comment, self.embed, fileorig, filethumb)
        self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout.")
        return True

    def capture_frame_from_video(self, video_path, thumb_path):
        """Захватывает кадр из видео и сохраняет как миниатюру JPG."""
        cap = None # Инициализируем до try
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError("Error: Unable to open video.")

            # Попробуем взять кадр на 1-й секунде, если не выйдет - первый кадр
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame_index = int(fps) if fps and fps > 0 and frame_count > fps else 0

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)
            ret, frame = cap.read()
            if not ret:
                # Если не удалось на 1 сек, берем самый первый
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    raise ValueError("Error: Unable to read any frame.")

            # Конвертируем BGR (OpenCV) в RGB (Pillow)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)

            # Создаем миниатюру
            pil_image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

            # Сохраняем как JPG
            pil_image.save(thumb_path, format='JPEG', quality=85)
            return True # Успешно

        except cv2.error as e:
             print(f"OpenCV error processing video {video_path}: {e}")
             return False
        except Exception as e:
            print(f"Error capturing frame from video {video_path}: {e}")
            return False
        finally:
            if cap:
                cap.release() # Обязательно освобождаем ресурс

    def handle_post(self):
        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session["captcha_text"]):
                flash("Invalid captcha.")
                return False

        upload_folder = './static/post_images/' # Базовая папка для постов
        processed_files = self.process_uploaded_files(upload_folder, is_thread=True)

        # Проверяем результат process_uploaded_files
        if processed_files is None:
             return False

        # Для нового треда нужен хотя бы один файл
        if not processed_files:
            flash("You need to upload at least one file to start a thread.")
            return False

        # Проверка: нужен либо текст, либо файл (хотя для треда файл обязателен)
        if not self.comment and not processed_files:
            # Эта проверка избыточна из-за предыдущей, но оставим для ясности
            flash("You need to type something or upload a file.")
            return False

        # --- Обновление для SocketIO и Базы Данных ---
        original_filenames = [f['original'] for f in processed_files]
        
        socket_files_data = [{'original': f['original'], 'thumbnail': url_for('static', filename=os.path.join(os.path.basename(upload_folder), 'thumbs', os.path.basename(f['thumbnail']))).replace('\\','/')} for f in processed_files]
        filethumb = [f"thumbs/{os.path.basename(f['thumbnail'])}" for f in processed_files]
        fileorig = [f"{os.path.basename(f['original'])}" for f in processed_files]


        self.socketio.emit('nova_postagem', {
            'type': 'New Thread',
            'post': {
                'id': database_module.get_max_post_id() + 1,
                'name': self.post_name,
                'content': self.comment,
                # Отправляем данные с миниатюрами
                
                'filesthb': filethumb,
                'files': fileorig,
                'date': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                'board': self.board_id,
                'role': 'user' # or whatever role system you have
            }
        }, broadcast=True)

        # Передаем всю структуру processed_files в базу данных
        database_module.add_new_post(self.user_ip, self.board_id, self.post_name,
                                   self.original_content, self.comment, self.embed, fileorig, filethumb)
        self.timeout_manager.apply_timeout(self.user_ip, duration_seconds=35, reason="Automatic timeout.")
        return True

@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    socketio = current_app.extensions['socketio']
    # Используем X-Forwarded-For если есть (для работы за прокси), иначе remote_addr
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    post_mode = request.form.get("post_mode", "post") # Default to post if not provided
    post_name = request.form.get("name", "Anonymous") # Default name
    board_id = request.form.get('board_id')
    comment = request.form.get('text', '') # Default to empty string
    embed = request.form.get('embed', '')
    captcha_input = 'none'

    if not board_id:
        flash('Board ID is missing.')
        return redirect(request.referrer or url_for('main.index')) # Redirect to referrer or main index

    if database_module.verify_board_captcha(board_id):
         # Проверяем наличие поля captcha перед доступом
        if 'captcha' not in request.form:
             flash("Captcha is required for this board.")
             return redirect(request.referrer)
        captcha_input = request.form['captcha']

    # Проверка XSS (можно улучшить библиотекой, например bleach)
    if formatting.filter_xss(comment) or formatting.filter_xss(post_name):
        flash('HTML tags are not allowed.')
        return redirect(request.referrer)

    handler = PostHandler(socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input)

    if not handler.check_banned():
        return redirect(request.referrer)

    if not handler.check_timeout():
        return redirect(request.referrer)

    # --- Логика определения режима поста (явный или по комментарию) ---
    is_reply_mode = (post_mode == "reply")
    reply_to_match = re.match(r'^#(\d+)', comment) # Проверяем комментарий на #<id>

    if is_reply_mode:
        # Явный режим ответа
        reply_to = request.form.get('thread_id')
        if not reply_to:
            flash("Reply mode selected, but thread ID is missing.")
            return redirect(request.referrer)
        # Удаляем #<id> из начала комментария, если он там есть, чтобы не дублировалось
        if reply_to_match and reply_to_match.group(1) == reply_to:
             handler.comment = formatting.format_comment(comment[len(reply_to_match.group(0)):].lstrip())

        if not handler.validate_comment() and not request.files.getlist('fileInput'): # Валидация + проверка на наличие файлов
             # Сообщение об ошибке будет установлено в validate_comment или process_uploaded_files
             return redirect(request.referrer)
        if not handler.handle_reply(reply_to):
            return redirect(request.referrer)

    elif reply_to_match:
        # Комментарий начинается с #<id>, неявный режим ответа
        reply_to = reply_to_match.group(1)
        # Проверяем, существует ли такой пост (может быть и тред, и ответ)
        if not database_module.check_post_exist(int(reply_to)):
             flash(f"Post #{reply_to} not found.")
             return redirect(request.referrer)
        # Удаляем #<id> из комментария перед обработкой
        original_comment_without_ref = comment[len(reply_to_match.group(0)):].lstrip()
        handler.comment = formatting.format_comment(original_comment_without_ref)
        handler.original_content = original_comment_without_ref # Обновляем и оригинал без #id

        # Определяем тред, к которому относится пост #reply_to
        thread_id_for_reply = database_module.get_thread_id_for_post(int(reply_to))
        if not thread_id_for_reply:
             # Это может случиться, если пост был удален между проверкой и этим моментом
             flash(f"Could not determine the thread for post #{reply_to}.")
             return redirect(request.referrer)

        if not handler.validate_comment() and not request.files.getlist('fileInput'):
             return redirect(request.referrer)
        if not handler.handle_reply(str(thread_id_for_reply)): # Передаем ID треда
            return redirect(request.referrer)

    else:
        # Режим создания нового треда
        # Валидация для треда: нужен либо текст, либо файл (но handle_post проверит наличие файла)
        if not handler.validate_comment() and not request.files.getlist('fileInput'):
            flash("You need to type something or upload a file to start a thread.")
            return redirect(request.referrer)
        if not handler.handle_post():
            return redirect(request.referrer)

    # Успешное создание поста/ответа
    flash("Post successful!") # Добавим сообщение об успехе
    # Перенаправляем на ту же доску
    return redirect(request.referrer)


# Этот эндпоинт обычно обрабатывается библиотекой SocketIO, его может не быть здесь
# @posts_bp.route('/socket.io/')
# def socket_io():
#     # Эта логика обычно внутри app.py или где инициализируется SocketIO
#     # from flask_socketio import socketio_manage
#     # socketio_manage(request.environ, {'/': SocketIOHandler}, request=request)
#     pass # Оставим пустым или удалим, если не используется явно