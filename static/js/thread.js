// --- START OF FILE thread.js ---

/**
 * Форматирует специальную разметку в постах и ответах (цитаты, ссылки, спойлеры и т.д.).
 * Эта функция должна вызываться после загрузки контента и при добавлении новых постов/ответов.
 */
function manipularConteudo() {
    // Выбираем все элементы <pre>, предполагая, что контент поста/ответа находится внутри них
    var postContents = document.querySelectorAll('pre');

    postContents.forEach(function(postContent) {
        // Получаем HTML-содержимое элемента <pre>
        // ВАЖНО: работаем с innerHTML, так как форматирование добавляет HTML-теги
        var content = postContent.innerHTML;

        // --- Форматирование ссылок ---
        // [wikinet]...[/wikinet] -> <a href="https://wikinet.pro/wiki/...">...</a>
        content = content.replace(/\[wikinet\](.*?)\[\/wikinet\]/g, '<a class="wikinet-hyper-link" href="https://wikinet.pro/wiki/$1" target="_blank" rel="noopener noreferrer"><span>$1</span></a>');
        // [text](url) -> <a href="url">text</a>
        content = content.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)<]+(?:\S)*)\)/g, '<a class="hyper-link" href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

        // --- Форматирование цитат >>id ---
        content = content.split('>>').map((part, index) => { // Используем HTML entity для >>
            if (index === 0) return part;
            const numberMatch = part.match(/^\d+/);
            if (numberMatch) {
                const quotedId = numberMatch[0];
                const targetDiv = document.querySelector(`div.post[id="${quotedId}"], div.reply[id="${quotedId}"]`);
                const isOperator = targetDiv && targetDiv.classList.contains('post') && targetDiv.getAttribute('post-role') === 'operator';
                const quoteSpan = `<span class="quote-reply" data-id="${quotedId}">>>${quotedId}</span>`;
                const operatorSpan = isOperator ? `<span class="operator-quote">(OP)</span>` : '';
                return `${quoteSpan}${operatorSpan}${part.slice(quotedId.length)}`;
            }
            return `>>${part}`;
        }).join('');

        // --- Форматирование зеленых строк >text ---
        content = content.split('>').map((part, index) => { // Используем HTML entity для >
            if (index === 0) return part;
            const textMatch = part.match(/^[^<&\n]+/);
            if (textMatch && textMatch[0].trim() !== '') {
                return `<span class="verde">>${textMatch[0]}</span>${part.slice(textMatch[0].length)}`;
            }
            return `>${part}`;
        }).join('');

        // --- Форматирование красных строк <text ---
        content = content.split('<').map((part, index) => { // Используем HTML entity для <
            if (index === 0) return part;
            const textMatch = part.match(/^[^<&\n]+/);
             if (textMatch && textMatch[0].trim() !== '') {
                return `<span class="vermelho"><${textMatch[0]}</span>${part.slice(textMatch[0].length)}`;
            }
            return `<${part}`;
        }).join('');

        // --- Форматирование обнаруженного текста (((text))) ---
        content = content.split('(((').map((part, index) => {
            if (index === 0) return part;
            const match = part.match(/^([^\)]+)\)\)\)(.*)/s);
            if (match) {
                return `<span class="detected">(((${match[1]})))</span>${match[2]}`;
            }
            return `(((${part}`;
        }).join('');

        // --- Форматирование красного текста ==text== ---
        content = content.split('==').map((part, index) => {
            if (index % 2 === 1) return `<span class="red-text">${part}</span>`;
            return part;
        }).join('');

        // --- Форматирование спойлеров ||text|| ---
        content = content.split('||').map((part, index) => {
            if (index % 2 === 1) return `<span class="spoiler">${part}</span>`;
            return part;
        }).join('');

        // --- Форматирование спойлеров [spoiler]text[/spoiler] ---
        content = content.replace(/\[spoiler\]/gi, '<span class="spoiler">')
                         .replace(/\[\/spoiler\]/gi, '</span>');

        // --- Форматирование радужного текста [r]text[/r] ---
        content = content.replace(/\[r\]/gi, '<span class="rainbowtext">')
                         .replace(/\[\/r\]/gi, '</span>');

        // Применяем измененное содержимое обратно к элементу <pre>
        postContent.innerHTML = content;
    });

    // После форматирования добавляем обработчики событий к новым элементам цитат
    adicionarEventosQuoteReply();
}


