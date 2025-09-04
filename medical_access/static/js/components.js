// === Components JS ===

// === Message Components ===
function showMessage(message, type = 'info', duration = 5000) {
    const messageDiv = document.getElementById('message');
    if (!messageDiv) {
        console.error('Message element not found');
        return;
    }
    
    messageDiv.textContent = message;
    messageDiv.className = `message message-${type}`;
    messageDiv.style.display = 'block';
    
    // Trigger animation
    setTimeout(() => {
        messageDiv.classList.add('show');
    }, 10);
    
    // Click to close
    messageDiv.onclick = function() {
        messageDiv.classList.remove('show');
        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 300);
    };
    
    // Auto close
    setTimeout(() => {
        messageDiv.classList.remove('show');
        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 300);
    }, duration);
}