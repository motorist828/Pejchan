#imports
from flask import current_app, Blueprint, render_template, redirect, request, flash, session
from database_modules import database_module, timeout_module, formatting
from flask_socketio import SocketIO, emit
from PIL import Image
import cv2
import re
import os
import shutil
import time  # Добавлен импорт модуля времени

#bluepint register.
posts_bp = Blueprint('posts', __name__)
#socketIO call.
socketio = SocketIO()

THUMBNAIL_SIZE = (250, 250)  # Размер миниатюры
AUDIO_THUMBNAIL = 'play.jpg'  # Шаблон для аудио миниатюр

def generate_unix_filename(original_filename):
    """Генерирует имя файла на основе Unix-времени с сохранением расширения"""
    unix_time = int(time.time())
    _, ext = os.path.splitext(original_filename)
    return f"{unix_time}{ext.lower()}"

#post handling class.
class PostHandler:
    def __init__(self, socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input):
        self.socketio = socketio
        self.user_ip = user_ip
        self.post_mode = post_mode
        self.post_name = post_name
        self.board_id = board_id
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

    def validate_comment(self):
        """Валидация текста комментария"""
        if len(self.comment) >= 10000:
            flash('Превышен лимит символов.')
            return False
        if self.comment == '':
            flash('Комментарий не может быть пустым.')
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
                    # Для GIF берем только первый кадр, но сохраняем как GIF
                    try:
                        img.seek(0)  # Переходим к первому кадру
                        frame = img.copy()
                        frame.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        
                        # Конвертируем в P (palette-based) если нужно
                        if frame.mode not in ('P', 'L'):
                            frame = frame.convert('P', palette=Image.ADAPTIVE)
                        
                        # Сохраняем как статичный GIF
                        frame.save(
                            thumb_path,
                            format='GIF',
                            optimize=True,
                            transparency=0 if img.info.get('transparency') is not None else None
                        )
                    except EOFError:
                        # Если не удалось прочитать кадр, используем обычное сохранение
                        img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        img.save(thumb_path)
                else:
                    # Обычные изображения
                    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.save(thumb_path)
            
            return thumb_path
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return None
            
            return thumb_path
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
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
            
            # Изменяем расширение на .jpg для миниатюры
            base_name = os.path.splitext(filename)[0]  # Удаляем оригинальное расширение
            thumb_filename = f"thumb_{base_name}.jpg"  # Добавляем .jpg
            thumb_path = os.path.join(thumb_folder, thumb_filename)
            
            shutil.copy2(template_path, thumb_path)
            
            return thumb_path
        except Exception as e:
            print(f"Error creating audio thumbnail: {e}")
            return None

    def handle_reply(self, reply_to):
        """Обработка ответа в треде"""
        if database_module.verify_locked_thread(int(reply_to)):
            flash("Тред закрыт.")
            return False
        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session["captcha_text"]):
                flash("Неверная капча.")
                return False
                
        if 'fileInput' in request.files:
            file = request.files['fileInput']
            if file.filename != '' and file.filename.endswith(('.jpeg','.mov', '.jpg', '.gif', '.png', '.webp', '.webm', '.mp4', '.mp3')):
                upload_folder = './static/reply_images/'
                os.makedirs(upload_folder, exist_ok=True)
                
                new_filename = generate_unix_filename(file.filename)
                file.save(os.path.join(upload_folder, new_filename))
                
                if new_filename.lower().endswith(('.jpeg', '.jpg', '.gif', '.png', '.webp')):
                    self.create_image_thumbnail(os.path.join(upload_folder, new_filename), new_filename)
                elif new_filename.lower().endswith(('.mov', '.webm', '.mp4')):
                    self.capture_frame_from_video(os.path.join(upload_folder, new_filename))
                elif new_filename.lower().endswith('.mp3'):
                    self.create_audio_thumbnail(os.path.join(upload_folder, new_filename), new_filename)
                
                database_module.add_new_reply(self.user_ip, reply_to, self.post_name, self.comment, self.embed, new_filename)
                self.socketio.emit('nova_postagem', 'New Reply', broadcast=True)
                timeout_module.timeout(self.user_ip)
                return True
        
        database_module.add_new_reply(self.user_ip, reply_to, self.post_name, self.comment, self.embed, "")
        self.socketio.emit('nova_postagem', 'New Reply', broadcast=True)
        timeout_module.timeout(self.user_ip)
        return True

    def capture_frame_from_video(self, video_path):
        """Создает миниатюру из видео"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError("Error: Unable to open video.")

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_at_second = int(fps)  
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_at_second)

            ret, frame = cap.read()
            if not ret:
                raise ValueError("Error: Unable to read frame.")

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
            print(f"Error processing video: {e}")
            return None

    def handle_post(self):
        """Обработка нового поста"""
        if database_module.verify_board_captcha(self.board_id):
            if not database_module.validate_captcha(self.captcha_input, session["captcha_text"]):
                flash("Неверная капча.")
                return False
                
        if 'fileInput' in request.files and self.post_mode != 'reply':
            file = request.files['fileInput']
            if file.filename != '' and file.filename.endswith(('.jpeg', '.jpg','.mov', '.gif', '.png', '.webp', '.webm', '.mp4', '.mp3')):
                upload_folder = './static/post_images/'
                os.makedirs(upload_folder, exist_ok=True)
                
                new_filename = generate_unix_filename(file.filename)
                file.save(os.path.join(upload_folder, new_filename))
                
                if new_filename.lower().endswith(('.jpeg', '.jpg', '.gif', '.png', '.webp')):
                    self.create_image_thumbnail(os.path.join(upload_folder, new_filename), new_filename)
                elif new_filename.lower().endswith(('.mp4', '.mov', '.webm')):
                    thumb_path = self.capture_frame_from_video(os.path.join(upload_folder, new_filename))
                    if not thumb_path:
                        flash("Ошибка создания миниатюры видео.")
                        return False
                elif new_filename.lower().endswith('.mp3'):
                    thumb_path = self.create_audio_thumbnail(os.path.join(upload_folder, new_filename), new_filename)
                    if not thumb_path:
                        flash("Ошибка создания миниатюры аудио.")
                        return False
                
                database_module.add_new_post(self.user_ip, self.board_id, self.post_name, self.comment, self.embed, new_filename)
                self.socketio.emit('nova_postagem', 'New Reply', broadcast=True)
                timeout_module.timeout(self.user_ip)
                return True
        
        if self.post_mode != 'reply':
            flash("Необходимо загрузить изображение или аудиофайл.")
            return False

#new post endpoint.
@posts_bp.route('/new_post', methods=['POST'])
def new_post():
    socketio = current_app.extensions['socketio']
    user_ip = request.remote_addr
    post_mode = request.form["post_mode"]
    post_name = request.form["name"]
    board_id = request.form['board_id']
    comment = request.form['text']
    embed = request.form['embed']
    captcha_input = 'none'
    if database_module.verify_board_captcha(board_id):
        captcha_input = request.form['captcha']
    
    if formatting.filter_xss(comment):
        flash('You cant use html tags.')
        return redirect(request.referrer)
    
    if formatting.filter_xss(post_name):
        flash('You cant use html tags.')
        return redirect(request.referrer)

    handler = PostHandler(socketio, user_ip, post_mode, post_name, board_id, comment, embed, captcha_input)

    if not handler.check_timeout():
        return redirect(request.referrer)
    if not handler.check_board():
        return redirect(request.referrer)

    if post_mode == "reply":
        reply_to = request.form['thread_id']
        if not handler.validate_comment():
            return redirect(request.referrer)
        if not handler.handle_reply(reply_to):
            return redirect(request.referrer)

    match = re.match(r'^#(\d+)', comment)
    if match:
        if post_mode == "reply":
            return redirect(request.referrer)
        reply_to = match.group(1)
        if not database_module.check_post_exist(int(reply_to)):
            reply_to = request.form['thread_id']
            if reply_to == '':
                reply_to = match.group(1)
        if not handler.handle_reply(reply_to):
            return redirect(request.referrer)
    else:
        if not handler.validate_comment():
            return redirect(request.referrer)
        if not handler.handle_post():
            return redirect(request.referrer)
    return redirect(request.referrer)

@posts_bp.route('/socket.io/')
def socket_io():
    socketio_manage(request.environ, {'/': SocketIOHandler}, request=request)