/**
 * Добавляет обработчики событий (клик и наведение) к элементам цитат (>>id).
 */
function adicionarEventosQuoteReply() {
    const quoteReplies = document.querySelectorAll('.quote-reply');
    let previewElement = null; // Хранит текущий элемент превью
    let updatePreviewPositionListener = null; // Хранит ссылку на обработчик движения мыши

    quoteReplies.forEach(span => {
        // --- Обработчик клика по цитате ---
        span.addEventListener('click', (event) => {
            event.preventDefault();
            const targetId = span.getAttribute('data-id');
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                document.querySelectorAll('.highlighted-quote').forEach(el => {
                    el.classList.remove('highlighted-quote');
                });
                targetElement.classList.add('highlighted-quote');
                setTimeout(() => {
                    if (targetElement.classList.contains('highlighted-quote')) {
                        targetElement.classList.remove('highlighted-quote');
                    }
                }, 2500);
                const offset = 80;
                const elementPosition = targetElement.getBoundingClientRect().top + window.scrollY;
                const offsetPosition = elementPosition - offset;
                window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
            } else {
                console.warn(`Элемент с ID "${targetId}" не найден для цитаты.`);
            }
        });

        // --- Обработчик наведения мыши на цитату (показ превью) ---
        span.addEventListener('mouseenter', (event) => {
            if (previewElement && document.body.contains(previewElement)) {
                document.body.removeChild(previewElement);
                if(updatePreviewPositionListener) {
                    document.removeEventListener('mousemove', updatePreviewPositionListener);
                }
            }

            const targetId = span.getAttribute('data-id');
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                previewElement = targetElement.cloneNode(true);
                const repliesBlock = previewElement.querySelector('div.replies');
                if (repliesBlock) repliesBlock.remove();
                previewElement.classList.add('quote-preview');
                previewElement.classList.remove('highlighted-quote');
                previewElement.style.backgroundColor = '';
                previewElement.style.borderColor = '';
                previewElement.style.position = 'absolute';
                previewElement.style.zIndex = '1000';
                previewElement.style.display = 'block';
                previewElement.style.maxWidth = '400px';
                document.body.appendChild(previewElement);

                updatePreviewPositionListener = (e) => {
                    let left = e.pageX + 15;
                    let top = e.pageY + 15;
                    if (left + previewElement.offsetWidth > window.innerWidth) {
                        left = e.pageX - previewElement.offsetWidth - 15;
                    }
                    if (top + previewElement.offsetHeight > window.innerHeight + window.scrollY) {
                       top = e.pageY - previewElement.offsetHeight - 15;
                    }
                    if (left < 0) left = 0;
                    if (top < window.scrollY) top = window.scrollY;
                    previewElement.style.left = `${left}px`;
                    previewElement.style.top = `${top}px`;
                };
                updatePreviewPositionListener(event);
                document.addEventListener('mousemove', updatePreviewPositionListener);
            }
        });

        // --- Обработчик ухода мыши с цитаты (удаление превью) ---
        span.addEventListener('mouseleave', () => {
            if (previewElement && document.body.contains(previewElement)) {
                document.body.removeChild(previewElement);
                previewElement = null;
            }
            if(updatePreviewPositionListener) {
                document.removeEventListener('mousemove', updatePreviewPositionListener);
                updatePreviewPositionListener = null;
            }
        });
    });
}

