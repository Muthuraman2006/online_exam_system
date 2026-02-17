/* ExamPro - Unified API Client + Futuristic Effects */
const API = '/api/v1';
const CACHE = new Map();
const CACHE_TTL = 30000; // 30 seconds

/* ============ Background (disabled - CSS gradient provides visual effect) ============ */
const NeoBackground = { init() {} };

// Token Management
const Auth = {
  TOKEN_KEY: 'exampro-token',
  USER_KEY: 'exampro-user',
  
  getToken: () => localStorage.getItem(Auth.TOKEN_KEY),
  getUser: () => JSON.parse(localStorage.getItem(Auth.USER_KEY) || 'null'),
  
  setAuth: (token, user) => {
    localStorage.setItem(Auth.TOKEN_KEY, token);
    localStorage.setItem(Auth.USER_KEY, JSON.stringify(user));
  },
  
  clear: () => {
    localStorage.removeItem(Auth.TOKEN_KEY);
    localStorage.removeItem(Auth.USER_KEY);
    CACHE.clear();
  },
  
  isValid: () => {
    const token = Auth.getToken();
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return Date.now() < payload.exp * 1000;
    } catch { return false; }
  },
  
  getRole: () => {
    const user = Auth.getUser();
    return user?.role?.toLowerCase() || null;
  },
  
  requireAuth: (allowedRoles = []) => {
    if (!Auth.isValid()) {
      window.location.href = '/login.html';
      return false;
    }
    if (allowedRoles.length && !allowedRoles.includes(Auth.getRole())) {
      window.location.href = '/login.html';
      return false;
    }
    return true;
  },
  
  logout: () => {
    Auth.clear();
    window.location.href = '/login.html';
  }
};

// HTTP Client with proper error handling and response timing
const http = {
  // Track pending requests to prevent duplicates
  _pending: new Map(),
  
  async request(method, endpoint, data = null, useCache = false) {
    const url = `${API}${endpoint}`;
    const cacheKey = `${method}:${url}`;
    const startTime = performance.now();
    
    // Check cache for GET requests
    if (method === 'GET' && useCache) {
      const cached = CACHE.get(cacheKey);
      if (cached && Date.now() - cached.time < CACHE_TTL) {
        console.log(`[CACHE HIT] ${method} ${endpoint} (${Math.round(performance.now() - startTime)}ms)`);
        return cached.data;
      }
    }
    
    // Prevent duplicate concurrent requests for same endpoint
    if (method === 'GET' && this._pending.has(cacheKey)) {
      return this._pending.get(cacheKey);
    }
    
    const headers = { 'Content-Type': 'application/json' };
    const token = Auth.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    
    const config = { method, headers };
    if (data) config.body = JSON.stringify(data);
    
    const requestPromise = (async () => {
      try {
        const res = await fetch(url, config);
        const duration = Math.round(performance.now() - startTime);
        console.log(`[API] ${method} ${endpoint} - ${res.status} (${duration}ms)`);
        
        if (res.status === 401) {
          Auth.clear();
          window.location.href = '/login.html?expired=1';
          throw new Error('Session expired');
        }
        
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          // Create enhanced error with field-level details
          const error = new Error(err.detail || `Request failed: ${res.status}`);
          error.errors = err.errors || [];
          error.status = res.status;
          error.statusText = res.statusText;
          
          // Log validation errors for debugging
          if (err.errors && err.errors.length > 0) {
            console.warn('[VALIDATION ERRORS]', err.errors);
          }
          
          throw error;
        }
        
        // Handle 204 No Content (common for DELETE requests)
        if (res.status === 204) {
          return {};
        }
        
        const result = res.headers.get('content-type')?.includes('json') 
          ? await res.json() 
          : {};
        
        // Cache GET responses
        if (method === 'GET' && useCache) {
          CACHE.set(cacheKey, { data: result, time: Date.now() });
        }
        
        return result;
      } finally {
        // Clean up pending request
        if (method === 'GET') {
          this._pending.delete(cacheKey);
        }
      }
    })();
    
    // Store pending GET requests
    if (method === 'GET') {
      this._pending.set(cacheKey, requestPromise);
    }
    
    return requestPromise;
  },
  
  get: (url, cache = true) => http.request('GET', url, null, cache),
  post: (url, data) => http.request('POST', url, data),
  patch: (url, data) => http.request('PATCH', url, data),
  put: (url, data) => http.request('PUT', url, data),
  delete: (url) => http.request('DELETE', url),
  
  clearCache: () => CACHE.clear()
};

