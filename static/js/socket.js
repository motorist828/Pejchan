// --- START OF FILE socket.js ---

var socket = io(); // Инициализируем соединение

console.log("--- socket.js executing ---"); // Лог выполнения файла
if (socket) {
    console.log("Socket object created. Initial state connected:", socket.connected);
} else {
    console.error("Socket object (io) FAILED to initialize!");
}


const defaultIconPath = '/static/imgs/decoration/icon.png';
const notificationIconPath = '/static/imgs/decoration/icon_reddot.png';
let missedMessages = 0;
let originalTitle = document.title;

// --- Утилитарные функции ---

function getCurrentBoard() {
    const path = window.location.pathname;
    // Удаляем слеш в начале и конце, если есть, затем берем первую часть
    const segments = path.replace(/^\/|\/$/g, '').split('/');
    return segments[0] || '';
}

function updateFavicon(src) {
    let link = document.querySelector("link[rel*='icon']");
    if (!link) {
        link = document.createElement('link');
        link.rel = 'shortcut icon';
        document.head.appendChild(link);
    }
    link.type = 'image/x-icon';
    link.href = src;
}


function updateTitle(count) {
    document.title = `[${count}] Pejcan`; // Используйте ваше название сайта
}

function resetNotifications() {
    if (missedMessages > 0) { // Сбрасываем только если были пропущенные
        missedMessages = 0;
        updateFavicon(defaultIconPath);
        document.title = originalTitle;
        console.log("Notifications reset.");
    }
}

// --- Обработчики событий для сброса уведомлений ---
// Срабатывают при взаимодействии пользователя с документом
document.addEventListener('click', resetNotifications, { capture: true, once: false });
document.addEventListener('mousemove', resetNotifications, { capture: true, once: false });
document.addEventListener('keypress', resetNotifications, { capture: true, once: false });
window.addEventListener('focus', resetNotifications); // Срабатывает при фокусе на вкладке

// --- Обработчики событий Socket.IO ---

socket.on('connect', () => {
    console.log('Socket.IO connected successfully. SID:', socket.id);
    // Сбрасываем уведомления при подключении/переподключении, если окно активно
    if (!document.hidden) {
        resetNotifications();
    }
});

socket.on('disconnect', (reason) => {
    console.warn('Socket.IO disconnected:', reason);
    // Логика переподключения обычно автоматическая, но можно добавить свое
    // if (reason === 'io server disconnect') { socket.connect(); }
});

socket.on('connect_error', (error) => {
    console.error('Socket.IO connection error:', error);
});

socket.on('reconnect_attempt', (attemptNumber) => {
    console.log('Socket.IO reconnect attempt:', attemptNumber);
});

socket.on('reconnect', (attemptNumber) => {
    console.log('Socket.IO reconnected after attempt:', attemptNumber);
    if (!document.hidden) { resetNotifications(); } // Сброс при реконнекте активной вкладки
});

socket.on('reconnect_failed', () => {
    console.error('Socket.IO reconnection failed.');
});

