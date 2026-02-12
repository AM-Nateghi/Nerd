// ==================== لاگ سیستم ====================
const logger = {
    info: (msg, ...args) => console.log(`[INFO] ${msg}`, ...args),
    warn: (msg, ...args) => console.warn(`[WARN] ${msg}`, ...args),
    error: (msg, ...args) => console.error(`[ERROR] ${msg}`, ...args),
    debug: (msg, ...args) => console.log(`[DEBUG] ${msg}`, ...args)
};

// ==================== متغیرهای اصلی ====================
const history = [];
let currentTaskId = null;

function isNearBottom($el, threshold = 120) {
    const el = $el[0];
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function scrollToBottomIfNear($el, shouldStick) {
    if (shouldStick) {
        $el[0].scrollTop = $el[0].scrollHeight;
    }
}

// ==================== تابع رندر پیام‌ها ====================
function renderMessages() {
    logger.debug('رندر کردن پیام‌ها...');
    const $messages = $('#nerd-messages');
    const shouldStick = isNearBottom($messages);

    const userMessages = history.filter(m => m.role !== 'system');

    if (userMessages.length === 0) {
        $messages.html(`
            <div class="empty-state">
                <i data-feather="message-square"></i>
                <p>سلام! چطور می‌تونم کمکت کنم؟</p>
            </div>
        `);
    } else {
        $messages.empty();

        userMessages.forEach((msg, index) => {
            const $item = $('<div>')
            .addClass(`message ${msg.role}`)
            .attr('data-index', index);

            // پردازش محتوا
            if (typeof msg.content === 'string') {
                const textContent = msg.content;
                if (msg.role === 'assistant' && typeof marked !== 'undefined') {
                    $item.html(marked.parse(textContent));
                } else {
                    $item.text(textContent);
                }
            } else if (Array.isArray(msg.content)) {
                const textContent = msg.content
                    .filter(part => part.type === 'text')
                    .map(part => part.text || '')
                    .join('');
                if (msg.role === 'assistant' && typeof marked !== 'undefined') {
                    $item.html(marked.parse(textContent));
                } else {
                    $item.text(textContent);
                }
            }

            $messages.append($item);
        });
    }

    feather.replace();
    scrollToBottomIfNear($messages, shouldStick);
}

function updateMessageContent(index, content) {
    const $messages = $('#nerd-messages');
    const shouldStick = isNearBottom($messages);
    const $item = $messages.find(`[data-index="${index}"]`);
    if ($item.length === 0) {
        renderMessages();
        return;
    }

    if (typeof marked !== 'undefined') {
        $item.html(marked.parse(content));
    } else {
        $item.text(content);
    }

    scrollToBottomIfNear($messages, shouldStick);
}

// ==================== تنظیم وضعیت ====================
function setStatus(text) {
    logger.debug('وضعیت:', text || 'خالی');
    $('#nerd-status').text(text || '');
}

// ==================== نمایش/مخفی لودینگ ====================
function showLoading(show) {
    $('#nerd-loading').toggle(show);
    $('#nerd-send').prop('disabled', show);
    $('#nerd-cancel').toggle(show);
}

// ==================== لغو درخواست ====================
async function cancelRequest() {
    if (!currentTaskId) {
        logger.warn('هیچ درخواست فعالی برای لغو وجود ندارد');
        return;
    }

    logger.info('لغو درخواست:', currentTaskId);

    try {
        await fetch(`/api/chat/cancel/${currentTaskId}`, {
            method: 'POST'
        });

        setStatus('درخواست لغو شد');
        showLoading(false);
        currentTaskId = null;
    } catch (err) {
        logger.error('خطا در لغو درخواست:', err.message);
    }
}

// ==================== ارسال پیام ====================
async function sendMessage() {
    const content = $('#nerd-text').val().trim();
    if (!content) {
        logger.warn('پیام خالی است');
        return;
    }

    logger.info('ارسال پیام:', content);

    const userMessage = {
        role: 'user',
        content: content
    };

    history.push(userMessage);
    $('#nerd-text').val('');
    renderMessages();

    setStatus('در حال تولید پاسخ...');
    showLoading(true);

    // Create a placeholder for the assistant response
    const assistantMessage = {
        role: 'assistant',
        content: ''
    };
    history.push(assistantMessage);
    const assistantIndex = history.filter(m => m.role !== 'system').length - 1;
    renderMessages();

    try {
        logger.debug('ارسال درخواست به سرور...');
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: history.slice(0, -1) }), // Don't send the empty assistant message
        });

        if (!response.ok) {
            throw new Error(`خطای سرور: ${response.status}`);
        }

        // Read the stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                logger.info('Stream completed');
                break;
            }

            buffer += decoder.decode(value, { stream: true });

            // Process complete messages from buffer
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));

                    if (data.error) {
                        throw new Error(data.error);
                    }

                    if (!data.done && data.message && data.message.content) {
                        // Append new content
                        assistantMessage.content += data.message.content;
                        updateMessageContent(assistantIndex, assistantMessage.content);
                    }

                    if (data.done) {
                        logger.info('پاسخ کامل شد');
                        setStatus('');
                        break;
                    }
                }
            }
        }

    } catch (err) {
        logger.error('خطا در ارسال پیام:', err.message);

        // Remove the empty assistant message and add error
        history.pop();
        history.push({
            role: 'assistant',
            content: `❌ مشکلی پیش آمد: ${err.message}\n\n🔍 مطمئن شو سرور در حال اجراست.`
        });
        renderMessages();
    } finally {
        showLoading(false);
        currentTaskId = null;
        $('#nerd-text').focus();
    }
}


// ==================== راه‌اندازی اولیه ====================
$(document).ready(function () {
    logger.info('='.repeat(50));
    logger.info('شروع Nerd Agent');
    logger.info('='.repeat(50));

    // رویدادها
    $('#nerd-send').on('click', sendMessage);
    $('#nerd-cancel').on('click', cancelRequest);

    $('#nerd-clear').on('click', () => {
        logger.info('پاک کردن تاریخچه');
        history.splice(0);
        renderMessages();
    });

    $('#nerd-text').on('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    $('#nerd-text').on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // راه‌اندازی اولیه
    renderMessages();

    // Replace feather icons
    feather.replace();

    logger.info('Nerd Agent آماده است ✓');
});
