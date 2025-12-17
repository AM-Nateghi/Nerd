# 🚀 راهنمای بهینه‌سازی عملکرد

## تنظیمات انجام شده برای RTX 4070 Super

### ✅ Ollama

فایل کانفیگ: `/etc/ollama/ollama.env`

```bash
# نگه داشتن مدل در GPU (بی‌نهایت)
OLLAMA_KEEP_ALIVE=-1

# تعداد GPU layers (برای RTX 4070 Super)
OLLAMA_NUM_GPU=999

# حافظه GPU
OLLAMA_MAX_LOADED_MODELS=1

# فعال کردن Flash Attention (سرعت بیشتر)
OLLAMA_FLASH_ATTENTION=1

# تعداد Thread های CPU
OLLAMA_NUM_THREAD=8
```

### 📊 نتایج

- **استفاده از GPU**: ~8.4GB / 12GB (68%)
- **مدل**: gemma3n (6.9B parameters, Q4_K_M)
- **Latency**: کاهش چشمگیر چون مدل دیگه unload نمیشه

### 🔧 دستورات مفید

```bash
# چک کردن وضعیت GPU
nvidia-smi

# چک کردن مدل‌های لود شده
curl http://127.0.0.1:11434/api/ps

# لاگ‌های Ollama
journalctl -u ollama -f

# ریستارت Ollama
sudo systemctl restart ollama
```

### ⚡ نکات بهینه‌سازی بیشتر

1. **استفاده از مدل کوچکتر برای چت ساده**:

   ```bash
   # مدل 1B پارامتری (خیلی سریعتر)
   ollama pull gemma3:1b
   ```

   بعد در `server.js` مدل رو به `gemma3:1b` تغییر بده.

2. **کاهش Context Length**:
   در `server.js` میتونی `num_ctx` رو کم کنی:

   ```javascript
   const body = {
     model: "gemma3n",
     stream: true,
     messages,
     num_ctx: 2048, // پیش‌فرض 4096
     keep_alive: -1,
   };
   ```

3. **Batch Processing**:
   اگه چند نفر همزمان استفاده می‌کنن، `OLLAMA_MAX_LOADED_MODELS` رو افزایش بده.

### 🐛 عیب‌یابی

اگه هنوز کنده:

1. چک کن مدل در GPU لود شده: `curl http://127.0.0.1:11434/api/ps`
2. چک کن استفاده از GPU: `nvidia-smi`
3. چک کن درایور NVIDIA به‌روز باشه: `nvidia-smi --query-gpu=driver_version --format=csv`

### 📈 مقایسه سرعت

| مدل            | اندازه | First Token | Tokens/sec |
| -------------- | ------ | ----------- | ---------- |
| gemma3n (6.9B) | 7.5GB  | ~2s         | ~20-30     |
| gemma3:1b      | 815MB  | ~0.5s       | ~50-80     |
| gemma3:270m    | 291MB  | ~0.2s       | ~100+      |

با RTX 4070 Super می‌تونی از `gemma3n` راحت استفاده کنی و سرعت خوبی بگیری! 🎯
