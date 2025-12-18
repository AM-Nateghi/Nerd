#!/bin/bash

# اسکریپت راه‌اندازی سرور Nerd در لینوکس

# رنگ‌ها برای output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🚀 راه‌اندازی Nerd Agent Server               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# چک کردن virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}📦 ساخت virtual environment...${NC}"
    python3 -m venv .venv
fi

# فعال‌سازی virtual environment
echo -e "${GREEN}🔌 فعال‌سازی virtual environment...${NC}"
source .venv/bin/activate

# نصب dependencies
echo -e "${GREEN}📥 نصب dependencies...${NC}"
pip install -q --upgrade pip
pip install -q -r requirements.txt

# تنظیم متغیرهای محیطی
export MODEL_PATH="/home/ai/DataDrive/AI-Model-Archive/gemma-3n-E4B-it"
export MAX_NEW_TOKENS="2048"
export TEMPERATURE="0.7"
export PYTHONWARNINGS="ignore::FutureWarning,ignore::DeprecationWarning"

# چک کردن وجود مدل
if [ -d "$MODEL_PATH" ]; then
    echo -e "${GREEN}✅ مدل در مسیر لوکال پیدا شد: $MODEL_PATH${NC}"
else
    echo -e "${YELLOW}⚠️  مدل در مسیر لوکال پیدا نشد. از Hugging Face دانلود می‌شود...${NC}"
    export MODEL_PATH="google/gemma-3n-e4b-it"
fi

# اجرای سرور
echo -e "${GREEN}🚀 شروع سرور...${NC}"
echo ""

python app.py
