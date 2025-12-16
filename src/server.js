import express from 'express';
import cors from 'cors';
import { Ollama } from 'ollama';
import crypto from 'crypto';

const app = express();
const PORT = process.env.PORT || 3000;
const OLLAMA_HOST = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';

// ساخت کلاینت Ollama
const ollama = new Ollama({ host: OLLAMA_HOST });

// ذخیره موقت تصاویر (در production از Redis یا دیتابیس استفاده کنید)
const imageStore = new Map();

// تابع helper برای دانلود و تبدیل تصویر به base64
async function fetchImageAsBase64(url) {
    try {
        // اگر URL لوکال ما هست، مستقیم از store بگیر
        if (url.includes('/api/images/')) {
            const id = url.split('/').pop();
            const image = imageStore.get(id);
            if (image) {
                return image.replace(/^data:image\/\w+;base64,/, '');
            }
        }

        // در غیر این صورت دانلود کن
        const response = await fetch(url);
        const buffer = await response.arrayBuffer();
        return Buffer.from(buffer).toString('base64');
    } catch (err) {
        console.error('[IMAGE] خطا در دانلود تصویر:', err.message);
        return null;
    }
}

app.use(cors());
app.use(express.json({ limit: '15mb' }));
app.use(express.static('public'));

// لاگ درخواست‌ها
app.use((req, res, next) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
    next();
});

app.get('/health', (_req, res) => {
    res.json({ ok: true, model: 'gemma3n' });
});

// آپلود تصویر
app.post('/api/upload-image', (req, res) => {
    const { image } = req.body;

    if (!image) {
        return res.status(400).json({ error: 'No image provided' });
    }

    // ساخت ID یونیک
    const imageId = crypto.randomUUID();

    // ذخیره تصویر (base64)
    imageStore.set(imageId, image);

    // پاک کردن بعد از 1 ساعت
    setTimeout(() => imageStore.delete(imageId), 60 * 60 * 1000);

    const imageUrl = `http://localhost:${PORT}/api/images/${imageId}`;
    console.log(`[IMAGE] تصویر آپلود شد: ${imageId}`);

    res.json({ url: imageUrl, id: imageId });
});

// سرو تصویر
app.get('/api/images/:id', (req, res) => {
    const { id } = req.params;
    const image = imageStore.get(id);

    if (!image) {
        return res.status(404).json({ error: 'Image not found' });
    }

    // تبدیل base64 به buffer
    const imageBuffer = Buffer.from(image.replace(/^data:image\/\w+;base64,/, ''), 'base64');

    res.setHeader('Content-Type', 'image/png');
    res.send(imageBuffer);
});

app.post('/api/chat', async (req, res) => {
    const startTime = Date.now();
    console.log('[CHAT] درخواست چت دریافت شد');

    const { messages, tools, model } = req.body || {};
    if (!Array.isArray(messages)) {
        console.error('[CHAT] خطا: messages یک آرایه نیست');
        res.status(400).json({ error: 'messages array required' });
        return;
    }

    console.log(`[CHAT] تعداد پیام‌ها: ${messages.length}`);
    console.log(`[CHAT] مدل: ${model || 'gemma3n'}`);

    try {
        console.log('[CHAT] تبدیل فرمت پیام‌ها...');

        // تبدیل فرمت پیام‌ها برای کتابخانه ollama
        const formattedMessages = await Promise.all(messages.map(async (msg) => {
            let content = '';
            let imageUrls = [];

            if (typeof msg.content === 'string') {
                // فرمت قدیمی - فقط متن
                content = msg.content;
            } else if (Array.isArray(msg.content)) {
                // فرمت جدید - استخراج متن و تصاویر
                msg.content.forEach(part => {
                    if (part.type === 'text') {
                        content += part.text || '';
                    } else if (part.type === 'image') {
                        imageUrls.push(part.url);
                    }
                });
            }

            const result = { role: msg.role, content: content || ' ' };

            // دانلود و تبدیل تصاویر به base64
            if (imageUrls.length > 0) {
                console.log(`[CHAT] دانلود ${imageUrls.length} تصویر...`);
                const images = await Promise.all(
                    imageUrls.map(url => fetchImageAsBase64(url))
                );
                result.images = images.filter(img => img !== null);
            }

            return result;
        }));

        console.log('[CHAT] ارسال به Ollama (بدون stream)...');

        // چت بدون stream - پاسخ کامل یکجا
        const response = await ollama.chat({
            model: model || 'gemma3n',
            messages: formattedMessages,
            tools,
            stream: false,
            keep_alive: -1,
        }); const duration = Date.now() - startTime;
        console.log(`[CHAT] ✅ پاسخ دریافت شد در ${duration}ms`);
        console.log(`[CHAT] محتوا: "${response.message.content.substring(0, 50)}..."`);

        // ارسال پاسخ کامل
        res.json({
            message: response.message,
            model: response.model,
            created_at: response.created_at,
            done: true,
        });

    } catch (err) {
        console.error('[CHAT] ❌ خطا در چت:', err.message);
        res.status(500).json({
            error: `خطا در Ollama: ${err.message}\nمطمئن شو Ollama در حال اجراست.`
        });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`╔══════════════════════════════════════════════════╗`);
    console.log(`║  🚀 Nerd Agent Server                           ║`);
    console.log(`║  📍 http://localhost:${PORT}                        ║`);
    console.log(`║  🤖 Ollama: ${OLLAMA_HOST}            ║`);
    console.log(`╚══════════════════════════════════════════════════╝`);
});
