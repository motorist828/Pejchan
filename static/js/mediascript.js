// <<< Начало вашего существующего кода (Глобальные переменные, closeModal) >>>

// Глобальные переменные
const storedVolume = sessionStorage.getItem('userMediaVolume');
let initialVolume = 0.5; // Громкость по умолчанию

if (storedVolume !== null) {
    const parsedVolume = parseFloat(storedVolume);
    if (!isNaN(parsedVolume) && parsedVolume >= 0 && parsedVolume <= 1) {
        initialVolume = parsedVolume;
    } else {
        sessionStorage.removeItem('userMediaVolume');
    }
}
window.mediaVolume = initialVolume;

window.currentMediaElement = null;
window.currentModal = null;
window.handleKeyDown = null;

// --- Функция очистки конкретного медиа-элемента ---
function cleanupTargetElement(targetElement) {
    if (!targetElement) return;

    // Снятие обработчиков с целевого элемента
    if (targetElement._handleMouseDown) {
        targetElement.removeEventListener('mousedown', targetElement._handleMouseDown);
        targetElement._handleMouseDown = null;
    }
    if (targetElement._handleMouseUp) {
        targetElement.removeEventListener('mouseup', targetElement._handleMouseUp);
        targetElement._handleMouseUp = null;
    }
    if (targetElement._handleClick) {
        targetElement.removeEventListener('click', targetElement._handleClick);
        targetElement._handleClick = null;
    }
    if (targetElement._handleContextMenu) { // <-- Снятие обработчика contextmenu
        targetElement.removeEventListener('contextmenu', targetElement._handleContextMenu);
        targetElement._handleContextMenu = null;
    }
     // Для media элементов снимаем обработчик volumechange
    if (targetElement.tagName === 'VIDEO' || targetElement.tagName === 'AUDIO') {
        if (targetElement._handleVolumeChange) {
            targetElement.removeEventListener('volumechange', targetElement._handleVolumeChange);
            targetElement._handleVolumeChange = null;
        }
        targetElement.pause();
        targetElement.removeAttribute('src');
        targetElement.load();
        if (window.currentMediaElement === targetElement) {
            window.currentMediaElement = null;
        }
    }
    if (targetElement.parentNode) {
        targetElement.parentNode.removeChild(targetElement);
    }
}

// --- Функция закрытия ---
function closeModal() {
    if (window.currentModal && window.currentModal.parentNode) {
        const modalToRemove = window.currentModal;

        cleanupTargetElement(modalToRemove.targetElement);
        modalToRemove.targetElement = null;

        if (modalToRemove._handleDocumentMouseMove) {
            document.removeEventListener('mousemove', modalToRemove._handleDocumentMouseMove);
            modalToRemove._handleDocumentMouseMove = null;
        }
        if (modalToRemove._handleDocumentMouseUp) {
            document.removeEventListener('mouseup', modalToRemove._handleDocumentMouseUp);
            document.removeEventListener('mouseleave', modalToRemove._handleDocumentMouseUp);
            modalToRemove._handleDocumentMouseUp = null;
        }
        if (window.handleKeyDown) {
            document.removeEventListener('keydown', window.handleKeyDown);
            window.handleKeyDown = null;
        }
        if (modalToRemove.customWheelHandler) {
            modalToRemove.removeEventListener('wheel', modalToRemove.customWheelHandler);
            modalToRemove.customWheelHandler = null;
        }
        if (modalToRemove.prevButton && modalToRemove.prevButton._clickHandler) {
            modalToRemove.prevButton.removeEventListener('click', modalToRemove.prevButton._clickHandler);
             modalToRemove.prevButton._clickHandler = null;
        }
        if (modalToRemove.nextButton && modalToRemove.nextButton._clickHandler) {
            modalToRemove.nextButton.removeEventListener('click', modalToRemove.nextButton._clickHandler);
             modalToRemove.nextButton._clickHandler = null;
        }
        if (modalToRemove.parentNode === document.body) {
             document.body.removeChild(modalToRemove);
        }
        window.currentModal = null;
        window.currentMediaElement = null;
    }
    if (window.currentMediaElement) {
        window.currentMediaElement.pause();
        window.currentMediaElement = null;
    }
}