/**
 * Вставляет ID поста/ответа в текстовое поле формы ответа.
 * Вызывается при клике на ID поста/ответа.
 * @param {string|number} postId - ID поста или ответа для цитирования.
 */
function quotePostId(postId) {
    const textarea = document.getElementById('text'); // ID текстового поля
    if (!textarea) {
        console.error('Текстовое поле с ID "text" не найдено.');
        return;
    }
    const quoteText = '>>' + postId;
    const currentText = textarea.value;
    const textToInsert = (currentText ? '\n' : '') + quoteText + '\n';
    if (textarea.selectionStart || textarea.selectionStart === 0) {
        const startPos = textarea.selectionStart;
        const endPos = textarea.selectionEnd;
        textarea.value = currentText.substring(0, startPos) + textToInsert + currentText.substring(endPos, currentText.length);
        textarea.selectionStart = textarea.selectionEnd = startPos + textToInsert.length;
    } else {
        textarea.value += textToInsert;
    }
    textarea.focus();
}


// --- Обработчики событий после загрузки DOM ---

// Обработчик для кнопки "Quote Selection"
document.addEventListener("DOMContentLoaded", function() {
    const textarea = document.getElementById('text');
    let quoteButton = null;

    document.addEventListener('mouseup', (event) => {
        if (quoteButton && quoteButton.contains(event.target)) return;
        const formElement = document.getElementById('postForm'); // ID вашей формы
        if (formElement && formElement.contains(event.target)) return;

        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (selectedText) {
            if (!quoteButton) {
                quoteButton = document.createElement('button');
                quoteButton.type = 'button';
                quoteButton.className = 'quote-selection-button';
                quoteButton.innerText = 'Quote Selection';
                quoteButton.style.position = 'absolute';
                quoteButton.style.zIndex = '1010';
                quoteButton.style.display = 'none';
                document.body.appendChild(quoteButton);

                quoteButton.addEventListener('click', () => {
                    const currentText = textarea.value;
                    const textToInsert = selectedText.split('\n').map(line => '>' + line).join('\n');
                    const finalText = (currentText ? currentText + '\n' : '') + textToInsert + '\n';
                    textarea.value = finalText;
                    textarea.focus();
                    quoteButton.style.display = 'none';
                    window.getSelection().removeAllRanges();
                });
            }

            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            quoteButton.style.left = `${rect.left + window.scrollX + 5}px`;
            quoteButton.style.top = `${rect.top + window.scrollY - quoteButton.offsetHeight - 5}px`;

            requestAnimationFrame(() => {
                quoteButton.style.display = 'block';
            });
        } else if (quoteButton) {
            quoteButton.style.display = 'none';
        }
    });

    document.addEventListener('mousedown', (e) => {
        if (quoteButton && quoteButton.style.display === 'block' && !quoteButton.contains(e.target)) {
            const selection = window.getSelection();
             if (!selection.toString().trim()) {
                quoteButton.style.display = 'none';
             }
        }
    });
});


