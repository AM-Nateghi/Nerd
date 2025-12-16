// ==================== لاگ سیستم ====================
const logger = {
    info: (msg, ...args) => console.log(`[INFO] ${msg}`, ...args),
    warn: (msg, ...args) => console.warn(`[WARN] ${msg}`, ...args),
    error: (msg, ...args) => console.error(`[ERROR] ${msg}`, ...args),
    debug: (msg, ...args) => console.log(`[DEBUG] ${msg}`, ...args)
};

// ==================== متغیرهای اصلی ====================
const systemPrompt = [{
    type: 'text',
    text: 'You are Nerd, a floating web guide. Answer concisely in Persian. Keep replies short and actionable.'
}];
const history = [{ role: 'system', content: systemPrompt }];
let lastImage = null;
let recognition = null;
let listening = false;
let pipWindow = null;
let currentTheme = localStorage.getItem('theme') || 'dark';

// ==================== تنظیم تم ====================
function setTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    const icon = theme === 'dark' ? 'sun' : 'moon';
    $('#nerd-theme i').attr('data-feather', icon);
    feather.replace();

    logger.info('تم تغییر کرد:', theme);
}

function toggleTheme() {
    setTheme(currentTheme === 'dark' ? 'light' : 'dark');
}

// ==================== تابع رندر پیام‌ها ====================
function renderMessages() {
    logger.debug('رندر کردن پیام‌ها...');
    const $messages = $('#nerd-messages');

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

        userMessages.forEach(msg => {
            const $item = $('<div>')
                .addClass(`message ${msg.role}`);

            // پردازش محتوا
            let textContent = '';
            const images = [];

            if (typeof msg.content === 'string') {
                // فرمت قدیمی
                textContent = msg.content;
            } else if (Array.isArray(msg.content)) {
                // فرمت جدید Ollama
                msg.content.forEach(part => {
                    if (part.type === 'text') {
                        textContent += part.text || '';
                    } else if (part.type === 'image') {
                        images.push(part.url);
                    }
                });
            }

            // رندر محتوای متنی با Markdown
            if (textContent) {
                if (msg.role === 'assistant' && typeof marked !== 'undefined') {
                    $item.html(marked.parse(textContent));
                } else {
                    $item.text(textContent);
                }
            }

            // اضافه کردن تصاویر
            images.forEach(imgUrl => {
                $item.append(
                    $('<img>')
                        .attr('src', imgUrl)
                        .attr('alt', 'image')
                );
            });

            $messages.append($item);
        });
    }

    feather.replace();
    $messages[0].scrollTop = $messages[0].scrollHeight;
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
}

// ==================== ارسال پیام ====================
async function sendMessage() {
    const content = $('#nerd-text').val().trim();
    if (!content && !lastImage) {
        logger.warn('پیام خالی است');
        return;
    }

    logger.info('ارسال پیام:', content);

    // ساخت محتوای پیام به فرمت Ollama
    const messageContent = [];
    let imageUrl = null;

    // اگر تصویر داریم، اول آپلودش کن
    if (lastImage) {
        try {
            logger.debug('آپلود تصویر...');
            const uploadRes = await fetch('/api/upload-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: lastImage }),
            });

            if (uploadRes.ok) {
                const { url } = await uploadRes.json();
                imageUrl = url;
                messageContent.push({ type: 'image', url });
                logger.info('تصویر آپلود شد:', url);
            }
        } catch (err) {
            logger.error('خطا در آپلود تصویر:', err.message);
        }
    }

    // اضافه کردن متن
    if (content) {
        messageContent.push({ type: 'text', text: content });
    }

    const userMessage = {
        role: 'user',
        content: messageContent
    };

    history.push(userMessage);
    lastImage = null;
    $('#nerd-text').val('');
    renderMessages();

    setStatus('در حال تولید پاسخ...');
    showLoading(true);

    try {
        logger.debug('ارسال درخواست به سرور...');
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: history }),
        });

        if (!response.ok) {
            throw new Error(`خطای سرور: ${response.status}`);
        }

        const data = await response.json();

        // استخراج محتوای پاسخ
        let responseContent = '';
        if (typeof data.message.content === 'string') {
            responseContent = data.message.content;
        } else if (Array.isArray(data.message.content)) {
            responseContent = data.message.content
                .filter(c => c.type === 'text')
                .map(c => c.text)
                .join('');
        }

        logger.info('پاسخ دریافت شد:', responseContent.substring(0, 50) + '...');

        // اضافه کردن پاسخ به تاریخچه
        history.push({
            role: 'assistant',
            content: [{ type: 'text', text: responseContent }]
        });

        renderMessages();
        setStatus('');

    } catch (err) {
        logger.error('خطا در ارسال پیام:', err.message);
        history.push({
            role: 'assistant',
            content: [{
                type: 'text',
                text: `❌ مشکلی پیش آمد: ${err.message}\n\n🔍 مطمئن شو Ollama در حال اجراست.`
            }]
        });
        renderMessages();
    } finally {
        showLoading(false);
        $('#nerd-text').focus();
    }
}

// ==================== انتخاب تصویر ====================
function selectImage() {
    $('#nerd-image-input').click();
}

$('#nerd-image-input').on('change', async function (e) {
    const file = e.target.files[0];
    if (!file) return;

    logger.info('تصویر انتخاب شد:', file.name);

    try {
        const reader = new FileReader();
        reader.onload = (event) => {
            lastImage = event.target.result;
            setStatus(`✓ تصویر انتخاب شد: ${file.name}`);
            logger.info('تصویر آماده ارسال است');
        };
        reader.readAsDataURL(file);
    } catch (err) {
        logger.error('خطا در خواندن تصویر:', err.message);
        alert('خطا در خواندن تصویر');
    }

    // ریست اینپوت
    this.value = '';
});

