document.addEventListener('DOMContentLoaded', () => {
    // --- Получение основных элементов ---
    const draggableForm = document.getElementById('draggableForm');
    if (!draggableForm) {
        console.error("[Init] Элемент формы 'draggableForm' не найден!");
        return;
    }

    const header = draggableForm.querySelector('.new-thread-header');
    const closeButton = draggableForm.querySelector('.close.postform-style');
    const messageTextarea = draggableForm.querySelector('textarea#text');
    const fileInput = document.getElementById('file');
    const uploadListContainer = draggableForm.querySelector('.upload-list');
    const postForm = document.getElementById('postform');
    const dropZoneLabel = draggableForm.querySelector('label.filelabel');
    const submitButton = document.getElementById('submitpost');
    const sendingIndicator = document.getElementById('sendingIndicator');

    // --- Переменные состояния ---
    let isDraggingForm = false;
    let selectedFiles = [];
    let fileCounter = 0;

    // --- Константы ---
    const MAX_FILES = 4;
    const MAX_TOTAL_SIZE_MB = 20;
    const MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024;
    const EDGE_MARGIN = 10; // <<<--- ДОБАВЛЕНО: Отступ от края экрана в пикселях

    // --- Проверка наличия необходимых элементов ---
    if (!fileInput) console.warn("[Init] Элемент input#file не найден. Функционал загрузки файлов не будет работать.");
    if (!uploadListContainer) console.warn("[Init] Элемент .upload-list не найден. Превью файлов не будут отображаться.");
    if (!messageTextarea) console.warn("[Init] Элемент textarea#text не найден. Вставка файлов и Ctrl+Enter не будут работать.");
    if (!postForm) console.warn("[Init] Элемент формы #postform не найден. Отправка формы не будет работать.");
    if (!dropZoneLabel) console.warn("[Init] Элемент label.filelabel не найден. Drag-n-drop файлов не будет работать.");
    if (!header) console.warn("[Init] Элемент .new-thread-header не найден. Перетаскивание формы не будет работать.");
    if (!closeButton) console.warn("[Init] Элемент .close.postform-style не найден в форме. Закрытие формы может не работать.");
    if (!submitButton) console.warn("[Init] Кнопка #submitpost не найдена. Индикатор отправки не будет работать.");
    if (!sendingIndicator) console.warn("[Init] Спиннер #sendingIndicator не найден. Индикатор отправки не будет работать.");


    // --- Вспомогательная функция для форматирования размера файла ---
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = bytes === 0 ? 0 : Math.floor(Math.log(bytes) / Math.log(k));
        const index = Math.min(i, sizes.length - 1);
        return parseFloat((bytes / Math.pow(k, index)).toFixed(2)) + ' ' + sizes[index];
    }

    // --- Функция для обновления фактического поля ввода файлов ---
    function updateFileInput() {
        if (!fileInput) return;
        const dataTransfer = new DataTransfer();
        selectedFiles.forEach(fileWrapper => {
            if (fileWrapper && fileWrapper.file) {
                 dataTransfer.items.add(fileWrapper.file);
            }
        });
        try {
            let changed = false;
            if (fileInput.files.length !== dataTransfer.files.length) {
                changed = true;
            } else {
                const currentFiles = Array.from(fileInput.files);
                const newFiles = Array.from(dataTransfer.files);
                for (let i = 0; i < currentFiles.length; i++) {
                    if (!newFiles[i] || currentFiles[i].name !== newFiles[i].name || currentFiles[i].size !== newFiles[i].size) {
                        changed = true;
                        break;
                    }
                }
            }
            if (changed) {
                 fileInput.files = dataTransfer.files;
            }
        } catch (e) {
            console.error("[updateFileInput] Не удалось обновить fileInput.files:", e);
        }
    }

    // --- Функция для добавления превью файлов ---
    function addFilePreviews(newFiles) {
        if (!uploadListContainer) return;

        const filesArray = Array.from(newFiles);
        let currentTotalSize = selectedFiles.reduce((sum, fw) => sum + (fw && fw.file ? fw.file.size : 0), 0);
        let currentFileCount = selectedFiles.filter(fw => fw && fw.file).length;
        let filesAdded = false;

        for (const file of filesArray) {
             const alreadyExists = selectedFiles.some(fw => fw && fw.file && fw.file.name === file.name && fw.file.size === file.size);
             if (alreadyExists) {
                 console.log(`Файл "${file.name}" уже добавлен.`);
                 continue;
             }

            if (currentFileCount >= MAX_FILES) {
                alert(`Вы можете загрузить не более ${MAX_FILES} файлов.`);
                break;
            }

            if (currentTotalSize + file.size > MAX_TOTAL_SIZE_BYTES) {
                 if (currentFileCount > 0 || file.size > MAX_TOTAL_SIZE_BYTES) {
                    alert(`Общий размер файлов не должен превышать ${MAX_TOTAL_SIZE_MB} MB.`);
                    if (file.size > MAX_TOTAL_SIZE_BYTES) {
                         alert(`Файл "${file.name}" (${formatFileSize(file.size)}) слишком большой (макс. ${MAX_TOTAL_SIZE_MB} MB).`);
                    }
                    continue;
                }
            }

            const fileId = `file-${fileCounter++}`;
            const fileWrapper = { id: fileId, file: file };
            selectedFiles.push(fileWrapper);
            currentTotalSize += file.size;
            currentFileCount++;
            filesAdded = true;

            const previewElement = document.createElement('div');
            previewElement.classList.add('file-preview');
            previewElement.dataset.fileId = fileId;

            const img = document.createElement('img');
            img.alt = "Превью";
            img.src = 'data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22%23ccc%22%3E%3Cpath%20d%3D%22M6%202h6l4%204v12a2%202%200%200%201-2%202H6a2%202%200%200%201-2-2V4a2%202%200%200%201%202-2zm0%202v16h12V7h-5V2H6z%22%2F%3E%3C%2Fsvg%3E';
            img.style.width = '50px';
            img.style.height = '50px';
            img.style.objectFit = 'cover';
            img.style.backgroundColor = '#eee';

            const infoDiv = document.createElement('div');
            infoDiv.classList.add('file-preview-info');
            const nameSpan = document.createElement('span');
            nameSpan.classList.add('file-preview-name');
            nameSpan.textContent = file.name;
            nameSpan.title = file.name;
            const sizeSpan = document.createElement('span');
            sizeSpan.classList.add('file-preview-size');
            sizeSpan.textContent = formatFileSize(file.size);
            infoDiv.appendChild(nameSpan);
            infoDiv.appendChild(sizeSpan);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.classList.add('file-remove-btn');
            removeBtn.innerHTML = '×';
            removeBtn.dataset.fileId = fileId;
            removeBtn.title = `Удалить ${file.name}`;
            removeBtn.setAttribute('aria-label', `Удалить ${file.name}`);

            previewElement.appendChild(img);
            previewElement.appendChild(infoDiv);
            previewElement.appendChild(removeBtn);
            uploadListContainer.appendChild(previewElement);

            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    img.src = e.target.result;
                    img.style.backgroundColor = 'transparent';
                }
                reader.onerror = () => {
                    console.error(`Не удалось прочитать файл изображения: ${file.name}`);
                    img.alt = 'Ошибка';
                }
                reader.readAsDataURL(file);
            }
        }

        if (filesAdded) {
             updateFileInput();
        }
    }

     // --- Функция для полной очистки файлов и превью ---
    function clearFilesAndPreviews() {
        const hadFiles = selectedFiles.length > 0;
        selectedFiles = [];
        if(uploadListContainer) {
            uploadListContainer.innerHTML = '';
        }
        if (fileInput && hadFiles) {
            updateFileInput();
        }
    }

    // --- Обработчик события изменения в поле ввода файлов (выбор через кнопку) ---
    if (fileInput) {
        fileInput.addEventListener('change', (event) => {
            if (event.target.files.length > 0) {
                addFilePreviews(event.target.files);
            }
            //event.target.value = null;
        });
    } else {
         const fileSectionLabel = draggableForm.querySelector('.row .label span:contains("Files")')?.closest('.label');
         if (fileSectionLabel) {
             const row = fileSectionLabel.closest('.row');
             if (row) row.style.display = 'none';
         } else {
             if(fileInput && fileInput.closest('.row')) fileInput.closest('.row').style.display = 'none';
         }
        if (dropZoneLabel) dropZoneLabel.style.display = 'none';
    }


    // --- Обработчик события для удаления файлов (делегирование на контейнер) ---
    if (uploadListContainer) {
        uploadListContainer.addEventListener('click', (event) => {
            const removeButton = event.target.closest('.file-remove-btn');
            if (removeButton) {
                event.stopPropagation();
                const fileIdToRemove = removeButton.dataset.fileId;
                if (!fileIdToRemove) {
                    console.warn("Не найден data-file-id на кнопке удаления");
                    return;
                }
                const indexToRemove = selectedFiles.findIndex(fw => fw && fw.id === fileIdToRemove);
                if (indexToRemove !== -1) {
                    selectedFiles.splice(indexToRemove, 1);
                    const previewElementToRemove = uploadListContainer.querySelector(`.file-preview[data-file-id="${fileIdToRemove}"]`);
                    if (previewElementToRemove) {
                        previewElementToRemove.remove();
                    }
                    updateFileInput();
                } else {
                    console.warn(`Файл с ID ${fileIdToRemove} не найден в selectedFiles для удаления.`);
                }
            }
        });
    }

    // --- Логика открытия/закрытия и перемещения формы ---
    function openDraggableForm(event, postId = null) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        let elementToFocus = null;
        if (postId && messageTextarea) {
            const quoteText = ">>" + postId + "\n";
            const currentValue = messageTextarea.value;
            let textToAdd = quoteText;
            if (currentValue.length > 0) {
                if (!currentValue.endsWith('\n')) {
                    textToAdd = "\n\n" + quoteText;
                } else if (!currentValue.endsWith('\n\n')) {
                    textToAdd = "\n" + quoteText;
                }
            }
            messageTextarea.value += textToAdd;
            elementToFocus = messageTextarea;
        } else if (messageTextarea) {
            elementToFocus = messageTextarea;
        }

        // Начальная точка (координаты клика или центр окна)
        const clickX = event ? event.pageX : (window.scrollX + window.innerWidth / 2);
        const clickY = event ? event.pageY : (window.scrollY + 50);

        draggableForm.style.position = 'absolute';
        draggableForm.style.display = 'block';

        // Используем requestAnimationFrame, чтобы браузер успел отрисовать форму
        // и мы могли получить ее реальные размеры (offsetWidth/offsetHeight)
        requestAnimationFrame(() => {
            const formWidth = draggableForm.offsetWidth;
            const formHeight = draggableForm.offsetHeight;

            // Рассчитываем начальное положение (например, под курсором или по центру)
            let newLeft = clickX - (event ? 0 : formWidth / 2); // По центру X, если без event
            let newTop = clickY + (event ? 10 : 0); // Чуть ниже клика Y

            // Получаем размеры видимой области окна и текущий скролл
            const viewportWidth = document.documentElement.clientWidth;
            const viewportHeight = document.documentElement.clientHeight;
            const scrollX = window.scrollX;
            const scrollY = window.scrollY;

            // --- ИЗМЕНЕНО: Расчет границ с учетом отступа ---
            // Минимальные координаты (левый верхний угол)
            const minLeft = scrollX + EDGE_MARGIN;
            const minTop = scrollY + EDGE_MARGIN;

            // Максимальные координаты (левый верхний угол)
            // Правый край окна (scrollX + viewportWidth) минус ширина формы минус отступ
            const maxLeft = scrollX + viewportWidth - formWidth - EDGE_MARGIN;
            // Нижний край окна (scrollY + viewportHeight) минус высота формы минус отступ
            const maxTop = scrollY + viewportHeight - formHeight - EDGE_MARGIN;

            // --- ИЗМЕНЕНО: Ограничиваем newLeft и newTop расчитанными границами ---
            // Убеждаемся, что newLeft не меньше minLeft и не больше maxLeft
            // Также обрабатываем случай, когда форма шире/выше окна (maxLeft/maxTop < minLeft/minTop)
            newLeft = Math.max(minLeft, Math.min(newLeft, maxLeft));
            // Убеждаемся, что newTop не меньше minTop и не больше maxTop
            newTop = Math.max(minTop, Math.min(newTop, maxTop));

            // Применяем скорректированные координаты
            draggableForm.style.left = newLeft + 'px';
            draggableForm.style.top = newTop + 'px';

            // Установка фокуса (тоже лучше внутри rAF)
            if (elementToFocus) {
                requestAnimationFrame(() => { // Дополнительный rAF для фокуса после позиционирования
                    try {
                        elementToFocus.focus();
                        if (typeof elementToFocus.setSelectionRange === 'function') {
                            const textLength = elementToFocus.value.length;
                            elementToFocus.setSelectionRange(textLength, textLength);
                        }
                        elementToFocus.scrollTop = elementToFocus.scrollHeight;
                    } catch (err) {
                        console.error('[Form] Ошибка установки фокуса:', err);
                    }
                });
            }
        });
    }

    function closeDraggableForm(event = null) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        clearFilesAndPreviews();
        draggableForm.style.display = 'none';
        isDraggingForm = false;

        if (submitButton) {
            submitButton.disabled = false;
            const originalValue = submitButton.dataset.originalValue;
            // Важно: Замените 'Отправить' на ваш текст по умолчанию или переменную из lang
            const defaultValue = 'Отправить'; // '{% if post_mode == "reply" %}New Reply{% else %}{{ lang["thread-form-button"] }}{% endif %}';
            submitButton.value = originalValue || defaultValue;
            delete submitButton.dataset.originalValue;
        }
        if (sendingIndicator) {
            sendingIndicator.style.display = 'none';
        }
    }


    // --- Обработчики событий для открытия/закрытия ---
     document.addEventListener('click', function(event) {
         if (isDraggingForm) {
            return;
        }
        const quoteLink = event.target.closest('a.js-quote-link');
        const toggleButton = event.target.closest('#togglePostFormLink a');
        const isClickInsideForm = event.target.closest('#draggableForm');
        const isClickOnCloseButton = event.target.closest('.close.postform-style');
        const isFormVisible = window.getComputedStyle(draggableForm).display !== 'none';

        if (quoteLink) {
            const postId = quoteLink.dataset.postId;
            openDraggableForm(event, postId);
        } else if (toggleButton) {
            event.preventDefault();
            if (isFormVisible) {
                closeDraggableForm();
            } else {
                openDraggableForm(event);
            }
        } else if (isClickOnCloseButton && isFormVisible) {
            // Клик на крестик обработается ниже
        } else if (!isClickInsideForm && isFormVisible) {
            // closeDraggableForm(); // Раскомментировать для закрытия при клике вне формы
        }
    });


    // Отдельный обработчик для кнопки закрытия (крестика)
    if (closeButton) {
        closeButton.addEventListener('click', (e) => {
             closeDraggableForm(e);
        });
    }


    // --- Логика перетаскивания самой ФОРМЫ ---
     if (header) {
        header.addEventListener('mousedown', function(e) {
            if (e.button !== 0 || window.getComputedStyle(draggableForm).display === 'none' || e.target.closest('button, a, input, select, textarea')) {
                return;
            }
            e.preventDefault();
            isDraggingForm = true;

            const rect = draggableForm.getBoundingClientRect();
            const shiftX = e.clientX - rect.left;
            const shiftY = e.clientY - rect.top;
            const formWidth = draggableForm.offsetWidth;
            const formHeight = draggableForm.offsetHeight;
            const initialZIndex = draggableForm.style.zIndex || 1000;

            draggableForm.style.position = 'absolute';
            draggableForm.style.zIndex = 2000;
            document.body.style.userSelect = 'none';

            function moveAt(pageX, pageY) {
                let newLeft = pageX - shiftX;
                let newTop = pageY - shiftY;

                const viewportWidth = document.documentElement.clientWidth;
                const viewportHeight = document.documentElement.clientHeight;
                const scrollX = window.scrollX;
                const scrollY = window.scrollY;

                // --- ИЗМЕНЕНО: Используем EDGE_MARGIN и при перетаскивании ---
                const minLeft = scrollX + EDGE_MARGIN;
                const minTop = scrollY + EDGE_MARGIN;
                const maxLeft = scrollX + viewportWidth - formWidth - EDGE_MARGIN;
                const maxTop = scrollY + viewportHeight - formHeight - EDGE_MARGIN;

                newLeft = Math.max(minLeft, Math.min(newLeft, maxLeft));
                newTop = Math.max(minTop, Math.min(newTop, maxTop));

                draggableForm.style.left = newLeft + 'px';
                draggableForm.style.top = newTop + 'px';
            }
            moveAt(e.pageX, e.pageY);

            function onMouseMove(event) {
                 if (!isDraggingForm) return;
                moveAt(event.pageX, event.pageY);
            }

            function onMouseUp() {
                if (!isDraggingForm) return;
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                draggableForm.style.zIndex = initialZIndex;
                document.body.style.userSelect = '';
                 setTimeout(() => { isDraggingForm = false; }, 50);
            }
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            draggableForm.ondragstart = () => false;
        });
    }


    // --- Обработчик вставки файлов (Ctrl+V) в поле текста ---
     if (messageTextarea) {
        messageTextarea.addEventListener('paste', (event) => {
            if (event.clipboardData && event.clipboardData.files && event.clipboardData.files.length > 0) {
                event.preventDefault();
                const pastedFiles = event.clipboardData.files;
                addFilePreviews(pastedFiles);
            }
        });
    }


    // --- ОБРАБОТКА DRAG-N-DROP ФАЙЛОВ на label ---
    if (dropZoneLabel && fileInput) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZoneLabel.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZoneLabel.addEventListener(eventName, () => {
                dropZoneLabel.classList.add('dragover-active');
            }, false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
             dropZoneLabel.addEventListener(eventName, () => {
                dropZoneLabel.classList.remove('dragover-active');
            }, false);
        });
        dropZoneLabel.addEventListener('drop', (event) => {
            const droppedFiles = event.dataTransfer.files;
            if (droppedFiles && droppedFiles.length > 0) {
                addFilePreviews(droppedFiles);
            }
        }, false);
    } else {
        if (!dropZoneLabel) console.warn("[DragNDrop] Зона для перетаскивания (label.filelabel) не найдена.");
    }


    // --- ОТПРАВКА ФОРМЫ ПО CTRL+ENTER из поля текста ---
     if (messageTextarea && postForm && submitButton) {
        messageTextarea.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                submitButton.click();
            }
        });
    } else {
        if (!messageTextarea) console.warn("[Ctrl+Enter] Элемент textarea#text не найден.");
        if (!postForm) console.warn("[Ctrl+Enter] Элемент формы #postform не найден.");
        if (!submitButton) console.warn("[Ctrl+Enter] Кнопка #submitpost не найдена.");
    }


    // --- Обработка отправки формы (показ спиннера, блокировка кнопки) ---
    if (postForm && submitButton && sendingIndicator) {
        postForm.addEventListener('submit', (event) => {
            console.log("Форма отправляется...");
            if (!submitButton.dataset.originalValue) {
                submitButton.dataset.originalValue = submitButton.value;
            }
            submitButton.disabled = true;
            submitButton.value = 'Sending...'; // Используйте текст по умолчанию или из lang
            sendingIndicator.style.display = 'inline-block';
        });
    } else {
        console.warn("[Submit Handler] Не удалось настроить обработчик отправки из-за отсутствия #postform, #submitpost или #sendingIndicator.");
    }

}); // --- Конец DOMContentLoaded ---