// Обработчик для форматирования дат
document.addEventListener('DOMContentLoaded', function() {

    const twelveHoursInMs = 12 * 60 * 60 * 1000;
    const minutesInMs = 60 * 1000;
    const hoursInMs = 60 * minutesInMs;

    /**
     * Форматирует дату как относительное время или полную дату.
     * @param {Date} dateObject - Объект Date для форматирования.
     * @returns {string|null} - Строка относительного времени или null.
     */
    function formatRelativeTime(dateObject) {
        const now = new Date();
        const diffInMs = now.getTime() - dateObject.getTime();

        if (diffInMs > twelveHoursInMs) return null; // Старше 12 часов

        const diffInSeconds = Math.round(diffInMs / 1000);
        const diffInMinutes = Math.round(diffInMs / minutesInMs);
        const diffInHours = Math.round(diffInMs / hoursInMs);

        if (diffInSeconds < 60) return "just now";
        if (diffInMinutes < 60) return `${diffInMinutes} ${diffInMinutes === 1 ? 'minute' : 'minutes'} ago`;
        return `${diffInHours} ${diffInHours === 1 ? 'hour' : 'hours'} ago`;
    }

    /**
     * Обновляет текстовое содержимое элемента с датой.
     * @param {HTMLElement} element - Элемент span.postDate.
     */
    function formatDate(element) {
        const isoDateString = element.dataset.isoDate;
        if (!isoDateString) return;

        try {
            const date = new Date(isoDateString);
            if (isNaN(date.getTime())) {
                 console.error('Invalid date value:', isoDateString);
                 element.textContent = "Invalid Date";
                 return;
            }

            const relativeTimeString = formatRelativeTime(date);

            if (relativeTimeString !== null) {
                element.textContent = relativeTimeString;
                // Форматируем полную дату для title
                const fullDateFormatter = new Intl.DateTimeFormat('ru-RU', { // Локаль для title
                   dateStyle: 'medium', // e.g., "1 мая 2025 г."
                   timeStyle: 'medium'  // e.g., "03:45:10"
                });
                element.title = fullDateFormatter.format(date);
            } else {
                // Форматируем полную дату для отображения
                const fullDateFormatter = new Intl.DateTimeFormat('ru-RU', { // Локаль для отображения
                    day: '2-digit', month: '2-digit', year: 'numeric',
                    hour: '2-digit', minute: '2-digit', second: '2-digit',
                    // timeZone: 'Europe/Moscow' // Раскомментируйте для конкретного пояса
                });
                element.textContent = fullDateFormatter.format(date);
                element.title = ''; // Убираем title
            }
        } catch (e) {
            console.error('Date formatting error:', e);
            element.textContent = "Error";
        }
    }

    /**
     * Обновляет все видимые даты на странице.
     */
    function updateAllDates() {
        document.querySelectorAll('span.postDate[data-iso-date]').forEach(formatDate);
    }

    /**
     * Наблюдатель за изменениями DOM для новых элементов.
     */
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) {
                    if (node.matches && node.matches('span.postDate[data-iso-date]')) {
                        formatDate(node);
                    }
                    if (node.querySelectorAll) {
                        node.querySelectorAll('span.postDate[data-iso-date]').forEach(formatDate);
                    }
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Первоначальное форматирование
    updateAllDates();

    // Периодическое обновление (каждые 30 секунд)
    setInterval(updateAllDates, 30000);

}); // Конец обработчика DOMContentLoaded для дат


// Обработчик для чекбоксов модерации
document.addEventListener('DOMContentLoaded', function() {
    document.body.addEventListener('change', function(event) {
        // 1. Проверяем, что событие произошло на нужном чекбоксе (по классу и ID)
        if (event.target.matches('input.deletionCheckBox[id^="togglemodoptions_"]')) {
            const checkbox = event.target;
            // 2. Ищем КОНКРЕТНОГО родителя по классу
            const postInfoDiv = checkbox.closest('.postInfo, .reply-postInfo');
            if (postInfoDiv) {
                // 3. Ищем блок опций модерации по КЛАССУ ВНУТРИ этого родителя
                const modOptions = postInfoDiv.querySelector('.thread-mod-options, .reply-mod-options');

                if (modOptions) {
                    // 4. Устанавливаем display: 'flex' (как в старом коде) или 'none'
                    modOptions.style.display = checkbox.checked ? 'flex' : 'none';
                } else {
                     // Если опции не найдены ВНУТРИ .postInfo/.reply-postInfo
                     console.warn('Блок опций модерации (.thread-mod-options или .reply-mod-options) не найден ВНУТРИ:', postInfoDiv);
                }
            } else {
                 console.warn('Родительский div (.postInfo или .reply-postInfo) не найден для чекбокса:', checkbox);
            }
        }
    });
});

// --- END OF FILE thread.js ---