// ==================== نمایش/مخفی کردن ویجت ====================
function toggleWidget(show) {
    const shouldShow = show !== undefined ? show : $('#nerd-widget').is(':hidden');
    logger.debug('تغییر وضعیت ویجت:', shouldShow ? 'نمایش' : 'مخفی');

    $('#nerd-widget').toggle(shouldShow);
    $('#nerd-launcher').toggle(!shouldShow);

    if (shouldShow) {
        $('#nerd-text').focus();
    }
}

// ==================== راه‌اندازی صوت ====================
function initVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        logger.warn('Speech Recognition در این مرورگر پشتیبانی نمی‌شود');
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'fa-IR';
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        logger.info('متن شنیده شده:', transcript);
        const currentVal = $('#nerd-text').val();
        $('#nerd-text').val(`${currentVal} ${transcript}`.trim());
    };

    recognition.onend = () => {
        logger.debug('ضبط صدا تمام شد');
        listening = false;
        $('#nerd-voice i').attr('data-feather', 'mic');
        feather.replace();
        setStatus('');
    };

    recognition.onerror = (err) => {
        logger.error('خطا در تشخیص صدا:', err.error);
        listening = false;
        $('#nerd-voice i').attr('data-feather', 'mic');
        feather.replace();
        setStatus('');
    };

    logger.info('سیستم صوتی فعال شد');
}

function toggleVoice() {
    if (!recognition) {
        alert('Voice API در این مرورگر در دسترس نیست.');
        return;
    }

    if (listening) {
        logger.debug('توقف ضبط صدا');
        recognition.stop();
        return;
    }

    logger.debug('شروع ضبط صدا');
    recognition.start();
    listening = true;
    $('#nerd-voice i').attr('data-feather', 'square');
    feather.replace();
    setStatus('در حال گوش دادن...');
}

// ==================== آپلود فایل صوتی ====================
$('#nerd-audio-input').on('change', async function (e) {
    const file = e.target.files[0];
    if (!file) return;

    logger.info('فایل صوتی انتخاب شد:', file.name);
    setStatus(`فایل صوتی: ${file.name} (تبدیل به متن فعلاً پشتیبانی نمی‌شود)`);

    // ریست
    this.value = '';
});

// ==================== حالت Picture-in-Picture ====================
async function togglePiP() {
    if (!('documentPictureInPicture' in window)) {
        alert('مرورگر شما از Document PiP پشتیبانی نمی‌کند.');
        logger.warn('Document PiP پشتیبانی نمی‌شود');
        return;
    }

    if (pipWindow) {
        logger.info('بستن پنجره PiP');
        pipWindow.close();
        return;
    }

    try {
        logger.info('باز کردن پنجره PiP...');
        pipWindow = await documentPictureInPicture.requestWindow({
            width: 420,
            height: 640
        });

        // کپی کردن استایل‌ها
        $('style, link[rel="stylesheet"]').each(function () {
            if (this.tagName === 'STYLE') {
                $(pipWindow.document.head).append(
                    $('<style>').text($(this).text())
                );
            } else {
                $(pipWindow.document.head).append(
                    $('<link>')
                        .attr('rel', 'stylesheet')
                        .attr('type', this.type)
                        .attr('media', this.media)
                        .attr('href', this.href)
                );
            }
        });

        // انتقال ویجت
        $(pipWindow.document.body).append($('#nerd-widget'));
        $('#nerd-widget').show();

        // نمایش لانچر در صفحه اصلی
        $('#nerd-launcher').show();

        $(pipWindow).on('pagehide', () => {
            logger.info('پنجره PiP بسته شد');
            $('body').append($('#nerd-widget'));
            $('#nerd-launcher').hide();
            pipWindow = null;
            feather.replace();
        });

        logger.info('پنجره PiP باز شد');

        // Replace feather icons در PiP
        setTimeout(() => {
            if (pipWindow && typeof feather !== 'undefined') {
                const script = pipWindow.document.createElement('script');
                script.src = 'https://unpkg.com/feather-icons';
                script.onload = () => {
                    pipWindow.feather.replace();
                };
                pipWindow.document.head.appendChild(script);
            }
        }, 100);

    } catch (err) {
        logger.error('خطا در باز کردن PiP:', err.message);
        alert('باز کردن PiP با خطا مواجه شد.');
    }
}

// ==================== راه‌اندازی اولیه ====================
$(document).ready(function () {
    logger.info('='.repeat(50));
    logger.info('شروع Nerd Agent');
    logger.info('='.repeat(50));

    // تنظیم تم
    setTheme(currentTheme);

    // رویدادها
    $('#nerd-launcher').on('click', () => toggleWidget(true));
    $('#nerd-close').on('click', () => toggleWidget(false));
    $('#nerd-send').on('click', sendMessage);
    $('#nerd-theme').on('click', toggleTheme);
    $('#nerd-pin').on('click', togglePiP);
    $('#nerd-image').on('click', selectImage);
    $('#nerd-voice').on('click', toggleVoice);
    $('#nerd-upload-audio').on('click', () => $('#nerd-audio-input').click());

    $('#nerd-clear').on('click', () => {
        logger.info('پاک کردن تاریخچه');
        history.splice(1);
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
    initVoice();
    renderMessages();
    toggleWidget(true);

    // Replace feather icons
    feather.replace();

    logger.info('Nerd Agent آماده است ✓');
});
