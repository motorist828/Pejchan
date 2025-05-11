var socket = io();

if (!socket) {
    console.error("Socket object (io) FAILED to initialize!");
}

const defaultIconPath = '/static/imgs/decoration/icon.png';
const notificationIconPath = '/static/imgs/decoration/icon_reddot.png';
let missedMessages = 0;
let originalTitle = document.title;

function getCurrentBoard() {
    const path = window.location.pathname;
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
    document.title = `[${count}] Pejcan`;
}

function resetNotifications() {
    if (missedMessages > 0) {
        missedMessages = 0;
        updateFavicon(defaultIconPath);
        document.title = originalTitle;
    }
}

document.addEventListener('click', resetNotifications, { capture: true, once: false });
document.addEventListener('mousemove', resetNotifications, { capture: true, once: false });
document.addEventListener('keypress', resetNotifications, { capture: true, once: false });
window.addEventListener('focus', resetNotifications);

socket.on('connect', () => {
    if (!document.hidden) {
        resetNotifications();
    }
});

socket.on('disconnect', (reason) => {
    console.warn('Socket.IO disconnected:', reason);
});

socket.on('connect_error', (error) => {
    console.error('Socket.IO connection error:', error);
});

socket.on('reconnect', (attemptNumber) => {
    if (!document.hidden) { resetNotifications(); }
});

socket.on('reconnect_failed', () => {
    console.error('Socket.IO reconnection failed.');
});

socket.on('nova_postagem', function(data) {
    if (!data || !data.post || typeof data.post.board === 'undefined') {
        console.error("Received invalid 'nova_postagem' data structure:", data);
        return;
    }

    const postData = data.post;
    const currentBoard = getCurrentBoard();
    const isSameBoard = currentBoard === postData.board;
    const currentPath = window.location.pathname;

    if (isSameBoard) {
        if (document.hidden) {
            missedMessages++;
            updateFavicon(notificationIconPath);
            updateTitle(missedMessages);
        } else {
            resetNotifications();
        }
    }

    if (isSameBoard) {
        if (data.type === 'New Thread') {
            const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
            if (isBoardIndexPage) {
                addNewThread(postData);
            }
        } else if (data.type === 'New Reply') {
            const parentThreadElement = document.getElementById(postData.thread_id);
            if (parentThreadElement) {
                addNewReply(postData);

                 const isBoardIndexPage = currentPath === `/${currentBoard}` || currentPath === `/${currentBoard}/`;
                 if (isBoardIndexPage) {
                    const postsBoard = document.getElementById('posts_board');
                    if (postsBoard) {
                         const existingDivider = parentThreadElement.previousElementSibling;
                         let divider = null;
                         if (!existingDivider || !existingDivider.classList.contains('divisoria')) {
                            parentThreadElement.insertAdjacentHTML('beforebegin', '<div class="divisoria"></div>');
                            divider = parentThreadElement.previousElementSibling;
                         } else {
                            divider = existingDivider;
                         }

                        postsBoard.insertBefore(parentThreadElement, postsBoard.firstChild);
                        if (divider) {
                             postsBoard.insertBefore(divider, parentThreadElement);
                        } else {
                             console.warn("Could not find or create divider for thread bump.");
                        }
                    } else {
                        console.warn("#posts_board container not found for thread bump.");
                    }
                 }
            } else {
                 console.warn(`Parent thread element NOT found for ID: ${postData.thread_id}. Reply ${postData.id} not added visually.`);
            }
        }
    }
});

