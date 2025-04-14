# imports
from flask import current_app, Blueprint, render_template, redirect, request, flash, session
from database_modules import database_module, timeout_module, formatting
from flask_socketio import SocketIO, emit
from PIL import Image
import cv2
import re
import os
import shutil
import time  # Добавлен импорт модуля времени

# bluepint register.
posts_bp = Blueprint('posts', __name__)
# socketIO call.
socketio = SocketIO()

THUMBNAIL_SIZE = (250, 250)  # Размер миниатюры
AUDIO_THUMBNAIL = 'play.jpg'  # Шаблон для аудио миниатюр
ALLOWED_EXTENSIONS = {'.jpeg', '.jpg', '.gif', '.png', '.webp', '.webm', '.mp4', '.mov', '.mp3'} # Допустимые расширения файлов

def generate_unix_filename(original_filename):
    """Генерирует имя файла на основе Unix-времени с сохранением расширения"""
    unix_time = int(time.time())
    _, ext = os.path.splitext(original_filename)
    return f"{unix_time}{ext.lower()}"

# post handling class.
class PostHandler:
    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode
        self.post_name = post_name
        self.board_id = board_id
        # Форматируем комментарий сразу, но будем проверять его на пустоту позже, если нужно
        self.raw_comment = comment # Сохраняем исходный комментарий для проверки на пустоту
        self.comment = formatting.format_comment(comment)
        self.embed = embed
        self.captcha_input = captcha_input

    def check_timeout(self):
        """Проверяет, не находится ли пользователь в таймауте"""
        if database_module.check_timeout_user(self.user_ip):
            flash('Подождите несколько секунд перед повторной отправкой.')
            return False
        return True

    def check_board(self):
        """Проверяет существование доски"""
        if not database_module.check_board(self.board_id):
            flash('Доска не существует.')
            return False
        return True

    def validate_comment_length(self):
        """Валидация длины комментария"""
        if len(self.comment) >= 10000:
            flash('Превышен лимит символов.')
            return False
        return True

    def create_image_thumbnail(self, image_path, filename):
        """Создает миниатюру для изображения"""
        try:
            thumb_folder = os.path.join(os.path.dirname(image_path), 'thumbs')
            os.makedirs(thumb_folder, exist_ok=True)

            thumb_path = os.path.join(thumb_folder, f"thumb_{filename}")

            with Image.open(image_path) as img:
                if filename.lower().endswith('.gif'):
                    try:
                        img.seek(0)
                        frame = img.copy()
                        frame.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        if frame.mode not in ('P', 'L'):
                            frame = frame.convert('P', palette=Image.ADAPTIVE)
                        frame.save(
                            thumb_path,
                            format='GIF',
                            optimize=True,
                            transparency=0 if img.info.get('transparency') is not None else None
                        )
                    except EOFError:
                        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        img.save(thumb_path)
                else:
                    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.save(thumb_path)

            return thumb_path
        except Exception as e:
            print(f"Error creating image thumbnail: {e}")
            return None

    def create_audio_thumbnail(self, audio_path, filename):
        """Создает миниатюру для аудио файла"""
        try:
            thumb_folder = os.path.join(os.path.dirname(audio_path), 'thumbs')
            os.makedirs(thumb_folder, exist_ok=True)

            template_path = os.path.join(current_app.static_folder, AUDIO_THUMBNAIL)

            if not os.path.exists(template_path):
                print(f"Audio thumbnail template not found at {template_path}")
                return None

            base_name = os.path.splitext(filename)[0]
            thumb_filename = f"thumb_{base_name}.jpg"
            thumb_path = os.path.join(thumb_folder, thumb_filename)

            shutil.copy2(template_path, thumb_path)

            return thumb_path
        except Exception as e:
            print(f"Error creating audio thumbnail: {e}")
            return None

    def capture_frame_from_video(self, video_path):
        """Создает миниатюру из видео"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError("Error: Unable to open video.")

            fps = cap.get(cv2.CAP_PROP_FPS)
            # Пытаемся взять кадр на 1-й секунде, или самый первый, если видео короче
            frame_number = int(fps) if fps > 0 else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            ret, frame = cap.read()
            if not ret:
                 # Если не удалось прочитать на 1й секунде, пробуем 0й кадр
                 cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                 ret, frame = cap.read()
                 if not ret:
                    raise ValueError("Error: Unable to read frame from video.")


            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            thumb_folder = os.path.join(os.path.dirname(video_path), 'thumbs')
            os.makedirs(thumb_folder, exist_ok=True)

            base, ext = os.path.splitext(os.path.basename(video_path))
            thumbnail_filename = f"thumb_{base}.jpg"
            thumb_path = os.path.join(thumb_folder, thumbnail_filename)

            pil_image = Image.fromarray(image)
            pil_image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            pil_image.save(thumb_path)

            cap.release()

            return thumb_path

        except Exception as e:
            print(f"Error processing video for thumbnail: {e}")
            return None

    def handle_reply(self, reply_to):
        """Обработка ответа в треде"""
        # --- Общие проверки ---
        if database_module.verify_locked_thread(int(reply_to)):
            flash("Тред закрыт.")
            return False
        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session.get("captcha_text")): # Используем .get для безопасности
                flash("Неверная капча.")
                return False
        if not self.validate_comment_length(): # Проверяем только длину, не пустоту
             return False

        # --- Обработка файла ---
        file_uploaded = False
        new_filename = ""
        file = request.files.get('fileInput') # Используем .get для безопасности

        if file and file.filename != '':
            _, ext = os.path.splitext(file.filename)
            if ext.lower() in ALLOWED_EXTENSIONS:
                upload_folder = './static/reply_images/'
                os.makedirs(upload_folder, exist_ok=True)

                new_filename = generate_unix_filename(file.filename)
                file_path = os.path.join(upload_folder, new_filename)
                file.save(file_path)

                thumb_created = False
                if new_filename.lower().endswith(('.jpeg', '.jpg', '.gif', '.png', '.webp')):
                    thumb_created = self.create_image_thumbnail(file_path, new_filename) is not None
                elif new_filename.lower().endswith(('.mov', '.webm', '.mp4')):
                    thumb_created = self.capture_frame_from_video(file_path) is not None
                elif new_filename.lower().endswith('.mp3'):
                    thumb_created = self.create_audio_thumbnail(file_path, new_filename) is not None

                if not thumb_created:
                    flash("Ошибка создания миниатюры для файла.")
                    # Попытаемся удалить загруженный файл, если миниатюру создать не удалось
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        print(f"Error deleting file after thumbnail failure: {e}")
                    return False # Ошибка при создании миниатюры

                file_uploaded = True # Файл успешно загружен и обработан
            else:
                flash("Недопустимый тип файла.")
                return False # Неверный тип файла

        # --- Проверка наличия контента (текст или файл) ---
        has_content = file_uploaded or self.raw_comment.strip()

        if not has_content:
            flash("Для ответа необходимо ввести текст или прикрепить файл.")
            return False

        # --- Добавление ответа в базу данных ---
        # Используем new_filename если файл был загружен, иначе пустую строку
        db_filename = new_filename if file_uploaded else ""
        database_module.add_new_reply(self.user_ip, reply_to, self.post_name, self.comment, self.embed, db_filename)
        self.socketio.emit('nova_postagem', {'type': 'reply', 'thread_id': reply_to}, broadcast=True) # Уточняем тип события
        timeout_module.timeout(self.user_ip)
        return True


    def handle_post(self):
        """Обработка нового поста (логика не меняется)"""
        # --- Общие проверки ---
        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session.get("captcha_text")):
                flash("Неверная капча.")
                return False
        # Для поста ВАЖНО проверить и длину, и НЕПУСТОТУ комментария
        if not self.validate_comment_length():
            return False
        if not self.raw_comment.strip(): # Проверка на пустой или состоящий из пробелов комментарий
             flash("Комментарий не может быть пустым для нового поста.")
             return False

        # --- Обработка файла (обязателен для поста) ---
        file = request.files.get('fileInput')

        if not file or file.filename == '':
             flash("Для создания нового поста необходимо прикрепить файл.")
             return False

        _, ext = os.path.splitext(file.filename)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            flash("Недопустимый тип файла.")
            return False

        upload_folder = './static/post_images/'
        os.makedirs(upload_folder, exist_ok=True)

        new_filename = generate_unix_filename(file.filename)
        file_path = os.path.join(upload_folder, new_filename)
        file.save(file_path)

        thumb_created = False
        thumb_path = None # Инициализируем переменную для пути к миниатюре

        if new_filename.lower().endswith(('.jpeg', '.jpg', '.gif', '.png', '.webp')):
            thumb_path = self.create_image_thumbnail(file_path, new_filename)
            thumb_created = thumb_path is not None
        elif new_filename.lower().endswith(('.mp4', '.mov', '.webm')):
            thumb_path = self.capture_frame_from_video(file_path)
            thumb_created = thumb_path is not None
        elif new_filename.lower().endswith('.mp3'):
            thumb_path = self.create_audio_thumbnail(file_path, new_filename)
            thumb_created = thumb_path is not None

        if not thumb_created:
            flash("Ошибка создания миниатюры для файла поста.")
             # Попытаемся удалить загруженный файл, если миниатюру создать не удалось
            try:
                os.remove(file_path)
                if thumb_path and os.path.exists(thumb_path): # Удаляем и миниатюру, если она создалась частично
                     os.remove(thumb_path)
            except OSError as e:
                print(f"Error deleting file/thumb after post thumbnail failure: {e}")
            return False # Ошибка при создании миниатюры

        # --- Добавление поста в базу данных ---
        database_module.add_new_post(self.user_ip, self.board_id, self.post_name, self.comment, self.embed, new_filename)
        self.socketio.emit('nova_postagem', {'type': 'post', 'board_id': self.board_id}, broadcast=True) # Уточняем тип события
        timeout_module.timeout(self.user_ip)
        return True

#new post endpoint.
@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    socketio = current_app.extensions['socketio']
    user_ip = request.remote_addr
    post_mode = request.form.get("post_mode", "post") # По умолчанию считаем, что это пост
    post_name = request.form.get("name", "")
    board_id = request.form.get('board_id')
    comment = request.form.get('text', "")
    embed = request.form.get('embed', "")
    captcha_input = 'none'

    # --- Базовые проверки ---
    if not board_id:
        flash('Ошибка: Не указана доска.')
        return redirect(request.referrer or '/') # Возврат на предыдущую или главную

    if database_module.verify_board_captcha(board_id):
        captcha_input = request.form.get('captcha', '')
        if not captcha_input: # Добавим проверку, что капча вообще передана, если она требуется
             flash("Необходимо ввести капчу.")
             # Используем f-строку для формирования URL доски
             return redirect(request.referrer or f'/{board_id}/')

    if formatting.filter_xss(comment):
        flash('Недопустимые символы в комментарии.')
        return redirect(request.referrer or f'/{board_id}/')

    if formatting.filter_xss(post_name):
        flash('Недопустимые символы в имени.')
        return redirect(request.referrer or f'/{board_id}/')

    # --- Инициализация обработчика ---
    # Передаем исходный comment в handler, форматирование происходит внутри
    handler = PostHandler(socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input)

    # --- Проверки таймаута и доски ---
    if not handler.check_timeout():
        return redirect(request.referrer or f'/{board_id}/')
    if not handler.check_board():
        # check_board уже устанавливает flash, просто редиректим
        return redirect(request.referrer or '/') # На главную, т.к. доска не существует

    # --- Определение режима: Reply или Post ---
    is_reply = False
    reply_to = request.form.get('thread_id') # Явный ответ из формы

    # Проверка на неявный ответ через #NNN в начале комментария
    # Работаем с handler.raw_comment для проверки и очистки
    match = re.match(r'^#(\d+)', handler.raw_comment.strip())
    if match:
        potential_reply_to = match.group(1)
        # Убедимся, что пост #NNN существует НА ЭТОЙ доске
        # Предполагаем, что такая функция существует в database_module
        # Если нет, нужно ее добавить или использовать check_post_exist, но с проверкой board_id
        if database_module.check_post_exist_on_board(int(potential_reply_to), board_id): # Уточненная проверка
            reply_to = potential_reply_to
            is_reply = True
            # Очищаем #NNN из комментария, если это неявный реплай
            handler.raw_comment = re.sub(r'^#\d+\s*', '', handler.raw_comment).strip()
            # Переформатируем комментарий без #NNN
            handler.comment = formatting.format_comment(handler.raw_comment)

    # Если reply_to был установлен явно или через #NNN
    if reply_to:
        is_reply = True # Убедимся, что флаг установлен, если reply_to не пустой

    # --- Вызов соответствующего обработчика ---
    if is_reply:
        if not reply_to: # Дополнительная проверка на случай странных ошибок
            flash("Ошибка: Не указан ID треда для ответа.")
            # Редирект на доску, если ID треда потерялся
            return redirect(request.referrer or f'/{board_id}/')

        # Вызываем handle_reply, который теперь сам проверяет наличие контента
        if not handler.handle_reply(reply_to):
            # handle_reply уже установил flash при ошибке
            # Редирект обратно в тред в случае ошибки
            return redirect(f'/{board_id}/thread/{reply_to}' or request.referrer) # Явный путь к треду
        else:
             # Успешный реплай, возвращаемся в тред
             # ИСПРАВЛЕНО: Добавлен '/thread/'
             return redirect(f'/{board_id}/thread/{reply_to}' or request.referrer)

    else: # Это новый пост
        # Вызываем handle_post, который проверяет и текст, и файл
        if not handler.handle_post():
            # handle_post уже установил flash при ошибке
            return redirect(request.referrer or f'/{board_id}/') # Редирект на доску при ошибке
        else:
            # Успешный пост, возвращаемся на доску
            return redirect(f'/{board_id}/' or request.referrer) # Редирект на доску при успехе

    # --- Страховочный return (добавлен для устранения ошибки 'did not return a valid response') ---
    # Если код каким-то образом дошел сюда, значит, ни один из return выше не сработал.
    # Лучше вернуть пользователя на предыдущую страницу с сообщением об ошибке.
    flash("Произошла непредвиденная ошибка при обработке вашего запроса.")
    # Пытаемся получить board_id, который должен был быть определен выше
    # Использование board_id здесь безопасно, т.к. проверка if not board_id была в начале
    referrer_fallback = f'/{board_id}/' if board_id else '/'
    return redirect(request.referrer or referrer_fallback)


@posts_bp.route('/socket.io/')
def socket_io():
    socketio_manage(request.environ, {'/': SocketIOHandler}, request=request)