document.addEventListener('DOMContentLoaded', () => {
    const draggableForm = document.getElementById('draggableForm');
    if (!draggableForm) {
        console.error("[Init] Draggable form element with ID 'draggableForm' not found!");
        return;
    }

    const header = draggableForm.querySelector('.new-thread-header');
    const closeButton = draggableForm.querySelector('.close.postform-style');
    const messageTextarea = draggableForm.querySelector('textarea');
    let isDragging = false; // Флаг для отслеживания состояния перетаскивания

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
        draggableForm.style.top = newTop + 'px' ;

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
        draggableForm.style.display = 'none';
    }

    document.addEventListener('click', function(event) {
        // Если происходит перетаскивание, игнорируем клик
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
            // Закрываем форму только если клик был вне формы
            closeDraggableForm();
        }
    });

    if (closeButton) {
        closeButton.addEventListener('click', closeDraggableForm);
    }

    if (header) {
        header.addEventListener('mousedown', function(e) {
            if (window.getComputedStyle(draggableForm).display === 'none') return;

            isDragging = true; // Устанавливаем флаг перетаскивания
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
                // Не сбрасываем isDragging здесь, чтобы клик после перетаскивания не закрывал форму
                setTimeout(() => { isDragging = false; }, 100);
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp, { once: true });

            draggableForm.ondragstart = () => false;
        });
    }
});