function addNewThread(postData) {
    const displayName = postData.name || (postData.post_user === '' || postData.post_user === 'Anonymous' ? 'Anon' : postData.post_user);
    const postDate = postData.date || 'now';
    const postId = postData.id || postData.post_id || Date.now();
    const boardId = postData.board || getCurrentBoard();

    const filesHTML = (postData.files_data && postData.files_data.length > 0)
        ? generateFilesHTMLFromData(postData.files_data, 'post')
        : '';

    const threadHTML = `
        <div class="divisoria"></div>
        <div class="post" post-role="${postData.role || 'user'}" id="${postId}">
            <div class="postInfo">
                <input id="togglemodoptions_${postId}" type="checkbox" class="deletionCheckBox" value="${postId}" form="banDeleteForm">
                 <span class="nameBlock"><span class="name">${displayName}</span></span> 
                <span class="postDate">${postDate}</span>
                <a href="/${boardId}/thread/${postId}" class="postLink">No. </a>
                <a class="postLink postNumber" href="/${boardId}/thread/${postId}">${postId}</a>
                <a class="postLink" href="/${boardId}/thread/${postId}"> [Reply]</a>
                <div id="threadmodoptions_${postId}" class="mod-options" style="display: none; gap: 1em; padding-left: 1em;"></div>
            </div>
            <div class="post_content_container">
                ${filesHTML}
                <div class="post_content">
                    <pre>${postData.content || ''}</pre> {# Используем |safe ОСТОРОЖНО #}
                </div>
                <div class="replies"></div>
            </div>
        </div>
    `;

    const postsContainer = document.getElementById('posts_board');
    if (postsContainer) {
         const tempDiv = document.createElement('div');
         tempDiv.innerHTML = threadHTML;
         while (tempDiv.firstChild) {
             postsContainer.insertBefore(tempDiv.firstChild, postsContainer.firstChild);
         }
    } else {
        console.error("Container #posts_board not found for adding new thread!");
    }
}

function addNewReply(replyData) {
    const displayName = replyData.name || (replyData.post_user === '' || replyData.post_user === 'Anonymous' ? 'Anon' : replyData.post_user);
    const replyDate = replyData.date || 'now';
    const replyId = replyData.id || replyData.reply_id || Date.now();
    const threadId = replyData.thread_id;
    const boardId = replyData.board || getCurrentBoard();

    if (!threadId) {
        console.error("Reply data missing thread_id:", replyData);
        return;
    }

    const filesHTML = (replyData.files_data && replyData.files_data.length > 0)
        ? generateFilesHTMLFromData(replyData.files_data, 'reply')
        : '';

    const currentPath = window.location.pathname;
    const threadPageRegex = /^\/[^\/]+\/thread\/\d+\/?$/;
    const isThreadPage = threadPageRegex.test(currentPath);

    let replyIdLinkHTML;
    if (isThreadPage) {
        replyIdLinkHTML = `<a class="postLink js-quote-link" href="javascript:void(0);" data-post-id="${replyId}">${replyId}</a>`;
    } else {
        replyIdLinkHTML = `<a class="postLink postNumber" href="/${boardId}/thread/${threadId}#${replyId}">${replyId}</a>`;
    }

    const replyHTML = `
        <div class="reply" id="${replyId}">
            <div class="reply-postInfo">
                <input id="togglemodoptions_${replyId}" type="checkbox" class="deletionCheckBox" value="${replyId}" form="banDeleteForm">
                <span class="nameBlock"><span class="name">${displayName}</span></span> 
                <span class="postDate">${replyDate}</span>
                <a href="/${boardId}/thread/${threadId}#${replyId}" class="postLink">No. </a>
                ${replyIdLinkHTML}
                
                <div id="replymodoptions_${replyId}" class="mod-options" style="display: none; gap: 1em;"></div>
            </div>
            <div class="post_content_container">
                ${filesHTML}
                <div class="reply_content">
                    <pre>${replyData.content || ''}</pre>
                </div>
            </div>
        </div>
    `;

    const repliesContainer = document.querySelector(`.post[id="${threadId}"] .replies`);
    if (repliesContainer) {
        repliesContainer.insertAdjacentHTML('beforeend', replyHTML);
    } else {
         console.warn(`Replies container for thread ${threadId} not found. Reply ${replyId} not added visually.`);
    }
}

