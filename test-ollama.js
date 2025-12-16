import { Ollama } from 'ollama';

const ollama = new Ollama({ host: 'http://127.0.0.1:11434' });

console.log('🧪 شروع تست Ollama...\n');

async function testChat() {
    try {
        console.log('📤 ارسال درخواست به Ollama...');
        const startTime = Date.now();

        const stream = await ollama.chat({
            model: 'gemma3n',
            messages: [
                { role: 'user', content: 'سلام! خوبی؟' }
            ],
            stream: true,
            keep_alive: -1,
        });

        console.log('✅ استریم شروع شد!\n');
        console.log('📨 دریافت پاسخ:\n');

        let fullResponse = '';
        let chunkCount = 0;

        for await (const chunk of stream) {
            chunkCount++;
            console.log(`Chunk #${chunkCount}:`, JSON.stringify(chunk, null, 2));

            if (chunk.message?.content) {
                fullResponse += chunk.message.content;
                process.stdout.write(chunk.message.content);
            }
        }

        const duration = Date.now() - startTime;
        console.log(`\n\n✅ استریم تمام شد!`);
        console.log(`📊 آمار: ${chunkCount} chunk در ${duration}ms`);
        console.log(`💬 پاسخ کامل: ${fullResponse}\n`);

    } catch (error) {
        console.error('❌ خطا:', error.message);
        console.error('Stack:', error.stack);
    }
}

testChat();