// --- Функция открытия/обработки клика ---
function handleMediaClick(e) {
    const clickedElement = e.target.closest('.post_img, .reply_img');
    if (!clickedElement) return;

    const threadContainer = clickedElement.closest('.post');
    if (!threadContainer) return;

    let mediaItems = [];
    let currentItemIndex = -1;
    const allMediaElements = threadContainer.querySelectorAll('.post_img, .reply_img');

    allMediaElements.forEach((el, index) => {
        const url = el.getAttribute('href');
        const thumb = el.getAttribute('src');
        if (url) {
             mediaItems.push({ href: url, thumb: thumb, element: el });
             if (el === clickedElement) {
                 currentItemIndex = index;
             }
        }
    });

    if (currentItemIndex === -1 || mediaItems.length === 0) {
        console.error("Не удалось найти медиа или кликнутый элемент.");
        return;
    }

    e.preventDefault();
    e.stopPropagation();

    if (window.currentModal) closeModal();

    const modal = document.createElement('div');
    modal.className = 'media-modal';
    modal.mediaItems = mediaItems;
    modal.currentIndex = currentItemIndex;
    modal.targetElement = null;
    modal.zoomPanHandlers = {};

    Object.assign(modal.style, {
        position: 'fixed', top: '0', left: '0', width: '100%', height: '100%',
        backgroundColor: 'rgba(0, 0, 0, 0.9)', display: 'flex',
        justifyContent: 'center', alignItems: 'center', zIndex: '1000',
        cursor: 'pointer', overflow: 'hidden'
    });

    const mediaContentWrapper = document.createElement('div');
    Object.assign(mediaContentWrapper.style, {
        position: 'relative', display: 'flex', justifyContent: 'center',
        alignItems: 'center', maxWidth: '100%', maxHeight: '100%',
        pointerEvents: 'none' // Чтобы клики проходили на фон
    });
    modal.appendChild(mediaContentWrapper);
    modal.mediaContentWrapper = mediaContentWrapper;

    let currentScale = 1;
    let currentTranslateX = 0;
    let currentTranslateY = 0;
    let isDragging = false;
    let isPotentialClick = false;
    let startX, startY;
    let initialTranslateX, initialTranslateY;
    const dragThreshold = 5;
    const zoomFactor = 1.1;
    const minScale = 0.2;
    const maxScale = 7.0;

    function applyTransform() {
        if (modal.targetElement) {
            modal.targetElement.style.transform = `translate(${currentTranslateX}px, ${currentTranslateY}px) scale(${currentScale})`;
        }
    }

    modal.zoomPanHandlers.handleWheel = (wheelEvent) => {
        if (!modal.targetElement) return;
        wheelEvent.preventDefault();
        wheelEvent.stopPropagation();

        const targetElement = modal.targetElement;
        const oldScale = currentScale;
        const rect = targetElement.getBoundingClientRect();
        const mouseX = wheelEvent.clientX;
        const mouseY = wheelEvent.clientY;
        const mouseRelativeToElementX = (mouseX - rect.left - currentTranslateX) / oldScale;
        const mouseRelativeToElementY = (mouseY - rect.top - currentTranslateY) / oldScale;

        if (wheelEvent.deltaY < 0) {
            currentScale = Math.min(maxScale, currentScale * zoomFactor);
        } else {
            currentScale = Math.max(minScale, currentScale / zoomFactor);
        }

        if (Math.abs(currentScale - oldScale) > 0.001) {
            if (Math.abs(currentScale - 1) < 0.01) {
                currentScale = 1;
                currentTranslateX = 0;
                currentTranslateY = 0;
            } else {
                currentTranslateX = mouseX - rect.left - (mouseRelativeToElementX * currentScale);
                currentTranslateY = mouseY - rect.top - (mouseRelativeToElementY * currentScale);
            }
            applyTransform();
        }
        targetElement.style.cursor = currentScale > 1 ? 'grab' : 'default';
    };

    modal.zoomPanHandlers.handleTargetMouseDown = (downEvent) => {
        if (downEvent.button !== 0 || !modal.targetElement) return;
        downEvent.stopPropagation();

        isPotentialClick = true;
        isDragging = false;
        startX = downEvent.clientX;
        startY = downEvent.clientY;
        initialTranslateX = currentTranslateX;
        initialTranslateY = currentTranslateY;

        document.addEventListener('mousemove', modal._handleDocumentMouseMove);
        document.addEventListener('mouseup', modal._handleDocumentMouseUp);
        document.addEventListener('mouseleave', modal._handleDocumentMouseUp);

        if (currentScale > 1) {
            modal.targetElement.style.cursor = 'grabbing';
        }
    };

    modal._handleDocumentMouseMove = (moveEvent) => {
        if (moveEvent.buttons !== 1) {
           if(modal._handleDocumentMouseUp) modal._handleDocumentMouseUp(moveEvent);
           return;
        }
        if (!modal.targetElement) return;

        const dx = moveEvent.clientX - startX;
        const dy = moveEvent.clientY - startY;

        if (!isDragging && (Math.abs(dx) > dragThreshold || Math.abs(dy) > dragThreshold)) {
             isDragging = true;
             isPotentialClick = false;
             if (currentScale > 1 && modal.targetElement) {
                 modal.targetElement.style.cursor = 'grabbing';
             }
        }

        if (isDragging && currentScale > 1) {
            moveEvent.preventDefault();
            currentTranslateX = initialTranslateX + dx;
            currentTranslateY = initialTranslateY + dy;
            applyTransform();
        } else if (isDragging && currentScale <= 1) {
            isDragging = false;
             if (modal.targetElement) {
                modal.targetElement.style.cursor = 'default';
             }
        }
    };

    modal.zoomPanHandlers.handleTargetMouseUp = (upEvent) => {
        // Не проверяем кнопку здесь, т.к. mouseup может быть для любой кнопки
        if (!modal.targetElement) return;
        upEvent.stopPropagation();

        // Закрывать будем только если это была левая кнопка и не было drag
        const clickShouldClose = upEvent.button === 0 && isPotentialClick;

        isDragging = false;
        isPotentialClick = false; // Сбрасываем в любом случае
        modal.targetElement.style.cursor = currentScale > 1 ? 'grab' : 'default';

        // Снимаем глобальные обработчики (если они еще есть)
        if (modal._handleDocumentMouseMove) {
             document.removeEventListener('mousemove', modal._handleDocumentMouseMove);
        }
        if (modal._handleDocumentMouseUp) {
            document.removeEventListener('mouseup', modal._handleDocumentMouseUp);
            document.removeEventListener('mouseleave', modal._handleDocumentMouseUp);
        }

        if (clickShouldClose) {
            closeModal();
        }
    };

    modal._handleDocumentMouseUp = (upEvent) => {
        // Эта функция вызывается, если мышь отпустили ВНЕ элемента targetElement
        if (upEvent.type === 'mouseup' && upEvent.button !== 0 && upEvent.buttons !== 0) return; // Игнорируем не левые клики

        const wasDragging = isDragging;

        isDragging = false;
        isPotentialClick = false;

        if (modal._handleDocumentMouseMove) {
            document.removeEventListener('mousemove', modal._handleDocumentMouseMove);
        }
        if (modal._handleDocumentMouseUp) {
            document.removeEventListener('mouseup', modal._handleDocumentMouseUp);
            document.removeEventListener('mouseleave', modal._handleDocumentMouseUp);
        }

        if (wasDragging && modal.targetElement) {
            modal.targetElement.style.cursor = currentScale > 1 ? 'grab' : 'default';
        }
    };

    modal.zoomPanHandlers.handleMediaElementClick = (clickEvent) => {
         if (modal.targetElement && clickEvent.target !== modal.targetElement) {
              clickEvent.stopPropagation();
         }
    };

    // --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
    modal.zoomPanHandlers.handleTargetContextMenu = (contextEvent) => {
        // contextEvent.preventDefault(); // <<<--- УДАЛЕНО ИЛИ ЗАКОММЕНТИРОВАНО
        contextEvent.stopPropagation(); // Оставляем, чтобы предотвратить всплытие до модалки
        // Больше ничего не делаем, позволяем браузеру показать стандартное меню
    };
    // --- КОНЕЦ ИЗМЕНЕНИЯ ---

    modal.zoomPanHandlers.handleVolumeChange = function() {
        if (window.currentMediaElement === this) {
            window.mediaVolume = this.volume;
            try {
                sessionStorage.setItem('userMediaVolume', window.mediaVolume.toString());
            } catch (error) {
                console.error('[Volume] Не удалось сохранить громкость:', error);
            }
        }
    };

    function updateMediaDisplay(index) {
        if (!modal || index < 0 || index >= modal.mediaItems.length) return;

        cleanupTargetElement(modal.targetElement);
        modal.targetElement = null;
        window.currentMediaElement = null;

        currentScale = 1;
        currentTranslateX = 0;
        currentTranslateY = 0;

        const item = modal.mediaItems[index];
        const fileUrl = item.href;
        const thumbSrc = item.thumb;
        modal.currentIndex = index;

        const isVideo = /\.(mp4|webm)$/i.test(fileUrl);
        const isAudio = /\.mp3$/i.test(fileUrl);
        let newElement = null;

        if (isVideo || isAudio) {
            const mediaElement = document.createElement(isAudio ? 'audio' : 'video');
            newElement = mediaElement;
            mediaElement.src = fileUrl;
            mediaElement.controls = true;
            mediaElement.volume = window.mediaVolume;
            if (isAudio) {
                mediaElement.style.minWidth = '300px';
            }
            if (isVideo && thumbSrc) {
                mediaElement.setAttribute('poster', thumbSrc);
            }
            Object.assign(mediaElement.style, {
                display: 'block', maxWidth: '90vw', maxHeight: '90vh',
                objectFit: 'contain', transformOrigin: 'center center',
                cursor: 'default', pointerEvents: 'auto'
            });
            window.currentMediaElement = mediaElement;

            mediaElement._handleVolumeChange = modal.zoomPanHandlers.handleVolumeChange;
            mediaElement.addEventListener('volumechange', mediaElement._handleVolumeChange);

            setTimeout(() => {
                if (window.currentModal === modal && window.currentMediaElement === mediaElement) {
                    mediaElement.play().catch(err => { console.warn("Ошибка автовоспроизведения:", err)});
                }
            }, 100);

        } else {
            const img = document.createElement('img');
            newElement = img;
            img.src = fileUrl;
            img.alt = 'Просмотр изображения';
            img.draggable = false;
            Object.assign(img.style, {
                display: 'block', maxWidth: '90vw', maxHeight: '90vh',
                objectFit: 'contain', transformOrigin: 'center center',
                cursor: 'default', pointerEvents: 'auto',
                userSelect: 'none', webkitUserSelect: 'none', MozUserSelect: 'none', msUserSelect: 'none',
                userDrag: 'none', webkitUserDrag: 'none'
            });
            window.currentMediaElement = null;
        }

        modal.targetElement = newElement;

        // Добавляем обработчики
        newElement._handleMouseDown = modal.zoomPanHandlers.handleTargetMouseDown;
        newElement._handleMouseUp = modal.zoomPanHandlers.handleTargetMouseUp;
        newElement._handleClick = modal.zoomPanHandlers.handleMediaElementClick;
        newElement._handleContextMenu = modal.zoomPanHandlers.handleTargetContextMenu; // Применяем измененный обработчик

        newElement.addEventListener('mousedown', newElement._handleMouseDown);
        newElement.addEventListener('mouseup', newElement._handleMouseUp);
        newElement.addEventListener('click', newElement._handleClick);
        newElement.addEventListener('contextmenu', newElement._handleContextMenu); // Добавляем обработчик

        modal.mediaContentWrapper.innerHTML = ''; // Очищаем обертку перед добавлением
        modal.mediaContentWrapper.appendChild(newElement);

        applyTransform();
        updateNavigationArrows();
    }

    function createArrow(direction) {
        const arrow = document.createElement('div');
        arrow.className = `media-modal-nav media-modal-${direction}`;
        // Стили лучше задать в CSS для .media-modal-nav, .media-modal-prev, .media-modal-next
        Object.assign(arrow.style, {
            position: 'absolute', top: '50%', transform: 'translateY(-50%)',
            [direction === 'prev' ? 'left' : 'right']: '20px',
            fontSize: '3em', color: 'white', backgroundColor: 'rgba(0,0,0,0.3)',
            padding: '10px 5px', borderRadius: '5px', userSelect: 'none',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', pointerEvents: 'auto', zIndex: 1 // Поверх mediaContentWrapper
        });
        arrow.innerHTML = direction === 'prev' ? '<' : '>';

        const handler = (clickEvent) => {
            clickEvent.stopPropagation();
            if (direction === 'prev') navigateToPrev();
            else navigateToNext();
        };
        arrow.addEventListener('click', handler);
        arrow._clickHandler = handler;
        modal.appendChild(arrow);
        return arrow;
    }

    function navigateToPrev() {
        if (modal.mediaItems.length <= 1) return;
        const newIndex = (modal.currentIndex - 1 + modal.mediaItems.length) % modal.mediaItems.length;
        updateMediaDisplay(newIndex);
    }

    function navigateToNext() {
        if (modal.mediaItems.length <= 1) return;
        const newIndex = (modal.currentIndex + 1) % modal.mediaItems.length;
        updateMediaDisplay(newIndex);
    }

    function updateNavigationArrows() {
        if (!modal.prevButton || !modal.nextButton) return;
        const showArrows = modal.mediaItems.length > 1;
        modal.prevButton.style.display = showArrows ? 'flex' : 'none';
        modal.nextButton.style.display = showArrows ? 'flex' : 'none';
    }

    modal.prevButton = createArrow('prev');
    modal.nextButton = createArrow('next');

    updateMediaDisplay(modal.currentIndex); // Показываем первый элемент

    modal.addEventListener('wheel', modal.zoomPanHandlers.handleWheel, { passive: false });
    modal.customWheelHandler = modal.zoomPanHandlers.handleWheel;

    modal.addEventListener('click', (clickEvent) => {
        if (clickEvent.target === modal) {
             closeModal();
        }
    });

    window.handleKeyDown = (ev) => {
        if (!window.currentModal) return;
        switch (ev.key) {
            case 'Escape': closeModal(); break;
            case 'ArrowLeft': navigateToPrev(); break;
            case 'ArrowRight': navigateToNext(); break;
        }
    };
    document.addEventListener('keydown', window.handleKeyDown);

    window.currentModal = modal;
    document.body.appendChild(modal);
}

// --- Инициализация ---
document.addEventListener('DOMContentLoaded', function() {
    document.body.addEventListener('click', handleMediaClick);
});