var jQuery = jQuery.noConflict();
var socket = io();

const defaultIconPath = '/static/imgs/decoration/icon.png';
const notificationIconPath = '/static/imgs/decoration/icon_reddot.png';
let missedMessages = 0;
let originalTitle = document.title;

// --- Утилитарные функции ---

function getCurrentBoard() {
    const path = window.location.pathname;
    const segments = path.replace(/^\//, '').split('/');
    return segments[0] || '';
}

function updateFavicon(src) {
    const link = document.querySelector("link[rel*='icon']") || document.createElement('link');
    link.type = 'image/x-icon';
    link.rel = 'shortcut icon';
    link.href = src;
    document.head.appendChild(link);
}

function updateTitle(count) {
    document.title = `[${count}]Pejcan`; // Используйте ваше название сайта
}

function resetNotifications() {
    missedMessages = 0;
    updateFavicon(defaultIconPath);
    document.title = originalTitle;
}

// --- Обработчики событий для сброса уведомлений ---

document.addEventListener('click', resetNotifications);
document.addEventListener('mousemove', resetNotifications);
document.addEventListener('keypress', resetNotifications);
window.addEventListener('focus', resetNotifications);

// --- Обработчик событий Socket.IO ---

socket.on('nova_postagem', function(data) {
    const currentBoard = getCurrentBoard();
    if (!data || !data.post || typeof data.post.board === 'undefined') {
        console.error("Received invalid post data:", data);
        return;
    }
    const isSameBoard = currentBoard === data.post.board;
    const currentPath = window.location.pathname;

    // Обновление уведомлений (иконка, заголовок)
    if (isSameBoard) {
        if (document.hidden) { // Обновляем только если вкладка неактивна
            missedMessages++;
            updateFavicon(notificationIconPath);
            updateTitle(missedMessages);
        }
    }

    // Обработка и отображение нового контента
    if (isSameBoard) {
        // Убедимся, что массивы существуют
        if (!data.post.files) data.post.files = [];
        if (!data.post.filesthb) data.post.filesthb = []; // Проверяем filesthb

        if (data.type === 'New Thread') {
            // Отображаем новый тред только на главной странице доски
            const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
            if (isBoardIndexPage) {
                addNewThread(data.post);
            }
        } else if (data.type === 'New Reply') {
            const parentThread = document.getElementById(data.post.thread_id);
            if (parentThread) {
                // Вызываем функцию добавления ответа
                addNewReply(data.post); // <--- Используется обновленная функция

                // Перемещаем тред наверх на главной странице доски при новом ответе
                 const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
                 if (isBoardIndexPage) {
                    const postsBoard = document.getElementById('posts_board');
                    if (postsBoard && parentThread) {
                         // Добавляем разделитель, если его нет
                         const existingDivider = parentThread.previousElementSibling;
                         if (!existingDivider || !existingDivider.classList.contains('divisoria')) {
                            parentThread.insertAdjacentHTML('beforebegin', '<div class="divisoria"></div>');
                         }
                        const divider = parentThread.previousElementSibling; // Получаем разделитель
                        // Перемещаем тред и его разделитель в начало
                        postsBoard.insertBefore(parentThread, postsBoard.firstChild);
                        if (divider && divider.classList.contains('divisoria')) {
                             postsBoard.insertBefore(divider, parentThread);
                        }
                    }
                 }
            }
        }
    }
});

// --- Функция добавления нового треда ---

function addNewThread(post) {
    const displayName = post.name === '' || post.name === 'Anonymous' ? 'Anon' : post.name;
    const postDate = post.date || 'agora mesmo'; // Используем дату как есть
    const postId = post.id || Date.now();
    const boardId = post.board || getCurrentBoard();

    const filesHTML = (post.files && post.files.length > 0)
        ? generateFilesHTML(post.files, post.filesthb || [], 'post', boardId)
        : '';

    // HTML для треда (ссылка на ID всегда обычная + класс postNumber)
    const threadHTML = `
        <div class="divisoria"></div>
        <div class="post" post-role="${post.role || 'user'}" id="${postId}" bis_skin_checked="1">
            <div class="postInfo" bis_skin_checked="1">
                <input id="togglemodoptions_${postId}" type="checkbox" class="deletionCheckBox" name="${postId}" form="banDeleteForm">
                &nbsp;<span class="nameBlock"><span class="name">${displayName}</span></span>&nbsp;
                <span class="postDate">${postDate}</span> 
                <a href="/${boardId}/thread/${postId}" class="postLink" bis_skin_checked="1">No. </a>
                <a class="postLink postNumber" href="/${boardId}/thread/${postId}" bis_skin_checked="1">${postId}</a> 
                <a class="postLink" href="/${boardId}/thread/${postId}" bis_skin_checked="1"> [Reply]</a> 
                <div id="threadmodoptions_${postId}" class="mod-options" style="display: none; gap: 1em; padding-left: 1em;" bis_skin_checked="1"></div>
            </div>
            <div class="post_content_container" bis_skin_checked="1">
                ${filesHTML}
                <div class="post_content" bis_skin_checked="1">
                    <pre>${post.content || ''}</pre>
                </div>
                <div class="replies" bis_skin_checked="1"></div>
            </div>
        </div>
    `;

    const postsContainer = document.getElementById('posts_board');
    if (postsContainer) {
         // Вставляем новый тред в начало контейнера
         if (postsContainer.firstChild) {
             postsContainer.insertBefore(document.createRange().createContextualFragment(threadHTML), postsContainer.firstChild);
         } else {
             postsContainer.innerHTML = threadHTML; // Если контейнер был пуст
         }
    } else {
        console.error("Container #posts_board not found!");
    }
}

// --- *ОБНОВЛЕННАЯ* Функция добавления нового ответа ---

function addNewReply(reply) { // reply содержит поле filesthb
    const displayName = reply.name === '' || reply.name === 'Anonymous' ? 'Anon' : reply.name;
    const replyDate = reply.date || 'agora mesmo'; // Используем дату как есть
    const replyId = reply.id || Date.now();
    const threadId = reply.thread_id;
    const boardId = reply.board || getCurrentBoard(); // Получаем boardId из данных или текущего URL

    if (!threadId) {
        console.error("Reply data missing thread_id:", reply);
        return;
    }

    // Генерируем HTML для файлов
    const filesHTML = (reply.files && reply.files.length > 0)
        ? generateFilesHTML(reply.files, reply.filesthb || [], 'reply', boardId)
        : '';

    // --- Определение типа страницы ---
    const currentPath = window.location.pathname;
    // Регулярное выражение для проверки, является ли страница страницей треда (/board/thread/number)
    const threadPageRegex = /^\/[^\/]+\/thread\/\d+\/?$/;
    const isThreadPage = threadPageRegex.test(currentPath);
    // ---------------------------------

    // --- Условная генерация ссылки на ID ответа ---
    let replyIdLinkHTML;
    if (isThreadPage) {
        // Версия для страницы треда (для цитирования)
        replyIdLinkHTML = `<a class="postLink js-quote-link" href="javascript:void(0);" data-post-id="${replyId}">${replyId}</a>`;
    } else {
        // Версия для других страниц (доска, каталог и т.д.) - обычная ссылка + класс postNumber
        // Добавим класс postNumber для единообразия с Jinja, если нужно
        replyIdLinkHTML = `<a class="postLink postNumber" href="/${boardId}/thread/${threadId}#${replyId}" bis_skin_checked="1">${replyId}</a>`;
    }
    // ----------------------------------------------

    // Формируем основной HTML для ответа, используя вычисленную ссылку replyIdLinkHTML
    const replyHTML = `
        <div class="reply" id="${replyId}" bis_skin_checked="1">
            <div class="reply-postInfo" bis_skin_checked="1">
                <input id="togglemodoptions_${replyId}" type="checkbox" class="deletionCheckBox" name="${replyId}" form="banDeleteForm">
                <span class="nameBlock"><span class="name">${displayName}</span></span>&nbsp;
                <span class="postDate">${replyDate}</span> 
                <a href="/${boardId}/thread/${threadId}#${replyId}" class="postLink" bis_skin_checked="1">No. </a>
                ${replyIdLinkHTML}
                 <div id="replymodoptions_${replyId}" class="mod-options" style="display: none; gap: 1em;" bis_skin_checked="1"></div>
            </div>
            <div class="post_content_container" bis_skin_checked="1">
                ${filesHTML}
                <div class="reply_content" bis_skin_checked="1">
                    <pre>${reply.content || ''}</pre>
                </div>
            </div>
        </div>
    `;

    // Вставляем HTML в контейнер ответов
    const repliesContainer = document.querySelector(`.post[id="${threadId}"] .replies`);
    if (repliesContainer) {
        repliesContainer.insertAdjacentHTML('beforeend', replyHTML);
    } else {
         // Это может произойти, если ответ пришел раньше, чем тред отрисовался,
         // или если мы на странице, где этого треда нет.
         console.warn(`Replies container for thread ${threadId} not found. Reply ${replyId} not added visually.`);
    }
}


// --- Функция генерации HTML для файлов ---

/**
 * Генерирует HTML для файлов, принимая массив путей к миниатюрам из поля filesthb.
 * @param {string[]} files - Массив имен оригинальных файлов.
 * @param {string[]} filesThbData - Массив путей к миниатюрам (как приходит от бэкенда, например, ["thumbs/thumb_1.jpg"]).
 * @param {'post' | 'reply'} type - Тип ('post' или 'reply').
 * @param {string} boardId - Идентификатор доски (для построения путей).
 * @returns {string} HTML-строка для файлов.
 */
function generateFilesHTML(files, filesThbData, type, boardId) {
    // Раскомментируйте для отладки получаемых данных
    // console.log(`generateFilesHTML called for type: ${type}`);
    // console.log("Received files:", JSON.stringify(files));
    // console.log("Received filesThbData:", JSON.stringify(filesThbData));

    // Убедимся, что filesThbData - это массив и обработаем его
    const safeThumbPaths = Array.isArray(filesThbData)
        ? files.map((_, i) => filesThbData[i] || '') // Заменяем null/undefined/etc на ''
        : files.map(() => ''); // Если не массив, создаем массив пустых строк

    // Определяем папки и CSS классы
    const folder = type === 'post' ? 'post_images' : 'reply_images';
    const filesContainerClass = type === 'post' ? 'post_files' : 'reply_files';
    const fileWrapperClass = type === 'post' ? 'post_image' : 'reply_image';
    const fileElementClass = type === 'post' ? 'post_img' : 'reply_img';
    const fileInfoClass = type === 'post' ? 'post_image_info' : 'reply_image_info';

    // Начинаем формирование HTML
    let html = `<div class="${filesContainerClass} ${files.length > 1 ? 'multiple_files' : ''}" bis_skin_checked="1">`;

    // Проходим по каждому файлу
    files.forEach((file, index) => {
        // Получаем относительный путь к миниатюре (например, "thumbs/thumb_1.jpg" или "")
        const thumbRelativePath = safeThumbPaths[index];
        // Формируем полный путь к оригинальному файлу
        const fullPath = `/static/${folder}/${file}`;
        // Проверяем, есть ли путь к миниатюре
        const hasThumbnail = thumbRelativePath && thumbRelativePath !== '';
        // Формируем абсолютный путь для атрибута src:
        // Если миниатюра есть, добавляем префикс /static/{folder}/
        // Если нет, используем полный путь к оригиналу как fallback
        const thumbSrcPath = hasThumbnail
            ? `/static/${folder}/${thumbRelativePath}`
            : fullPath;

        // Раскомментируйте для отладки путей
        // console.log(`File ${index}: original=${file}, thumbRelativePath=${thumbRelativePath}, finalThumbSrcPath=${thumbSrcPath}`);

        // Формируем отображаемое имя файла (сокращенное)
        const baseName = file.split('.').slice(0, -1).join('.');
        const extension = file.split('.').pop();
        const displayName = baseName.length > 17
            ? `${baseName.substring(0, 17)}...${extension}`
            : `${baseName}.${extension}`;
        // Формируем alt текст для изображения
        const altText = `${type === 'post' ? 'Post' : 'Reply'} file ${displayName}`;

        // Добавляем HTML для текущего файла
        html += `<div class="${fileWrapperClass}" bis_skin_checked="1">`; // Обертка файла
        html += `  <div class="${fileInfoClass}" bis_skin_checked="1">`;   // Инфо о файле
        html += `    <a class="image_url" href="${fullPath}" target="_blank" rel="noopener noreferrer" bis_skin_checked="1">${displayName}</a>`; // Ссылка на оригинал
        html += `  </div>`;
        // Изображение: src указывает на миниатюру (или оригинал), href на оригинал
        html += `  <img draggable="false" class="${fileElementClass}" src="${thumbSrcPath}" href="${fullPath}" alt="${altText}">`;
        html += `</div>`; // Конец обертки файла
    });

    html += '</div>'; // Конец контейнера файлов
    return html;
}

// --- Инициализация при загрузке страницы ---
if (document.hidden) {
    // Можно установить иконку по умолчанию или специальную иконку для неактивных вкладок
     updateFavicon(defaultIconPath);
} else {
    // Сбрасываем уведомления, если вкладка загрузилась активной
    resetNotifications();
}