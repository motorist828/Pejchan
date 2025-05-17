// --- START OF FILE thread.js ---

// Функция для вставки цитаты в текстовое поле
function insertQuoteIntoTextarea(textToQuote, isSelectionQuote = false, targetPostId = null) {
    // ... (код функции без изменений, как в предыдущем ответе) ...
    const textarea = document.getElementById('text') || document.getElementById('shampoo') || document.getElementById('qr-shampoo');
    if (!textarea) {
        console.warn("Textarea for quoting not found in insertQuoteIntoTextarea.");
        return;
    }
    let textToInsert;
    if (isSelectionQuote) {
        textToInsert = textToQuote.split('\n').map(line => '> ' + line).join('\n') + '\n\n';
    } else if (targetPostId) {
        textToInsert = '>>' + targetPostId + '\n';
    } else {
        return;
    }
    const currentTextareaValue = textarea.value;
    let separator = "";
    if (currentTextareaValue.trim() !== "") {
        separator = currentTextareaValue.endsWith('\n\n') ? "" : (currentTextareaValue.endsWith('\n') ? "\n" : "\n\n");
    }
    const finalTextToInsert = separator + textToInsert;
    if (typeof textarea.selectionStart === 'number' && typeof textarea.selectionEnd === 'number') {
        const startPos = textarea.selectionStart;
        const endPos = textarea.selectionEnd;
        const scrollTop = textarea.scrollTop;
        textarea.value = currentTextareaValue.substring(0, startPos) + finalTextToInsert + currentTextareaValue.substring(endPos);
        const newCursorPos = startPos + finalTextToInsert.length;
        textarea.focus();
        textarea.setSelectionRange(newCursorPos, newCursorPos);
        textarea.scrollTop = scrollTop;
    } else {
        textarea.value += finalTextToInsert;
        textarea.focus();
    }
    textarea.scrollTop = textarea.scrollHeight;
}

// Функция для добавления маркера (OP) к цитатам
function enhanceQuotesWithOpMarker(parentElement) {
    // ... (код функции без изменений, как в предыдущем ответе) ...
    const contentElements = parentElement.querySelectorAll('.post_content pre, .reply_content pre');
    contentElements.forEach(contentElement => {
        if (contentElement.dataset.opQuotesEnhanced) return;
        const quoteSpans = contentElement.querySelectorAll('span.quote-reply');
        quoteSpans.forEach(quoteSpan => {
            const quotedId = quoteSpan.dataset.id;
            if (quotedId) {
                const isOperatorPost = document.querySelector(`div.post[id="${quotedId}"][post-role="operator"]`);
                if (isOperatorPost) {
                    const nextSibling = quoteSpan.nextSibling;
                    if (!nextSibling || !(nextSibling.nodeType === Node.ELEMENT_NODE && nextSibling.classList.contains('operator-quote-marker'))) {
                        const operatorMarker = document.createElement('span');
                        operatorMarker.className = 'operator-quote-marker';
                        operatorMarker.textContent = ' (OP)';
                        quoteSpan.parentNode.insertBefore(operatorMarker, quoteSpan.nextSibling);
                    }
                }
            }
        });
        contentElement.dataset.opQuotesEnhanced = 'true';
    });
}