// UI Helpers with improved error handling
const UI = {
  toast: (msg, type = 'success') => {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('fade-out');
      toast.addEventListener('transitionend', () => toast.remove(), { once: true });
      setTimeout(() => toast.remove(), 500);
    }, 3000);
  },
  
  loading: (el, show = true, timeoutMs = 10000) => {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    if (show) {
      el.dataset.originalContent = el.innerHTML;
      el.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
      // Timeout fallback: show error message after timeoutMs
      if (timeoutMs > 0) {
        el._loadingTimeout = setTimeout(() => {
          if (el.querySelector('.spinner')) {
            el.innerHTML = '<div class="empty"><div class="empty-title">Request timed out</div><p class="text-sm text-gray">Please refresh the page</p></div>';
          }
        }, timeoutMs);
      }
    } else {
      if (el._loadingTimeout) {
        clearTimeout(el._loadingTimeout);
        delete el._loadingTimeout;
      }
      if (el.dataset.originalContent) {
        el.innerHTML = el.dataset.originalContent;
        delete el.dataset.originalContent;
      }
    }
  },
  
  empty: (el, msg = 'No data found') => {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    el.innerHTML = `<div class="empty"><div class="empty-title">${msg}</div></div>`;
  },
  
  // Form validation helpers
  clearErrors: (form) => {
    if (typeof form === 'string') form = document.getElementById(form);
    if (!form) return;
    form.querySelectorAll('.form-error').forEach(el => el.remove());
    form.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
  },
  
  showFieldError: (fieldId, message) => {
    const field = document.getElementById(fieldId);
    if (!field) return false;
    
    // Add error class to input
    field.classList.add('input-error');
    
    // Remove existing error for this field
    const existing = field.parentElement.querySelector('.form-error');
    if (existing) existing.remove();
    
    // Add error message
    const errorEl = document.createElement('div');
    errorEl.className = 'form-error';
    errorEl.textContent = message;
    field.parentElement.appendChild(errorEl);
    
    // Scroll to first error
    field.scrollIntoView({ behavior: 'smooth', block: 'center' });
    field.focus();
    
    return true;
  },
  
  showErrors: (form, errors) => {
    if (typeof form === 'string') form = document.getElementById(form);
    UI.clearErrors(form);
    
    if (!errors || !errors.length) return;
    
    let firstErrorField = null;
    
    errors.forEach(err => {
      // Try to find matching input field - comprehensive field name mapping
      const fieldName = err.field.toLowerCase();
      const dashField = fieldName.replace(/_/g, '-');
      const formPrefix = form?.id?.replace('-form', '') || '';
      
      const possibleIds = [
        fieldName,
        dashField,
        `${formPrefix}-${fieldName}`,
        `${formPrefix}-${dashField}`,
        err.field,
        // Common field mappings
        fieldName === 'question_bank_id' ? 'exam-bank' : null,
        fieldName === 'question_text' ? 'q-text' : null,
        fieldName === 'correct_answer' ? 'q-correct' : null,
        fieldName === 'duration_minutes' ? 'exam-duration' : null,
        fieldName === 'total_questions' ? 'exam-questions' : null,
        fieldName === 'total_marks' ? 'exam-total' : null,
        fieldName === 'passing_marks' ? 'exam-passing' : null,
        fieldName === 'start_time' ? 'exam-start' : null,
        fieldName === 'end_time' ? 'exam-end' : null,
      ].filter(Boolean);
      
      let found = false;
      for (const id of possibleIds) {
        const field = document.getElementById(id);
        if (field) {
          if (!firstErrorField) firstErrorField = field;
          // Add error styling
          field.classList.add('input-error');
          const existing = field.parentElement.querySelector('.form-error');
          if (existing) existing.remove();
          const errorEl = document.createElement('div');
          errorEl.className = 'form-error';
          errorEl.textContent = err.message;
          field.parentElement.appendChild(errorEl);
          found = true;
          break;
        }
      }
      
      // If no field found, show as toast
      if (!found) {
        UI.toast(`${err.field}: ${err.message}`, 'error');
      }
    });
    
    // Focus on first error field
    if (firstErrorField) {
      firstErrorField.scrollIntoView({ behavior: 'smooth', block: 'center' });
      firstErrorField.focus();
    }
  },
  
  // Button loading state
  btnLoading: (btn, loading = true) => {
    if (typeof btn === 'string') btn = document.querySelector(btn);
    if (!btn) return;
    
    if (loading) {
      btn.disabled = true;
      btn.dataset.originalText = btn.textContent;
      btn.innerHTML = '<span class="btn-spinner"></span> Saving...';
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.originalText || 'Save';
    }
  },
  
  formatDate: (d) => {
    if (!d) return '-';
    return new Date(d).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric', year: 'numeric' });
  },
  
  formatDateTime: (d) => {
    if (!d) return '-';
    const date = new Date(d);
    return date.toLocaleString('en-IN', { 
      timeZone: 'Asia/Kolkata',
      month: 'short', 
      day: 'numeric', 
      hour: 'numeric', 
      minute: '2-digit',
      hour12: true 
    }) + ' IST';
  },
  
  formatTime: (d) => {
    if (!d) return '-';
    return new Date(d).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit', hour12: true }) + ' IST';
  },
  
  formatDuration: (mins) => {
    if (!mins) return '-';
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return h ? `${h}h ${m}m` : `${m}m`;
  },
  
  // Global error handler for API calls
  handleError: (error, form = null) => {
    console.error('[ERROR]', error);
    
    // Handle validation errors (422)
    if (error.errors && error.errors.length > 0) {
      if (form) {
        UI.showErrors(form, error.errors);
      }
      // Show first error as toast for visibility
      UI.toast(error.errors[0].message, 'error');
      return;
    }
    
    // Handle status-specific errors
    if (error.status) {
      switch (error.status) {
        case 400:
          UI.toast('Invalid request. Please check your input.', 'error');
          break;
        case 401:
          UI.toast('Session expired. Please login again.', 'error');
          Auth.clear();
          setTimeout(() => window.location.href = '/login.html', 1500);
          break;
        case 403:
          UI.toast('Permission denied.', 'error');
          break;
        case 404:
          UI.toast('Resource not found.', 'error');
          break;
        case 500:
          UI.toast('Server error. Please try again later.', 'error');
          break;
        default:
          UI.toast(error.message || 'An error occurred', 'error');
      }
      return;
    }
    
    // Default error message
    UI.toast(error.message || 'An error occurred', 'error');
  },
  
  // Wrap async operations with error handling
  async wrapAsync(fn, form = null, btn = null) {
    if (btn) UI.btnLoading(btn, true);
    try {
      return await fn();
    } catch (error) {
      UI.handleError(error, form);
      throw error;
    } finally {
      if (btn) UI.btnLoading(btn, false);
    }
  }
};

