import { Ollama } from 'ollama';
import express from 'express';

const app = express();
const ollama = new Ollama({ host: 'http://127.0.0.1:11434' });

app.use(express.json());

app.post('/test', async (req, res) => {
    console.log('📥 درخواست دریافت شد');
    
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    
    try {
        console.log('🚀 شروع چت...');
        
        const stream = await ollama.chat({
            model: 'gemma3n',
            messages: [{ role: 'user', content: 'فقط بگو سلام' }],
            stream: true,
        });

        console.log('✅ stream دریافت شد');
        let count = 0;

        for await (const chunk of stream) {
            count++;
            console.log(`Chunk #${count}:`, chunk.message?.content || '(empty)');
            res.write(JSON.stringify(chunk) + '\n');
        }

        console.log(`🎉 تمام شد! ${count} chunks`);
        res.end();
    } catch (err) {
        console.error('❌ خطا:', err.message);
        res.status(500).json({ error: err.message });
    }
});

app.listen(3001, () => {
    console.log('🧪 تست سرور: http://localhost:3001/test');
});
