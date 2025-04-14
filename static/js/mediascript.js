// Глобальные переменные для хранения состояния
window.mediaVolume = 0.5; // Начальная громкость (50%)
window.currentMediaElement = null; // Текущий медиа-элемент (видео/аудио)
window.currentModal = null; // Текущее модальное окно
window.handleKeyDown = null; // Ссылка на обработчик keydown для его удаления

// Функция для закрытия модального окна
function closeModal() {
    // Проверяем, существует ли модальное окно и прикреплено ли оно к DOM
    if (window.currentModal && window.currentModal.parentNode) {
        // Если есть медиа-элемент (видео/аудио)
        if (window.currentMediaElement) {
            // Сохраняем текущую громкость ПЕРЕД остановкой
            window.mediaVolume = window.currentMediaElement.volume;
            // Останавливаем воспроизведение
            window.currentMediaElement.pause();
            // Сбрасываем время на начало (не обязательно, но часто полезно)
            window.currentMediaElement.currentTime = 0;
            // Убираем ссылку на медиа-элемент
            window.currentMediaElement = null;
        }
        // Удаляем модальное окно из DOM
        document.body.removeChild(window.currentModal);
        // Убираем ссылку на модальное окно
        window.currentModal = null;

        // Удаляем обработчик нажатия клавиши Escape
        if (window.handleKeyDown) {
            document.removeEventListener('keydown', window.handleKeyDown);
            window.handleKeyDown = null; // Сбрасываем ссылку на обработчик
        }
    }
}

// Функция для обработки кликов по медиа-элементам
function handleMediaClick(e) {
    const element = e.target.closest('.post_img, .reply_img');
    // Если клик не по целевому элементу или его дочерним элементам, выходим
    if (!element) return;

    // Иногда ссылки могут быть внутри картинки, проверяем наличие href
    const fileUrl = element.getAttribute('href');
    if (!fileUrl) return;

    // Предотвращаем стандартное действие (переход по ссылке) и всплытие события
    e.preventDefault();
    e.stopPropagation();

    // --- Важное исправление: Закрываем ЛЮБОЕ предыдущее модальное окно ПЕРЕД созданием нового ---
    // Это предотвращает ситуации, когда старое окно не удалилось корректно
    if (window.currentModal) {
        closeModal(); // Используем общую функцию закрытия
    }
    // --- Конец исправления ---

    const thumbSrc = element.tagName === 'IMG' ? element.getAttribute('src') : null; // Получаем src только если это IMG
    const isVideo = /\.(mp4|webm)$/i.test(fileUrl); // Убрал mp3 отсюда
    const isAudio = /\.mp3$/i.test(fileUrl);

    const modal = document.createElement('div');
    modal.className = 'media-modal';
    Object.assign(modal.style, {
        position: 'fixed',
        top: '0',
        left: '0',
        width: '100%',
        height: '100%',
        backgroundColor: 'rgba(0, 0, 0, 0.9)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: '1000',
        cursor: 'pointer'
    });

    let mediaElement = null; // Локальная переменная для медиа элемента

    if (isVideo || isAudio) {
        mediaElement = document.createElement(isAudio ? 'audio' : 'video');
        mediaElement.src = fileUrl;
        mediaElement.controls = true;
        mediaElement.volume = window.mediaVolume; // Устанавливаем сохраненную громкость

        Object.assign(mediaElement.style, {
            maxWidth: '90vw',
            minWidth: isAudio ? '300px' : '350px', // Можно настроить по желанию
            maxHeight: '90vh',
            objectFit: 'contain',
            cursor: 'default' // Чтобы курсор на самом видео был обычным
        });

        // Устанавливаем постер для видео
        if (isVideo && thumbSrc) {
            mediaElement.setAttribute('poster', thumbSrc);
        }

        // Сохраняем ссылку на ТЕКУЩИЙ медиа-элемент в глобальной переменной
        window.currentMediaElement = mediaElement;

        // Обработчик изменения громкости для СОХРАНЕНИЯ
        // Используем локальную переменную mediaElement, чтобы избежать путаницы
        mediaElement.addEventListener('volumechange', function() {
            // Сохраняем только если это текущий активный элемент
            if (window.currentMediaElement === this) {
                 window.mediaVolume = this.volume;
            }
        });

        // Обработчик клика на сам медиа элемент, чтобы он не закрывал модалку
        mediaElement.addEventListener('click', (ev) => {
            ev.stopPropagation(); // Останавливаем всплытие до модального окна
        });


        modal.appendChild(mediaElement);

        // Пытаемся запустить воспроизведение после небольшой задержки
        // Добавляем проверку, что модальное окно все еще существует к моменту запуска
        setTimeout(() => {
            // Проверяем, что медиа элемент все еще принадлежит текущему модальному окну
            if (window.currentModal === modal && window.currentMediaElement === mediaElement) {
                mediaElement.play().catch(err => {
                    console.log('Autoplay was prevented or failed:', err);
                    // Можно показать кнопку Play вручную, если автоплей заблокирован
                });
            }
        }, 100); // Небольшая задержка может помочь с готовностью элемента

    } else { // Если это изображение
        const img = document.createElement('img');
        img.src = fileUrl;
        img.alt = element.alt || 'Просмотр изображения'; // Добавляем alt по умолчанию
        Object.assign(img.style, {
            maxWidth: '90vw',
            maxHeight: '90vh',
            objectFit: 'contain',
            pointerEvents: 'none' // Чтобы клики проходили сквозь картинку на фон модалки
        });
        modal.appendChild(img);
        // Для изображений нет currentMediaElement
        window.currentMediaElement = null;
    }

    // Сохраняем ссылку на ТЕКУЩЕЕ модальное окно
    window.currentModal = modal;
    document.body.appendChild(modal);

    // Обработчик клика на фон модального окна для закрытия
    // Используем closeModal напрямую
    modal.addEventListener('click', closeModal);

    // Создаем именованную функцию для обработчика keydown, чтобы ее можно было удалить
    window.handleKeyDown = (ev) => {
        if (ev.key === 'Escape') {
            closeModal();
            // Удаление обработчика теперь происходит внутри closeModal
        }
    };
    // Добавляем обработчик нажатия Escape
    document.addEventListener('keydown', window.handleKeyDown);
}

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    // --- Важное исправление: Добавляем ОДИН обработчик на весь документ ---
    // Используем делегирование событий. Этот обработчик будет ловить клики
    // по `.post_img` и `.reply_img`, даже если они добавлены динамически позже.
    document.addEventListener('click', handleMediaClick);

    // --- Важное исправление: Убираем повторное добавление обработчика в socketio ---
    // Если socketio используется для добавления новых постов,
    // делегирование событий уже позаботится о новых элементах.
    // Повторное добавление `document.addEventListener('click', handleMediaClick)`
    // при каждом новом сообщении приводило к множественным вызовам `handleMediaClick`
    // на один клик, что и могло быть причиной проблемы.
    /*
    if (typeof socketio !== 'undefined') {
        socketio.on('nova_postagem', function() {
            // НЕ НУЖНО СНОВА ДОБАВЛЯТЬ ОБРАБОТЧИК ЗДЕСЬ
            // document.addEventListener('click', handleMediaClick);
            console.log('New post arrived, click handler is already active.');
        });
    }
    */
});