// Icons (inline SVG)
const Icons = {
  dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  exams: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h6"/></svg>',
  questions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>',
  students: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  results: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
};

// Sidebar Generator
function renderSidebar(activePage) {
  const user = Auth.getUser();
  const role = Auth.getRole();
  
  const adminLinks = [
    { id: 'dashboard', label: 'Dashboard', href: '/admin-dashboard.html', icon: 'dashboard' },
    { id: 'exams', label: 'Exams', href: '/exams.html', icon: 'exams' },
    { id: 'questions', label: 'Question Banks', href: '/question-banks.html', icon: 'questions' },
    { id: 'students', label: 'Students', href: '/students.html', icon: 'students' },
    { id: 'results', label: 'Results', href: '/results.html', icon: 'results' }
  ];
  
  const studentLinks = [
    { id: 'dashboard', label: 'Dashboard', href: '/student-dashboard.html', icon: 'dashboard' },
    { id: 'results', label: 'My Results', href: '/student-results.html', icon: 'results' }
  ];
  
  const links = role === 'admin' ? adminLinks : studentLinks;
  
  return `
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-brand">ExamPro</div>
      <nav class="sidebar-nav">
        ${links.map(l => `
          <a href="${l.href}" class="sidebar-link ${activePage === l.id ? 'active' : ''}">
            ${Icons[l.icon]}
            <span>${l.label}</span>
          </a>
        `).join('')}
      </nav>
      <div class="sidebar-footer">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <div class="sidebar-link" style="color: var(--gray-300); cursor: default; flex:1; margin:0; padding:8px 16px;">
            ${Icons.user}
            <span>${user?.full_name || user?.email || 'User'}</span>
          </div>
          <button class="theme-toggle" id="themeToggle" title="Toggle theme">🌙</button>
        </div>
        <a href="#" class="sidebar-link" onclick="Auth.logout(); return false;">
          ${Icons.logout}
          <span>Logout</span>
        </a>
      </div>
    </aside>
  `;
}

