(function() { // Используем IIFE для изоляции
    const themeSelector = document.getElementById('theme-selector');
    const customCssModal = document.getElementById('custom-css-modal');
    const customCssInput = document.getElementById('custom-css-input');
    const saveCustomCssButton = document.getElementById('save-custom-css');
    const cancelCustomCssButton = document.getElementById('cancel-custom-css');

    // --- Константы ---
    const THEME_LINK_ID = 'dynamic-theme-link'; // ID для <link>
    const CUSTOM_STYLE_ID = 'dynamic-custom-style'; // ID для <style>
    const STORAGE_KEY_SELECTED = 'selectedTheme'; // Ключ для localStorage (выбор)
    const STORAGE_KEY_CUSTOM_CSS = 'customThemeCss'; // Ключ для localStorage (CSS текст)

    // --- Переменная для отмены ---
    let previousThemeValue = null; // Храним предыдущее значение селектора

    // --- Функции модального окна ---
    function showCustomCssModal() {
        // Запоминаем текущее значение перед показом (для отмены)
        // Ищем активную тему (вдруг страница загрузилась с custom)
        const activeTheme = localStorage.getItem(STORAGE_KEY_SELECTED) || 'none';
        // Если текущее значение селектора не "custom", значит мы его только что выбрали
        // и предыдущее значение - это то, что было до "custom"
        if (themeSelector && themeSelector.value !== 'custom') {
             previousThemeValue = themeSelector.value;
        } else {
             // Если селектор уже был "custom", то предыдущее - это то, что сохранено
             // (или 'none', если ничего не сохранено кроме custom)
             previousThemeValue = activeTheme === 'custom' ? 'none' : activeTheme;
        }


        // Загружаем сохраненный CSS в textarea
        const savedCustomCss = localStorage.getItem(STORAGE_KEY_CUSTOM_CSS) || '';
        if (customCssInput) {
            customCssInput.value = savedCustomCss;
        }
        if (customCssModal) {
            customCssModal.style.display = 'flex';
        }
    }

    function hideCustomCssModal() {
        if (customCssModal) {
            customCssModal.style.display = 'none';
        }
    }

    // --- Функции управления стилями ---

    // Универсальная функция удаления ЛЮБОЙ динамической темы (link или style)
    function removeCurrentThemeStyle() {
        const existingLink = document.getElementById(THEME_LINK_ID);
        if (existingLink) {
            existingLink.remove();
            // console.log('Removed theme link:', existingLink.href);
        }
        const existingStyle = document.getElementById(CUSTOM_STYLE_ID);
        if (existingStyle) {
            existingStyle.remove();
            // console.log('Removed custom style tag.');
        }
    }

    // Применение темы из файла (URL)
    function applyThemeFromFile(themeUrl) {
        removeCurrentThemeStyle(); // Удаляем предыдущие стили

        if (!themeUrl || themeUrl === 'none') {
             // console.log('Applying no theme.');
            return; // Ничего не добавляем, если 'none'
        }

        const newLink = document.createElement('link');
        newLink.rel = 'stylesheet';
        newLink.href = themeUrl;
        newLink.id = THEME_LINK_ID; // Используем ID
        document.head.appendChild(newLink);
        // console.log('Applied theme from file:', themeUrl);
    }

    // Применение пользовательского CSS из текста
    function applyCustomCss(cssText) {
        removeCurrentThemeStyle(); // Удаляем предыдущие стили

        if (!cssText) {
             // console.log('Applying no custom CSS (empty).');
            return; // Ничего не добавляем, если текст пуст
        }

        const newStyle = document.createElement('style');
        newStyle.id = CUSTOM_STYLE_ID; // Используем ID
        newStyle.textContent = cssText; // Вставляем CSS как текст
        document.head.appendChild(newStyle);
        // console.log('Applied custom CSS.');
    }

    // --- Инициализация при загрузке страницы ---
    function initializeTheme() {
        const savedThemeSelection = localStorage.getItem(STORAGE_KEY_SELECTED);

        if (savedThemeSelection === 'custom') {
            const savedCustomCss = localStorage.getItem(STORAGE_KEY_CUSTOM_CSS);
            applyCustomCss(savedCustomCss || ''); // Применяем сохраненный CSS
            if (themeSelector) themeSelector.value = 'custom'; // Устанавливаем селектор
        } else if (savedThemeSelection && savedThemeSelection !== 'none') {
            applyThemeFromFile(savedThemeSelection); // Применяем тему из файла
            if (themeSelector) themeSelector.value = savedThemeSelection; // Устанавливаем селектор
        } else {
            // Нет сохраненной темы или выбрано 'none'
            removeCurrentThemeStyle(); // Просто удаляем (на всякий случай)
            if (themeSelector) themeSelector.value = 'none'; // Устанавливаем селектор в 'none'
        }
    }

    // --- Обработчики событий ---

    // Изменение в селекторе
    if (themeSelector) {
        themeSelector.addEventListener('change', function() {
            const selectedValue = this.value;

            // Сразу сохраняем выбор в localStorage
            localStorage.setItem(STORAGE_KEY_SELECTED, selectedValue);

            if (selectedValue === 'custom') {
                showCustomCssModal(); // Показываем окно для ввода
                // Не применяем стили сразу, ждем нажатия "Сохранить"
            } else if (selectedValue === 'none') {
                removeCurrentThemeStyle(); // Удаляем стили
                localStorage.removeItem(STORAGE_KEY_CUSTOM_CSS); // Опционально: очистить сохраненный кастомный CSS при выборе "none"? Решите сами. Оставим сохраненным.
            } else {
                applyThemeFromFile(selectedValue); // Применяем тему из файла
            }
        });
    } else {
         console.warn('Theme selector element with ID "theme-selector" not found.');
    }

    // Кнопка "Сохранить" в модальном окне
    if (saveCustomCssButton) {
        saveCustomCssButton.addEventListener('click', function() {
            const cssText = customCssInput ? customCssInput.value : '';
            localStorage.setItem(STORAGE_KEY_CUSTOM_CSS, cssText); // Сохраняем CSS текст
            localStorage.setItem(STORAGE_KEY_SELECTED, 'custom'); // Убеждаемся, что выбор 'custom' сохранен
            applyCustomCss(cssText); // Применяем введенный CSS
            hideCustomCssModal(); // Скрываем окно
            if (themeSelector) themeSelector.value = 'custom'; // Обновляем селектор на всякий случай
        });
    }

    // Кнопка "Отмена" в модальном окне
    if (cancelCustomCssButton) {
        cancelCustomCssButton.addEventListener('click', function() {
            hideCustomCssModal(); // Просто скрываем окно
            // Восстанавливаем предыдущее значение селектора и сохраненный выбор
            if (themeSelector && previousThemeValue !== null) {
                themeSelector.value = previousThemeValue;
                // Имитируем событие change, чтобы применилась предыдущая тема
                // и значение сохранилось в localStorage
                themeSelector.dispatchEvent(new Event('change'));
            } else if (themeSelector) {
                // Если нет previousThemeValue, просто откатываем на 'none'
                 themeSelector.value = 'none';
                 themeSelector.dispatchEvent(new Event('change'));
            }
        });
    }

    // --- Запуск инициализации ---
    initializeTheme();

})(); // Конец IIFE
