document.addEventListener('DOMContentLoaded', function() {
    // Проверяем наличие обоих элементов
    const button = document.getElementById('waring-button');
    const container = document.getElementById('waring-container');
    
    if (!button || !container) {
        console.warn('Элементы для закрытия сообщения не найдены');
        return;
    }
    
    // Добавляем обработчик
    button.addEventListener('click', function() {
        container.style.display = 'none';
        
        // Дополнительно: можно добавить анимацию
        container.style.transition = 'opacity 0.3s';
        container.style.opacity = '0';
        
        setTimeout(() => {
            container.style.display = 'none';
        }, 300);
    });
});