// Initialize page
function initPage(pageName, allowedRoles = ['admin']) {
  if (!Auth.requireAuth(allowedRoles)) return false;
  
  // Apply saved theme before rendering anything (prevent flash)
  applyTheme();
  
  // Inject sidebar
  const sidebarHtml = renderSidebar(pageName);
  document.body.insertAdjacentHTML('afterbegin', sidebarHtml);
  
  // Inject hamburger menu button + sidebar overlay for mobile
  const hamburgerHtml = `<button class="hamburger" id="hamburgerBtn" aria-label="Open menu">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
  </button>
  <div class="sidebar-overlay" id="sidebarOverlay"></div>`;
  document.body.insertAdjacentHTML('afterbegin', hamburgerHtml);
  
  // Initialize animated background
  NeoBackground.init();
  
  // Initialize theme toggle button
  initThemeToggle();
  
  // Initialize hamburger menu
  initHamburger();
  
  return true;
}

// ============ Hamburger Menu ============
function initHamburger() {
  const btn = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!btn || !sidebar) return;
  
  function openSidebar() {
    sidebar.classList.add('open');
    if (overlay) overlay.classList.add('active');
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  }
  
  function closeSidebar() {
    sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
  }
  
  btn.addEventListener('click', () => {
    sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
  });
  
  if (overlay) {
    overlay.addEventListener('click', closeSidebar);
  }
  
  // Close sidebar when a link is clicked (mobile)
  sidebar.querySelectorAll('.sidebar-link[href]').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 768) closeSidebar();
    });
  });
  
  // Close sidebar on escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar.classList.contains('open')) closeSidebar();
  });
}

// ============ Theme Toggle ============
function applyTheme() {
  const theme = localStorage.getItem('exampro-theme');
  if (theme === 'dark') {
    document.body.classList.add('dark');
  } else {
    document.body.classList.remove('dark');
  }
}

function initThemeToggle() {
  const toggleBtn = document.getElementById('themeToggle');
  if (!toggleBtn) return;
  
  // Set initial icon
  if (localStorage.getItem('exampro-theme') === 'dark') {
    toggleBtn.textContent = '🌙';
  } else {
    toggleBtn.textContent = '☀️';
  }
  
  toggleBtn.addEventListener('click', () => {
    document.body.classList.toggle('dark');
    
    if (document.body.classList.contains('dark')) {
      localStorage.setItem('exampro-theme', 'dark');
      toggleBtn.textContent = '🌙';
    } else {
      localStorage.setItem('exampro-theme', 'light');
      toggleBtn.textContent = '☀️';
    }
  });
}
