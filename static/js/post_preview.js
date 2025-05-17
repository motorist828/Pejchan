// --- START OF FILE post_preview.js ---

document.addEventListener('DOMContentLoaded', function() {

    // --- Multi-Level Post Preview Logic ---
    const activePreviews = []; // Стек активных превью (элементы DOM)
    let showPreviewTimer = null;
    let hideAllPreviewsTimer = null; // Таймер для скрытия ВСЕХ превью
    const SHOW_DELAY = 250;    // ms, задержка перед показом
    const HIDE_ALL_DELAY = 600; // ms, задержка перед скрытием всех превью, если курсор ушел со всего
    let nextZIndex = 1010; // Начальный z-index для первого превью
    let mouseIsOverAnyPreviewOrTrigger = false; // Флаг, что мышь над превью или триггером

    function createPreviewElement() {
        const popup = document.createElement('div');
        popup.className = 'post-preview-popup multi-level-preview'; // Добавим класс для стилизации
        popup.style.position = 'absolute';
        popup.style.border = '1px solid var(--cor-borda)';
        popup.style.backgroundColor = 'var(--cor-fundo-claro)';
        popup.style.padding = '10px';
        popup.style.maxWidth = '800px';
        popup.style.maxHeight = '50vh';
        popup.style.overflowY = 'auto';
        popup.style.boxShadow = 'var(--shadow-dark-md)';
        popup.style.borderRadius = 'var(--border-radius-md)';
        popup.style.fontSize = '0.9em';
        popup.style.display = 'none'; // Скрыт по умолчанию
        popup.style.zIndex = nextZIndex++; // Увеличиваем z-index для каждого нового превью
        document.body.appendChild(popup);

        popup.addEventListener('mouseover', function() {
            mouseIsOverAnyPreviewOrTrigger = true;
            clearTimeout(hideAllPreviewsTimer);
            // Если есть таймер на скрытие конкретно этого превью (не реализовано), его тоже отменить
        });

        popup.addEventListener('mouseout', function(event) {
            const related = event.relatedTarget;
            // Проверяем, не перешла ли мышь на другой элемент превью или триггер
            if (!related || (!related.closest('.multi-level-preview') && !related.closest(quoteSelector))) {
                mouseIsOverAnyPreviewOrTrigger = false;
                startHideAllPreviewsTimer();
            }
        });
        return popup;
    }

    function showPostPreview(event, targetPostId, triggerElement) {
        // Перед показом нового, можно скрыть все превью, которые "глубже" (правее) текущего уровня
        // Это усложнит логику, пока просто добавляем поверх.
        // Или, если уже есть превью для этого triggerElement, просто поднять его z-index и обновить?

        const popup = createPreviewElement(); // Всегда создаем новое превью для каскада
        activePreviews.push(popup); // Добавляем в стек

        const targetPostElement = document.getElementById(String(targetPostId));

        if (targetPostElement) {
            const clonedPost = targetPostElement.cloneNode(true);

            // Очистка клона (удаляем то, что не нужно в превью)
            const innerReplies = clonedPost.querySelector('.replies');
            if (innerReplies) innerReplies.remove();

            // Refmap можно оставить, но ссылки внутри него ДОЛЖНЫ БЫТЬ активны для следующего уровня
            // Удаляем только кнопки модерации и чекбоксы из клона
            const modOptions = clonedPost.querySelectorAll('.mod-options, .thread-mod-options, .reply-mod-options');
            modOptions.forEach(opt => opt.remove());
            const checkboxes = clonedPost.querySelectorAll('input[type="checkbox"].deletionCheckBox');
            checkboxes.forEach(cb => cb.remove());

            const imagesInClone = clonedPost.querySelectorAll('.post_img, .reply_img');
            imagesInClone.forEach(img => {
                img.style.maxWidth = '140px'; // Еще меньше для вложенных
                img.style.maxHeight = '140px';
                img.style.objectFit = 'contain';
            });
            
            // Убедимся, что ссылки для цитирования внутри клона будут работать (если они не были изменены)
            // Это важно, если мы хотим открывать превью из превью.

            popup.innerHTML = clonedPost.outerHTML;
        } else {
            popup.innerHTML = `<div style="padding:10px;">Post #${targetPostId} not found.</div>`;
        }

        // Позиционирование относительно triggerElement
        const triggerRect = triggerElement.getBoundingClientRect();
        let top = triggerRect.bottom + window.scrollY + 5;
        let left = triggerRect.right + window.scrollX + 5; // Появляется правее и ниже триггера

        popup.style.display = 'block';
        const popupRect = popup.getBoundingClientRect();

        // Коррекция, чтобы не выходило за экран
        if (left + popupRect.width > window.innerWidth - 10) {
            left = triggerRect.left + window.scrollX - popupRect.width - 5; // Попробовать слева от триггера
            if (left < 5) left = 5; // Если и слева не лезет
        }
        if (top + popupRect.height > window.innerHeight + window.scrollY - 10) {
            top = triggerRect.top + window.scrollY - popupRect.height - 5; // Попробовать сверху от триггера
            if (top < window.scrollY + 5) top = window.scrollY + 5;
        }

        popup.style.left = left + 'px';
        popup.style.top = top + 'px';
    }

    function startShowTimer(event, postId, triggerElement) {
        clearTimeout(showPreviewTimer);
        showPreviewTimer = setTimeout(() => {
            showPostPreview(event, postId, triggerElement);
        }, SHOW_DELAY);
    }

    function hideAllPreviews() {
        clearTimeout(hideAllPreviewsTimer); // На всякий случай
        while(activePreviews.length > 0) {
            const popupToHide = activePreviews.pop();
            if (popupToHide && document.body.contains(popupToHide)) {
                document.body.removeChild(popupToHide);
            }
        }
        nextZIndex = 1010; // Сбрасываем z-index
        mouseIsOverAnyPreviewOrTrigger = false;
    }

    function startHideAllPreviewsTimer() {
        clearTimeout(hideAllPreviewsTimer);
        hideAllPreviewsTimer = setTimeout(() => {
            if (!mouseIsOverAnyPreviewOrTrigger) { // Скрываем, только если мышь нигде (ни на триггере, ни на превью)
                hideAllPreviews();
            }
        }, HIDE_ALL_DELAY);
    }

    const quoteSelector = 'span.quote-reply[data-id], a.refmap-link[data-post-id]';

    document.body.addEventListener('mouseover', function(event) {
        const targetTrigger = event.target.closest(quoteSelector);
        if (targetTrigger) {
            mouseIsOverAnyPreviewOrTrigger = true;
            clearTimeout(hideAllPreviewsTimer); // Отменяем глобальный таймер скрытия

            const postId = targetTrigger.dataset.id || targetTrigger.dataset.postId;
            if (postId) {
                // Если курсор перешел с одного превью на ссылку в нем же,
                // старое превью (родительское) не должно закрываться немедленно.
                // Эта логика усложняется. Пока просто показываем новое.
                startShowTimer(event, postId, targetTrigger);
            }
        }
    });

    document.body.addEventListener('mouseout', function(event) {
        const targetTrigger = event.target.closest(quoteSelector);
        if (targetTrigger) {
            clearTimeout(showPreviewTimer);
            // Проверяем, не перешла ли мышь на одно из активных превью
            let onPreview = false;
            const related = event.relatedTarget;
            if (related) {
                for (const p of activePreviews) {
                    if (p.contains(related)) {
                        onPreview = true;
                        break;
                    }
                }
            }
            if (!onPreview) { // Если мышь ушла и не на превью
                mouseIsOverAnyPreviewOrTrigger = false;
                startHideAllPreviewsTimer();
            }
        } else if (event.target.closest('.multi-level-preview')) {
            // Это событие mouseout с самого превью, оно уже обработано в createPreviewElement
        } else {
            // Мышь ушла с элемента, который не является ни триггером, ни превью
            // Если до этого она была над ними, запускаем таймер
            if (mouseIsOverAnyPreviewOrTrigger) {
                mouseIsOverAnyPreviewOrTrigger = false;
                startHideAllPreviewsTimer();
            }
        }
    });



    const logger = window.logger || { /* ... простой логгер ... */ };
});
// --- END OF FILE post_preview.js ---