document.addEventListener('DOMContentLoaded', () => {
    const draggableForm = document.getElementById('draggableForm');
    if (!draggableForm) {
        console.error("[Init] Draggable form element with ID 'draggableForm' not found!");
        return;
    }

    const header = draggableForm.querySelector('.new-thread-header');
    const closeButton = draggableForm.querySelector('.close.postform-style');
    const messageTextarea = draggableForm.querySelector('textarea');
    const fileInput = draggableForm.querySelector('input[type="file"]');
    const uploadList = draggableForm.querySelector('.upload-list');
    let isDragging = false;

    // Функция для обновления списка файлов
    function updateFileList() {
        if (!fileInput || !uploadList) return;

        uploadList.innerHTML = '';

        if (fileInput.files.length === 0) {
            uploadList.style.display = 'none';
            return;
        }

        uploadList.style.display = 'block';

        for (let i = 0; i < fileInput.files.length; i++) {
            const file = fileInput.files[i];
            const fileElement = document.createElement('div');
            fileElement.className = 'upload-item';
            fileElement.innerHTML = `
                <span class="file-icon">📄</span>
                <span class="filename">${file.name}</span>
                <span class="filesize">(${(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                <span class="remove-file" data-index="${i}" title="Remove file">×</span>
            `;
            uploadList.appendChild(fileElement);
        }

        const removeButtons = uploadList.querySelectorAll('.remove-file');
        removeButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const index = parseInt(button.getAttribute('data-index'));
                removeFile(index);
            });
        });
    }

    function removeFile(index) {
        if (!fileInput) return;

        const dataTransfer = new DataTransfer();
        for (let i = 0; i < fileInput.files.length; i++) {
            if (i !== index) {
                dataTransfer.items.add(fileInput.files[i]);
            }
        }
        fileInput.files = dataTransfer.files;
        updateFileList();
    }

    // Обработчик вставки файлов
    if (messageTextarea) {
        messageTextarea.addEventListener('paste', async (event) => {
            const items = (event.clipboardData || event.originalEvent.clipboardData).items;
            let filePasted = false;
            
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file && fileInput) {
                        filePasted = true;
                        const dataTransfer = new DataTransfer();
                        
                        for (let j = 0; j < fileInput.files.length; j++) {
                            dataTransfer.items.add(fileInput.files[j]);
                        }
                        
                        dataTransfer.items.add(file);
                        fileInput.files = dataTransfer.files;
                        updateFileList();
                    }
                }
            }
            
            if (filePasted) {
                event.preventDefault();
                // Показываем уведомление о добавлении файла
                const notification = document.createElement('div');
                notification.className = 'file-notification';
                notification.textContent = 'File added from clipboard';
                document.body.appendChild(notification);
                setTimeout(() => notification.remove(), 2000);
            }
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', updateFileList);
        
        // Drag and drop для файлов
        const fileLabel = draggableForm.querySelector('.filelabel');
        if (fileLabel) {
            fileLabel.addEventListener('dragover', (e) => {
                e.preventDefault();
                fileLabel.style.backgroundColor = '#e0e0e0';
            });
            
            fileLabel.addEventListener('dragleave', () => {
                fileLabel.style.backgroundColor = '#f0f0f0';
            });
            
            fileLabel.addEventListener('drop', (e) => {
                e.preventDefault();
                fileLabel.style.backgroundColor = '#f0f0f0';
                
                if (e.dataTransfer.files.length > 0) {
                    const dataTransfer = new DataTransfer();
                    
                    // Добавляем существующие файлы
                    for (let i = 0; i < fileInput.files.length; i++) {
                        dataTransfer.items.add(fileInput.files[i]);
                    }
                    
                    // Добавляем новые файлы
                    for (let i = 0; i < e.dataTransfer.files.length; i++) {
                        dataTransfer.items.add(e.dataTransfer.files[i]);
                    }
                    
                    fileInput.files = dataTransfer.files;
                    updateFileList();
                }
            });
        }
    }

    function openDraggableForm(event, postId = null) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        let elementToFocus = null;
        if (postId && messageTextarea) {
            const quoteText = ">>" + postId + "\n";
            const currentValue = messageTextarea.value;
            let textToAdd;

            if (currentValue.length > 0 && !currentValue.endsWith('\n')) {
                textToAdd = "\n" + quoteText;
            } else {
                textToAdd = quoteText;
            }

            messageTextarea.value += textToAdd;
            elementToFocus = messageTextarea;
        }

        const clickX = event ? event.pageX : (window.scrollX + window.innerWidth / 2);
        const clickY = event ? event.pageY : (window.scrollY + 50);

        draggableForm.style.position = 'absolute';
        draggableForm.style.display = 'block';

        const formWidth = draggableForm.offsetWidth;
        const formHeight = draggableForm.offsetHeight;

        let newLeft = clickX - (event ? 0 : formWidth / 2);
        let newTop = clickY + (event ? 10 : 0);

        const docWidth = Math.max(
            document.body.scrollWidth, document.documentElement.scrollWidth,
            document.body.offsetWidth, document.documentElement.offsetWidth,
            document.body.clientWidth, document.documentElement.clientWidth
        );
        const docHeight = Math.max(
            document.body.scrollHeight, document.documentElement.scrollHeight,
            document.body.offsetHeight, document.documentElement.offsetHeight,
            document.body.clientHeight, document.documentElement.clientHeight
        );

        const rightEdge = docWidth - formWidth;
        const bottomEdge = docHeight - formHeight;

        newLeft = Math.max(0, Math.min(newLeft, rightEdge));
        newTop = Math.max(0, Math.min(newTop, bottomEdge)) -50;

        draggableForm.style.left = newLeft + 'px';
        draggableForm.style.top = newTop + 'px';

        if (elementToFocus) {
            setTimeout(() => {
                try {
                    elementToFocus.focus();
                    const textLength = elementToFocus.value.length;
                    elementToFocus.selectionStart = textLength;
                    elementToFocus.selectionEnd = textLength;
                    elementToFocus.scrollTop = elementToFocus.scrollHeight;
                } catch (err) {
                    console.error('[Form] Error setting focus:', err);
                }
            }, 0);
        }
    }

    function closeDraggableForm(event = null) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if (messageTextarea) {
            messageTextarea.value = '';
        }
        if (fileInput) {
            fileInput.value = '';
        }
        if (uploadList) {
            uploadList.innerHTML = '';
            uploadList.style.display = 'none';
        }
        draggableForm.style.display = 'none';
    }

    document.addEventListener('click', function(event) {
        if (isDragging) {
            isDragging = false;
            return;
        }

        const quoteLink = event.target.closest('a.js-quote-link');
        const toggleButton = event.target.closest('#togglePostFormLink');
        const isFormClick = event.target.closest('#draggableForm');

        if (quoteLink) {
            openDraggableForm(event, quoteLink.dataset.postId);
        } else if (toggleButton) {
            if (window.getComputedStyle(draggableForm).display === 'none') {
                openDraggableForm(event);
            } else {
                closeDraggableForm();
            }
        } else if (!isFormClick) {
            closeDraggableForm();
        }
    });

    if (closeButton) {
        closeButton.addEventListener('click', closeDraggableForm);
    }

    if (header) {
        header.addEventListener('mousedown', function(e) {
            if (window.getComputedStyle(draggableForm).display === 'none') return;

            isDragging = true;
            e.stopPropagation();
            e.preventDefault();

            let rect = draggableForm.getBoundingClientRect();
            let shiftX = e.clientX - rect.left;
            let shiftY = e.clientY - rect.top;
            const formWidth = draggableForm.offsetWidth;
            const formHeight = draggableForm.offsetHeight;
            const originalZIndex = draggableForm.style.zIndex;

            draggableForm.style.position = 'absolute';
            draggableForm.style.zIndex = (parseInt(originalZIndex) || 1000) + 1;

            function moveAt(pageX, pageY) {
                let newLeft = pageX - shiftX;
                let newTop = pageY - shiftY;
                const docWidth = Math.max(
                    document.body.scrollWidth, document.documentElement.scrollWidth,
                    document.body.offsetWidth, document.documentElement.offsetWidth,
                    document.body.clientWidth, document.documentElement.clientWidth
                );
                const docHeight = Math.max(
                    document.body.scrollHeight, document.documentElement.scrollHeight,
                    document.body.offsetHeight, document.documentElement.offsetHeight,
                    document.body.clientHeight, document.documentElement.clientHeight
                );

                newLeft = Math.max(0, Math.min(newLeft, docWidth - formWidth));
                newTop = Math.max(0, Math.min(newTop, docHeight - formHeight));

                draggableForm.style.left = newLeft + 'px';
                draggableForm.style.top = newTop + 'px';
            }

            function onMouseMove(event) {
                moveAt(event.pageX, event.pageY);
            }

            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                draggableForm.style.zIndex = originalZIndex;
                draggableForm.ondragstart = null;
                setTimeout(() => { isDragging = false; }, 100);
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp, { once: true });

            draggableForm.ondragstart = () => false;
        });
    }

    // Инициализация списка файлов при загрузке
    updateFileList();
});