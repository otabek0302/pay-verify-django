// Enhanced Toast notification system
function showToast(message, type = 'info', duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${getToastIcon(type)}</div>
        <div class="toast-content">${message}</div>
        <button class="toast-close" onclick="closeToast(this)">&times;</button>
    `;
    
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 100);
    
    // Auto remove
    setTimeout(() => {
        if (toast.parentNode) {
            closeToast(toast.querySelector('.toast-close'));
        }
    }, duration);
}

function getToastIcon(type) {
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    return icons[type] || icons.info;
}

function closeToast(button) {
    const toast = button.closest('.toast');
    toast.classList.remove('show');
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 300);
}

// Enhanced message system with animations
function showMessage(message, type = 'info', duration = 5000) {
    // Try toast first, fallback to legacy message
    if (document.querySelector('.toast-container') || type !== 'info') {
        showToast(message, type, duration);
        return;
    }
    
    const messageEl = document.createElement('div');
    messageEl.className = `message ${type}`;
    messageEl.textContent = message;
    
    // Remove existing messages
    const existingMessages = document.querySelectorAll('.message');
    existingMessages.forEach(msg => msg.remove());
    
    document.body.appendChild(messageEl);
    
    // Trigger animation
    setTimeout(() => messageEl.classList.add('show'), 100);
    
    // Auto remove
    setTimeout(() => {
        if (messageEl.parentNode) {
            messageEl.classList.remove('show');
            setTimeout(() => {
                if (messageEl.parentNode) {
                    messageEl.parentNode.removeChild(messageEl);
                }
            }, 300);
        }
    }, duration);
}

function validateForm(form) {
    const inputs = form.querySelectorAll('input[required], select[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = 'var(--error-color)';
            input.style.boxShadow = '0 0 0 3px rgba(239, 68, 68, 0.1)';
            isValid = false;
        } else {
            input.style.borderColor = 'var(--border)';
            input.style.boxShadow = 'none';
        }
    });
    
    return isValid;
}

function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        }
    };
    
    return fetch(url, { ...defaultOptions, ...options });
}

function getCSRFToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// General page initialization
document.addEventListener('DOMContentLoaded', function() {
    
    // Sidebar navigation highlighting
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar-nav .nav-link');
    
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
    
    // Mobile sidebar toggle (if needed)
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            const sidebar = document.querySelector('.sidebar');
            sidebar.classList.toggle('open');
        });
    }
});

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    showMessage('An unexpected error occurred', 'error');
});

// Export functions for use in templates
window.PayVerify = {
    showMessage,
    showToast,
    validateForm,
    apiRequest,
    getCSRFToken,
    closeToast
};
