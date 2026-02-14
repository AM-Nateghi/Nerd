// ==================== Logger ====================
const logger = {
    info: (msg, ...args) => console.log(`[INFO] ${msg}`, ...args),
    warn: (msg, ...args) => console.warn(`[WARN] ${msg}`, ...args),
    error: (msg, ...args) => console.error(`[ERROR] ${msg}`, ...args),
};

// ==================== Cookie Helpers ====================
function setCookie(name, value, days = 365) {
    const d = new Date();
    d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${encodeURIComponent(value)};expires=${d.toUTCString()};path=/;SameSite=Lax`;
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

// ==================== Theme ====================
function getTheme() {
    return localStorage.getItem('nerd_theme') || 'dark';
}

function applyTheme(theme) {
    if (theme === 'light') {
        document.body.setAttribute('data-theme', 'light');
        $('#icon-sun').hide();
        $('#icon-moon').show();
    } else {
        document.body.removeAttribute('data-theme');
        $('#icon-sun').show();
        $('#icon-moon').hide();
    }
    localStorage.setItem('nerd_theme', theme);
}

function toggleTheme() {
    const current = getTheme();
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ==================== State ====================
const history = [];
let currentTaskId = null;
let sessionId = localStorage.getItem('nerd_session_id') || null;
let userId = getCookie('nerd_user_id') || null;
let username = getCookie('nerd_username') || null;
let pipelineState = { active: false, status: '', detail: '' };

function statusText(status, detail = '') {
    if (status === 'thinking') return 'در حال فکر کردن';
    if (status === 'searching') return `جستجو${detail ? ` "${detail}"` : ''}`;
    if (status === 'search_results_received') return 'دریافت نتایج جستجو';
    if (status === 'tool') return 'اجرای ابزار';
    if (status === 'tool_result_received') return 'دریافت نتیجه ابزار';
    return 'در حال فکر کردن';
}

// ==================== Username Registration ====================
async function registerUser(name) {
    try {
        const res = await fetch('/api/user/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: name }),
        });
        if (!res.ok) throw new Error('Registration failed');
        const data = await res.json();
        userId = data.user_id;
        username = data.username;
        setCookie('nerd_user_id', userId);
        setCookie('nerd_username', username);
        logger.info('User registered:', username, userId);

        // Link current session if exists
        if (sessionId) {
            linkSession(userId, sessionId);
        }

        return data;
    } catch (err) {
        logger.error('Registration error:', err.message);
        throw err;
    }
}

async function linkSession(uid, sid) {
    try {
        await fetch('/api/sessions/link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: uid, session_id: sid }),
        });
    } catch (e) {
        logger.warn('Failed to link session:', e.message);
    }
}

async function loadChatHistory() {
    if (!sessionId) return;
    try {
        const res = await fetch(`/api/history/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
            history.splice(0);
            data.messages.forEach(m => {
                history.push({ role: m.role, content: m.content });
            });
            logger.info(`Loaded ${data.messages.length} messages from history`);
        }
    } catch (err) {
        logger.warn('Failed to load history:', err.message);
    }
}

function showUsernameModal() {
    $('#username-modal').removeAttr('hidden').show();
    $('#username-input').focus();
}

function hideUsernameModal() {
    $('#username-modal').attr('hidden', true).hide();
}

function updateUsernameDisplay() {
    if (username) {
        $('#username-display').text(username);
    } else {
        $('#username-display').text('');
    }
}