// Обработчик новых постов/ответов
socket.on('nova_postagem', function(data) {
    console.log(">>> Received 'nova_postagem' event. Data:", JSON.stringify(data, null, 2));

    // Базовая проверка данных
    if (!data || !data.post || typeof data.post.board === 'undefined') {
        console.error("Received invalid 'nova_postagem' data structure:", data);
        return;
    }

    const postData = data.post; // Упростим доступ к данным поста/ответа
    const currentBoard = getCurrentBoard();
    const isSameBoard = currentBoard === postData.board;
    const currentPath = window.location.pathname;

    console.log("Current board from URL:", currentBoard, "| Post board:", postData.board, "| Is same board?", isSameBoard);

    // Обновление уведомлений (иконка, заголовок)
    if (isSameBoard) {
        if (document.hidden) { // Обновляем только если вкладка неактивна
            missedMessages++;
            updateFavicon(notificationIconPath);
            updateTitle(missedMessages);
            console.log("Updated notifications for hidden tab. Count:", missedMessages);
        } else {
            // Если вкладка активна, сбрасываем уведомления (на случай, если они остались)
            resetNotifications();
        }
    }

    // Обработка и отображение нового контента ТОЛЬКО если мы на той же доске
    if (isSameBoard) {
        if (data.type === 'New Thread') {
            console.log("Processing as New Thread");
            // Отображаем новый тред только на главной странице доски
            const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
            console.log("Is board index page?", isBoardIndexPage);
            if (isBoardIndexPage) {
                addNewThread(postData); // Передаем postData
            } else {
                console.log("New thread received, but not on board index page. Ignoring visual update.");
            }
        } else if (data.type === 'New Reply') {
            console.log("Processing as New Reply");
            const parentThreadElement = document.getElementById(postData.thread_id); // Ищем родительский тред
            if (parentThreadElement) {
                console.log("Parent thread element found:", parentThreadElement);
                addNewReply(postData); // Добавляем ответ визуально

                // Перемещаем тред наверх на главной странице доски при новом ответе
                 const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
                 console.log("Is board index page for bump?", isBoardIndexPage);
                 if (isBoardIndexPage) {
                    const postsBoard = document.getElementById('posts_board');
                    if (postsBoard) {
                         const existingDivider = parentThreadElement.previousElementSibling;
                         let divider = null;
                         // Ищем или создаем разделитель ПЕРЕД тредом
                         if (!existingDivider || !existingDivider.classList.contains('divisoria')) {
                            parentThreadElement.insertAdjacentHTML('beforebegin', '<div class="divisoria"></div>');
                            divider = parentThreadElement.previousElementSibling;
                            console.log("Added new divider before thread.");
                         } else {
                            divider = existingDivider;
                            console.log("Found existing divider before thread.");
                         }

                        // Перемещаем тред и его разделитель в начало контейнера postsBoard
                        postsBoard.insertBefore(parentThreadElement, postsBoard.firstChild);
                        if (divider) {
                             postsBoard.insertBefore(divider, parentThreadElement); // Вставляем разделитель перед тредом
                             console.log("Moved thread and divider to top.");
                        } else {
                             console.warn("Could not find or create divider for thread bump.");
                        }
                    } else {
                        console.warn("#posts_board container not found for thread bump.");
                    }
                 }
            } else {
                 // Тред, к которому пришел ответ, не найден на текущей странице
                 console.warn(`Parent thread element NOT found for ID: ${postData.thread_id}. Reply ${postData.id} not added visually.`);
            }
        }
    } else {
        console.log("Received post/reply for a different board. Ignoring visual update.");
    }
});

// --- Функция добавления нового треда ---
function addNewThread(postData) {
    console.log("--- addNewThread called with data:", JSON.stringify(postData, null, 2));
    // Используем display_name, если он пришел, иначе генерируем
    const displayName = postData.name || (postData.post_user === '' || postData.post_user === 'Anonymous' ? 'Anon' : postData.post_user); // Используем name от сервера
    const postDate = postData.date || 'now';
    const postId = postData.id || postData.post_id || Date.now(); // Приоритет id из сокета
    const boardId = postData.board || getCurrentBoard();

    // Используем новую функцию для генерации HTML файлов
    const filesHTML = (postData.files_data && postData.files_data.length > 0)
        ? generateFilesHTMLFromData(postData.files_data, 'post') // Передаем files_data
        : '';

    // HTML для треда
    const threadHTML = `
        <div class="divisoria"></div>
        <div class="post" post-role="${postData.role || 'user'}" id="${postId}">
            <div class="postInfo">
                <input id="togglemodoptions_${postId}" type="checkbox" class="deletionCheckBox" value="${postId}" form="banDeleteForm">
                 <span class="nameBlock"><span class="name">${displayName}</span></span>  {# Используем |safe, если имя содержит HTML трипкод #}
                <span class="postDate">${postDate}</span>
                <a href="/${boardId}/thread/${postId}" class="postLink">No. </a>
                <a class="postLink postNumber" href="/${boardId}/thread/${postId}">${postId}</a>
                <a class="postLink" href="/${boardId}/thread/${postId}"> [Reply]</a>
                {# Тут должны быть реальные опции модерации, если они нужны динамически #}
                <div id="threadmodoptions_${postId}" class="mod-options" style="display: none; gap: 1em; padding-left: 1em;"></div>
            </div>
            <div class="post_content_container">
                ${filesHTML}
                <div class="post_content">
                    <pre>${postData.content || ''}</pre> {# Используем |safe ОСТОРОЖНО #}
                </div>
                <div class="replies"></div> {# Пустой контейнер для будущих ответов #}
            </div>
        </div>
    `;

    const postsContainer = document.getElementById('posts_board');
    if (postsContainer) {
         console.log(`Inserting new thread ${postId} into #posts_board`);
         // Создаем временный элемент для вставки HTML
         const tempDiv = document.createElement('div');
         tempDiv.innerHTML = threadHTML;
         // Вставляем все дочерние узлы (divisoria и post)
         while (tempDiv.firstChild) {
             postsContainer.insertBefore(tempDiv.firstChild, postsContainer.firstChild);
         }
    } else {
        console.error("Container #posts_board not found for adding new thread!");
    }
}