/**
 * Генерирует HTML для файлов на основе данных из поля files_data.
 * @param {Array<Object>} filesData - Массив объектов вида {original: 'url', thumbnail: 'url'}.
 * @param {'post' | 'reply'} type - Тип ('post' или 'reply').
 * @returns {string} HTML-строка для файлов.
 */
function generateFilesHTMLFromData(filesData, type) {
    if (!Array.isArray(filesData) || filesData.length === 0) {
        return '';
    }

    const filesContainerClass = type === 'post' ? 'post_files' : 'reply_files';
    const fileWrapperClass = type === 'post' ? 'post_image' : 'reply_image';
    const fileElementClass = type === 'post' ? 'post_img' : 'reply_img';
    const fileInfoClass = type === 'post' ? 'post_image_info' : 'reply_image_info';

    let html = `<div class="${filesContainerClass} ${filesData.length > 1 ? 'multiple_files' : ''}">`;

    filesData.forEach((fileInfo, index) => {
        if (!fileInfo || !fileInfo.original || !fileInfo.thumbnail) {
            console.warn(`Invalid fileInfo at index ${index}:`, fileInfo);
            return;
        }

        const originalUrlInput = fileInfo.original; // e.g., "/static/reply_images%5C1746721173607_vsts.png"
        const thumbnailUrl = fileInfo.thumbnail;

        // 1. Формируем URL для href (с прямыми слешами)
        const hrefUrl = originalUrlInput.replace(/%5C/g, '/'); // Заменяем %5C на /

        // 2. Извлекаем и формируем displayName
        let actualFilename = 'file'; // Имя файла по умолчанию
        try {
            // Декодируем URL, чтобы избавиться от %-кодирования (например, %5C -> \)
            let decodedPath = decodeURIComponent(originalUrlInput); // e.g., "/static/reply_images\1746721173607_vsts.png"

            // Разбиваем путь по '/' и '\' и берем последний элемент
            const parts = decodedPath.replace(/\\/g, '/').split('/');
            actualFilename = parts[parts.length - 1];

            if (!actualFilename) { // Если имя файла пустое после всех манипуляций
                actualFilename = 'file';
            }
        } catch (e) {
            console.error("Error parsing filename from URL:", originalUrlInput, e);
            actualFilename = 'file'; // В случае ошибки парсинга
        }

        let displayName = actualFilename;
        const maxDisplayLength = 25; // Максимальная длина отображаемого имени

        if (actualFilename.length > maxDisplayLength) {
            const dotIndex = actualFilename.lastIndexOf('.');
            let baseName, extension = "";

            if (dotIndex > 0 && dotIndex > actualFilename.length - 7) { // Расширение разумной длины (до 5 символов + точка)
                baseName = actualFilename.substring(0, dotIndex);
                extension = actualFilename.substring(dotIndex);
            } else {
                baseName = actualFilename;
            }
            
            const availableForBase = maxDisplayLength - extension.length - 3; // 3 for "..."
            if (baseName.length > availableForBase && availableForBase > 0) {
                displayName = baseName.substring(0, availableForBase) + "..." + extension;
            } else { // Если базовое имя короткое или сокращение не улучшает ситуацию
                 displayName = actualFilename.substring(0, maxDisplayLength - 3) + "...";
            }
        }
        // Если actualFilename <= maxDisplayLength, displayName останется actualFilename

        const altText = `${type === 'post' ? 'Post' : 'Reply'} file ${displayName}`;

        html += `<div class="${fileWrapperClass}">`;
        html += `  <div class="${fileInfoClass}">`;
        html += `    <a class="image_url" href="${hrefUrl}" target="_blank" rel="noopener noreferrer">${displayName}</a>`;
        html += `  </div>`;
        html += `    <img draggable="false" class="${fileElementClass}" src="${thumbnailUrl}" href="${hrefUrl}">`;
        html += `  </a>`;
        html += `</div>`;
    });

    html += '</div>';
    return html;
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.hidden) {
        updateFavicon(defaultIconPath);
    } else {
        resetNotifications();
    }
});