// --- НОВАЯ ФУНКЦИЯ ДЛЯ ИНТЕРАКТИВНЫХ ЦИТАТ (ПОДСВЕТКА И СКРОЛЛ) ---
function initializeQuoteReplyInteractions(parentElement) {
    // Ищем оба типа ссылок: span.quote-reply И a.refmap-link с data-post-id
    // Также можно добавить и другие селекторы, если есть еще типы ссылок на посты
    const clickableQuoteLinks = parentElement.querySelectorAll(
        'span.quote-reply[data-id], a.post-link.refmap-link[data-post-id]'
    );

    clickableQuoteLinks.forEach(linkElement => {
        // Проверяем, не был ли обработчик уже добавлен этому элементу
        if (linkElement.dataset.quoteClickHandlerAdded) {
            return;
        }

        linkElement.addEventListener('click', (event) => {
            event.preventDefault(); // Предотвращаем стандартное действие для <a> (переход по якорю)
                                   // чтобы наша плавная прокрутка работала без конфликтов

            let targetId = null;
            if (linkElement.matches('span.quote-reply')) {
                targetId = linkElement.getAttribute('data-id');
            } else if (linkElement.matches('a.refmap-link')) {
                targetId = linkElement.getAttribute('data-post-id');
                // Как запасной вариант, если data-post-id нет, можно попробовать извлечь из href
                if (!targetId && linkElement.hash) { // linkElement.hash вернет "#57"
                    targetId = linkElement.hash.substring(1); // Убираем '#'
                }
            }

            if (!targetId) {
                console.warn("Could not determine target ID from quote link:", linkElement);
                return;
            }

            // Ищем элемент с ID как в посте, так и в ответе
            const targetElement = document.getElementById(targetId); // Это может быть div.post или div.reply

            if (targetElement) {
                // Убираем подсветку со всех ранее подсвеченных элементов
                document.querySelectorAll('.highlighted-quote-target').forEach(el => {
                    el.classList.remove('highlighted-quote-target');
                });

                // Добавляем класс для подсветки
                targetElement.classList.add('highlighted-quote-target');

                // Убираем подсветку через некоторое время
                setTimeout(() => {
                    targetElement.classList.remove('highlighted-quote-target');
                }, 500);

                // Плавная прокрутка с отступом сверху
                const navbarElement = document.querySelector('.navbar'); // Предполагаем, что навбар имеет класс .navbar
                const navbarHeight = navbarElement ? navbarElement.offsetHeight : 0;
                const offset = navbarHeight + 20; // Отступ = высота навбара + еще немного
                
                // Вычисляем позицию элемента относительно верха документа
                const bodyRect = document.body.getBoundingClientRect();
                const elementRect = targetElement.getBoundingClientRect();
                const elementPosition = elementRect.top - bodyRect.top; // Позиция элемента от верха документа
                
                const offsetPosition = elementPosition - offset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            } else {
                console.warn(`Quoted element with ID "${targetId}" not found.`);
            }
        });
        // Помечаем, что обработчик добавлен
        linkElement.dataset.quoteClickHandlerAdded = 'true';
    });
}
// --- КОНЕЦ НОВОЙ ФУНКЦИИ ДЛЯ ИНТЕРАКТИВНЫХ ЦИТАТ ---