// ==================== Helpers ====================
function isNearBottom($el, threshold = 120) {
    const el = $el[0];
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function scrollToBottom($el, force) {
    if (force) {
        $el[0].scrollTop = $el[0].scrollHeight;
    }
}

function createMsgRow(role, content) {
    const $row = $('<div>').addClass(`msg-row ${role}`);
    const $inner = $('<div>').addClass('msg-inner');

    // Label
    const labelText = role === 'user' ? (username || 'شما') : 'Nerd';
    const $label = $('<div>').addClass('msg-label').text(labelText);
    $inner.append($label);

    // Body
    const $body = $('<div>').addClass('msg-body');
    if (role === 'assistant' && typeof marked !== 'undefined') {
        $body.html(marked.parse(content || ''));
    } else {
        $body.text(content || '');
    }
    $inner.append($body);

    $row.append($inner);
    return $row;
}

// ==================== Render ====================
function renderMessages() {
    const $messages = $('#chat-messages');
    const shouldStick = isNearBottom($messages);
    const userMessages = history.filter(m => m.role !== 'system');

    if (userMessages.length === 0) {
        $messages.html(`
            <div class="welcome-screen" id="welcome-screen">
                <div class="welcome-logo">
                    <img src="/static/icon.svg" alt="Nerd" width="48" height="48" />
                </div>
                <h1 class="welcome-title">چطور می‌تونم کمکت کنم؟</h1>
                <div class="welcome-chips">
                    <button class="chip" data-prompt="یک متن خلاقانه بنویس">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                        یک متن خلاقانه بنویس
                    </button>
                    <button class="chip" data-prompt="کد پایتون بنویس">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                        کد پایتون بنویس
                    </button>
                    <button class="chip" data-prompt="درباره هوش مصنوعی توضیح بده">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                        درباره هوش مصنوعی توضیح بده
                    </button>
                </div>
            </div>
        `);
        bindChipEvents();
    } else {
        $messages.empty();
        userMessages.forEach((msg, index) => {
            let content = '';
            if (typeof msg.content === 'string') {
                content = msg.content;
            } else if (Array.isArray(msg.content)) {
                content = msg.content
                    .filter(part => part.type === 'text')
                    .map(part => part.text || '')
                    .join('');
            }
            const $row = createMsgRow(msg.role, content);
            $row.attr('data-index', index);
            $messages.append($row);
        });
    }

    renderPipeline($messages);
    scrollToBottom($messages, shouldStick);
}

function renderPipeline($messages) {
    $messages.find('.msg-row.pipeline').remove();
    if (!pipelineState.active) return;

    const label = statusText(pipelineState.status, pipelineState.detail);
    const $row = $('<div>').addClass('msg-row assistant pipeline');
    const $inner = $('<div>').addClass('msg-inner');
    $inner.html(`
        <div class="pipeline-status">
            <div class="pipeline-dots"><span></span><span></span><span></span></div>
            <span>${label}</span>
        </div>
    `);
    $row.append($inner);
    $messages.append($row);
}

function updateMessageContent(index, content) {
    const $messages = $('#chat-messages');
    const shouldStick = isNearBottom($messages);
    const $row = $messages.find(`[data-index="${index}"]`);
    if ($row.length === 0) {
        renderMessages();
        return;
    }

    const $body = $row.find('.msg-body');
    if (typeof marked !== 'undefined') {
        $body.html(marked.parse(content));
    } else {
        $body.text(content);
    }

    scrollToBottom($messages, shouldStick);
}

// ==================== Status & Loading ====================
function setStatus(text) {
    $('#status-text').text(text || '');
}

function showLoading(show) {
    $('#btn-send').prop('disabled', show);
    if (show) {
        $('#btn-cancel').removeAttr('hidden').show();
    } else {
        $('#btn-cancel').attr('hidden', true).hide();
    }
}

// ==================== Cancel ====================
async function cancelRequest() {
    if (!currentTaskId) return;
    try {
        await fetch(`/api/chat/cancel/${currentTaskId}`, { method: 'POST' });
        setStatus('درخواست لغو شد');
        showLoading(false);
        currentTaskId = null;
    } catch (err) {
        logger.error('Cancel error:', err.message);
    }
}

// ==================== Send Message ====================
async function sendMessage(content) {
    if (!content) content = $('#message-input').val().trim();
    if (!content) return;

    history.push({ role: 'user', content });
    $('#message-input').val('').css('height', 'auto');
    renderMessages();

    setStatus('در حال تولید پاسخ...');
    showLoading(true);
    pipelineState = { active: true, status: 'thinking', detail: '' };

    const assistantMessage = { role: 'assistant', content: '' };
    history.push(assistantMessage);
    const assistantIndex = history.filter(m => m.role !== 'system').length - 1;
    renderMessages();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(sessionId ? { 'X-Session-Id': sessionId } : {}),
            },
            body: JSON.stringify({
                messages: history.slice(0, -1),
                session_id: sessionId,
            }),
        });

        if (!response.ok) throw new Error(`خطای سرور: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = JSON.parse(line.slice(6));

                if (data.error) throw new Error(data.error);

                if (data.type === 'status' && !data.done) {
                    pipelineState = {
                        active: true,
                        status: data.status || 'thinking',
                        detail: data.detail || '',
                    };
                    const $messages = $('#chat-messages');
                    renderPipeline($messages);
                    setStatus(statusText(pipelineState.status, pipelineState.detail));
                    continue;
                }

                if (data.session_id) {
                    sessionId = data.session_id;
                    localStorage.setItem('nerd_session_id', sessionId);
                    // Link session to user
                    if (userId) {
                        linkSession(userId, sessionId);
                    }
                }

                if (data.task_id) currentTaskId = data.task_id;

                if (!data.done && data.message && data.message.content) {
                    pipelineState.active = false;
                    $('#chat-messages').find('.msg-row.pipeline').remove();
                    assistantMessage.content += data.message.content;
                    updateMessageContent(assistantIndex, assistantMessage.content);
                }

                if (data.done) {
                    pipelineState.active = false;
                    setStatus('');
                    if (data.task_id) currentTaskId = data.task_id;
                    break;
                }
            }
        }
    } catch (err) {
        logger.error('Send error:', err.message);
        pipelineState.active = false;
        history.pop();
        history.push({
            role: 'assistant',
            content: `مشکلی پیش آمد: ${err.message}\n\nمطمئن شو سرور در حال اجراست.`,
        });
        renderMessages();
    } finally {
        pipelineState.active = false;
        showLoading(false);
        currentTaskId = null;
        $('#message-input').focus();
    }
}

// ==================== Chip events ====================
function bindChipEvents() {
    $(document).off('click', '.chip').on('click', '.chip', function () {
        const prompt = $(this).data('prompt');
        if (prompt) sendMessage(prompt);
    });
}

// ==================== Init ====================
$(document).ready(async function () {
    logger.info('Nerd starting...');

    // Apply saved theme
    applyTheme(getTheme());

    // Theme toggle
    $('#btn-theme').on('click', toggleTheme);

    // Check if user exists
    if (!userId || !username) {
        showUsernameModal();
    } else {
        updateUsernameDisplay();
        // Load chat history from DB
        await loadChatHistory();
        renderMessages();
    }

    // Username modal submit
    $('#username-submit').on('click', async () => {
        const name = $('#username-input').val().trim();
        if (name.length < 2) return;
        try {
            await registerUser(name);
            hideUsernameModal();
            updateUsernameDisplay();
            // Load existing chat history if session exists
            await loadChatHistory();
            renderMessages();
        } catch (e) {
            logger.error('Registration failed');
        }
    });

    $('#username-input').on('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            $('#username-submit').click();
        }
    });

    // Chat events
    $('#btn-send').on('click', () => sendMessage());
    $('#btn-cancel').on('click', cancelRequest);

    $('#btn-clear').on('click', () => {
        // Create new session
        sessionId = null;
        localStorage.removeItem('nerd_session_id');
        history.splice(0);
        renderMessages();
        setStatus('');
    });

    $('#message-input').on('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    $('#message-input').on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 160) + 'px';
    });

    // Chip events
    bindChipEvents();

    // Initial render (if user already registered)
    if (userId && username) {
        // already rendered above
    } else {
        renderMessages();
    }

    logger.info('Nerd ready');
});
