# --- START OF FILE app.py ---
from flask import Flask, render_template, session, redirect, url_for, request
from flask_socketio import SocketIO
import os
import logging
from datetime import timedelta # Для настройки времени жизни сессии

# --- Импорт блюпринтов ---
from blueprints.auth_bp import auth_bp
from blueprints.boards_bp import boards_bp
from blueprints.posts_bp import posts_bp
# Добавьте другие блюпринты, если они есть

# --- Конфигурация логирования ---
# Можно настроить более детально, если требуется
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Создание экземпляра Flask ---
app = Flask(__name__)

# --- Конфигурация приложения ---
# Секретный ключ для сессий (ВАЖНО: измените на свой случайный ключ!)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'your_very_secret_random_key_here_change_me')
# Время жизни сессии
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7) # Например, 7 дней

# Настройки для загрузки файлов (опционально, если нужны глобальные)
# app.config['UPLOAD_FOLDER'] = 'static/uploads' # Пример
# app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB, соответствует Nginx

# --- Инициализация SocketIO ---
# Для Gunicorn с несколькими worker'ами и SocketIO рекомендуется использовать
# message queue (например, Redis или RabbitMQ) для синхронизации.
# Если у вас один worker или вы тестируете, можно оставить без message_queue.
# async_mode можно установить в 'threading', 'eventlet', или 'gevent'.
# Gunicorn обычно хорошо работает с 'gevent' или 'eventlet', если они установлены.
# Для 'gevent' или 'eventlet' Gunicorn нужно запускать с соответствующим worker_class.
socketio_async_mode = os.environ.get('SOCKETIO_ASYNC_MODE', None) # e.g., 'gevent'
socketio_message_queue = os.environ.get('SOCKETIO_MESSAGE_QUEUE', None) # e.g., 'redis://localhost:6379/0'

socketio = SocketIO(app, async_mode='gevent', message_queue=socketio_message_queue)
logger.info(f"SocketIO initialized. Async mode: {socketio.async_mode}, Message queue: {socketio_message_queue or 'Not used'}")


# --- Регистрация блюпринтов ---
app.register_blueprint(auth_bp)
app.register_blueprint(boards_bp)
app.register_blueprint(posts_bp) # Добавил префикс для примера, если нужно
# Замените '/posts' на актуальный префикс или уберите, если он не нужен.
# Если в posts_bp роут /new_post, то с префиксом он станет /posts/new_post
# Если блюпринты уже имеют свои префиксы, этот url_prefix не нужен.

# --- Обработчики ошибок (глобальные, если не переопределены в блюпринтах) ---
@app.errorhandler(404)
def page_not_found_global(e):
    logger.warning(f"Global 404 error: {request.path} - {e}")
    # Можно отрендерить общий шаблон 404 или вернуть JSON
    return render_template('errors/404.html', error=e, message="Page not found (Global Handler)."), 404

@app.errorhandler(500)
def internal_server_error_global(e):
    logger.error(f"Global 500 error: {request.path}", exc_info=e)
    return render_template('errors/500.html', error=e, error_message="An internal server error occurred (Global Handler)."), 500

# --- Базовый роут (если нужен) ---
@app.route('/health')
def health_check():
    return "OK", 200

# --- Запуск для разработки (не используется Gunicorn'ом) ---
# Gunicorn импортирует объект `app` и сам запускает сервер.
# Этот блок `if __name__ == '__main__':` нужен только для локального запуска
# через `python app.py`.
if __name__ == '__main__':
    logger.info("Запуск Flask development server...")
    # При локальном запуске используйте Flask's development server
    # host='0.0.0.0' делает сервер доступным по IP адресу машины
    # debug=True включает режим отладки (не для продакшена!)
    # use_reloader=True автоматически перезапускает сервер при изменениях кода
    # Для SocketIO лучше использовать socketio.run
    socketio.run(app, host='0.0.0.0', port=3000, debug=True, use_reloader=True, allow_unsafe_werkzeug=True)
    # app.run(host='0.0.0.0', port=5000, debug=True) # Стандартный запуск без SocketIO

# --- END OF FILE app.py ---
