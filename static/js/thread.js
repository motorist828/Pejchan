function manipularConteudo() {
    var postContents = document.querySelectorAll('pre');

    postContents.forEach(function(postContent) {
        var content = postContent.innerHTML;

        content = content.replace(/\[wikinet\](.*?)\[\/wikinet\]/g, '<a class="wikinet-hyper-link" href="https://wikinet.pro/wiki/$1" target="_blank"><span>$1</span></a>');

        content = content.replace(/\[([^\]]+)\]\((https?:\/\/[^\s]+(?:\S)*)\)/g, '<a class="hyper-link" href="$2">$1</a>');

        content = content.split('&gt;&gt;').map((part, index) => {
            if (index === 0) return part;
            const number = part.match(/^\d+/);
            if (number) {
                const quotedId = number[0];
                const quotedDiv = document.querySelector(`div[id="${quotedId}"]`);
                const isOperator = quotedDiv && quotedDiv.getAttribute('post-role') === 'operator';

                const quoteSpan = `<span class="quote-reply" data-id="${quotedId}">&gt;&gt;${quotedId}</span>`;
                const operatorSpan = isOperator ? `<span class="operator-quote">(OP)</span>` : '';
                return `${quoteSpan}${operatorSpan}${part.slice(quotedId.length)}`;
            }
            return `&gt;&gt;${part}`;
        }).join('');

        content = content.split('&gt;').map((part, index) => {
            if (index === 0) return part;
            const match = part.match(/^[^<&\n]+/);
            return match ? `<span class="verde">&gt;${match}</span>${part.slice(match[0].length)}` : `&gt;${part}`;
        }).join('');

        content = content.split('&lt;').map((part, index) => {
            if (index === 0) return part;
            const match = part.match(/^[^<&\n]+/);
            return match ? `<span class="vermelho">&lt;${match}</span>${part.slice(match[0].length)}` : `&lt;${part}`;
        }).join('');

        content = content.split('(((').map((part, index) => {
            if (index === 0) return part;
            const match = part.match(/^([^\)]+)\)\)\)(.*)/);
            return match ? `<span class="detected">(((${match[1]})))</span>${match[2]}` : `(((${part}`;
        }).join('');

        content = content.split('==').map((part, index) => {
            if (index % 2 === 1) return `<span class="red-text">${part}</span>`;
            return part;
        }).join('');

        content = content.split('||').map((part, index) => {
            if (index % 2 === 1) return `<span class="spoiler">${part}</span>`;
            return part;
        }).join('');

        content = content.split('[spoiler]').join('<span class="spoiler">').split('[/spoiler]').join('</span>');

        content = content.split('[r]').join('<span class="rainbowtext">').split('[/r]').join('</span>');

        postContent.innerHTML = content;
    });
    adicionarEventosQuoteReply();
}


function adicionarEventosQuoteReply() {

    const quoteReplies = document.querySelectorAll('.quote-reply');

    quoteReplies.forEach(span => {
        span.addEventListener('click', () => {
            const targetId = span.getAttribute('data-id');
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                document.querySelectorAll('.target').forEach(el => {
                    el.style.backgroundColor = '';
                });

                targetElement.style.backgroundColor = '#6d99ba73';
                targetElement.style.borderColor = '#82cece';

                setTimeout(() => {
                    targetElement.style.backgroundColor = '';
                    targetElement.style.borderColor = '';
                }, 2000);

                targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });

                const offset = 100;
                const elementPosition = targetElement.getBoundingClientRect().top + window.scrollY;
                const offsetPosition = elementPosition - offset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            }
        });

        span.addEventListener('mouseenter', (event) => {
            const targetId = span.getAttribute('data-id');
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                const preview = targetElement.cloneNode(true);
                const replies = preview.querySelectorAll('div.replies');
                replies.forEach(reply => reply.remove());
                if (!preview.style.backgroundColor) {
                    
                }
                preview.style.position = 'absolute';
                preview.style.zIndex = '1000';
                
                preview.style.display = 'block';

                document.body.appendChild(preview);

                const updatePreviewPosition = (e) => {
                    preview.style.left = `${e.pageX + 10}px`;
                    preview.style.top = `${e.pageY + 10}px`;
                };

                document.addEventListener('mousemove', updatePreviewPosition);

                span.addEventListener('mouseleave', () => {
                    if (preview && document.body.contains(preview)) {
                        document.body.removeChild(preview);
                        document.removeEventListener('mousemove', updatePreviewPosition);
                    }
                });
            }
        });
    });
}

function quotePostId(postId) {
    const textarea = document.getElementById('text');
    const draggableForm = document.getElementById('draggableForm');

    textarea.value += '' + (textarea.value ? '\n>>' : '>>') + postId;

    draggableForm.style.position = 'absolute';

    const mouseX = event.pageX;
    const mouseY = event.pageY + 10;

    const rightEdge = window.innerWidth - draggableForm.offsetWidth;
    const bottomEdge = window.innerHeight - draggableForm.offsetHeight;

    let newLeft = mouseX;
    let newTop = mouseY;

    if (newLeft < 0) newLeft = 0;
    if (newTop < 0) newTop = 0;
    if (newLeft > rightEdge) newLeft = rightEdge;
    if (newTop > bottomEdge) newTop = bottomEdge;

    draggableForm.style.display = 'block';
    draggableForm.style.left = `${newLeft}px`;
    draggableForm.style.top = `${newTop}px`;
}

document.addEventListener("DOMContentLoaded", function() {
    manipularConteudo();

    const textarea = document.getElementById('text');
    let quoteButton;

    document.addEventListener('mouseup', () => {
        const selection = window.getSelection();
        if (selection.toString()) {
            if (!quoteButton) {
                quoteButton = document.createElement('button');
                quoteButton.className = 'quote-button';
                quoteButton.innerText = 'Quotar';
                document.body.appendChild(quoteButton);
            }

            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();

            quoteButton.style.left = `${rect.left + window.scrollX}px`;
            quoteButton.style.top = `${rect.top + window.scrollY - 10}px`;

            requestAnimationFrame(() => {
                quoteButton.style.display = 'block';
            });
        } else if (quoteButton) {
            quoteButton.style.display = 'none';
        }
    });

    document.addEventListener('click', (e) => {
        if (quoteButton && e.target !== quoteButton) {
            quoteButton.style.display = 'none';
        }
    });

    document.addEventListener('click', (e) => {
        if (quoteButton && e.target === quoteButton) {
            const selection = window.getSelection();
            const selectedText = selection.toString();
            textarea.value += '' + (textarea.value ? '\n>' : '>') + selectedText;
            quoteButton.style.display = 'none';
            window.getSelection().removeAllRanges();
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