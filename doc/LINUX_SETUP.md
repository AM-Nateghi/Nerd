# 🐧 راهنمای نصب و اجرا در لینوکس (Ubuntu)

## پیش‌نیازها

```bash
# آپدیت سیستم
sudo apt update && sudo apt upgrade -y

# نصب Python و ابزارهای مورد نیاز
sudo apt install python3 python3-pip python3-venv -y

# نصب CUDA (اگر GPU دارید)
# برای RTX 3090 و بالاتر
sudo apt install nvidia-cuda-toolkit -y
```

## نصب و راه‌اندازی

### روش 1: اجرای دستی

```bash
# رفتن به پوشه پروژه
cd ~/Desktop/Nerd

# ساخت virtual environment
python3 -m venv .venv

# فعال‌سازی
source .venv/bin/activate

# نصب dependencies
pip install --upgrade pip
pip install -r requirements.txt

# تنظیم متغیر محیطی برای مسیر مدل
export MODEL_PATH="/home/ai/DataDrive/AI-Model-Archive/gemma-3n-E4B-it"

# اجرای سرور
python app.py
```

### روش 2: استفاده از اسکریپت (راحت‌تر)

```bash
# اجازه اجرا دادن به اسکریپت
chmod +x start.sh

# اجرا
./start.sh
```

## تنظیم مسیر مدل

### اگر مدل رو لوکال دارید:

```bash
# مسیر رو بدون ~ و $ بنویسید
export MODEL_PATH="/home/ai/DataDrive/AI-Model-Archive/gemma-3n-E4B-it"
```

### اگر می‌خواهید از Hugging Face دانلود بشه:

```bash
export MODEL_PATH="google/gemma-3n-e4b-it"
```

## راه‌اندازی به عنوان Service (اجرای خودکار)

برای اینکه سرور همیشه در حال اجرا باشه و با reboot سیستم خودش start بشه:

```bash
# کپی کردن service file
sudo cp nerd-server.service /etc/systemd/system/

# ویرایش مسیرها در service file (اگر لازم باشه)
sudo nano /etc/systemd/system/nerd-server.service

# Reload systemd
sudo systemctl daemon-reload

# فعال‌سازی service
sudo systemctl enable nerd-server

# شروع service
sudo systemctl start nerd-server

# چک کردن وضعیت
sudo systemctl status nerd-server

# دیدن logs
sudo journalctl -u nerd-server -f
```

### کنترل Service:

```bash
# توقف
sudo systemctl stop nerd-server

# ری‌استارت
sudo systemctl restart nerd-server

# غیرفعال کردن (disable auto-start)
sudo systemctl disable nerd-server
```

## رفع مشکلات رایج

### خطای مسیر مدل

```bash
# اگر این خطا رو دیدید:
# "Incorrect path_or_model_id: '~/DataDrive/...$'"

# مطمئن شوید:
1. از ~ استفاده نکنید، مسیر کامل بنویسید: /home/ai/...
2. در انتهای مسیر $ نداشته باشید
3. مسیر واقعا وجود داشته باشه
```

بررسی مسیر:
```bash
# چک کردن وجود فولدر مدل
ls -la /home/ai/DataDrive/AI-Model-Archive/gemma-3n-E4B-it

# باید فایل‌های مدل رو ببینید:
# - config.json
# - model.safetensors یا pytorch_model.bin
# - tokenizer_config.json
# و ...
```

### خطای CUDA

```bash
# چک کردن GPU
nvidia-smi

# اگر GPU رو نمی‌بینه، CUDA رو دوباره نصب کنید
sudo apt install nvidia-driver-535 nvidia-cuda-toolkit -y
sudo reboot
```

### خطای حافظه

```bash
# اگر RAM کم دارید، می‌تونید از CPU استفاده کنید (کندتر)
# در app.py تغییر بدید:
# device="cpu"  # به جای "auto"
```

### خطای Permission

```bash
# اگر permission error دیدید
chmod +x start.sh
chmod -R 755 ~/Desktop/Nerd
```

## بهینه‌سازی برای Production

### 1. استفاده از Gunicorn

```bash
# نصب gunicorn
pip install gunicorn

# اجرا با 4 worker
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### 2. استفاده از Nginx (Reverse Proxy)

```bash
# نصب nginx
sudo apt install nginx -y

# ایجاد config
sudo nano /etc/nginx/sites-available/nerd-server
```

محتوای config:
```nginx
server {
    listen 80;
    server_name your-domain.com;  # یا IP سرور

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
# فعال‌سازی config
sudo ln -s /etc/nginx/sites-available/nerd-server /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## مانیتورینگ

### دیدن logs به صورت زنده:

```bash
# logs اپلیکیشن
tail -f ~/.nerd-server.log

# logs systemd
sudo journalctl -u nerd-server -f

# فقط errors
sudo journalctl -u nerd-server -p err -f
```

### چک کردن منابع:

```bash
# CPU و RAM
htop

# GPU
watch -n 1 nvidia-smi

# دیسک
df -h
```

## تست سرور

```bash
# Health check
curl http://localhost:8000/health

# با jq برای خروجی قشنگ
curl -s http://localhost:8000/health | jq

# تست chat (ساده)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "سلام"}
    ]
  }' | jq
```

## Firewall

اگر می‌خواهید از خارج به سرور دسترسی داشته باشید:

```bash
# باز کردن port 8000
sudo ufw allow 8000/tcp

# یا اگر از nginx استفاده می‌کنید
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

## Backup

```bash
# backup از مدل (اگر لوکال دارید)
tar -czf gemma-3n-backup.tar.gz /home/ai/DataDrive/AI-Model-Archive/gemma-3n-E4B-it

# backup از پروژه
tar -czf nerd-project-backup.tar.gz ~/Desktop/Nerd
```

## چک‌لیست نصب

- [ ] Python 3.12+ نصب شده
- [ ] Virtual environment ساخته شده
- [ ] Dependencies نصب شده
- [ ] مسیر مدل صحیح تنظیم شده (بدون ~ و $)
- [ ] GPU و CUDA کار می‌کند (اختیاری)
- [ ] پورت 8000 باز است
- [ ] سرور بدون خطا start می‌شود
- [ ] API ها جواب می‌دهند
- [ ] Frontend به سرور متصل می‌شود

موفق باشید! 🚀