// --- Функция добавления нового ответа ---
function addNewReply(replyData) {
    console.log("--- addNewReply called with data:", JSON.stringify(replyData, null, 2));
    const displayName = replyData.name || (replyData.post_user === '' || replyData.post_user === 'Anonymous' ? 'Anon' : replyData.post_user); // Используем name от сервера
    const replyDate = replyData.date || 'now';
    const replyId = replyData.id || replyData.reply_id || Date.now(); // Приоритет id из сокета
    const threadId = replyData.thread_id;
    const boardId = replyData.board || getCurrentBoard();

    if (!threadId) {
        console.error("Reply data missing thread_id:", replyData);
        return;
    }

    // Используем новую функцию для генерации HTML файлов
    const filesHTML = (replyData.files_data && replyData.files_data.length > 0)
        ? generateFilesHTMLFromData(replyData.files_data, 'reply') // Передаем files_data
        : '';

    // --- Определение типа страницы для ссылки на ID ответа ---
    const currentPath = window.location.pathname;
    const threadPageRegex = /^\/[^\/]+\/thread\/\d+\/?$/;
    const isThreadPage = threadPageRegex.test(currentPath);

    let replyIdLinkHTML;
    if (isThreadPage) {
        // Ссылка для цитирования на странице треда
        replyIdLinkHTML = `<a class="postLink js-quote-link" href="javascript:void(0);" data-post-id="${replyId}">${replyId}</a>`;
    } else {
        // Обычная ссылка на других страницах
        replyIdLinkHTML = `<a class="postLink postNumber" href="/${boardId}/thread/${threadId}#${replyId}">${replyId}</a>`;
    }

    // Формируем HTML для ответа
    const replyHTML = `
        <div class="reply" id="${replyId}">
            <div class="reply-postInfo">
                <input id="togglemodoptions_${replyId}" type="checkbox" class="deletionCheckBox" value="${replyId}" form="banDeleteForm">
                <span class="nameBlock"><span class="name">${displayName}</span></span>  {# Используем |safe, если имя содержит HTML трипкод #}
                <span class="postDate">${replyDate}</span>
                <a href="/${boardId}/thread/${threadId}#${replyId}" class="postLink">No. </a>
                ${replyIdLinkHTML}
                {# Тут должны быть реальные опции модерации #}
                <div id="replymodoptions_${replyId}" class="mod-options" style="display: none; gap: 1em;"></div>
            </div>
            <div class="post_content_container">
                ${filesHTML}
                <div class="reply_content">
                    <pre>${replyData.content || ''}</pre> {# Используем |safe ОСТОРОЖНО #}
                </div>
            </div>
        </div>
    `;

    // Вставляем HTML в контейнер ответов соответствующего треда
    const repliesContainer = document.querySelector(`.post[id="${threadId}"] .replies`);
    console.log(`Searching for replies container: .post[id="${threadId}"] .replies`);
    if (repliesContainer) {
        console.log(`Replies container found for thread ${threadId}. Inserting reply ${replyId}.`);
        repliesContainer.insertAdjacentHTML('beforeend', replyHTML);
    } else {
         console.warn(`Replies container for thread ${threadId} not found. Reply ${replyId} not added visually.`);
    }
}


