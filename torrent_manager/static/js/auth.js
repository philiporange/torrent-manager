// Auth Logic for Login Page

async function handleLogin(event) {
    event.preventDefault();
    const form = event.target;
    const username = form.username.value;
    const password = form.password.value;
    const rememberMe = form.rememberMe.checked;
    const btn = form.querySelector('button[type="submit"]');
    
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Signing in...';

    try {
        await apiRequest('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password, remember_me: rememberMe })
        });
        window.location.href = '/';
    } catch (error) {
        btn.disabled = false;
        btn.innerHTML = originalText;
        // Error handled by apiRequest
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const form = event.target;
    const username = form.username.value;
    const password = form.password.value;
    const btn = form.querySelector('button[type="submit"]');

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Creating...';

    try {
        await apiRequest('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        
        showToast('Registration successful! Please login.', 'success');
        
        // Switch tabs (simple implementation)
        document.getElementById('tab-login').click();
        form.reset();
        document.getElementById('login-username').value = username;
        
    } catch (error) {
        // Error handled
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const loginTab = document.getElementById('tab-login');
    const registerTab = document.getElementById('tab-register');
    const loginForm = document.getElementById('login-form-container');
    const registerForm = document.getElementById('register-form-container');

    if (loginTab && registerTab) {
        loginTab.addEventListener('click', () => {
            loginTab.classList.add('text-indigo-600', 'border-indigo-600');
            loginTab.classList.remove('text-slate-500', 'border-transparent');
            registerTab.classList.add('text-slate-500', 'border-transparent');
            registerTab.classList.remove('text-indigo-600', 'border-indigo-600');
            
            loginForm.classList.remove('hidden');
            registerForm.classList.add('hidden');
        });

        registerTab.addEventListener('click', () => {
            registerTab.classList.add('text-indigo-600', 'border-indigo-600');
            registerTab.classList.remove('text-slate-500', 'border-transparent');
            loginTab.classList.add('text-slate-500', 'border-transparent');
            loginTab.classList.remove('text-indigo-600', 'border-indigo-600');
            
            registerForm.classList.remove('hidden');
            loginForm.classList.add('hidden');
        });
    }
    
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('register-form').addEventListener('submit', handleRegister);
});