document.addEventListener("DOMContentLoaded", function() {
    // --- Логика кнопки "Quotar" при выделении текста ---
    // ... (существующий код кнопки "Quotar" без изменений) ...
    const textareaForQuoteButton = document.getElementById('text') || document.getElementById('shampoo') || document.getElementById('qr-shampoo');
    let quoteButton = null;
    document.addEventListener('mouseup', (event) => {
        if ((textareaForQuoteButton && textareaForQuoteButton.contains(event.target)) || (quoteButton && quoteButton.contains(event.target))) {
            if (quoteButton && event.target !== quoteButton && window.getSelection().toString().trim() === "") {
                quoteButton.style.display = 'none';
            }
            return;
        }
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        if (selectedText) {
            if (!quoteButton) {
                quoteButton = document.createElement('button');
                quoteButton.className = 'quote-button';
                quoteButton.type = 'button';
                quoteButton.textContent = 'Quote Selected';
                document.body.appendChild(quoteButton);
                quoteButton.addEventListener('click', (clickEvent) => {
                    clickEvent.stopPropagation();
                    insertQuoteIntoTextarea(selectedText, true);
                    quoteButton.style.display = 'none';
                    window.getSelection().removeAllRanges();
                });
            }
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            let buttonLeft = rect.right + window.scrollX + 5;
            let buttonTop = rect.top + window.scrollY + (rect.height / 2) - (quoteButton.offsetHeight / 2);
            const buttonWidth = quoteButton.offsetWidth;
            const buttonHeight = quoteButton.offsetHeight;
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;
            if (buttonLeft + buttonWidth > viewportWidth + window.scrollX - 10) {
                buttonLeft = rect.left + window.scrollX - buttonWidth - 10;
            }
            if (buttonTop < window.scrollY + 5) { buttonTop = window.scrollY + 5; }
            if (buttonTop + buttonHeight > viewportHeight + window.scrollY - 5) {
                buttonTop = viewportHeight + window.scrollY - buttonHeight - 5;
            }
            if (buttonLeft < window.scrollX + 5) { buttonLeft = window.scrollX + 5; }
            quoteButton.style.left = `${buttonLeft}px`;
            quoteButton.style.top = `${buttonTop}px`;
            quoteButton.style.display = 'block';
        } else if (quoteButton && event.target !== quoteButton) {
            quoteButton.style.display = 'none';
        }
    });
    document.addEventListener('mousedown', (event) => {
        if (quoteButton && quoteButton.style.display === 'block' && event.target !== quoteButton) {
            if (!window.getSelection() || window.getSelection().toString().trim() === "") {
                 quoteButton.style.display = 'none';
            }
        }
    });

    // --- Логика форматирования дат ---
    // ... (существующий код форматирования дат без изменений) ...
    const twelveHoursInMs = 12 * 60 * 60 * 1000;
    const minutesInMs = 60 * 1000;
    const hoursInMs = 60 * minutesInMs;
    function formatRelativeTime(dateObject) {
        const now = new Date(); const diffInMs = now.getTime() - dateObject.getTime();
        if (diffInMs < 0 || diffInMs > twelveHoursInMs) return null;
        const diffInSeconds = Math.round(diffInMs / 1000);
        const diffInMinutes = Math.round(diffInMs / minutesInMs);
        const diffInHours = Math.round(diffInMs / hoursInMs);
        if (diffInSeconds < 60) return "just now";
        if (diffInMinutes < 60) return `${diffInMinutes} ${diffInMinutes === 1 ? 'minute' : 'minutes'} ago`;
        return `${diffInHours} ${diffInHours === 1 ? 'hour' : 'hours'} ago`;
    }
    function formatDateElement(element) {
        const isoDateString = element.dataset.isoDate; if (!isoDateString) return;
        try {
            const date = new Date(isoDateString); if (isNaN(date.getTime())) { element.textContent = "Invalid Date"; return; }
            const relativeTimeString = formatRelativeTime(date);
            const langAttr = document.documentElement.lang || 'en-US';
            if (relativeTimeString !== null) {
                element.textContent = relativeTimeString;
                const fullDateFormatter = new Intl.DateTimeFormat(langAttr, { dateStyle: 'medium', timeStyle: 'medium', hour12: false });
                element.title = fullDateFormatter.format(date);
            } else {
                const fullDateFormatter = new Intl.DateTimeFormat(langAttr, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                element.textContent = fullDateFormatter.format(date); element.title = '';
            }
        } catch (e) { console.error('Date formatting error:', e, "for string:", isoDateString, "in element:", element); element.textContent = "Error"; }
    }
    function updateAllDates() { document.querySelectorAll('span.postDate[data-iso-date]').forEach(formatDateElement); }


    // --- MutationObserver для дат, цитат OP И ИНТЕРАКТИВНЫХ ЦИТАТ ---
    const postsContainer = document.getElementById('posts_board') || document.body;
    const contentObserver = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) { // Только элементы узлов
                    // Обновление дат
                    if (node.matches && node.matches('span.postDate[data-iso-date]')) { formatDateElement(node); }
                    if (node.querySelectorAll) { node.querySelectorAll('span.postDate[data-iso-date]').forEach(formatDateElement); }

                    // Обновление цитат OP
                    enhanceQuotesWithOpMarker(node);

                    // Инициализация интерактивных цитат
                    initializeQuoteReplyInteractions(node);
                }
            });
        });
    });
    contentObserver.observe(postsContainer, { childList: true, subtree: true });

    // Первоначальное форматирование/инициализация
    updateAllDates();
    enhanceQuotesWithOpMarker(postsContainer);
    initializeQuoteReplyInteractions(postsContainer); // Инициализируем для существующих цитат

    setInterval(updateAllDates, 30 * 1000);
    // enhanceQuotesWithOpMarker и initializeQuoteReplyInteractions не нужно вызывать по интервалу,
    // только при добавлении нового контента через MutationObserver.

    // --- Обработчик для чекбоксов модерации ---
    // ... (существующий код обработчика чекбоксов без изменений) ...
    document.body.addEventListener('change', function(event) {
        if (event.target.matches('input.deletionCheckBox[id^="togglemodoptions_"]')) {
            const checkbox = event.target;
            const postInfoContainer = checkbox.closest('.postInfo, .reply-postInfo');
            if (postInfoContainer) {
                const modOptions = postInfoContainer.querySelector('.thread-mod-options, .reply-mod-options');
                if (modOptions) { modOptions.style.display = checkbox.checked ? 'flex' : 'none'; }
                 else { console.warn('Блок опций модерации (.mod-options) не найден внутри:', postInfoContainer); }
            } else { console.warn('Родительский div (.postInfo или .reply-postInfo) не найден для чекбокса:', checkbox); }
        }
    });
});
// --- END OF FILE thread.js ---