// --- *НОВАЯ* Функция генерации HTML для файлов из files_data ---
/**
 * Генерирует HTML для файлов на основе данных из поля files_data.
 * @param {Array<Object>} filesData - Массив объектов вида {original: 'url', thumbnail: 'url'}.
 * @param {'post' | 'reply'} type - Тип ('post' или 'reply').
 * @returns {string} HTML-строка для файлов.
 */
function generateFilesHTMLFromData(filesData, type) {
    console.log(`--- generateFilesHTMLFromData called for type: ${type} with data:`, JSON.stringify(filesData));
    if (!Array.isArray(filesData) || filesData.length === 0) {
        return ''; // Возвращаем пустую строку, если данных нет
    }

    // Определяем CSS классы
    const filesContainerClass = type === 'post' ? 'post_files' : 'reply_files';
    const fileWrapperClass = type === 'post' ? 'post_image' : 'reply_image';
    const fileElementClass = type === 'post' ? 'post_img' : 'reply_img';
    const fileInfoClass = type === 'post' ? 'post_image_info' : 'reply_image_info';

    let html = `<div class="${filesContainerClass} ${filesData.length > 1 ? 'multiple_files' : ''}">`;

    filesData.forEach((fileInfo, index) => {
        if (!fileInfo || !fileInfo.original || !fileInfo.thumbnail) {
            console.warn(`Invalid fileInfo at index ${index}:`, fileInfo);
            return; // Пропускаем невалидные данные
        }

        const originalUrl = fileInfo.original;
        const thumbnailUrl = fileInfo.thumbnail;

        // Пытаемся извлечь имя файла из URL оригинала
        let displayName = 'file';
        try {
            const urlParts = originalUrl.split('/');
            const filename = urlParts[urlParts.length - 1];
            const baseName = filename.split('.').slice(0, -1).join('.');
            const extension = filename.split('.').pop();
             displayName = filename.length > 20 // Сокращаем длинные имена
                ? `${baseName.substring(0, 15)}...${extension}`
                : filename;
        } catch (e) {
             console.error("Error parsing filename from URL:", originalUrl, e);
        }

        const altText = `${type === 'post' ? 'Post' : 'Reply'} file ${displayName}`;

        html += `<div class="${fileWrapperClass}">`; // Обертка файла
        html += `  <div class="${fileInfoClass}">`;   // Инфо о файле
        html += `    <a class="image_url" href="${originalUrl}" target="_blank" rel="noopener noreferrer">${displayName}</a>`; // Ссылка на оригинал
        html += `  </div>`;
        // Миниатюра как ссылка на оригинал
        html += `  <a href="${originalUrl}" target="_blank" rel="noopener noreferrer">`;
        html += `    <img draggable="false" class="${fileElementClass}" src="${thumbnailUrl}" alt="${altText}">`; // Используем URL миниатюры
        html += `  </a>`;
        html += `</div>`; // Конец обертки файла
    });

    html += '</div>'; // Конец контейнера файлов
    return html;
}


// --- Старая функция (больше не используется, можно удалить) ---
/*
function generateFilesHTML(files, filesThbData, type, boardId) {
    // ... старый код ...
}
*/

// --- Инициализация при загрузке страницы ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");
    if (document.hidden) {
        console.log("Tab loaded hidden.");
        updateFavicon(defaultIconPath); // Установить иконку по умолчанию
    } else {
        console.log("Tab loaded active.");
        resetNotifications(); // Сбросить уведомления при активной загрузке
    }
});

console.log("--- socket.js finished executing ---");

// --- END OF FILE socket.js ---